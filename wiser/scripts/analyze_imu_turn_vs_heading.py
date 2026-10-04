r"""Phase 0 of turn-aided WISER: does the head gyro's turn track the WISER heading change? (cohort 2026c)

Plan: implementation_plan/2026-10-04-imu-turn-vs-wiser-heading.md (approved by the user 2026-10-04, "做"; committed
5281fc6 before any result; operational details in its Amendment 1, written before any number). Report (full
Definitions section): results/<cohort>/wiser_baseline/reports/wiser_baseline_imu_turn_vs_heading_<cohort>.md

  WISER heading  theta(h) = atan2 of d(h) = m(h + 0.5) - m(h - 0.5), m = coordinate-wise median of the raw fixes
                 (tau*-aligned) in [t - 0.5, t + 0.5) (>= 3 fixes); defined when |d| / 1 s >= 10 in/s and every second
                 overlapping [h - 1, h + 1) is a step-B clean second. Secondary: the same on the V3 track.
  Gyro heading   psi(t) = integral of make_imu turn_dps (+ = CCW seen from above) over QC-ok 50-Hz samples;
                 psibar(h) = mean of psi over [h - 0.5, h + 0.5).
  Pairs          W in {1, 2, 3} s, centres c on the 0.5-s grid: dtheta = wrap(theta(c + W/2) - theta(c - W/2)),
                 dpsi = psibar(c + W/2) - psibar(c - W/2); every 50-Hz sample of [c - W/2 - 0.5, c + W/2 + 0.5) QC-ok.
  Fit            OLS of dtheta on dpsi through the origin (gate; centred R2) and with intercept (check), |dpsi| <= 150 deg;
                 residual r = wrap(dtheta - b wrap(dpsi)); circular correlation; 10-min block bootstrap.
  Gate           calm nights, W = 2 s, raw-median heading: |b| in [0.8, 1.2] and R2 >= 0.5 -> PASS, else FAIL;
                 +1 h-shifted gyro control with R2 >= 0.1 -> INVALID.
  Reported       W = 1 / 3, rain, per animal (sign of b = frame handedness), speed bands, V3 heading, turn-sign agreement,
                 scanning tail, turns in place that WISER misses, lag scan, expected heading noise (R2 ceiling).

Inputs (all read-only): step B's per-second tables (clean seconds, u1, floor seconds), the failure audit's config
(periods, exclusions, tau*), the WISER fix caches, the make_imu 50-Hz npz, the V3 tracks. Existing scripts are imported,
never modified.

Usage:
  python wiser/scripts/analyze_imu_turn_vs_heading.py --cohort 2026c [--workers 6]
  python wiser/scripts/analyze_imu_turn_vs_heading.py --report-only <run_dir>     # re-aggregate / re-render from tables
  python wiser/scripts/analyze_imu_turn_vs_heading.py --selftest                  # synthetic data, no field data
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
import analyze_wiser_failure_audit as FA  # noqa: E402  (context, fix loader, IMU loader + sample QC, medians, bootstrap; unmodified)
import analyze_imu_speed_proxy as SP  # noqa: E402  (house membership, step-B speed estimator; unmodified)

DIRECTION = "wiser_baseline"
NAME = "imu_turn_vs_heading"
STEM = f"{DIRECTION}_imu_turn_vs_heading"
PLAN = "implementation_plan/2026-10-04-imu-turn-vs-wiser-heading.md"
DRIVER = "wiser/scripts/analyze_imu_turn_vs_heading.py"
RAYLEIGH_MED = math.sqrt(2.0 * math.log(2.0))      # median of a Rayleigh(sigma) variable / sigma
STATS = ["b0", "R2_0", "b1", "a1", "R2_1", "rho_c", "med_r", "p90_r", "tail", "sign_agree"]
# colours: categorical slots 1-3 of the dataviz reference palette (light); text stays neutral
COL = {"calm": "#2a78d6", "rain": "#eb6834", "control": "#1baf7a", "ink": "#0b0b0b", "ink2": "#52514e", "grid": "#d9d8d4"}


def log_to(fh, msg: str) -> None:
    print(msg, flush=True)
    if fh is not None:
        fh.write(msg + "\n")
        fh.flush()


# ====================================================================================================== config / context
def load_cfg(cohort: str, path: str | None = None) -> dict:
    cp = Path(path) if path else REPO / "wiser" / "configs" / f"imu_turn_vs_heading_{cohort}.json"
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    cfg["_path"] = str(cp)
    cfg["_cohort"] = cohort
    return cfg


def load_acfg(cfg: dict) -> dict:
    return FA.load_cfg(cfg["_cohort"], str(REPO / cfg["audit_config"]))


_CTX: dict = {}


def _ctx(acfg: dict) -> dict:
    if acfg["_path"] not in _CTX:
        _CTX[acfg["_path"]] = FA.context(acfg)
    return _CTX[acfg["_path"]]


def night_sets(cfg: dict) -> dict:
    return {p: s for s, ps in cfg["nights"].items() for p in ps}


def lag_col(d: float) -> str:
    return f"dpsi_lag{int(round(d * 10)):+d}"


# ====================================================================================================== core estimators
def wrap(x) -> np.ndarray:
    """((x + 180) mod 360) - 180 -> [-180, 180) (degrees)."""
    return (np.asarray(x, float) + 180.0) % 360.0 - 180.0


def headings(t: np.ndarray, p: np.ndarray, g: np.ndarray, hc: dict) -> dict:
    """1-s medians m on the grid g (step = the median offset) and, at every g[j], d = m(g[j] + off) - m(g[j] - off),
    speed |d| / (2 off) and heading atan2(d_y, d_x) in degrees (NaN where a median is missing)."""
    step = float(g[1] - g[0])
    off = float(hc["median_offset_s"])
    k = int(round(off / step))
    assert abs(k * step - off) < 1e-9, "median offset must be a multiple of the grid step"
    m, nf = FA.roll_median(t, p, g, float(hc["median_half_s"]), int(hc["min_fix"]))
    d = np.full((len(g), 2), np.nan)
    if len(g) > 2 * k:
        d[k:len(g) - k] = m[2 * k:] - m[:len(g) - 2 * k]
    spd = np.hypot(d[:, 0], d[:, 1]) / (2.0 * off)
    th = np.degrees(np.arctan2(d[:, 1], d[:, 0]))
    return {"m": m, "nfix": nf, "d": d, "spd": spd, "th": th}


def support_clean(g: np.ndarray, secs: np.ndarray, clean: np.ndarray) -> np.ndarray:
    """True where every field-PC second [s, s + 1) overlapping [g - 1, g + 1) exists and is clean (Amendment 1.3)."""
    s0, n = int(secs[0]), len(secs)
    a = (np.floor(g - 1.0) - s0).astype(np.int64)
    b = (np.ceil(g + 1.0) - s0).astype(np.int64)
    inside = (a >= 0) & (b <= n) & (b > a)
    cs = np.r_[0, np.cumsum(~np.asarray(clean, bool))]
    ac, bc = np.clip(a, 0, n), np.clip(b, 0, n)
    return inside & ((cs[bc] - cs[ac]) == 0)


class Gyro:
    """Integrated turn psi on the 50-Hz samples (QC-failed samples contribute 0; spans containing them are refused)."""

    def __init__(self, u_s, turn, valid, fs: float, max_gap_samples: float):
        u = np.asarray(u_s, float)
        keep = np.r_[True, np.diff(u) > 0] if len(u) else np.zeros(0, bool)
        self.n_dup = int((~keep).sum())
        u = u[keep]
        turn = np.asarray(turn, float)[keep]
        good = np.asarray(valid, bool)[keep] & np.isfinite(turn)
        self.u, self.fs, self.tol = u, float(fs), float(max_gap_samples) / float(fs)
        self.psi = np.cumsum(np.where(good, turn, 0.0) / self.fs)
        self.cpsi = np.r_[0.0, np.cumsum(self.psi)]
        self.cbad = np.r_[0, np.cumsum(~good)]
        self.cgap = np.r_[0, np.cumsum(np.diff(u) > self.tol)] if len(u) > 1 else np.zeros(max(len(u), 1), np.int64)
        self.n_good = int(good.sum())

    def mean(self, x, half: float = 0.5) -> np.ndarray:
        """Mean of psi over the samples with u in [x - half, x + half)."""
        x = np.asarray(x, float)
        i0 = np.searchsorted(self.u, x - half, "left")
        i1 = np.searchsorted(self.u, x + half, "left")
        n = i1 - i0
        with np.errstate(invalid="ignore", divide="ignore"):
            out = (self.cpsi[i1] - self.cpsi[i0]) / n
        out = np.where(n > 0, out, np.nan)
        return out

    def span_ok(self, a, b) -> np.ndarray:
        """[a, b) holds >= 2 samples, all QC-ok, no inter-sample gap > tol, covered to within tol at both ends."""
        a = np.asarray(a, float)
        b = np.asarray(b, float)
        N = len(self.u)
        if N < 2:
            return np.zeros(a.shape, bool)
        i0 = np.searchsorted(self.u, a, "left")
        i1 = np.searchsorted(self.u, b, "left")
        n = i1 - i0
        i0c = np.clip(i0, 0, N - 1)
        i1m = np.clip(i1 - 1, 0, N - 1)
        ok = n >= 2
        ok &= (self.cbad[i1] - self.cbad[i0]) == 0
        ok &= (self.cgap[i1m] - self.cgap[i0c]) == 0
        ok &= (self.u[i0c] - a) <= self.tol
        ok &= (b - self.u[i1m]) <= self.tol
        return ok

    def at(self, x) -> np.ndarray:
        x = np.asarray(x, float)
        return np.interp(x, self.u, self.psi) if len(self.u) else np.full(x.shape, np.nan)


def build_pairs(g: np.ndarray, Hr: dict, Hv: dict, ok_r: np.ndarray, ok_v: np.ndarray, gyro: Gyro, pc: dict,
                lags: list, shift: float) -> pd.DataFrame:
    """All pairs (h1, h2 = h1 + W) on the grid with both raw (or both V3) headings defined and the gyro span QC-ok."""
    step = float(g[1] - g[0])
    half = float(pc["gyro_window_s"]) / 2.0
    out = []
    for W in pc["W_s"]:
        k = int(round(float(W) / step))
        if len(g) <= k:
            continue
        j1 = np.arange(len(g) - k)
        j2 = j1 + k
        okr = ok_r[j1] & ok_r[j2]
        okv = ok_v[j1] & ok_v[j2]
        sel = okr | okv
        j1, j2, okr, okv = j1[sel], j2[sel], okr[sel], okv[sel]
        h1, h2 = g[j1], g[j2]
        span = gyro.span_ok(h1 - half, h2 + half)
        j1, j2, okr, okv, h1, h2 = j1[span], j2[span], okr[span], okv[span], h1[span], h2[span]
        d = {"W": np.full(len(j1), float(W)), "c": 0.5 * (h1 + h2), "ok_raw": okr, "ok_v3": okv,
             "dtheta": np.where(okr, wrap(Hr["th"][j2] - Hr["th"][j1]), np.nan),
             "spd1": np.where(okr, Hr["spd"][j1], np.nan), "spd2": np.where(okr, Hr["spd"][j2], np.nan),
             "dtheta_v3": np.where(okv, wrap(Hv["th"][j2] - Hv["th"][j1]), np.nan),
             "spd1_v3": np.where(okv, Hv["spd"][j1], np.nan), "spd2_v3": np.where(okv, Hv["spd"][j2], np.nan),
             "dpsi": gyro.mean(h2, half) - gyro.mean(h1, half)}
        cok = gyro.span_ok(h1 - half + shift, h2 + half + shift)
        d["dpsi_ctrl"] = np.where(cok, gyro.mean(h2 + shift, half) - gyro.mean(h1 + shift, half), np.nan)
        for dl in lags:
            lok = gyro.span_ok(h1 - half + dl, h2 + half + dl)
            d[lag_col(dl)] = np.where(lok, gyro.mean(h2 + dl, half) - gyro.mean(h1 + dl, half), np.nan)
        out.append(pd.DataFrame(d))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def turn_events(gyro: Gyro, lo_s: float, hi_s: float, ic: dict) -> pd.DataFrame:
    """Runs of consecutive same-sign grid points t with |psi(t + w) - psi(t)| >= turn_deg and [t, t + w) QC-ok."""
    w, st = float(ic["window_s"]), float(ic["grid_s"])
    n = int(np.floor((hi_s - w - lo_s) / st + 1e-9)) + 1
    cols = ["t0", "t1", "sign", "max_abs_d3", "net_deg", "n_grid"]
    if n <= 0 or len(gyro.u) < 2:
        return pd.DataFrame(columns=cols)
    tt = lo_s + st * np.arange(n)
    ok = gyro.span_ok(tt, tt + w)
    d3 = gyro.at(tt + w) - gyro.at(tt)
    cand = ok & (np.abs(d3) >= float(ic["turn_deg"]))
    ev = []
    for sgn in (1, -1):
        for a, b in C.true_runs(cand & (np.sign(d3) == sgn)):
            t0, t1 = float(tt[a]), float(tt[b - 1] + w)
            ev.append({"t0": t0, "t1": t1, "sign": sgn, "max_abs_d3": float(np.abs(d3[a:b]).max()),
                       "net_deg": float(gyro.at(np.array([t1]))[0] - gyro.at(np.array([t0]))[0]), "n_grid": int(b - a)})
    return pd.DataFrame(ev, columns=cols).sort_values("t0").reset_index(drop=True) if ev else pd.DataFrame(columns=cols)


def classify_events(E: pd.DataFrame, secs: np.ndarray, u1: np.ndarray, thr: float) -> tuple[list, list]:
    """WISER coverage = u1 exists on >= ceil(n / 2) of the n overlapping seconds (Amendment 2); with coverage: missed (every
    available u1 < thr) / wiser_moving (some available u1 >= thr); without: no_wiser."""
    s0, n = int(secs[0]), len(secs)
    cls, umax = [], []
    for r in E.itertuples():
        a, b = int(np.floor(r.t0)) - s0, int(np.ceil(r.t1)) - s0
        if a < 0 or b > n or b <= a:
            cls.append("no_wiser")
            umax.append(np.nan)
            continue
        v = u1[a:b]
        fin = np.isfinite(v)
        if fin.sum() < math.ceil(len(v) / 2.0):
            cls.append("no_wiser")
        elif (v[fin] >= thr).any():
            cls.append("wiser_moving")
        else:
            cls.append("missed")
        umax.append(float(np.nanmax(v)) if np.isfinite(v).any() else np.nan)
    return cls, umax


def zone_vec(x: np.ndarray, y: np.ndarray, houses: list, buf: float) -> np.ndarray:
    fin = np.isfinite(x) & np.isfinite(y)
    inh = SP.in_house(np.where(fin, x, 0.0), np.where(fin, y, 0.0), houses, buf) & fin
    return np.where(~fin, "unknown", np.where(inh, "house", "field"))


# ====================================================================================================== statistics
def _pct(a: np.ndarray) -> tuple[float, float]:
    a = a[np.isfinite(a)]
    if len(a) < 2:
        return np.nan, np.nan
    lo, hi = np.percentile(a, [2.5, 97.5])
    return float(lo), float(hi)


def fit_stats(x, y, blk, n_boot: int, seed: int, max_fit: float = 150.0, tail_deg: float = 30.0, sgn: float = 1.0,
              smin: float = 30.0, smax: float = 150.0, chunk: int = 50) -> dict:
    """Through-origin and intercept OLS of y (dtheta) on x (dpsi) over |x| <= max_fit; circular correlation; residual
    quantiles and tail share (all pairs, wrapped x, each replicate's b); sign agreement on smin <= |x| <= smax.
    Block bootstrap: row 0 = point estimate, rows 1.. = resampled blocks (FA.boot_counts)."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    blk = np.asarray(blk)
    fin = np.isfinite(x) & np.isfinite(y)
    x, y, blk = x[fin], y[fin], blk[fin]
    fit = np.abs(x) <= max_fit
    res = {"n_pairs": int(len(x)), "n_fit": int(fit.sum()), "n_excl": int((~fit).sum())}
    if fit.sum() < 10:
        res.update({"n_blocks": int(len(np.unique(blk))), "n_sign": 0, "var_dtheta": np.nan})
        for s in STATS:
            res[s] = res[s + "_lo"] = res[s + "_hi"] = np.nan
        return res
    _, bi = np.unique(blk, return_inverse=True)
    K = int(bi.max()) + 1
    res["n_blocks"] = K
    cnt = FA.boot_counts(K, n_boot, np.random.default_rng(seed)) if n_boot > 0 else np.ones((1, K))
    xf, yf, bf = x[fit], y[fit], bi[fit]

    def S(v):
        return cnt @ np.bincount(bf, weights=v, minlength=K)
    n = cnt @ np.bincount(bf, minlength=K).astype(float)
    Sx, Sy, Sxx, Sxy, Syy = S(xf), S(yf), S(xf * xf), S(xf * yf), S(yf * yf)
    A, B = np.radians(yf), np.radians(xf)
    sA, cA, sB, cB = np.sin(A), np.cos(A), np.sin(B), np.cos(B)
    with np.errstate(invalid="ignore", divide="ignore"):
        b0 = Sxy / Sxx
        sst = Syy - Sy ** 2 / n
        R2_0 = 1.0 - (Syy - 2.0 * b0 * Sxy + b0 ** 2 * Sxx) / sst
        cxy, cxx = Sxy - Sx * Sy / n, Sxx - Sx ** 2 / n
        b1 = cxy / cxx
        a1 = (Sy - b1 * Sx) / n
        R2_1 = cxy ** 2 / (cxx * sst)
        ma, mb = np.arctan2(S(sA), S(cA)), np.arctan2(S(sB), S(cB))
        ca, sa, cb, sb = np.cos(ma), np.sin(ma), np.cos(mb), np.sin(mb)
        num = ca * cb * S(sA * sB) - ca * sb * S(sA * cB) - sa * cb * S(cA * sB) + sa * sb * S(cA * cB)
        dA = ca ** 2 * S(sA * sA) - 2.0 * ca * sa * S(sA * cA) + sa ** 2 * S(cA * cA)
        dB = cb ** 2 * S(sB * sB) - 2.0 * cb * sb * S(sB * cB) + sb ** 2 * S(cB * cB)
        rho = num / np.sqrt(dA * dB)
    xw = wrap(x)
    R = cnt.shape[0]
    med, p90, tl = np.empty(R), np.empty(R), np.empty(R)
    for i in range(0, R, chunk):
        bb = b0[i:i + chunk]
        a = np.abs(wrap(y[None, :] - bb[:, None] * xw[None, :]))
        w = cnt[i:i + chunk][:, bi]
        o = np.argsort(a, axis=1)
        a_s = np.take_along_axis(a, o, 1)
        cw = np.cumsum(np.take_along_axis(w, o, 1), axis=1)
        tot = cw[:, -1]
        rr = np.arange(len(bb))
        med[i:i + chunk] = a_s[rr, np.minimum((cw < 0.5 * tot[:, None]).sum(axis=1), len(x) - 1)]
        p90[i:i + chunk] = a_s[rr, np.minimum((cw < 0.9 * tot[:, None]).sum(axis=1), len(x) - 1)]
        with np.errstate(invalid="ignore", divide="ignore"):
            tl[i:i + chunk] = (w * (a > tail_deg)).sum(axis=1) / tot
    ms = (np.abs(x) >= smin) & (np.abs(x) <= smax)
    ag = ms & (np.sign(y) == sgn * np.sign(x))
    with np.errstate(invalid="ignore", divide="ignore"):
        sign_agree = (cnt @ np.bincount(bi[ag], minlength=K).astype(float)) / (cnt @ np.bincount(bi[ms], minlength=K).astype(float))
    res["n_sign"] = int(ms.sum())
    res["var_dtheta"] = float(np.var(yf))
    for name, arr in (("b0", b0), ("R2_0", R2_0), ("b1", b1), ("a1", a1), ("R2_1", R2_1), ("rho_c", rho), ("med_r", med),
                      ("p90_r", p90), ("tail", tl), ("sign_agree", sign_agree)):
        res[name] = float(arr[0])
        res[name + "_lo"], res[name + "_hi"] = _pct(arr[1:]) if R > 1 else (np.nan, np.nan)
    return res


def noise_ceiling(x: np.ndarray, y: np.ndarray, s1: np.ndarray, s2: np.ndarray, sig_d: np.ndarray, max_fit: float) -> dict:
    """sigma_theta per end = sigma_d / |d| (rad -> deg); R2_max = 1 - mean(s1^2 + s2^2) / Var(dtheta) on the fit set."""
    fin = np.isfinite(x) & np.isfinite(y) & np.isfinite(s1) & np.isfinite(s2) & np.isfinite(sig_d) & (np.abs(x) <= max_fit)
    if fin.sum() < 10:
        return {"ceiling_R2": np.nan, "sigma_theta_med_deg": np.nan, "sigma_dtheta_rms_deg": np.nan}
    t1 = np.degrees(sig_d[fin] / s1[fin])
    t2 = np.degrees(sig_d[fin] / s2[fin])
    nv = float(np.mean(t1 ** 2 + t2 ** 2))
    return {"ceiling_R2": 1.0 - nv / float(np.var(y[fin])), "sigma_theta_med_deg": float(np.median(np.r_[t1, t2])),
            "sigma_dtheta_rms_deg": math.sqrt(nv)}


# ====================================================================================================== one animal-night
def process(job: dict) -> dict:
    t_job = time.time()
    cfg, acfg, animal, pkey = job["cfg"], job["acfg"], job["animal"], job["pkey"]
    ctx = _ctx(acfg)
    tz = ctx["tz"]
    p = acfg["periods"][pkey]
    lo, hi = C.to_ms(p["start"], tz), C.to_ms(p["end"], tz)
    set_ = night_sets(cfg)[pkey]
    hc, pc, ic, gc, imc = cfg["heading"], cfg["pairs"], cfg["in_place"], cfg["gate"], cfg["imu"]
    # ---- step-B seconds (clean seconds, u1, floor seconds, audit IMU ok / state)
    S = pd.read_csv(Path(cfg["speed_proxy_run"]) / "seconds" / f"{animal}_{pkey}.csv.gz",
                    usecols=["sec", "ok", "still", "state", "clean", "u1", "floor_ok"])
    secs = S["sec"].to_numpy(np.int64)
    assert np.all(np.diff(secs) == 1), "step-B seconds not contiguous"
    assert int(secs[0]) == int(lo // 1000), "step-B seconds do not start at the period start"
    clean = S["clean"].astype(bool).to_numpy()
    ok_s = S["ok"].astype(bool).to_numpy()
    u1 = S["u1"].to_numpy(float)
    state = S["state"].to_numpy(np.int8)
    floor_ok = S["floor_ok"].astype(bool).to_numpy()
    lo_s, hi_s = int(secs[0]), int(secs[-1]) + 1
    # ---- fixes (tau*-aligned) and the V3 track at the same fixes
    tau = float(ctx["taus"][animal])
    fx = FA.load_fixes(acfg, pkey, animal, lo, hi, tau)
    t = fx["t_al_ms"].to_numpy(np.float64) / 1000.0
    z = fx[["x", "y"]].to_numpy(np.float64)
    with np.load(Path(cfg["v3_run"]) / "tracks" / f"{animal}_{pkey}.npz") as v:
        if not np.array_equal(v["t_ms"].astype(np.int64), fx["t_ms"].to_numpy(np.int64)):
            raise ValueError(f"{animal} {pkey}: V3 track t_ms differs from the fix cache")
        zv = v["V3"].astype(np.float64)
    # ---- headings on the 0.5-s grid
    step = float(pc["grid_s"])
    g = lo_s + step * np.arange(int(round((hi_s - lo_s) / step)) + 1)
    Hr = headings(t, z, g, hc)
    Hv = headings(t, zv, g, hc)
    sup = support_clean(g, secs, clean)
    vmin = float(hc["min_speed_inps"])
    with np.errstate(invalid="ignore"):
        ok_r = sup & np.isfinite(Hr["spd"]) & (Hr["spd"] >= vmin)
        ok_v = sup & np.isfinite(Hv["spd"]) & (Hv["spd"] >= vmin)
    # ---- IMU (night - margin ... night + 1 h + margin for the control)
    shift = float(gc["control_shift_s"])
    mg = float(imc["margin_s"])
    ilo, ihi = lo - mg * 1000.0, hi + (shift + mg) * 1000.0
    sid = C.resolve_tag(ctx["ids"], animal, lo, hi)
    vf, vu = C.tag_window(ctx["ids"], sid, animal, (lo + hi) / 2)
    sess = FA.sessions_for(acfg, ctx, animal, ilo, ihi)
    imu = FA.load_imu(sess, ilo, ihi, tz)
    valid = FA.sample_valid(imu, ctx, animal, ilo, ihi, vf, vu)
    gyro = Gyro(imu["unix_ms"] / 1000.0, imu["turn_dps"], valid, float(imc["fs"]), float(imc["max_gap_samples"]))
    # ---- pairs
    P = build_pairs(g, Hr, Hv, ok_r, ok_v, gyro, pc, cfg["lag_scan_s"], shift)
    if len(P):
        P.insert(0, "set", set_)
        P.insert(0, "period", pkey)
        P.insert(0, "animal", animal)
        P["block"] = ((P["c"] - lo_s) // float(cfg["bootstrap"]["block_s"])).astype(np.int64)
        P["state"] = state[np.clip(np.floor(P["c"].to_numpy() - lo_s).astype(np.int64), 0, len(secs) - 1)]
        P.insert(3, "c_ms", np.round(P["c"].to_numpy() * 1000.0).astype(np.int64))    # exact in CSV (Amendment 3.i)
        P = P.drop(columns="c")
    # ---- floor displacements (the same 1-s estimator on certified still seconds; heading centre h = s + 0.5)
    fs_ = secs[floor_ok]
    jf = 2 * (fs_ - lo_s) + 1
    jf = jf[(jf >= 0) & (jf < len(g))]
    Fd = pd.DataFrame({"animal": animal, "period": pkey, "set": set_, "sec": lo_s + (jf - 1) // 2,
                       "dx": Hr["d"][jf, 0], "dy": Hr["d"][jf, 1]}).dropna()
    # ---- turns in place
    E = turn_events(gyro, lo_s, hi_s, ic)
    houses, buf = ctx["houses"], float(ic["house_buffer_in"])
    if len(E):
        cls, umax = classify_events(E, secs, u1, float(ic["u1_floor_p95_inps"]))
        E["cls"], E["u1_max"] = cls, umax
        mx, my, nfx = [], [], []
        for r in E.itertuples():
            i0, i1 = np.searchsorted(t, [r.t0, r.t1])
            nfx.append(int(i1 - i0))
            if i1 - i0 >= int(hc["min_fix"]):
                mx.append(float(np.median(z[i0:i1, 0])))
                my.append(float(np.median(z[i0:i1, 1])))
            else:
                mx.append(np.nan)
                my.append(np.nan)
        E["x_med"], E["y_med"], E["n_fix"] = mx, my, nfx
        E["zone"] = zone_vec(E["x_med"].to_numpy(float), E["y_med"].to_numpy(float), houses, buf)
        k0 = np.clip(np.floor(E["t0"].to_numpy()).astype(np.int64) - lo_s, 0, len(secs) - 1)
        E["state_t0"] = state[k0]
        E["t0_ms"] = np.round(E["t0"].to_numpy(float) * 1000.0).astype(np.int64)    # exact in CSV (Amendment 3.i)
        E["t1_ms"] = np.round(E["t1"].to_numpy(float) * 1000.0).astype(np.int64)
        E["dur_s"] = E["t1"] - E["t0"]
        E = E.drop(columns=["t0", "t1"])
        E.insert(0, "set", set_)
        E.insert(0, "period", pkey)
        E.insert(0, "animal", animal)
    # ---- IMU-ok seconds per zone (zone of a second = median raw fix of [s - 1, s + 2), >= 3 fixes: the shortest event
    #      window, so numerator and denominator use comparable windows; Amendment 3.ii)
    m1, _ = FA.roll_median(t, z, secs.astype(np.float64) + 0.5, 1.5, int(hc["min_fix"]))
    zs = zone_vec(m1[:, 0], m1[:, 1], houses, buf)
    Z = pd.DataFrame({"zone": zs[ok_s]}).value_counts().rename("n_ok_s").reset_index()
    Z.insert(0, "set", set_)
    Z.insert(0, "period", pkey)
    Z.insert(0, "animal", animal)
    inwin = (imu["unix_ms"] >= lo) & (imu["unix_ms"] < hi) if len(imu["unix_ms"]) else np.zeros(0, bool)
    info = {"animal": animal, "period": pkey, "set": set_, "shortid": sid, "tau_s": tau, "n_fix": int(((fx.t_ms >= lo) & (fx.t_ms < hi)).sum()),
            "clean_s": int(clean.sum()), "imu_ok_s": int(ok_s.sum()), "imu_valid_50hz_h": float(valid[inwin].sum() / float(imc["fs"]) / 3600.0),
            "imu_dup_samples": gyro.n_dup, "headings_raw": int(ok_r.sum()), "headings_v3": int(ok_v.sum()),
            **{f"pairs_W{int(W)}_raw": int((P["ok_raw"] & (P["W"] == W)).sum()) if len(P) else 0 for W in pc["W_s"]},
            "floor_s": int(len(Fd)), "turn_events": int(len(E)),
            "sessions": ";".join(s["session"] for s in sess), "runtime_s": round(time.time() - t_job, 1)}
    return {"info": info, "pairs": P, "events": E, "zones": Z, "floor": Fd}


def _process_safe(job: dict) -> dict:
    try:
        return process(job)
    except Exception as e:  # noqa: BLE001
        import traceback
        return {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc(), "animal": job["animal"], "pkey": job["pkey"]}


def run_compute(cfg: dict, workers: int) -> Path:
    t0 = time.time()
    acfg = load_acfg(cfg)
    out = output_paths.run_dir(NAME, cfg["_cohort"])
    (out / "tables").mkdir(exist_ok=True)
    fh = open(out / "log.txt", "w", encoding="utf-8")
    log_to(fh, f"run dir {out}; git {C.git_commit()}; config {cfg['_path']}; step-B run {cfg['speed_proxy_run']}; V3 run {cfg['v3_run']}")
    _ctx(acfg)
    jobs = [{"cfg": cfg, "acfg": acfg, "animal": a, "pkey": pk} for pk in night_sets(cfg) for a in cfg["animals"]]
    res = {"pairs": [], "events": [], "zones": [], "floor": []}
    infos = []
    with ProcessPoolExecutor(max_workers=max(1, min(6, workers))) as ex:
        for r in ex.map(_process_safe, jobs):
            if "error" in r:
                log_to(fh, f"ERROR {r['animal']} {r['pkey']}: {r['error']}\n{r['trace']}")
                continue
            i = r["info"]
            log_to(fh, f"{i['animal']} {i['period']}: headings raw {i['headings_raw']:,}, pairs W2 {i['pairs_W2_raw']:,}, "
                       f"IMU valid {i['imu_valid_50hz_h']:.2f} h, turn events {i['turn_events']}, {i['runtime_s']} s")
            infos.append(i)
            for k in res:
                if len(r[k]):
                    res[k].append(r[k])
    tb = out / "tables"
    pd.concat(res["pairs"], ignore_index=True).to_csv(tb / "pairs.csv.gz", index=False, float_format="%.5g")
    pd.concat(res["events"], ignore_index=True).to_csv(tb / "in_place_turns.csv.gz", index=False, float_format="%.6g")
    pd.concat(res["zones"], ignore_index=True).to_csv(tb / "imu_ok_seconds_by_zone.csv", index=False)
    pd.concat(res["floor"], ignore_index=True).to_csv(tb / "floor_displacements.csv.gz", index=False, float_format="%.5g")
    pd.DataFrame(infos).to_csv(tb / "periods_info.csv", index=False)
    man = {}
    for k in ("speed_proxy_run", "v3_run", "audit_run"):
        mp = Path(cfg[k]) / "run_manifest.json"
        man[k] = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else None
    prov = {"config": Path(cfg["_path"]).relative_to(REPO).as_posix(), "audit_config": cfg["audit_config"],
            "speed_proxy_run": cfg["speed_proxy_run"], "v3_run": cfg["v3_run"], "audit_run": cfg["audit_run"],
            "fix_cache_root": acfg["fix_cache"]["root"], "imu_root": acfg["imu_root"], "git_commit": C.git_commit(),
            "run_manifests": man, "imu_sessions": [{k: i[k] for k in ("animal", "period", "sessions")} for i in infos],
            "tau_star_s": _ctx(acfg)["taus"], "runtime_compute_s": round(time.time() - t0, 1)}
    (out / "input_provenance.json").write_text(json.dumps(prov, indent=2, default=str), encoding="utf-8")
    log_to(fh, f"compute done ({time.time() - t0:.0f} s)")
    fh.close()
    return out


# ====================================================================================================== aggregate
def analyze(out: Path, cfg: dict, fh=None) -> dict:
    t0 = time.time()
    tb = out / "tables"
    P = pd.read_csv(tb / "pairs.csv.gz")
    for c in ("ok_raw", "ok_v3"):
        P[c] = P[c].astype(bool)
    E = pd.read_csv(tb / "in_place_turns.csv.gz")
    Z = pd.read_csv(tb / "imu_ok_seconds_by_zone.csv")
    Fd = pd.read_csv(tb / "floor_displacements.csv.gz")
    info = pd.read_csv(tb / "periods_info.csv")
    bc, gc, sg = cfg["bootstrap"], cfg["gate"], cfg["sign"]
    nb, seed = int(bc["n_boot"]), int(bc["seed"])
    mf, tail = float(cfg["pairs"]["max_abs_dpsi_fit_deg"]), float(cfg["scanning_tail_deg"])
    P["blk"] = P["animal"] + "|" + P["period"] + "|" + P["block"].astype(str)
    # ---- noise floor of the 1-s displacement (certified still)
    Fd["r"] = np.hypot(Fd["dx"], Fd["dy"])
    sigd = {}
    for s in ("calm", "rain", "all"):
        r = Fd["r"].to_numpy(float) if s == "all" else Fd.loc[Fd["set"] == s, "r"].to_numpy(float)
        sigd[s] = {"n_s": int(len(r)), "p50_inps": float(np.median(r)) if len(r) else np.nan,
                   "p95_inps": float(np.percentile(r, 95)) if len(r) else np.nan,
                   "sigma_d_in": float(np.median(r) / RAYLEIGH_MED) if len(r) else np.nan,
                   "sigma_d_rms_in": float(np.sqrt(np.mean(r ** 2) / 2.0)) if len(r) else np.nan}
    ref = cfg["u1_floor_reference"]
    sigd["step_b_u1"] = {"p50_inps": ref["p50_inps"], "p95_inps": ref["p95_inps"], "sigma_d_in": ref["p50_inps"] / RAYLEIGH_MED}
    P["sig_d"] = P["set"].map({s: sigd[s]["sigma_d_in"] for s in ("calm", "rain")})
    # ---- convention from the pooled calm W = 2 slope
    m0 = P[(P["set"] == gc["set"]) & (P["W"] == gc["W_s"]) & P["ok_raw"]]
    mm = m0[np.abs(m0["dpsi"]) <= mf]
    b_pt = float((mm["dpsi"] * mm["dtheta"]).sum() / (mm["dpsi"] ** 2).sum())
    sigma = 1.0 if b_pt >= 0 else -1.0
    log_to(fh, f"pairs {len(P):,}; convention sigma = {sigma:+.0f}")
    rows = []

    def sel(set_, W, heading="raw", animal=None, band=None):
        m = P["W"] == W
        if set_ != "all":
            m &= P["set"] == set_
        m &= P["ok_raw"] if heading == "raw" else P["ok_v3"]
        if animal:
            m &= P["animal"] == animal
        if band is not None:
            s1, s2 = ("spd1", "spd2") if heading == "raw" else ("spd1_v3", "spd2_v3")
            vm = np.minimum(P[s1], P[s2])
            m &= vm >= band[0]
            if band[1] is not None:
                m &= vm < band[1]
        return P[m]

    def fit(sub, group, set_, W, heading="raw", animal="pooled", band="all", xcol="dpsi", nboot=nb):
        ycol = "dtheta" if heading == "raw" else "dtheta_v3"
        r = fit_stats(sub[xcol].to_numpy(float), sub[ycol].to_numpy(float), sub["blk"].to_numpy(), nboot, seed, mf, tail, sigma,
                      float(sg["min_abs_dpsi_deg"]), float(sg["max_abs_dpsi_deg"]))
        r.update({"group": group, "set": set_, "W": W, "heading": heading, "animal": animal, "band": band, "x": xcol,
                  "n_animal_nights": int(sub[["animal", "period"]].drop_duplicates().shape[0])})
        if heading == "raw" and xcol == "dpsi":
            r.update(noise_ceiling(sub[xcol].to_numpy(float), sub[ycol].to_numpy(float), sub["spd1"].to_numpy(float),
                                   sub["spd2"].to_numpy(float), sub["sig_d"].to_numpy(float), mf))
        rows.append(r)
        return r

    gate = fit(sel(gc["set"], gc["W_s"]), "gate", gc["set"], gc["W_s"])
    ctrl = fit(sel(gc["set"], gc["W_s"]), "control", gc["set"], gc["W_s"], xcol="dpsi_ctrl")
    log_to(fh, f"gate: b {gate['b0']:+.3f} [{gate['b0_lo']:+.3f}, {gate['b0_hi']:+.3f}], R2 {gate['R2_0']:.3f} "
               f"[{gate['R2_0_lo']:.3f}, {gate['R2_0_hi']:.3f}], n {gate['n_fit']:,}; control b {ctrl['b0']:+.3f}, R2 {ctrl['R2_0']:.3f}")
    for s in ("calm", "rain", "all"):
        for W in cfg["pairs"]["W_s"]:
            fit(sel(s, W), "W", s, W)
    fit(sel("rain", gc["W_s"]), "control", "rain", gc["W_s"], xcol="dpsi_ctrl")
    bands = [(b[0], b[1]) for b in cfg["speed_bands_inps"]]
    for s in ("calm", "rain"):
        for a in cfg["animals"]:
            fit(sel(s, gc["W_s"], animal=a), "animal", s, gc["W_s"], animal=a)
            if s == "calm":
                fit(sel(s, gc["W_s"], animal=a), "animal_control", s, gc["W_s"], animal=a, xcol="dpsi_ctrl")
        for bd in bands:
            lab = f"{bd[0]:g}-{bd[1]:g}" if bd[1] is not None else f">={bd[0]:g}"
            fit(sel(s, gc["W_s"], band=bd), "band", s, gc["W_s"], band=lab)
            fit(sel(s, gc["W_s"], heading="v3", band=bd), "band_v3", s, gc["W_s"], heading="v3", band=lab)
        for W in cfg["pairs"]["W_s"]:
            fit(sel(s, W, heading="v3"), "v3", s, W, heading="v3")
    # ---- lag scan (one common pair set: QC-ok at every shift)
    lc = [lag_col(d) for d in cfg["lag_scan_s"]]
    L = sel(gc["set"], gc["W_s"])
    L = L[np.isfinite(L[lc]).all(axis=1)]
    lag_rows = []
    for d, c in zip(cfg["lag_scan_s"], lc):
        r = fit_stats(L[c].to_numpy(float), L["dtheta"].to_numpy(float), L["blk"].to_numpy(), 0, seed, mf, tail, sigma)
        lag_rows.append({"delta_s": d, "n_fit": r["n_fit"], "b0": r["b0"], "R2_0": r["R2_0"], "b1": r["b1"], "R2_1": r["R2_1"],
                         "med_r": r["med_r"], "rho_c": r["rho_c"]})
    LS = pd.DataFrame(lag_rows)
    peak = LS.loc[LS["R2_0"].idxmax()] if LS["R2_0"].notna().any() else None
    FT = pd.DataFrame(rows)
    # ---- confusion table (gate fit set)
    gs = sel(gc["set"], gc["W_s"])
    gs = gs[np.abs(gs["dpsi"]) <= mf]
    st = float(sg["straight_deg"])

    def cls3(v):
        return np.where(v >= st, "left", np.where(v <= -st, "right", "straight"))
    CT = pd.crosstab(pd.Series(cls3(gs["dpsi"].to_numpy()), name="gyro"), pd.Series(cls3(sigma * gs["dtheta"].to_numpy()), name="wiser"))
    CT = CT.reindex(index=["left", "straight", "right"], columns=["left", "straight", "right"], fill_value=0)
    # ---- turns in place
    ip = []
    H = Z.groupby(["set", "zone"])["n_ok_s"].sum()
    for s in ("calm", "rain", "all"):
        for zn in ("field", "house", "unknown", "all"):
            e = E if s == "all" else E[E["set"] == s]
            e = e if zn == "all" else e[e["zone"] == zn]
            h = H if s == "all" else H[H.index.get_level_values(0) == s]
            h = h if zn == "all" else h[h.index.get_level_values(1) == zn]
            hrs = float(h.sum()) / 3600.0
            nm, nmv, nn = int((e["cls"] == "missed").sum()), int((e["cls"] == "wiser_moving").sum()), int((e["cls"] == "no_wiser").sum())
            ip.append({"set": s, "zone": zn, "imu_ok_h": hrs, "events": int(len(e)), "missed": nm, "wiser_moving": nmv, "no_wiser": nn,
                       "events_per_h": len(e) / hrs if hrs > 0 else np.nan, "missed_per_h": nm / hrs if hrs > 0 else np.nan,
                       "share_missed": nm / (nm + nmv) if nm + nmv > 0 else np.nan})
    IP = pd.DataFrame(ip)
    ipa = []
    Ha = Z.groupby(["animal", "set"])["n_ok_s"].sum()
    for a in cfg["animals"]:
        for s in ("calm", "rain"):
            e = E[(E["animal"] == a) & (E["set"] == s)]
            hrs = float(Ha.get((a, s), 0)) / 3600.0
            nm = int((e["cls"] == "missed").sum())
            nmf = int(((e["cls"] == "missed") & (e["zone"] == "field")).sum())
            nmh = int(((e["cls"] == "missed") & (e["zone"] == "house")).sum())
            ipa.append({"animal": a, "set": s, "imu_ok_h": hrs, "events": int(len(e)), "missed": nm, "missed_field": nmf, "missed_house": nmh,
                        "missed_per_h": nm / hrs if hrs > 0 else np.nan})
    IPA = pd.DataFrame(ipa)
    # event overlap (an event's window starting before the previous event's window ends, same animal-night)
    Es = E.sort_values(["animal", "period", "t0_ms"])
    grp = Es.groupby(["animal", "period"])
    ov = (Es["t0_ms"] < grp["t1_ms"].shift()).to_numpy()
    same = ov & (Es["sign"].to_numpy() == grp["sign"].shift().to_numpy())
    mis = (Es["cls"] == "missed").to_numpy()
    Em = Es[mis]
    ovm = (Em["t0_ms"] < Em.groupby(["animal", "period"])["t1_ms"].shift()).to_numpy()
    ev_ov = {"share_overlapping_previous": float(ov.mean()), "share_overlapping_previous_same_sign": float(same.mean()),
             "missed_share_overlapping_previous_missed": float(ovm.mean()) if len(ovm) else np.nan,
             "dur_s_median": float(Es["dur_s"].median()), "missed_dur_s_median": float(Em["dur_s"].median()) if len(Em) else np.nan}
    # ---- decision
    invalid = bool(ctrl["R2_0"] >= float(gc["control_max_R2"]))
    lo_b, hi_b = gc["abs_b_range"]
    pass_b = bool(lo_b <= abs(gate["b0"]) <= hi_b)
    pass_r = bool(gate["R2_0"] >= float(gc["min_R2"]))
    verdict = "INVALID" if invalid else ("PASS" if pass_b and pass_r else "FAIL")
    pass_b1 = bool(lo_b <= abs(gate["b1"]) <= hi_b)
    pass_r1 = bool(gate["R2_1"] >= float(gc["min_R2"]))
    verdict_icpt = "INVALID" if invalid else ("PASS" if pass_b1 and pass_r1 else "FAIL")
    an = FT[(FT["group"] == "animal") & (FT["set"] == "calm")].set_index("animal")
    signs = {a: ("+" if an.loc[a, "b0"] > 0 else "-") + ("" if (an.loc[a, "b0_lo"] > 0 or an.loc[a, "b0_hi"] < 0) else " (CI spans 0)")
             for a in an.index}
    dec = {"verdict": verdict, "pass_abs_b": pass_b, "pass_R2": pass_r, "control_invalid": invalid,
           "b": gate["b0"], "b_ci": [gate["b0_lo"], gate["b0_hi"]], "R2": gate["R2_0"], "R2_ci": [gate["R2_0_lo"], gate["R2_0_hi"]],
           "n_pairs_fit": gate["n_fit"], "control_b": ctrl["b0"], "control_R2": ctrl["R2_0"], "control_R2_ci": [ctrl["R2_0_lo"], ctrl["R2_0_hi"]],
           "intercept_fit": {"b1": gate["b1"], "a1": gate["a1"], "R2_1": gate["R2_1"], "verdict": verdict_icpt},
           "convention": "b > 0: WISER heading increases counter-clockwise like the gyro (right-handed WISER plan view)" if gate["b0"] > 0
           else "b < 0: WISER plan view mirrored relative to 'seen from above' (a left turn is negative in WISER)",
           "sign_by_animal_calm": signs, "lag_peak_s": None if peak is None else float(peak["delta_s"]),
           "ceiling_R2": gate.get("ceiling_R2")}
    log_to(fh, f"verdict {verdict} (intercept fit: {verdict_icpt}); aggregate {time.time() - t0:.0f} s")
    return {"cfg": cfg, "P": P, "FT": FT, "LS": LS, "CT": CT, "IP": IP, "IPA": IPA, "E": E, "Z": Z, "sigd": sigd, "info": info, "ev_ov": ev_ov,
            "dec": dec, "gate": gate, "ctrl": ctrl, "sigma": sigma, "lag_n": int(len(L)), "out": out}


def _jd(o):
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return str(o)


def write_tables(A: dict) -> None:
    tb = A["out"] / "tables"
    A["FT"].to_csv(tb / "fits.csv", index=False, float_format="%.6g")
    boot = A["FT"][["group", "set", "W", "heading", "animal", "band", "x", "n_fit", "n_blocks"]
                   + [c for s in STATS for c in (s, s + "_lo", s + "_hi")]]
    boot.to_csv(tb / "bootstrap_ci.csv", index=False, float_format="%.6g")
    sa = A["FT"][["group", "set", "W", "heading", "animal", "band", "x", "n_sign", "sign_agree", "sign_agree_lo", "sign_agree_hi",
                  "tail", "tail_lo", "tail_hi"]]
    sa.to_csv(tb / "sign_agreement.csv", index=False, float_format="%.6g")
    A["CT"].to_csv(tb / "confusion_gate.csv")
    A["LS"].to_csv(tb / "lag_scan.csv", index=False, float_format="%.6g")
    A["IP"].to_csv(tb / "in_place_rates.csv", index=False, float_format="%.6g")
    A["IPA"].to_csv(tb / "in_place_rates_by_animal.csv", index=False, float_format="%.6g")
    pd.DataFrame([{"set": k, **v} for k, v in A["sigd"].items()]).to_csv(tb / "heading_noise_floor.csv", index=False, float_format="%.6g")
    summ = {"decision": A["dec"], "sigma_convention": A["sigma"], "gate": A["gate"], "control": A["ctrl"], "sigma_d": A["sigd"],
            "lag_scan": A["LS"].to_dict("records"), "lag_common_pairs": A["lag_n"], "in_place": A["IP"].to_dict("records"),
            "in_place_event_overlap": A["ev_ov"],
            "confusion_gate": A["CT"].to_dict()}
    (A["out"] / "summary.json").write_text(json.dumps(summ, indent=2, default=_jd), encoding="utf-8")


# ====================================================================================================== figures
def _style(ax):
    ax.grid(True, color=COL["grid"], lw=0.6, alpha=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(COL["ink2"])
    ax.tick_params(colors=COL["ink2"], labelsize=8)


def make_figures(A: dict, fdir: Path) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm
    cfg, P, FT, gc = A["cfg"], A["P"], A["FT"], A["cfg"]["gate"]
    cohort = cfg["_cohort"]
    mf = float(cfg["pairs"]["max_abs_dpsi_fit_deg"])
    figs = {}
    plt.rcParams.update({"font.size": 9, "axes.titlesize": 9, "axes.labelcolor": COL["ink"], "text.color": COL["ink"]})
    g = P[(P["set"] == gc["set"]) & (P["W"] == gc["W_s"]) & P["ok_raw"]]
    # 1 --- scatter (2-D histogram) gate and control + residual distributions
    fig, axs = plt.subplots(1, 3, figsize=(13.5, 4.3))
    edges = np.linspace(-180, 180, 73)
    for ax, xc, title, row in ((axs[0], "dpsi", "gyro (true time)", A["gate"]), (axs[1], "dpsi_ctrl", "+1 h control", A["ctrl"])):
        d = g[np.isfinite(g[xc]) & np.isfinite(g["dtheta"])]
        h = ax.hist2d(wrap(d[xc]), d["dtheta"], bins=[edges, edges], cmap="Blues", norm=LogNorm(vmin=1), rasterized=True)
        xs = np.array([-mf, mf])
        ax.plot(xs, row["b0"] * xs, color=COL["ink"], lw=2, label=f"fit b = {row['b0']:+.2f}")
        ax.plot([-180, 180], [-180, 180], color=COL["ink2"], lw=1, ls=":", label="Δθ = Δψ")
        ax.plot([-180, 180], [180, -180], color=COL["ink2"], lw=1, ls="--", label="Δθ = −Δψ")
        for v in (-mf, mf):
            ax.axvline(v, color=COL["ink2"], lw=0.6, alpha=0.6)
        ax.set_xlim(-180, 180)
        ax.set_ylim(-180, 180)
        ax.set_aspect("equal")
        ax.set_xlabel("head turn Δψ (deg, gyro; + = CCW from above)")
        ax.set_ylabel("WISER path turn Δθ (deg)")
        ax.set_title(f"Calm nights, W = {gc['W_s']} s, {title}\nb = {row['b0']:+.2f} [{row['b0_lo']:+.2f}, {row['b0_hi']:+.2f}], "
                     f"R² = {row['R2_0']:.2f}, n = {row['n_fit']:,}")
        ax.legend(loc="upper left", fontsize=7, frameon=False)
        _style(ax)
        fig.colorbar(h[3], ax=ax, shrink=0.75, label="pairs")
    ax = axs[2]
    be = np.linspace(-180, 180, 73)
    for s in ("calm", "rain"):
        r = FT[(FT["group"] == "W") & (FT["set"] == s) & (FT["W"] == gc["W_s"])].iloc[0]
        d = P[(P["set"] == s) & (P["W"] == gc["W_s"]) & P["ok_raw"]]
        rr = wrap(d["dtheta"] - r["b0"] * wrap(d["dpsi"]))
        ax.hist(rr, bins=be, density=True, histtype="step", lw=2, color=COL[s], label=f"{s}: median |r| {r['med_r']:.0f}°, |r| > 30° {100 * r['tail']:.0f} %")
    for v in (-30, 30):
        ax.axvline(v, color=COL["ink2"], lw=0.8, ls="--")
    ax.set_xlim(-180, 180)
    ax.set_xlabel("residual r = wrap(Δθ − b Δψ) (deg)")
    ax.set_ylabel("density")
    ax.set_title(f"Residuals, W = {gc['W_s']} s (dashed: scanning-tail bounds ± 30°)")
    ax.legend(loc="upper left", fontsize=7, frameon=False)
    _style(ax)
    fig.tight_layout()
    f = f"{STEM}_scatter_{cohort}.png"
    fig.savefig(fdir / f, dpi=150)
    plt.close(fig)
    figs["scatter"] = f
    # 2 --- per animal: slope and R2 (calm, rain, control)
    fig, axs = plt.subplots(1, 2, figsize=(11, 3.8), sharey=True)
    animals = list(cfg["animals"])
    yb = np.arange(len(animals))
    series = (("animal", "calm", "calm", "calm nights"), ("animal", "rain", "rain", "rain nights"), ("animal_control", "calm", "control", "+1 h control (calm)"))
    for k, (grp, s, ck, lab) in enumerate(series):
        d = FT[(FT["group"] == grp) & (FT["set"] == s)].set_index("animal").reindex(animals)
        off = (k - 1) * 0.22
        for ax, st in ((axs[0], "b0"), (axs[1], "R2_0")):
            ax.errorbar(d[st], yb + off, xerr=[d[st] - d[st + "_lo"], d[st + "_hi"] - d[st]], fmt="o", ms=5, color=COL[ck],
                        ecolor=COL[ck], elinewidth=1.5, capsize=2, label=lab)
    lo_b, hi_b = gc["abs_b_range"]
    axs[0].axvspan(lo_b, hi_b, color=COL["calm"], alpha=0.08, lw=0)
    axs[0].axvspan(-hi_b, -lo_b, color=COL["rain"], alpha=0.08, lw=0)
    axs[0].axvline(0, color=COL["ink2"], lw=0.8)
    axs[0].set_xlabel("slope b (WISER path turn per degree of head turn)")
    axs[0].set_title("Slope per animal (W = 2 s); shaded = |b| in [0.8, 1.2] (blue normal, orange mirrored)")
    axs[1].axvline(float(gc["min_R2"]), color=COL["ink2"], lw=1, ls="--")
    axs[1].axvline(float(gc["control_max_R2"]), color=COL["control"], lw=1, ls=":")
    axs[1].set_xlabel("R² (through the origin, centred)")
    axs[1].set_title("R² per animal; dashed = gate 0.5, dotted = control limit 0.1")
    axs[0].set_yticks(yb)
    axs[0].set_yticklabels(animals)
    axs[0].invert_yaxis()
    hd, lb = axs[1].get_legend_handles_labels()
    fig.legend(hd, lb, loc="lower center", ncol=3, fontsize=8, frameon=False)
    for ax in axs:
        _style(ax)
    fig.tight_layout(rect=[0, 0.07, 1, 1])
    f = f"{STEM}_animals_{cohort}.png"
    fig.savefig(fdir / f, dpi=150)
    plt.close(fig)
    figs["animals"] = f
    # 3 --- lag scan (R2 and b in separate panels)
    LS = A["LS"]
    fig, axs = plt.subplots(1, 2, figsize=(9.5, 3.4))
    axs[0].plot(LS["delta_s"], LS["R2_0"], "-o", color=COL["calm"], lw=2, ms=5)
    axs[0].set_ylabel("R²")
    axs[1].plot(LS["delta_s"], LS["b0"], "-o", color=COL["calm"], lw=2, ms=5)
    axs[1].set_ylabel("slope b")
    for ax in axs:
        ax.axvline(0, color=COL["ink2"], lw=0.8, ls="--")
        ax.set_xlabel("gyro shift δ (s; gyro read at t + δ)")
        _style(ax)
    axs[0].set_title(f"Lag scan, calm, W = 2 s, n = {A['lag_n']:,} common pairs")
    axs[1].set_title("Slope vs gyro shift")
    fig.tight_layout()
    f = f"{STEM}_lag_{cohort}.png"
    fig.savefig(fdir / f, dpi=150)
    plt.close(fig)
    figs["lag"] = f
    # 4 --- observed R2 vs the WISER-noise ceiling by subset
    sub = []
    for s in ("calm", "rain"):
        for W in cfg["pairs"]["W_s"]:
            r = FT[(FT["group"] == "W") & (FT["set"] == s) & (FT["W"] == W)].iloc[0]
            sub.append((f"{s} W={int(W)} s", s, r))
        for r in FT[(FT["group"] == "band") & (FT["set"] == s)].itertuples():
            rr = FT.loc[r.Index]
            sub.append((f"{s} W=2 s, {rr['band']} in/s", s, rr))
    fig, ax = plt.subplots(figsize=(8.5, 0.32 * len(sub) + 1.4))
    yy = np.arange(len(sub))
    for i, (lab, s, r) in enumerate(sub):
        ax.errorbar(r["R2_0"], i, xerr=[[r["R2_0"] - r["R2_0_lo"]], [r["R2_0_hi"] - r["R2_0"]]], fmt="o", ms=6, color=COL[s], capsize=2,
                    label="observed R² (95 % CI)" if i == 0 else None)
        ax.plot(r["ceiling_R2"], i, marker="D", ms=7, mfc="none", mec=COL["ink"], ls="none",
                label="ceiling from WISER noise (ideal gyro)" if i == 0 else None)
    ax.axvline(float(gc["min_R2"]), color=COL["ink2"], lw=1, ls="--")
    ax.set_yticks(yy)
    ax.set_yticklabels([s[0] for s in sub], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("R²")
    ax.set_xlim(-0.05, 1.0)
    ax.set_title("Observed R² vs the still-floor ceiling an ideal gyro could reach (dashed = gate 0.5)")
    hd, lb = ax.get_legend_handles_labels()
    fig.legend(hd, lb, loc="lower center", ncol=2, fontsize=8, frameon=False)
    _style(ax)
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    f = f"{STEM}_ceiling_{cohort}.png"
    fig.savefig(fdir / f, dpi=150)
    plt.close(fig)
    figs["ceiling"] = f
    return figs


# ====================================================================================================== report
def _f(x, nd: int = 2, sign: bool = False) -> str:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "—"
    if not np.isfinite(x):
        return "—"
    return f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"


def _ci(r, k: str, nd: int = 2, sign: bool = False, pct: bool = False) -> str:
    m = 100.0 if pct else 1.0
    v, lo, hi = r.get(k), r.get(k + "_lo"), r.get(k + "_hi")
    s = _f(None if v is None else m * v, nd, sign)
    if lo is None or not np.isfinite(float(lo)):
        return s
    return f"{s} [{_f(m * lo, nd, sign)}, {_f(m * hi, nd, sign)}]"


DEFINITIONS = r"""
All positions are WISER native **inches** (unverified offset origin; nothing here is placed in the paddock); angles in
degrees; times are field-PC time (WISER fix times shifted by the per-animal clock lag $\tau^*$ of the smoothing pilot).
Symbols: $t_i$, $\mathbf z_i$ = aligned time and raw position of fix $i$; $h$ = a heading centre and $c$ = a pair centre,
both on the 0.5-s grid of whole field-PC seconds from 21:00; $W$ = pair separation (s); $\omega_k$ = make_imu `turn_dps`
of 50-Hz sample $k$ at time $u_k$.

### 1-s position median $\mathbf m(t)$
$$\mathbf m(t)=\operatorname{med}_{\text{coordinate-wise}}\{\mathbf z_i:\ t_i\in[t-0.5,\ t+0.5)\},\qquad\text{defined if}\ \ge 3\ \text{fixes}$$
**Text:** median raw position in a 1-s window (in); smoother-independent.

### WISER heading $\theta(h)$ and 1-s speed $v(h)$
$$\mathbf d(h)=\mathbf m(h+0.5)-\mathbf m(h-0.5),\qquad v(h)=\lVert\mathbf d(h)\rVert/1\ \mathrm s,\qquad \theta(h)=\operatorname{atan2}(d_y,\ d_x)$$
**Text:** direction of travel from the median position of $[h-1,h)$ to that of $[h,h+1)$ (deg, + = from WISER $+x$ toward
$+y$). Defined when $v(h)\ge 10$ in/s and every second overlapping $[h-1,h+1)$ is a step-B clean second. **V3 heading**
$\theta_{V3}$: the same with $\mathbf z_i$ replaced by the V3 track at the fix times.

### Locomotion threshold (10 in/s)
Value **10 in/s** on $v(h)$, from the plan (marked operational): ≈ 5 × the clean-WISER 1-s noise floor p50 (1.90 in/s) and
≈ 2 × its p95 (5.26 in/s), so a heading is not dominated by jitter. Selects locomotion; slow walking is excluded by construction.

### Clean second (step B)
A field-PC second $[s,s+1)$ whose fixes in $[s-1.5,\ s+2.5]$ all have ≥ 8 anchors, are valid and unmasked (handling,
all-tag silences, tag validity, ADC lane), contain no jump (> 30 in within ≤ 0.35 s) and number ≥ 12 (≥ 3 Hz), whose two
u3 medians lie outside the house ROIs + 14 in, and whose IMU second is QC-ok (`analyze_imu_speed_proxy.reference`).

### Gyro heading $\psi$ and its 1-s mean $\bar\psi$
$$\psi(u_k)=\sum_{j\le k}\omega_j\,q_j\,\Delta,\qquad \bar\psi(h)=\frac1{|K_h|}\sum_{k\in K_h}\psi(u_k),\qquad K_h=\{k:\ u_k\in[h-0.5,\ h+0.5)\}$$
$\Delta$ = 0.02 s; $q_j\in\{0,1\}$ = the failure audit's sample QC (finite, not saturated / frozen / invalid / unreliable,
frozen rule, handling ± 5 min, all-tag silences ± 2 min, ADC lane, tag window). **Text:** integrated head turn about
the vertical (deg, + = counter-clockwise seen from above), unwrapped. Only differences enter, so the unobservable
IMU-to-WISER heading offset cancels; the gyro bias drift (≈ 2 °/min) adds ≤ 0.1° over 3 s.

### Pair quantities $\Delta\theta$, $\Delta\psi$
$$\Delta\theta(c,W)=\operatorname{wrap}\!\big(\theta(c+\tfrac W2)-\theta(c-\tfrac W2)\big),\qquad \Delta\psi(c,W)=\bar\psi(c+\tfrac W2)-\bar\psi(c-\tfrac W2),\qquad \operatorname{wrap}(x)=((x+180)\bmod 360)-180$$
**Text:** change of the travel direction (WISER) and of the head yaw (gyro) between two 1-s windows $W$ s apart (deg). A
pair needs both headings defined and every 50-Hz sample of $[c-\frac W2-0.5,\ c+\frac W2+0.5)$ QC-ok with no gap.

### Slope $b$ and $R^2$ (gate fit, through the origin); fit with intercept ($b_1$, $a_1$, $R^2_1$)
$$b=\frac{\sum\Delta\psi\,\Delta\theta}{\sum\Delta\psi^2},\qquad R^2=1-\frac{\sum(\Delta\theta-b\,\Delta\psi)^2}{\sum(\Delta\theta-\overline{\Delta\theta})^2}$$
$$b_1=\frac{\sum(\Delta\psi-\overline{\Delta\psi})(\Delta\theta-\overline{\Delta\theta})}{\sum(\Delta\psi-\overline{\Delta\psi})^2},\qquad a_1=\overline{\Delta\theta}-b_1\overline{\Delta\psi},\qquad R^2_1=\operatorname{corr}(\Delta\psi,\Delta\theta)^2$$
over the pairs with $|\Delta\psi|\le150°$ (wrap ambiguity beyond). **Text:** $b$ = degrees of WISER path turn per degree
of head turn (gyro = regressor, the less noisy one); $b\approx+1$ same sense and scale, $b\approx-1$ mirrored WISER plan
view, $b\approx0$ unrelated. $R^2$ = share of the variance of $\Delta\theta$ explained by $b\,\Delta\psi$ (≤ 1; < 0 possible
for a fit through the origin); $R^2\le R^2_1$ always.

### Residual $r$, median |r|, p90 |r|, scanning tail
$$r=\operatorname{wrap}\!\big(\Delta\theta-b\,\operatorname{wrap}(\Delta\psi)\big),\qquad \text{tail}=\frac{\#\{|r|>30°\}}{\#\{\text{pairs}\}}$$
**Text:** the path turn not explained by the head turn (deg), over all pairs of the subset (incl. $|\Delta\psi|>150°$);
|r| > 30° = the head turned without the path turning (scanning) or the path turned without the head.

### Circular correlation $\rho_c$
$$\rho_c=\frac{\sum\sin(\alpha-\bar\alpha)\sin(\beta-\bar\beta)}{\sqrt{\sum\sin^2(\alpha-\bar\alpha)\,\sum\sin^2(\beta-\bar\beta)}},\qquad \alpha=\Delta\theta,\ \beta=\Delta\psi$$
$\bar\alpha,\bar\beta$ = circular means. **Text:** Jammalamadaka–SenGupta correlation of two angles, range [−1, 1]; a check
independent of the linear fit (fit set).

### Turn-sign agreement $A$ and confusion table
$$A=\frac{\#\{\operatorname{sgn}\Delta\theta=\sigma\operatorname{sgn}\Delta\psi,\ 30°\le|\Delta\psi|\le150°\}}{\#\{30°\le|\Delta\psi|\le150°\}},\qquad \sigma=\operatorname{sgn}b_{\text{calm},W=2}$$
**Text:** share of clear head turns whose path turn has the same sense after the convention set by the pooled slope;
0.5 = chance, 1 = always. Confusion classes (fit set): left $\ge 15°$, right $\le -15°$, straight otherwise — on $\Delta\psi$
for the gyro and on $\sigma\Delta\theta$ for WISER.

### Expected heading noise $\sigma_\theta$ and the $R^2$ ceiling $R^2_{\max}$
$$\sigma_d=\frac{\operatorname{med}\lVert\mathbf d\rVert_{\text{still}}}{\sqrt{2\ln 2}},\qquad \sigma_\theta(h)=\frac{\sigma_d}{\lVert\mathbf d(h)\rVert},\qquad R^2_{\max}=1-\frac{\overline{\sigma_\theta^2(c-\frac W2)+\sigma_\theta^2(c+\frac W2)}}{\operatorname{Var}(\Delta\theta)}$$
$\lVert\mathbf d\rVert_{\text{still}}$ = the same 1-s displacement on step-B floor seconds (certified still by the head IMU,
fixes clean), per set. **Text:** $\sigma_d$ = per-coordinate SD of the displacement noise (in; Rayleigh median), $\sigma_\theta$ =
the heading noise it causes (rad, shown in deg), $R^2_{\max}$ = the $R^2$ a gyro that measured the body heading exactly
could reach given WISER noise alone (fit set). Independent ends assumed (approximate at W = 1, where both headings share
$\mathbf m(c)$). $R^2$ far below $R^2_{\max}$ means the shortfall is head–path mismatch, not WISER noise.

### Speed band
A pair's band = its slower end speed $\min\{v(c-\frac W2),\ v(c+\frac W2)\}$: [10, 20) or ≥ 20 in/s.

### +1 h control
$\Delta\psi_{+1h}(c,W)=\bar\psi(c+\frac W2+3600)-\bar\psi(c-\frac W2+3600)$ with the sample QC at the shifted times,
fitted exactly as $\Delta\psi$. **Text:** keeps the statistics of both signals but breaks their alignment; expected
$b\approx0$, $R^2\approx0$; $R^2_{+1h}\ge 0.1$ declares the analysis invalid (pipeline artefact).

### Lag scan
$\Delta\psi_\delta$ = $\Delta\psi$ with the gyro read at $t+\delta$, $\delta\in\{-0.5,-0.4,\dots,+0.5\}$ s, on one common pair
set (calm, W = 2 s, QC-ok at all shifts); point estimates of $b$ and $R^2$. **Text:** a residual clock lag after $\tau^*$
would move the $R^2$ peak away from 0.

### Turns in place that WISER misses
$$\text{candidate}(t):\ |\psi(t+3)-\psi(t)|\ge 90°\ \text{and}\ [t,t+3)\ \text{QC-ok},\qquad t\in\{t_0,\ t_0+0.1,\ \dots\}$$
$\psi$ linearly interpolated between samples. A turn event = a run of consecutive same-sign candidates; window
$[t_{\text{first}},\ t_{\text{last}}+3]$. WISER coverage = $u_1$ exists on $\ge\lceil n/2\rceil$ of the $n$ seconds
overlapping the window (Amendment 2); with coverage, **missed by WISER** = every available $u_1<5.26$ in/s, "WISER moving" =
some available $u_1\ge5.26$; without coverage, "no WISER". $u_1$ = step B's 1-s speed (0.75-s raw medians at
$s+0.5\pm0.5$); 5.26 in/s = its all-period noise-floor p95. Zone = the median raw fix of the window vs the house ROIs
+ 14 in. Rate = events / IMU-ok hours of the stratum (audit per-second `ok`; zone of a second = the median raw fix of
$[s-1,\ s+2)$, the shortest event window, Amendment 3; 'unknown' with < 3 fixes).
**Text:** head turns ≥ 90° within 3 s during which a WISER speed rule would call the animal stationary (events per hour).

### Bootstrap CI
Blocks = 10 min from 21:00 per (animal, night); 1000 resamples of the blocks with replacement (seed 20261004); every
statistic is recomputed per resample (residual quantiles with the resample's $b$); CI = 2.5–97.5 %. Point estimates
decide; CIs are reported.

### Gate (pre-registered)
Calm nights (09-05 … 09-08), W = 2 s, raw-median heading, fit through the origin: $|b|\in[0.8,\ 1.2]$ and $R^2\ge0.5$ →
**PASS** (head yaw is a usable body-turn signal during locomotion), otherwise **FAIL**; $R^2_{+1h}\ge0.1$ → **INVALID**.
Values from the plan, fixed before any result: a unit gain within ± 20 % and at least half of the path-turn variance explained.
"""


def _fit_row(FT: pd.DataFrame, **kw) -> dict:
    m = np.ones(len(FT), bool)
    for k, v in kw.items():
        m &= (FT[k] == v).to_numpy()
    d = FT[m]
    return d.iloc[0].to_dict() if len(d) else {}


def render_report(A: dict, out: Path, figs: dict, meta: dict) -> str:
    cfg, FT, dec, gate, ctrl = A["cfg"], A["FT"], A["dec"], A["gate"], A["ctrl"]
    gc = cfg["gate"]
    sigd, info = A["sigd"], A["info"]
    L = []
    w = L.append
    v = dec["verdict"]
    w(f"# WISER baseline 2026c — Phase 0 of turn-aided WISER: head gyro turn vs WISER heading change\n")
    w(f"- **Status:** measurement report, {pd.Timestamp.now(tz=cfg['tz']).strftime('%Y-%m-%d')}. Plan `{PLAN}` (approved by the user "
      f"2026-10-04, \"做\"; committed 5281fc6 before any result; operational details in its Amendment 1, written before any number). "
      f"Driver `{DRIVER}`, config `{meta['config']}` (verdict in `decision`), run `{out}`, git `{meta['git_commit']}`.")
    w("- **What this is:** whether the head gyro's *relative* turn (no absolute heading needed) follows the WISER path heading "
      "change during locomotion, so that it could aid a smoother (V7). **No behavioural claim.** Frame: WISER native inches, "
      "unverified offset origin; only turn *differences* are used, so the frame origin and the IMU-to-WISER heading offset (unobservable, V6) do not enter.")
    w("- **Regime context (regime-aware-wiser-tracking):** clean seconds only (≥ 8 anchors, open field, no jumps, ≥ 3 Hz, IMU QC-ok), "
      "speed ≥ 10 in/s (locomotion); agreement in the houses, at slow walking and in turns in place is not measured by the fit. "
      "Raw-median headings carry WISER jitter (attenuates R², conservative). Rain nights (09-03, 09-09) are reported, not gated.\n")
    # ---- verdict
    w("## Verdict\n")
    w("| Gate quantity (calm 09-05…09-08, W = 2 s, raw-median heading) | value [95 % CI] | rule | met |")
    w("|---|---|---|---|")
    w(f"| slope b (through the origin) | {_ci(gate, 'b0', 3, True)} | \\|b\\| ∈ [{gc['abs_b_range'][0]}, {gc['abs_b_range'][1]}] | {'yes' if dec['pass_abs_b'] else 'no'} |")
    w(f"| R² (centred) | {_ci(gate, 'R2_0', 3)} | ≥ {gc['min_R2']} | {'yes' if dec['pass_R2'] else 'no'} |")
    w(f"| +1 h control R² | {_ci(ctrl, 'R2_0', 3)} (b {_f(ctrl['b0'], 3, True)}) | < {gc['control_max_R2']} (else INVALID) | {'yes' if not dec['control_invalid'] else 'NO'} |")
    w(f"| pairs in the fit | {gate['n_fit']:,} ({gate['n_blocks']} ten-minute blocks, {gate['n_animal_nights']} animal-nights; {gate['n_excl']} with \\|Δψ\\| > 150° excluded) | | |")
    w("")
    w(f"**{v}.** " + {
        "PASS": "Head yaw tracks the body's path turn during locomotion closely enough to be used as a turn annotation; the agreed follow-up is a turn-rate-aided smoother (V7), built and tested like V3/V6.",
        "FAIL": "Head yaw does not track the WISER path turn closely enough during locomotion (pre-registered rule). Per the plan, head turns stay a head-behaviour signal only; no turn-rate-aided smoother (V7) is built.",
        "INVALID": "The +1 h control explains ≥ 10 % of the variance: the analysis is declared a pipeline artefact and no conclusion is drawn."}[v])
    w(f"Intercept fit (check): b₁ {_ci(gate, 'b1', 3, True)}, intercept a₁ {_f(gate['a1'], 2, True)}°, R²₁ {_ci(gate, 'R2_1', 3)} → "
      f"the same rule gives **{dec['intercept_fit']['verdict']}**" + (" (agrees)." if dec["intercept_fit"]["verdict"] == v else " (disagrees — the verdict stays with the through-origin fit, Amendment 1.5)."))
    w(f"Circular correlation ρ_c {_ci(gate, 'rho_c', 3)}; turn-sign agreement for 30° ≤ |Δψ| ≤ 150° {_ci(gate, 'sign_agree', 1, pct=True)} % "
      f"(n {gate['n_sign']:,}); scanning tail |r| > 30° {_ci(gate, 'tail', 1, pct=True)} %; median |r| {_ci(gate, 'med_r', 1)}°, p90 {_ci(gate, 'p90_r', 1)}°.")
    w(f"WISER-noise ceiling for R² (ideal gyro): {_f(gate.get('ceiling_R2'), 3)} (σ_d {_f(sigd['calm']['sigma_d_in'], 2)} in; median per-end "
      f"σ_θ {_f(gate.get('sigma_theta_med_deg'), 1)}°).")
    w(f"**Convention:** {dec['convention']}. Per animal (calm): " + ", ".join(f"{a} {s}" for a, s in dec["sign_by_animal_calm"].items()) + ".\n")
    # ---- reading
    w("## Reading\n")
    for line in reading(A):
        w(f"- {line}")
    w("")
    w("Classification (regime-aware-wiser-tracking): a **measurement** result about the head IMU and WISER (no behavioural content). "
      "The turns-in-place counts measure what a WISER speed rule cannot see, not a behaviour rate.\n")
    # ---- 1 figure
    w("## 1. Gate fit and +1 h control\n")
    w(f"![scatter](../figures/{figs['scatter']})\n")
    w("Left: calm W = 2 s pairs (2-D histogram, log colour), the fitted line and the ± identity lines; vertical lines = the ± 150° fit limit. "
      "Middle: the same pairs against the gyro read 1 h later. Right: residual distributions (calm and rain) with the ± 30° scanning-tail bounds.\n")
    # ---- 2 W and rain
    w("## 2. Separations W = 1, 2, 3 s, calm and rain (raw-median heading)\n")
    w("| set | W (s) | pairs (fit / all) | b [CI] | R² [CI] | b₁ | a₁ (°) | R²₁ | ρ_c | median \\|r\\| (°) | p90 \\|r\\| (°) | tail \\|r\\| > 30° (%) | sign agreement (%) | R² ceiling |")
    w("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for s in ("calm", "rain", "all"):
        for W in cfg["pairs"]["W_s"]:
            r = _fit_row(FT, group="W", set=s, W=W)
            if not r:
                continue
            w(f"| {s} | {int(W)} | {r['n_fit']:,} / {r['n_pairs']:,} | {_ci(r, 'b0', 3, True)} | {_ci(r, 'R2_0', 3)} | {_f(r['b1'], 3, True)} | "
              f"{_f(r['a1'], 2, True)} | {_f(r['R2_1'], 3)} | {_f(r['rho_c'], 3)} | {_f(r['med_r'], 1)} | {_f(r['p90_r'], 1)} | "
              f"{_f(100 * r['tail'], 1)} | {_f(100 * r['sign_agree'], 1)} | {_f(r.get('ceiling_R2'), 3)} |")
    w("")
    w(f"![ceiling](../figures/{figs['ceiling']})\n")
    # ---- 3 per animal
    w("## 3. Per animal (W = 2 s) — the sign of b is the frame handedness per animal\n")
    w(f"![animals](../figures/{figs['animals']})\n")
    w("| animal | set | pairs (fit) | b [CI] | sign | R² [CI] | ρ_c | sign agreement (%) | tail \\|r\\| > 30° (%) | +1 h control b / R² (calm) |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for a in cfg["animals"]:
        for s in ("calm", "rain"):
            r = _fit_row(FT, group="animal", set=s, animal=a)
            if not r:
                continue
            c = _fit_row(FT, group="animal_control", set="calm", animal=a) if s == "calm" else {}
            sgn = ("+ (normal)" if r["b0"] > 0 else "− (mirrored)") + ("" if (r["b0_lo"] > 0 or r["b0_hi"] < 0) else ", CI spans 0")
            w(f"| {a} | {s} | {r['n_fit']:,} | {_ci(r, 'b0', 3, True)} | {sgn} | {_ci(r, 'R2_0', 3)} | {_f(r['rho_c'], 3)} | "
              f"{_ci(r, 'sign_agree', 1, pct=True)} | {_f(100 * r['tail'], 1)} | {(_f(c.get('b0'), 3, True) + ' / ' + _f(c.get('R2_0'), 3)) if c else ''} |")
    w("")
    w("Sign agreement uses the pooled convention σ for every animal, so a mirrored animal would show < 50 %.\n")
    # ---- 4 speed bands
    w("## 4. Speed bands (W = 2 s; band = the slower end speed)\n")
    w("| set | heading | band (in/s) | pairs (fit) | b [CI] | R² [CI] | median \\|r\\| (°) | tail (%) | median σ_θ per end (°) | RMS σ_Δθ (°) | R² ceiling |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    for s in ("calm", "rain"):
        for grp, hd in (("band", "raw"), ("band_v3", "v3")):
            for r in FT[(FT["group"] == grp) & (FT["set"] == s)].to_dict("records"):
                w(f"| {s} | {hd} | {r['band']} | {r['n_fit']:,} | {_ci(r, 'b0', 3, True)} | {_ci(r, 'R2_0', 3)} | {_f(r['med_r'], 1)} | "
                  f"{_f(100 * r['tail'], 1)} | {_f(r.get('sigma_theta_med_deg'), 1)} | {_f(r.get('sigma_dtheta_rms_deg'), 1)} | {_f(r.get('ceiling_R2'), 3)} |")
    w("")
    # ---- 5 V3
    w("## 5. V3-track heading instead of raw medians\n")
    w("| set | W (s) | pairs (fit / all) | b [CI] | R² [CI] | b₁ | R²₁ | ρ_c | median \\|r\\| (°) | tail (%) | sign agreement (%) |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    for s in ("calm", "rain"):
        for W in cfg["pairs"]["W_s"]:
            r = _fit_row(FT, group="v3", set=s, W=W)
            if not r:
                continue
            w(f"| {s} | {int(W)} | {r['n_fit']:,} / {r['n_pairs']:,} | {_ci(r, 'b0', 3, True)} | {_ci(r, 'R2_0', 3)} | {_f(r['b1'], 3, True)} | "
              f"{_f(r['R2_1'], 3)} | {_f(r['rho_c'], 3)} | {_f(r['med_r'], 1)} | {_f(100 * r['tail'], 1)} | {_f(100 * r['sign_agree'], 1)} |")
    w("")
    w("V3 uses the head IMU (ZUPT in still runs, q × 10 on IMU-locomoting steps) but not the gyro's turn, so it is not circular here; "
      "its heading is smoother than the raw medians' (no WISER-noise ceiling is computed for it).\n")
    # ---- 6 sign agreement / confusion
    CT = A["CT"]
    w("## 6. Turn-sign agreement and the left / straight / right confusion table (gate fit set)\n")
    w(f"Convention σ = {A['sigma']:+.0f} (sign of the pooled calm slope). Rows = gyro (Δψ), columns = WISER (σΔθ); "
      f"left ≥ 15°, right ≤ −15°, straight otherwise; counts and row shares.\n")
    w("| gyro \\ WISER | left | straight | right | n |")
    w("|---|---|---|---|---|")
    for i in CT.index:
        n = int(CT.loc[i].sum())
        w(f"| {i} | " + " | ".join(f"{int(CT.loc[i, c]):,} ({_f(100 * CT.loc[i, c] / n if n else np.nan, 0)} %)" for c in CT.columns) + f" | {n:,} |")
    w("")
    w(f"Turn-sign agreement for 30° ≤ |Δψ| ≤ 150° (calm, W = 2 s): {_ci(gate, 'sign_agree', 1, pct=True)} % of {gate['n_sign']:,} pairs; "
      f"rain: {_ci(_fit_row(FT, group='W', set='rain', W=gc['W_s']), 'sign_agree', 1, pct=True)} %.\n")
    # ---- 7 scanning tail
    w("## 7. Scanning tail\n")
    w("Share of pairs with |r| > 30° (head turned without the path turning, or the reverse), with the subset's own slope:\n")
    w("| subset | tail (%) [CI] | median \\|r\\| (°) | p90 \\|r\\| (°) |")
    w("|---|---|---|---|")
    for s in ("calm", "rain"):
        for W in cfg["pairs"]["W_s"]:
            r = _fit_row(FT, group="W", set=s, W=W)
            w(f"| {s}, W = {int(W)} s | {_ci(r, 'tail', 1, pct=True)} | {_ci(r, 'med_r', 1)} | {_ci(r, 'p90_r', 1)} |")
    w("")
    # ---- 8 turns in place
    IP, IPA = A["IP"], A["IPA"]
    ic = cfg["in_place"]
    w(f"## 8. What WISER misses: gyro turns ≥ {ic['turn_deg']:g}° within {ic['window_s']:g} s while u1 < {ic['u1_floor_p95_inps']} in/s\n")
    w("Coverage rule (Amendment 2): u1 on at least half of the event's seconds; 'missed' = every available u1 below the floor p95.\n")
    w("| set | zone | IMU-ok hours | turn events | missed by WISER | WISER moving | no WISER | events / h | **missed / h** | missed / (missed + moving) |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for r in IP.to_dict("records"):
        w(f"| {r['set']} | {r['zone']} | {_f(r['imu_ok_h'], 1)} | {r['events']:,} | {r['missed']:,} | {r['wiser_moving']:,} | {r['no_wiser']:,} | "
          f"{_f(r['events_per_h'], 1)} | **{_f(r['missed_per_h'], 1)}** | {_f(100 * r['share_missed'], 0)} % |")
    w("")
    eo = A["ev_ov"]
    w(f"**Events are not independent turns.** Event windows last {_f(eo['dur_s_median'], 1)} s (median; missed events "
      f"{_f(eo['missed_dur_s_median'], 1)} s). {_f(100 * eo['share_overlapping_previous'], 0)} % of all events start before the previous "
      f"event's window ends ({_f(100 * eo['share_overlapping_previous_same_sign'], 0)} % with the same sign, i.e. one turning bout split by a "
      f"dip below 90° or a QC-failed sample; the rest are back-and-forth sweeps, which count one event per direction). Among missed events, "
      f"{_f(100 * eo['missed_share_overlapping_previous_missed'], 0)} % overlap the previous missed event. The rates are events per hour under "
      "the pre-registered rule, not counts of separate behaviours.\n")
    w("Per animal (all zones):\n")
    w("| animal | set | IMU-ok hours | turn events | missed (field / house) | missed / h |")
    w("|---|---|---|---|---|---|")
    for r in IPA.to_dict("records"):
        w(f"| {r['animal']} | {r['set']} | {_f(r['imu_ok_h'], 1)} | {r['events']:,} | {r['missed']:,} ({r['missed_field']:,} / {r['missed_house']:,}) | {_f(r['missed_per_h'], 1)} |")
    w("")
    w("Zone = the median raw fix of the event window (house ROIs + 14 in); denominators: zone of an IMU-ok second = the median raw fix of "
      "[s − 1, s + 2) (Amendment 3); 'unknown' = fewer than 3 fixes. The house zone has fewer anchors "
      "and more WISER noise, so its u1 crosses 5.26 in/s more often (fewer events can qualify as missed there).\n")
    # ---- 9 lag
    LS = A["LS"]
    w("## 9. Lag check (gyro read at t + δ; calm, W = 2 s, one common pair set)\n")
    w(f"![lag](../figures/{figs['lag']})\n")
    w("| δ (s) | " + " | ".join(_f(d, 1, True) for d in LS["delta_s"]) + " |")
    w("|---|" + "---|" * len(LS))
    w("| R² | " + " | ".join(_f(x, 3) for x in LS["R2_0"]) + " |")
    w("| b | " + " | ".join(_f(x, 3, True) for x in LS["b0"]) + " |")
    w("")
    w(f"Peak R² at δ = {_f(dec['lag_peak_s'], 1, True)} s (n = {A['lag_n']:,} common pairs; τ* already applied to the fix times).\n")
    # ---- 10 noise
    w("## 10. Expected heading noise (the ceiling an ideal gyro could reach)\n")
    w("| floor source | seconds | p50 \\|d\\| (in/s) | p95 \\|d\\| (in/s) | σ_d (in, Rayleigh median) | σ_d (in, RMS) |")
    w("|---|---|---|---|---|---|")
    for s in ("calm", "rain", "all"):
        r = sigd[s]
        w(f"| 1-s medians at h ± 0.5 on step-B floor seconds, {s} nights | {r['n_s']:,} | {_f(r['p50_inps'], 2)} | {_f(r['p95_inps'], 2)} | {_f(r['sigma_d_in'], 2)} | {_f(r['sigma_d_rms_in'], 2)} |")
    r = sigd["step_b_u1"]
    w(f"| step B's u1 floor (0.75-s medians, all periods; reference only) | — | {_f(r['p50_inps'], 2)} | {_f(r['p95_inps'], 2)} | {_f(r['sigma_d_in'], 2)} | — |")
    w("")
    w("Per pair end σ_θ = σ_d / ‖d‖ (at 10 in/s: " + f"{_f(np.degrees(sigd['calm']['sigma_d_in'] / 10.0), 1)}°, at 20 in/s: {_f(np.degrees(sigd['calm']['sigma_d_in'] / 20.0), 1)}° calm). "
      "The ceilings are in §2 and §4. **Caveat (post hoc, declared):** the floor is measured on a still head; the V3-heading result (§5) "
      "shows that the raw-median heading noise during locomotion is larger, so these ceilings are upper bounds under the still-noise model, "
      "not the attainable R².\n")
    # ---- coverage
    w("## 11. Data and coverage\n")
    w("| animal | night | set | clean s | IMU-ok s | IMU valid 50 Hz (h) | raw headings | pairs W = 1 / 2 / 3 | floor s | turn events |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for r in info.sort_values(["period", "animal"]).to_dict("records"):
        w(f"| {r['animal']} | {r['period'][6:]} | {r['set']} | {r['clean_s']:,} | {r['imu_ok_s']:,} | {_f(r['imu_valid_50hz_h'], 2)} | {r['headings_raw']:,} | "
          f"{r['pairs_W1_raw']:,} / {r['pairs_W2_raw']:,} / {r['pairs_W3_raw']:,} | {r['floor_s']:,} | {r['turn_events']:,} |")
    w("")
    # ---- definitions
    w("## Definitions\n")
    w(DEFINITIONS.strip() + "\n")
    # ---- amendments, caveats, outputs
    w("## Amendments and decisions\n")
    w("- **Amendment 1 (before any number):** operational resolutions in the plan (scope; grid; clean-second support of a heading; "
      "sample-level IMU QC over the pair span; the gate uses the through-origin fit with a centred R², the intercept fit beside it; "
      "residual statistics over all pairs with wrapped Δψ; sign agreement over 30–150° with the pooled convention; bootstrap; "
      "speed band by the slower end; σ_d from the plan's own estimator on floor seconds; +1 h control from t + 3600 s; lag scan on one "
      "common pair set; turns-in-place event rule; V3 heading; point estimates decide).")
    w("- **Amendment 2 (after a single-job smoke test, before any pooled number):** step B's u1 is missing on ~35 % of seconds "
      "(< 3 fixes in 0.75 s), so 'no WISER' if any second lacks u1 left the turns-in-place quantity nearly uncountable; an event now "
      "needs u1 on at least half of its seconds, and 'missed' = every available u1 < 5.26 in/s.")
    w("- **Amendment 3 (after the pooled results of the first full run `imu_turn_vs_heading_20261004_1007`; no gate quantity changes):** "
      "(i) times in the bulk CSVs are stored as integer ms (they had been rounded to 5–6 significant digits; nothing computed changed); "
      "(ii) the zone of an IMU-ok second in the turns-in-place denominators is the median raw fix of [s − 1, s + 2) instead of [s, s + 1), "
      "matching the shortest event window (first-run calm missed/h: field 46.1, house 24.3, all 27.4; rain all 20.1); "
      "(iii) the declared post-hoc caveat on the noise ceiling (§10).")
    for am in meta.get("amendments_after", []):
        w(f"- {am}")
    w("")
    w("## Caveats\n")
    w("- Clean seconds are open-field and ≥ 8 anchors: agreement in the houses is not measured; slow walking (< 10 in/s) is excluded by construction.")
    w("- The gyro measures the **head**; head yaw includes scanning, and the 1-s mean removes only part of it. The tag is on the head, "
      "so WISER's path is the head's path too; the comparison is between the head's travel direction and its yaw.")
    w("- The gyro sign convention (+ = counter-clockwise from above) rests on make_imu's assumption about the undocumented CE64 IMU chip "
      "(right-hand-rule rates on the accelerometer axes; calibration pilot §M4). A sign of b therefore fixes the *relation* between WISER and the gyro; "
      "absolute left/right needs one video event with a known turn direction.")
    w("- The M4 test of the calibration pilot (Spearman ρ 0.17–0.32) used 2-s windows of 1-s medians without the clean-second filter and "
      "the 10-in/s heading rule; it is not the same estimator and is not superseded by this step.\n")
    w("## Outputs and rerun\n")
    w(f"- Bulk `{out}`: `tables/` (pairs.csv.gz = every pair with Δθ raw / V3, Δψ, +1 h and lag-shifted Δψ; fits.csv; bootstrap_ci.csv; "
      "sign_agreement.csv; confusion_gate.csv; lag_scan.csv; in_place_turns.csv.gz (every event), in_place_rates*.csv, "
      "imu_ok_seconds_by_zone.csv; floor_displacements.csv.gz, heading_noise_floor.csv; periods_info.csv), `summary.json`, "
      "`input_provenance.json`, `log.txt`, `figures/`.")
    w(f"- Pointer `results/{cfg['_cohort']}/wiser_baseline/reports/run_manifest_imu_turn_vs_heading_{cfg['_cohort']}.json`; config `decision` block.")
    w(f"- Rerun: `python {DRIVER} --cohort {cfg['_cohort']} --workers 6`; re-aggregate: `python {DRIVER} --report-only <run_dir>`; "
      f"self-test: `python {DRIVER} --selftest`.")
    return "\n".join(L) + "\n"


def reading(A: dict) -> list:
    FT, dec, gate, ctrl, cfg = A["FT"], A["dec"], A["gate"], A["ctrl"], A["cfg"]
    gc = cfg["gate"]
    out = []
    rain = _fit_row(FT, group="W", set="rain", W=gc["W_s"])
    w1 = _fit_row(FT, group="W", set="calm", W=1)
    w3 = _fit_row(FT, group="W", set="calm", W=3)
    out.append(f"Gate (calm, W = 2 s): b {_ci(gate, 'b0', 2, True)}, R² {_ci(gate, 'R2_0', 2)} → **{dec['verdict']}** "
               f"({'slope in range' if dec['pass_abs_b'] else 'slope out of range'}, {'R² ≥ 0.5' if dec['pass_R2'] else 'R² < 0.5'}). "
               f"W = 1 s: b {_f(w1.get('b0'), 2, True)}, R² {_f(w1.get('R2_0'), 2)}; W = 3 s: b {_f(w3.get('b0'), 2, True)}, R² {_f(w3.get('R2_0'), 2)}; "
               f"rain W = 2 s: b {_f(rain.get('b0'), 2, True)}, R² {_f(rain.get('R2_0'), 2)}.")
    out.append(f"+1 h control: b {_f(ctrl['b0'], 3, True)}, R² {_f(ctrl['R2_0'], 3)} — the pipeline does not manufacture agreement"
               + (" (control valid)." if not dec["control_invalid"] else "; **the control fails, the analysis is invalid**."))
    ce = gate.get("ceiling_R2")
    v3 = _fit_row(FT, group="v3", set="calm", W=gc["W_s"])
    if ce is not None and np.isfinite(ce):
        out.append(f"The plan's noise ceiling (WISER noise as measured on certified-still seconds, σ_d {_f(A['sigd']['calm']['sigma_d_in'], 2)} in) "
                   f"would allow R² ≈ {_f(ce, 2)}; the observed R² is {_f(gate['R2_0'], 2)}. **Post hoc (declared, no verdict uses it):** the "
                   f"same kind of pairs with the V3-track heading reach R² {_f(v3.get('R2_0'), 2)} (median |r| {_f(v3.get('med_r'), 1)}° vs "
                   f"{_f(gate['med_r'], 1)}°). Still-floor noise could not produce that gain, so the raw-median heading noise *during locomotion* "
                   "is well above the still floor and the ceiling is optimistic. Both the raw-median and the V3 heading also fall short in "
                   f"slope (b {_f(gate['b0'], 2, True)} / {_f(v3.get('b0'), 2, True)}), and noise in Δθ does not bias b. The shortfall is "
                   "consistent with part of the head-turn variance not being path turn (scanning, head–body decoupling, the head leading the "
                   "path; see the lag scan). The window kernels also differ (θ: displacement between two 1-s medians; ψ̄: 1-s mean).")
    an = FT[(FT["group"] == "animal") & (FT["set"] == "calm")]
    npos = int((an["b0"] > 0).sum())
    nsig = int(((an["b0_lo"] > 0) | (an["b0_hi"] < 0)).sum())
    nsa = int((an["sign_agree_lo"] > 0.5).sum())
    out.append(f"Sign per animal (calm): b > 0 on {npos}/{len(an)} animals, CI excluding 0 on {nsig}/{len(an)}; turn-sign agreement under the "
               f"pooled convention has its CI above 50 % on {nsa}/{len(an)} animals. "
               + ("All agree with the pooled convention" if npos in (0, len(an)) else "The animals disagree on the sign")
               + f" ({dec['convention']}). This answers the per-animal handedness question V6 left open (SF07 'mirrored' on a noise-level LLR): "
               + ("one relation for all animals, the normal (right-handed) one, given make_imu's gyro sign convention."
                  if npos == len(an) and nsa == len(an) else "only where the CIs exclude chance."))
    out.append(f"Turn-sign agreement for clear head turns (30–150°): {_f(100 * gate['sign_agree'], 1)} % (chance 50 %); "
               f"scanning tail |r| > 30°: {_f(100 * gate['tail'], 1)} % of pairs.")
    IP = A["IP"]
    rc = IP[(IP["set"] == "calm") & (IP["zone"] == "all")].iloc[0]
    rf = IP[(IP["set"] == "calm") & (IP["zone"] == "field")].iloc[0]
    rh = IP[(IP["set"] == "calm") & (IP["zone"] == "house")].iloc[0]
    rr = IP[(IP["set"] == "rain") & (IP["zone"] == "all")].iloc[0]
    out.append(f"Turns in place that WISER misses (gyro ≥ 90° in 3 s, every available u1 < 5.26 in/s): calm {_f(rc['missed_per_h'], 1)} per IMU-ok hour "
               f"(open field {_f(rf['missed_per_h'], 1)}, house {_f(rh['missed_per_h'], 1)}), rain {_f(rr['missed_per_h'], 1)}; "
               f"{_f(100 * rc['share_missed'], 0)} % of the calm turn events with WISER coverage happen without WISER speed above its noise floor.")
    LS = A["LS"]
    r0 = LS.loc[np.isclose(LS["delta_s"], 0.0), "R2_0"]
    rp = LS["R2_0"].max()
    out.append(f"Lag scan: R² peaks at δ = {_f(dec['lag_peak_s'], 1, True)} s (R² {_f(rp, 3)} vs {_f(r0.iloc[0] if len(r0) else np.nan, 3)} at 0; τ* applied). "
               + ("No residual lag." if dec["lag_peak_s"] is not None and abs(dec["lag_peak_s"]) <= 0.1 + 1e-9
                  else ("The gyro read earlier matches better, i.e. the WISER path turn lags the head turn. τ* was fitted on speed, so this "
                        "is either a heading-specific lag such as the head turning before the body, or a residual clock offset (not separable "
                        "here). It is reported, not acted on; even at the peak the gate is not met.")
                  if dec["lag_peak_s"] is not None and dec["lag_peak_s"] < 0 else "The WISER path turn leads the gyro (reported, not acted on)."))
    out.append(f"V3-track heading (calm, W = 2 s; reported, not gated): b {_ci(v3, 'b0', 2, True)}, R² {_ci(v3, 'R2_0', 2)}, "
               f"sign agreement {_f(100 * v3.get('sign_agree', np.nan), 1)} % → the gate's bars would not be met with it either "
               f"(|b| {'≥' if abs(v3.get('b0', 0)) >= gc['abs_b_range'][0] else '<'} {gc['abs_b_range'][0]}, R² {'≥' if v3.get('R2_0', 0) >= gc['min_R2'] else '<'} {gc['min_R2']}).")
    lo_b, hi_b = gc["abs_b_range"]
    meet = an[(an["b0"].abs() >= lo_b) & (an["b0"].abs() <= hi_b) & (an["R2_0"] >= gc["min_R2"])]
    if len(meet):
        out.append("Per animal (calm, reported only; the pooled gate decides): the bars are met by "
                   + ", ".join(f"{r['animal']} (b {_f(r['b0'], 2, True)}, R² {_f(r['R2_0'], 2)}, {int(r['n_fit'])} pairs)" for _, r in meet.iterrows())
                   + f"; not by the other {len(an) - len(meet)}.")
    if dec["verdict"] == "PASS":
        out.append("Consequence (plan): the turn annotation is usable during locomotion → build and test V7 (turn-rate-aided smoother) like V3/V6.")
    elif dec["verdict"] == "FAIL":
        out.append("Consequence (plan): head turns stay a head-behaviour signal only; V3 remains the default implanted-animal track, B2 the baseline.")
    return out


def publish(A: dict, out: Path, fh=None, amendments_after: list | None = None) -> None:
    import shutil
    cfg = A["cfg"]
    cohort = cfg["_cohort"]
    write_tables(A)
    fdir = output_paths.figure_dir(cohort, DIRECTION)
    figs = make_figures(A, fdir)
    (out / "figures").mkdir(exist_ok=True)
    for f in figs.values():
        shutil.copy2(fdir / f, out / "figures" / f)
    rdir = output_paths.report_dir(cohort, DIRECTION)
    rep = rdir / f"{STEM}_{cohort}.md"
    dec = A["dec"]
    meta = {"cohort": cohort, "direction": DIRECTION, "analysis": NAME, "report": rep.name, "driver": DRIVER,
            "config": Path(cfg["_path"]).relative_to(REPO).as_posix(), "plan": PLAN, "git_commit": C.git_commit(), "figures": sorted(figs.values()),
            "speed_proxy_run": cfg["speed_proxy_run"], "v3_run": cfg["v3_run"], "audit_run": cfg["audit_run"],
            "verdict": dec["verdict"], "b": dec["b"], "R2": dec["R2"], "control_R2": dec["control_R2"],
            "amendments_after": amendments_after or []}
    rep.write_text(render_report(A, out, figs, meta), encoding="utf-8")
    output_paths.write_run_manifest(out, out, **{k: v for k, v in meta.items() if k != "amendments_after"})
    mp = rdir / f"run_manifest_imu_turn_vs_heading_{cohort}.json"
    mp.write_text(json.dumps({"run_dir": str(out.resolve()), **{k: v for k, v in meta.items() if k != "amendments_after"}}, indent=2, default=_jd) + "\n",
                  encoding="utf-8")
    cp = Path(cfg["_path"])
    cj = json.loads(cp.read_text(encoding="utf-8"))
    cj["decision"] = {**json.loads(json.dumps(dec, default=_jd)), "run_dir": str(out), "report": f"results/{cohort}/wiser_baseline/reports/{rep.name}",
                      "decided_local": pd.Timestamp.now(tz=cfg["tz"]).strftime("%Y-%m-%d %H:%M:%S")}
    cp.write_text(json.dumps(cj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log_to(fh, f"report {rep}\nmanifest {mp}\ndecision written into {cp.name}")


# ====================================================================================================== selftest
def _synth(seed: int = 7, dur_s: float = 8000.0, sigma_in: float = 2.0, rate_sd: float = 60.0, mirror: bool = False,
           fix_dt: float = 0.2) -> dict:
    """Synthetic head track: still bouts (30 %; each with one planted in-place turn of 120 deg in 2 s) and walking bouts at
    12-30 in/s whose turn rate is piecewise constant (0.5-2.5 s segments, N(0, rate_sd) clipped at +-150 deg/s). Head yaw =
    path heading + 25 deg sin(2 pi 1.5 t) (scanning) + 2 deg/min bias. Fixes every fix_dt s, offset so that no fix falls on
    a window boundary (exactly 1 / fix_dt fixes per 1-s window), Gaussian noise sigma_in per axis; mirror flips WISER y. Planted: a 170 deg turn on [3005.5, 3006.5) crossing
    +-180 deg in WISER (100 -> 270 deg), IMU not QC-ok on [5000, 5010), seconds [1000, 1010) not clean."""
    rng = np.random.default_rng(seed)
    T0 = 1.7e9
    dt = 0.01
    g = np.arange(0.0, dur_s, dt)
    n = len(g)
    rate = np.zeros(n)
    speed = np.zeros(n)
    still = np.zeros(n, bool)
    planted = []
    tt = 0.0
    while tt < dur_s:
        a = int(tt / dt)
        if rng.random() < 0.3:
            d = rng.uniform(15.0, 40.0)
            b = min(int((tt + d) / dt), n)
            still[a:b] = True
            tm = tt + d / 2.0
            ia, ib = int(tm / dt), int((tm + 2.0) / dt)
            if ib < b - 300 and not (2950 < tm < 3050):
                rate[ia:ib] = rng.choice([-60.0, 60.0])
                planted.append((tm, tm + 2.0))
        else:
            d = rng.uniform(20.0, 60.0)
            b = min(int((tt + d) / dt), n)
            speed[a:b] = rng.uniform(12.0, 30.0)
            k = a
            while k < b:
                L = max(1, int(rng.uniform(0.5, 2.5) / dt))
                rate[k:min(k + L, b)] = float(np.clip(rng.normal(0.0, rate_sd), -150.0, 150.0))
                k += L
        tt += d
    # planted 170-deg turn: still [2980, 2990) rotating slowly to heading 100 deg, then walk 20 in/s on [2990, 3020)
    i80, i90, i55, i65, i20 = (int(round(x / dt)) for x in (2980.0, 2990.0, 3005.5, 3006.5, 3020.0))
    rate[i80:i20] = 0.0
    speed[i80:i90] = 0.0
    still[i80:i90] = True
    speed[i90:i20] = 20.0
    still[i90:i20] = False
    phi80 = float(np.sum(rate[:i80]) * dt)
    need = float(wrap(100.0 - phi80))
    rate[i80:i90] = need / 10.0
    rate[i55:i65] = 170.0
    planted = [(a_, b_) for a_, b_ in planted if not (2975 < a_ < 3025)]
    phi = np.cumsum(rate) * dt
    pos = np.cumsum(np.column_stack([speed * np.cos(np.radians(phi)), speed * np.sin(np.radians(phi))]), axis=0) * dt + 1000.0
    off = 0.05 if abs(fix_dt - 0.2) < 1e-9 else 0.25 * fix_dt
    tf = off + fix_dt * np.arange(int((dur_s - 0.1) / fix_dt))
    truth = np.column_stack([np.interp(tf, g, pos[:, 0]), np.interp(tf, g, pos[:, 1])])
    z = truth + rng.normal(0.0, sigma_in, truth.shape)
    if mirror:
        z[:, 1] = -z[:, 1]
    u = np.arange(0.0, dur_s, 0.02)

    def yaw(x):
        return np.interp(x, g, phi) + 25.0 * np.sin(2 * np.pi * 1.5 * x) + (2.0 / 60.0) * x
    turn = (yaw(u + 0.01) - yaw(u - 0.01)) / 0.02
    valid = ~((u >= 5000.0) & (u < 5010.0))
    secs = np.arange(0, int(dur_s), dtype=np.int64)
    clean = ~((secs >= 1000) & (secs < 1010))
    st_s = np.array([still[int(s / dt):min(int((s + 1) / dt), n)].all() for s in secs])
    floor = np.array([st_s[max(0, s - 2):s + 3].all() for s in range(len(secs))])
    return {"T0": T0, "t": tf + T0, "z": z, "u": u + T0, "turn": turn, "valid": valid, "secs": secs + int(T0), "clean": clean,
            "floor": floor, "planted": [(a_ + T0, b_ + T0) for a_, b_ in planted], "sigma_in": sigma_in,
            "n_per_window": int(round(1.0 / fix_dt))}


def _synth_run(S: dict, cfg: dict) -> dict:
    hc, pc = cfg["heading"], cfg["pairs"]
    lo_s, hi_s = int(S["secs"][0]), int(S["secs"][-1]) + 1
    g = lo_s + pc["grid_s"] * np.arange(int(round((hi_s - lo_s) / pc["grid_s"])) + 1)
    H = headings(S["t"], S["z"], g, hc)
    sup = support_clean(g, S["secs"], S["clean"])
    with np.errstate(invalid="ignore"):
        ok = sup & np.isfinite(H["spd"]) & (H["spd"] >= hc["min_speed_inps"])
    gyro = Gyro(S["u"], S["turn"], S["valid"], 50.0, 1.5)
    P = build_pairs(g, H, H, ok, ok, gyro, pc, cfg["lag_scan_s"], 3600.0)
    P["blk"] = ((P["c"] - lo_s) // 600).astype(int)
    fl = S["secs"][S["floor"]]
    jf = 2 * (fl - lo_s) + 1
    dfl = H["d"][jf]
    dfl = dfl[np.isfinite(dfl).all(axis=1)]
    sig_d = float(np.median(np.hypot(dfl[:, 0], dfl[:, 1])) / RAYLEIGH_MED)
    return {"g": g, "H": H, "ok": ok, "sup": sup, "gyro": gyro, "P": P, "sig_d": sig_d, "lo_s": lo_s, "hi_s": hi_s}


def selftest() -> int:
    fails = []

    def check(name, cond, info=""):
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {info}", flush=True)
        if not cond:
            fails.append(name)
    cfg = load_cfg("2026c")
    mf = cfg["pairs"]["max_abs_dpsi_fit_deg"]
    # ---- unit checks
    wv = wrap([179.0, 181.0, -181.0, 360.0, -180.0, 540.0])
    check("wrap() maps into [-180, 180)", np.allclose(wv, [179, -179, 179, 0, -180, -180]), str(wv))
    xx = np.linspace(-100, 100, 200)
    r = fit_stats(xx, 2.0 * xx + 0.0, np.zeros(200), 0, 1, max_fit=1e9)
    check("fit_stats on y = 2x: b = 2, R2 = 1, b1 = 2, R2_1 = 1", abs(r["b0"] - 2) < 1e-9 and abs(r["R2_0"] - 1) < 1e-9
          and abs(r["b1"] - 2) < 1e-9 and abs(r["R2_1"] - 1) < 1e-9, f"b {r['b0']:.4f} R2 {r['R2_0']:.4f}")
    r = fit_stats(xx, xx, np.zeros(200), 0, 1, max_fit=1e9)
    rm = fit_stats(xx, -xx, np.zeros(200), 0, 1, max_fit=1e9)
    check("circular correlation: y = x -> +1, y = -x -> -1", abs(r["rho_c"] - 1) < 1e-9 and abs(rm["rho_c"] + 1) < 1e-9,
          f"{r['rho_c']:.4f} / {rm['rho_c']:.4f}")
    secs = np.arange(100, 120)
    cl = np.ones(20, bool)
    cl[10] = False
    gg = np.array([101.0, 109.0, 109.5, 110.0, 111.0, 111.5, 112.0])
    check("support_clean: seconds overlapping [g-1, g+1) must be clean",
          support_clean(gg, secs, cl).tolist() == [True, True, False, False, False, False, True], str(support_clean(gg, secs, cl).tolist()))
    ue = np.array([1.0, np.nan, 1.0, np.nan, np.nan, np.nan, 1.0, 1.0, 6.0, 1.0])
    Ee = pd.DataFrame({"t0": [0.2, 3.2, 6.1], "t1": [3.2, 6.2, 9.1]})     # seconds 0-3 | 3-6 | 6-9
    ce, _ = classify_events(Ee, np.arange(10), ue, 5.26)
    check("coverage rule (Amendment 2): missed / no_wiser / wiser_moving", ce == ["missed", "no_wiser", "wiser_moving"], str(ce))
    # ---- main synthetic
    S = _synth()
    R = _synth_run(S, cfg)
    P = R["P"]
    m2 = P[(P["W"] == 2) & P["ok_raw"]]
    F = fit_stats(m2["dpsi"], m2["dtheta"], m2["blk"], 200, 1, mf, 30.0, 1.0)
    check("W = 2: b recovered within 0.05 of +1", abs(F["b0"] - 1.0) <= 0.05, f"b {F['b0']:.3f} [{F['b0_lo']:.3f}, {F['b0_hi']:.3f}], n {F['n_fit']}")
    check("bootstrap CI contains the point estimate", F["b0_lo"] <= F["b0"] <= F["b0_hi"] and F["R2_0_lo"] <= F["R2_0"] <= F["R2_0_hi"])
    check("turn-sign agreement >= 0.9", F["sign_agree"] >= 0.9, f"{F['sign_agree']:.3f}")
    Fc = fit_stats(m2["dpsi_ctrl"], m2["dtheta"], m2["blk"], 200, 1, mf, 30.0, 1.0)
    check("+1 h control: |b| < 0.1 and R2 < 0.05", abs(Fc["b0"]) < 0.1 and Fc["R2_0"] < 0.05, f"b {Fc['b0']:+.3f} R2 {Fc['R2_0']:.3f}, n {Fc['n_fit']}")
    lr = []
    common = m2[np.isfinite(m2[[lag_col(d) for d in cfg["lag_scan_s"]]]).all(axis=1)]
    for d in cfg["lag_scan_s"]:
        rr = fit_stats(common[lag_col(d)], common["dtheta"], common["blk"], 0, 1, mf)
        lr.append(rr["R2_0"])
    dpk = cfg["lag_scan_s"][int(np.nanargmax(lr))]
    check("lag scan peaks at 0 +- 0.1 s", abs(dpk) <= 0.1 + 1e-9, f"peak {dpk:+.1f} s, R2 {['%.3f' % x for x in lr]}")
    # planted 170-deg turn (W = 3, c = 3006)
    pw = P[(P["W"] == 3) & (np.abs(P["c"] - (S["T0"] + 3006.0)) < 1e-6)]
    ok170 = len(pw) == 1 and bool(pw["ok_raw"].iloc[0])
    if ok170:
        dth, dps = float(pw["dtheta"].iloc[0]), float(pw["dpsi"].iloc[0])
        rres = float(wrap(dth - F["b0"] * wrap(dps)))
        check("planted 170 deg turn: WISER dtheta wraps to ~ +170", abs(float(wrap(dth - 170.0))) < 15.0, f"dtheta {dth:+.1f}")
        check("planted 170 deg turn: |dpsi| > 150 -> excluded from the fit", abs(dps) > mf, f"dpsi {dps:+.1f}")
        check("planted 170 deg turn: |r| small after wrapping", abs(rres) < 25.0, f"r {rres:+.1f}")
    else:
        check("planted 170 deg turn pair exists", False, f"rows {len(pw)}")
    # QC exclusion and clean rule
    bad_imu = ((P["c"] - P["W"] / 2 - 0.5) < S["T0"] + 5010.0) & ((P["c"] + P["W"] / 2 + 0.5) > S["T0"] + 5000.0)
    check("no pair spans the QC-failed IMU stretch", not bad_imu.any(), f"{int(bad_imu.sum())} pairs")
    hbad = R["ok"] & (R["g"] - 1 < S["T0"] + 1010) & (R["g"] + 1 > S["T0"] + 1000)
    check("no heading with support on unclean seconds", not hbad.any(), f"{int(hbad.sum())} headings")
    # turns in place
    u1, _, _ = SP.scale_speed(S["t"], S["z"], S["secs"], 0.5, 0.375, 3)
    E = turn_events(R["gyro"], R["lo_s"], R["hi_s"], cfg["in_place"])
    cls, _ = classify_events(E, S["secs"], u1, cfg["in_place"]["u1_floor_p95_inps"])
    E["cls"] = cls
    hit = 0
    for a_, b_ in S["planted"]:
        e = E[(E["t0"] <= a_ + 0.05) & (E["t1"] >= b_ - 0.05)]
        hit += int((e["cls"] == "missed").any())
    share = hit / max(len(S["planted"]), 1)
    check("planted in-place turns detected and classified 'missed' (>= 90 %)", share >= 0.9, f"{hit}/{len(S['planted'])}")
    check("walking turns >= 90 deg in 3 s classified 'wiser_moving' exist", (E["cls"] == "wiser_moving").sum() > 0,
          f"{int((E['cls'] == 'wiser_moving').sum())} events")
    # ---- mirrored axes
    Sm = _synth(mirror=True)
    Rm = _synth_run(Sm, cfg)
    mm = Rm["P"][(Rm["P"]["W"] == 2) & Rm["P"]["ok_raw"]]
    Fm = fit_stats(mm["dpsi"], mm["dtheta"], mm["blk"], 0, 1, mf)
    check("mirrored WISER y: b ~ -1 (within 0.05)", abs(Fm["b0"] + 1.0) <= 0.05, f"b {Fm['b0']:+.3f}")
    # ---- noisy synthetic: R2 vs the analytic value from the known noise model (25-Hz fixes, so the spread of the moving
    #      points inside a 1-s window is negligible against the noise and the median's variance is that of n iid normals)
    Sn = _synth(seed=9, sigma_in=12.0, rate_sd=15.0, fix_dt=0.04)
    Rn = _synth_run(Sn, cfg)
    mn = Rn["P"][(Rn["P"]["W"] == 2) & Rn["P"]["ok_raw"]]
    Fn = fit_stats(mn["dpsi"], mn["dtheta"], mn["blk"], 0, 1, mf)
    vn = float(np.var(np.median(np.random.default_rng(0).standard_normal((200000, Sn["n_per_window"])), axis=1)))
    sd_true = Sn["sigma_in"] * math.sqrt(2.0 * vn)
    x, y = mn["dpsi"].to_numpy(float), mn["dtheta"].to_numpy(float)
    an_ = noise_ceiling(x, y, mn["spd1"].to_numpy(float), mn["spd2"].to_numpy(float), np.full(len(mn), sd_true), mf)
    est = noise_ceiling(x, y, mn["spd1"].to_numpy(float), mn["spd2"].to_numpy(float), np.full(len(mn), Rn["sig_d"]), mf)
    check("noisy synthetic: b within 0.05 of +1", abs(Fn["b0"] - 1.0) <= 0.05, f"b {Fn['b0']:.3f}")
    check("noisy synthetic: R2 within 0.05 of the analytic value", abs(Fn["R2_0"] - an_["ceiling_R2"]) <= 0.05,
          f"R2 {Fn['R2_0']:.3f} vs analytic {an_['ceiling_R2']:.3f} (sigma_d {sd_true:.2f} in)")
    check("floor-estimated sigma_d within 10 % of the noise model's", abs(Rn["sig_d"] / sd_true - 1.0) <= 0.10,
          f"{Rn['sig_d']:.2f} vs {sd_true:.2f} in; ceiling {est['ceiling_R2']:.3f}")
    print(f"selftest: {'ALL PASS' if not fails else f'{len(fails)} FAIL: ' + '; '.join(fails)}")
    return 0 if not fails else 1


# ====================================================================================================== main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", default=None)
    ap.add_argument("--config", default=None)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--report-only", default=None, help="re-aggregate and re-render an existing run (no compute)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    if a.report_only:
        out = Path(a.report_only)
        man = json.loads((out / "input_provenance.json").read_text(encoding="utf-8"))
        cohort = a.cohort or out.parent.name
        cfg = load_cfg(cohort, a.config or str(REPO / man["config"]))
        fh = open(out / "log_report.txt", "a", encoding="utf-8")
        A = analyze(out, cfg, fh)
        publish(A, out, fh)
        fh.close()
        return
    cohort = output_paths.resolve_cohort(a.cohort)
    cfg = load_cfg(cohort, a.config)
    workers = min(6, a.workers or int(cfg.get("workers", 6)))
    out = run_compute(cfg, workers)
    fh = open(out / "log.txt", "a", encoding="utf-8")
    A = analyze(out, cfg, fh)
    publish(A, out, fh)
    fh.close()


if __name__ == "__main__":
    main()
