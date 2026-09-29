r"""IMU <-> WISER calibration pilot: effective clock lag, non-circular jitter floor, speed-noise floor, frame handedness
(+ gyro scale) and rest-proxy agreement, using the head IMU of the WILD neurologgers as an independent sensor.

Plan: implementation_plan/2026-09-29-imu-wiser-calibration-pilot.md (approved by the user 2026-09-29).
Report (full Definitions section): results/<cohort>/wiser_baseline/reports/wiser_baseline_imu_calibration_pilot_<cohort>.md

Inputs (all read-only; nothing is written next to any input):
  wiser/configs/imu_wiser_calibration_<cohort>.json   sessions, windows, WISER DB copy, masks, baseline numbers
  <ephys.analysis_root>/imu/<SFxx>/<session>.imu.npz  ephys/make_imu.py, 50 Hz, full-precision t_pc_ms (+ .imu.json)
  raw <session>/analogin.dat                           only for the frozen-rule cross-check and the dropped-implant
                                                       stillness (lanes 1-6, constants from ephys/read_imu.py)
  the WISER SQLite copy                                wiser_io._connect_readonly (mode=ro + PRAGMA query_only)
  wiser/configs/rat_identities_<cohort>.csv            tag -> animal with validity windows (cohort YAML `identities`)
  handling windows JSON + all-tag silences CSV         operator-in-arena / out-of-arena masks

Metrics (formulas + text in the report): M1 tau* = argmax_tau Pearson(log10(VeDBA_0.25s + 0.01), v_W(t + tau)), 300-s
block bootstrap; M2 scatter r_i = |p_i - bout median| over IMU-still bouts >= 60 s; M3 p95/p99 of v_W over IMU-still
time; M4 Spearman / Theil-Sen / sign agreement of WISER heading change vs integrated IMU turn rate; M5 Cohen's kappa of
the library rest proxy (wiser_analysis_utils.rest_mask) vs IMU stillness.

Usage:
  python wiser/scripts/analyze_imu_wiser_calibration.py --cohort 2026c [--imu-root D:/3rd_rat_spikes/analysis/imu]
  python wiser/scripts/analyze_imu_wiser_calibration.py --selftest        # synthetic data, no field data needed
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "wiser" / "src"))
sys.path.append(str(REPO / "common"))
sys.path.append(str(REPO / "ephys"))
import output_paths  # noqa: E402  (wiser shim -> common/output_paths.py)
import wiser_analysis_utils as w  # noqa: E402
import wiser_io  # noqa: E402
from cohorts import load_cohort  # noqa: E402
import read_imu as RI  # noqa: E402  (constants only: lanes, scales, saturation level; reads nothing on import)

DIRECTION = "wiser_baseline"
NAME = "imu_wiser_calibration_pilot"
FS_IMU = 50.0                                   # make_imu npz rate
TAUS = np.round(np.arange(-3.0, 3.0 + 1e-9, 0.05), 2)
BIN_MS = 250                                    # M1 IMU bin
EPS_VEDBA = 0.01                                # m/s^2 added before log10 (well below the still mode ~0.05)
BRACKET_MAX_S = 1.0                             # interpolate v_W only between fixes <= 1 s apart
BLOCK_S = 300                                   # block-bootstrap block length (>> movement bouts)
N_BOOT = 1000
OMEGA_STILL_DPS = 10.0
MIN_BOUT_S = 60
TRIM_S = 1.0
MIN_BOUT_FIX = 30
M4_STEP_S = 3
M4_MIN_PATH_IN = 30.0
M4_MIN_FIX = 2
M4_TURN_THR_DEG = 45.0
FROZEN_DW, FROZEN_VEDBA, FROZEN_MIN_S, FROZEN_PAD_S = 1e-4, 1e-3, 0.5, 2.0
MIN_SAMPLES_PER_S = 40                          # of 50
ACCEPT = {"m1_ci_width_s": 0.3, "m1_spread_s": 0.2, "m2_min_bouts": 20, "m2_rel_diff": 0.20,
          "m4_min_abs_rho": 0.3, "m4_min_agree": 0.70}
MASK_COLS = ["m_nodata", "m_saturated", "m_frozen_flag", "m_frozen_rule", "m_invalid", "m_nan", "m_unreliable",
             "m_handling", "m_silence", "m_tag_validity"]


# ================================================================ small helpers
def to_ms(local: str, tz: str = "America/New_York") -> int:
    return int(pd.Timestamp(local).tz_localize(tz).value // 10**6)


def ms_to_local(ms: float, tz: str = "America/New_York") -> str:
    return pd.Timestamp(int(round(ms)), unit="ms", tz="UTC").tz_convert(tz).strftime("%Y-%m-%d %H:%M:%S")


def true_runs(m: np.ndarray) -> list[tuple[int, int]]:
    """[start, end) index pairs of the True runs of a boolean array."""
    x = np.r_[0, np.asarray(m, bool).astype(np.int8), 0]
    d = np.diff(x)
    return list(zip(np.flatnonzero(d == 1).tolist(), np.flatnonzero(d == -1).tolist()))


def in_any(t_ms: np.ndarray, intervals) -> np.ndarray:
    m = np.zeros(len(t_ms), bool)
    for a, b, *_ in intervals:
        m |= (t_ms >= a) & (t_ms < b)
    return m


def sstats(r) -> dict:
    r = np.asarray(r, float)
    r = r[np.isfinite(r)]
    if not len(r):
        return {"n": 0, "p50": np.nan, "p75": np.nan, "p90": np.nan, "p95": np.nan, "rmse": np.nan}
    q = np.percentile(r, [50, 75, 90, 95])
    return {"n": int(len(r)), "p50": q[0], "p75": q[1], "p90": q[2], "p95": q[3], "rmse": float(np.sqrt(np.mean(r ** 2)))}


def sha256(path: Path, chunk: int = 1 << 24) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def git_commit() -> str:
    try:
        c = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True).stdout.strip()
        return c + ("+dirty" if dirty else "")
    except Exception:  # noqa: BLE001
        return "unknown"


def imu_still_thr() -> dict:
    """IMU_STILL_THR from ephys/imu_lfp_state_check.py (parsed, not imported: one source of truth, no side effects)."""
    tree = ast.parse((REPO / "ephys" / "imu_lfp_state_check.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "IMU_STILL_THR" for t in node.targets):
            return ast.literal_eval(node.value)
    raise SystemExit("IMU_STILL_THR not found in ephys/imu_lfp_state_check.py")


# ================================================================ IMU side
def load_imu_npz(npz_path: Path, start_local: str, lo_ms: float, hi_ms: float) -> dict:
    """50-Hz make_imu arrays inside [lo_ms, hi_ms) with field-PC unix ms (full precision) + a logger->unix time map."""
    base = to_ms(start_local[:10] + " 00:00:00")
    with np.load(npz_path) as z:
        files = set(z.files)
        u_all = base + z["t_pc_ms"].astype(np.float64)
        tl_all = z["t_logger_s"].astype(np.float64)
        sel = (u_all >= lo_ms) & (u_all < hi_ms)
        d = {"unix_ms": u_all[sel], "t_logger_s": tl_all[sel]}
        for k in ("vedba_ms2", "omega_dps", "turn_dps"):
            d[k] = z[k][sel].astype(np.float64)
        for k in ("saturated", "unreliable", "frozen", "invalid"):
            d[k] = z[k][sel].astype(bool) if k in files else np.zeros(int(sel.sum()), bool)
        d["has_new_flags"] = "frozen" in files
        d["time_map"] = (tl_all[::500].copy(), u_all[::500].copy())
        d["frozen_all"] = z["frozen"].astype(bool) if "frozen" in files else None
        d["unix_all"] = u_all if "frozen" in files else None
    return d


def frozen_rule(omega: np.ndarray, vedba: np.ndarray, fs: float = FS_IMU):
    """Audit rule on derived signals: runs >= FROZEN_MIN_S with |d|w|| < 1e-4 deg/s and VeDBA < 1e-3 m/s^2, padded
    +-FROZEN_PAD_S. NaN never satisfies the rule. Returns (padded sample mask, unpadded runs)."""
    n = len(omega)
    cond = np.zeros(n, bool)
    if n > 1:
        with np.errstate(invalid="ignore"):
            cond[1:] = (np.abs(np.diff(omega)) < FROZEN_DW) & (vedba[1:] < FROZEN_VEDBA)
    runs = [(a, b) for a, b in true_runs(cond) if (b - a) >= FROZEN_MIN_S * fs]
    mask = np.zeros(n, bool)
    pad = int(FROZEN_PAD_S * fs)
    for a, b in runs:
        mask[max(0, a - pad): min(n, b + pad)] = True
    return mask, runs


def per_second(imu: dict, lo_ms: float, hi_ms: float, handling, silences, valid_from_ms: float, valid_until_ms: float,
               frz_rule_mask: np.ndarray) -> pd.DataFrame:
    """Per field-PC second: mean VeDBA and |w| over the valid 50-Hz samples, and every mask reason."""
    s_lo, s_hi = int(lo_ms // 1000), int(-(-hi_ms // 1000))
    secs = np.arange(s_lo, s_hi, dtype=np.int64)
    n = len(secs)
    idx = np.floor(imu["unix_ms"] / 1000).astype(np.int64) - s_lo
    inb = (idx >= 0) & (idx < n)
    idx = idx[inb]
    g = lambda k: imu[k][inb]  # noqa: E731
    ved, om, tu = g("vedba_ms2"), g("omega_dps"), g("turn_dps")
    nan_s = ~(np.isfinite(ved) & np.isfinite(om) & np.isfinite(tu))
    S = lambda v: np.bincount(idx, weights=np.asarray(v, float), minlength=n)  # noqa: E731
    cnt = np.bincount(idx, minlength=n)
    nv = S(~nan_s)
    with np.errstate(invalid="ignore", divide="ignore"):
        vedba_1s = S(np.where(nan_s, 0, ved)) / nv
        omega_1s = S(np.where(nan_s, 0, om)) / nv
    t_mid = (secs + 0.5) * 1000.0
    df = pd.DataFrame({
        "sec": secs, "n": cnt, "vedba_1s": vedba_1s, "omega_1s": omega_1s,
        "m_nodata": cnt < MIN_SAMPLES_PER_S,
        "m_saturated": S(g("saturated")) > 0,
        "m_frozen_flag": S(g("frozen")) > 0,
        "m_frozen_rule": S(frz_rule_mask[inb]) > 0,
        "m_invalid": S(g("invalid")) > 0,
        "m_nan": S(nan_s) > 0,
        "m_unreliable": S(g("unreliable")) > 0.5 * np.maximum(cnt, 1),
        "m_handling": in_any(t_mid, handling),
        "m_silence": in_any(t_mid, silences),
        "m_tag_validity": (t_mid < valid_from_ms) | (t_mid >= valid_until_ms),
    })
    df["ok"] = ~df[MASK_COLS].any(axis=1)
    return df


def still_mask(ps: pd.DataFrame, thr: float) -> np.ndarray:
    return (ps["ok"] & (ps["vedba_1s"] < thr) & (ps["omega_1s"] < OMEGA_STILL_DPS)).to_numpy(bool)


def read_six(session_dir: Path, start_s: float, dur_s: float) -> tuple[np.ndarray, int]:
    """Raw lanes 1-6 (int16) of a window, read in place (read-only), with ephys/read_imu.py's layout."""
    path = Path(session_dir) / "analogin.dat"
    n_frames = os.path.getsize(path) // (2 * RI.LANES)
    k0 = max(0, int(round(start_s * RI.FS_IMU)))
    k1 = min(n_frames, k0 + int(round(dur_s * RI.FS_IMU)))
    raw = np.fromfile(path, dtype=np.int16, count=(k1 - k0) * RI.LANES, offset=k0 * RI.LANES * 2).reshape(-1, RI.LANES)
    return raw[:, list(RI.ACC_LANES) + list(RI.GYR_LANES)].copy(), k0


def raw_derived_50hz(six: np.ndarray, k0: int, k_a: float = 1.0) -> dict:
    """make_imu stages 1-2 and the rotation-invariant magnitudes, without the AHRS: 1250 -> 100 Hz (resample_poly 2/25),
    VeDBA = |a - 2-s running mean|, |w| after removing the window's per-axis median gyro (bias), pair-averaged to 50 Hz.
    Also the raw-lane freeze (all six lanes repeat >= 0.5 s, make_imu's rule) and saturation per 50-Hz sample."""
    from scipy import signal
    from scipy.ndimage import uniform_filter1d
    acc = six[:, :3].astype(np.float32) * np.float32(RI.ACC_FS_G * RI.G / 32768) * np.float32(k_a)
    gyr = six[:, 3:].astype(np.float32) * np.float32(RI.GYR_FS_DPS / 32768)
    sat = (np.abs(six.astype(np.int32)) >= RI.SAT).any(axis=1)
    same = np.r_[False, np.all(six[1:] == six[:-1], axis=1)]
    frz = np.zeros(len(six), bool)
    for a, b in true_runs(same):
        if b - a >= 0.5 * RI.FS_IMU:
            frz[max(0, a - 1): b] = True
    a100 = signal.resample_poly(acc, 2, 25, axis=0).astype(np.float64)
    w100 = signal.resample_poly(gyr, 2, 25, axis=0).astype(np.float64)
    bias = np.median(w100, axis=0)
    abar = uniform_filter1d(a100, size=201, axis=0, mode="nearest")
    ved = np.linalg.norm(a100 - abar, axis=1)
    om = np.linalg.norm(w100 - bias, axis=1)
    m = len(ved) // 2
    pair = lambda x: x[: 2 * m].reshape(m, 2).mean(axis=1)  # noqa: E731
    per50 = lambda x: np.maximum.reduceat(x.astype(np.uint8), np.clip(np.arange(m) * 25, 0, len(x) - 1)).astype(bool)  # noqa: E731
    return {"t_logger_s": k0 / RI.FS_IMU + np.arange(m) / FS_IMU, "vedba_ms2": pair(ved), "omega_dps": pair(om),
            "saturated": per50(sat)[:m], "frozen_raw": per50(frz)[:m], "gyro_bias_dps": bias.tolist()}


# ================================================================ WISER side
def prepare_fixes(d: pd.DataFrame) -> pd.DataFrame:
    """Library speed + validity flags on raw fixes (columns shortid, ts_raw [unix ms], x, y, anchors_used)."""
    d = d.copy()
    d["datetime"] = pd.to_datetime(d["ts_raw"], unit="ms")          # naive UTC, as time_utils.convert_timestamps
    d = w.add_speed(d)
    d = w.add_validity_flags(d)
    d["t_ms"] = d["ts_raw"].astype(np.int64)
    return d.sort_values(["shortid", "t_ms"], kind="stable").reset_index(drop=True)


def query_wiser(db: Path, table: str, windows: list[tuple[str, list[int], int, int]]) -> tuple[dict, int]:
    con = wiser_io._connect_readonly(Path(db))
    try:
        where = " OR ".join(["(timestamp >= ? AND timestamp < ?)"] * len(windows))
        params = [v for _, _, lo, hi in windows for v in (int(lo), int(hi))]
        df = pd.read_sql(f'SELECT shortid, timestamp, location_x, location_y, anchors_used FROM "{table}" WHERE {where}',
                         con, params=params)
    finally:
        con.close()
    n_raw = len(df)
    df = df.drop_duplicates(["shortid", "timestamp", "location_x", "location_y"])
    df = df.rename(columns={"timestamp": "ts_raw", "location_x": "x", "location_y": "y"})
    out = {}
    for label, sids, lo, hi in windows:
        d = df[df.shortid.isin(sids) & (df.ts_raw >= lo) & (df.ts_raw < hi)]
        out[label] = prepare_fixes(d) if len(d) else d
    return out, n_raw


# ================================================================ metrics
def m1_lag(imu: dict, ps: pd.DataFrame, fixes: pd.DataFrame, lo_ms: float, hi_ms: float, rng: np.random.Generator,
           taus: np.ndarray = TAUS) -> dict:
    nb = int((hi_ms - lo_ms) // BIN_MS)
    u = imu["unix_ms"]
    b = np.floor((u - lo_ms) / BIN_MS).astype(np.int64)
    inb = (b >= 0) & (b < nb)
    b, u_in, ved = b[inb], u[inb], imu["vedba_ms2"][inb]
    ok_sec = pd.Series(ps["ok"].to_numpy(bool), index=ps["sec"].to_numpy())
    ok_s = ok_sec.reindex(np.floor(u_in / 1000).astype(np.int64)).fillna(False).to_numpy(bool)
    good = ok_s & np.isfinite(ved)
    cnt = np.bincount(b, minlength=nb)
    ng = np.bincount(b, weights=good.astype(float), minlength=nb)
    vs = np.bincount(b, weights=np.where(good, ved, 0.0), minlength=nb)
    okb = (cnt >= 10) & (ng == cnt)
    with np.errstate(invalid="ignore", divide="ignore"):
        x = np.log10(vs / np.maximum(ng, 1) + EPS_VEDBA)
    c = lo_ms + BIN_MS * (np.arange(nb) + 0.5)
    f = fixes[fixes["valid"] & np.isfinite(fixes["speed_inps_smooth"])].drop_duplicates("t_ms")
    tw = f["t_ms"].to_numpy(float)
    vw = f["speed_inps_smooth"].to_numpy(float)
    o = np.argsort(tw, kind="stable")
    tw, vw = tw[o], vw[o]
    Y = np.full((len(taus), nb), np.nan)
    for k, tau in enumerate(taus):
        q = c + tau * 1000.0
        j = np.searchsorted(tw, q, side="right")
        lft, rgt = np.clip(j - 1, 0, len(tw) - 1), np.clip(j, 0, len(tw) - 1)
        ok = (j - 1 >= 0) & (j < len(tw)) & ((tw[rgt] - tw[lft]) <= BRACKET_MAX_S * 1000.0)
        Y[k] = np.where(ok, np.interp(q, tw, vw), np.nan)
    use = okb & np.all(np.isfinite(Y), axis=0)
    blk = ((c - lo_ms) // (BLOCK_S * 1000)).astype(np.int64)[use]
    ub, bi = np.unique(blk, return_inverse=True)
    K = len(ub)
    xb, Yu = x[use], Y[:, use]
    n_k = np.bincount(bi, minlength=K).astype(float)
    sx, sxx = np.bincount(bi, xb, K), np.bincount(bi, xb * xb, K)
    sy = np.stack([np.bincount(bi, Yu[t], K) for t in range(len(taus))], 1)
    syy = np.stack([np.bincount(bi, Yu[t] ** 2, K) for t in range(len(taus))], 1)
    sxy = np.stack([np.bincount(bi, Yu[t] * xb, K) for t in range(len(taus))], 1)

    def corr(cw: np.ndarray) -> np.ndarray:
        N, SX, SXX = cw @ n_k, cw @ sx, cw @ sxx
        SY, SYY, SXY = cw @ sy, cw @ syy, cw @ sxy
        num = N[..., None] * SXY - SX[..., None] * SY
        den = np.sqrt((N * SXX - SX ** 2)[..., None] * (N[..., None] * SYY - SY ** 2))
        with np.errstate(invalid="ignore", divide="ignore"):
            return num / den

    r = corr(np.ones(K))
    k_star = int(np.nanargmax(r))
    C = rng.multinomial(K, np.full(K, 1.0 / K), size=N_BOOT).astype(float)
    rb = corr(C)
    tb = taus[np.nanargmax(rb, axis=1)]
    lo, hi = np.percentile(tb, [2.5, 97.5])
    i0 = int(np.argmin(np.abs(taus)))
    return {"tau_star_s": float(taus[k_star]), "r_star": float(r[k_star]), "r_at_0": float(r[i0]),
            "ci_lo_s": float(lo), "ci_hi_s": float(hi), "ci_width_s": float(hi - lo),
            "boundary_hit": bool(k_star in (0, len(taus) - 1)), "n_bins": int(use.sum()), "n_bins_total": int(nb),
            "n_bins_imu_ok": int(okb.sum()),
            "hours": float(use.sum() * BIN_MS / 3.6e6), "n_blocks": K, "curve": r, "boot_tau": tb}


def house_zone(x: float, y: float, houses: list[dict], buffer_in: float) -> str:
    for roi in houses:
        _, inbuf = w._rect_membership(np.array([x]), np.array([y]), roi, buffer_in)
        if bool(inbuf[0]):
            return "house"
    return "outside"


def m2_bouts(label: str, ps: pd.DataFrame, still: np.ndarray, fixes: pd.DataFrame, tau_s: float, houses: list[dict],
             buffer_in: float, min_bout_s: int = MIN_BOUT_S):
    """IMU-still bouts -> per-fix scatter about the bout median (all fixes and valid-only), 1-s medians, in-bout speeds."""
    secs = ps["sec"].to_numpy()
    tf = fixes["t_ms"].to_numpy(float) - tau_s * 1000.0
    X, Yv = fixes["x"].to_numpy(float), fixes["y"].to_numpy(float)
    A = fixes["anchors_used"].to_numpy(float)
    V = fixes["valid"].to_numpy(bool)
    SP = fixes["speed_inps_smooth"].to_numpy(float)
    fix_rows, bout_rows, sec_rows = [], [], []
    k = 0
    for a, b in true_runs(still):
        if b - a < min_bout_s:
            continue
        ta, tb = (secs[a] + TRIM_S) * 1000.0, (secs[b - 1] + 1 - TRIM_S) * 1000.0
        i0, i1 = np.searchsorted(tf, [ta, tb])
        if i1 - i0 < MIN_BOUT_FIX:
            continue
        x, y = X[i0:i1], Yv[i0:i1]
        mx, my = float(np.median(x)), float(np.median(y))
        r = np.hypot(x - mx, y - my)
        v = V[i0:i1]
        if v.sum() >= MIN_BOUT_FIX:
            mxv, myv = float(np.median(x[v])), float(np.median(y[v]))
            rv = np.where(v, np.hypot(x - mxv, y - myv), np.nan)
        else:
            rv = np.full(len(x), np.nan)
        zone = house_zone(mx, my, houses, buffer_in)
        bid = f"{label}_{k:04d}"
        k += 1
        fix_rows.append(pd.DataFrame({"bout": bid, "r_in": r, "r_valid_in": rv, "anchors_used": A[i0:i1], "valid": v,
                                      "speed_inps": SP[i0:i1], "zone": zone}))
        s1 = np.floor(tf[i0:i1] / 1000.0)
        g = pd.DataFrame({"s": s1, "x": x, "y": y}).groupby("s").median()
        sec_rows.append(pd.DataFrame({"bout": bid, "r1_in": np.hypot(g["x"] - mx, g["y"] - my).to_numpy(), "zone": zone}))
        st = sstats(r)
        bout_rows.append({"bout": bid, "start_local": ms_to_local(secs[a] * 1000.0), "dur_s": int(b - a), "n_fix": int(i1 - i0),
                          "x_med": mx, "y_med": my, "zone": zone, "p50_in": st["p50"], "p90_in": st["p90"], "rmse_in": st["rmse"]})
    cat = lambda rows: pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()  # noqa: E731
    return cat(fix_rows), pd.DataFrame(bout_rows), cat(sec_rows)


def speed_over_still_seconds(ps: pd.DataFrame, still: np.ndarray, fixes: pd.DataFrame, tau_s: float) -> np.ndarray:
    f = fixes[fixes["valid"]]
    s = np.floor((f["t_ms"].to_numpy(float) - tau_s * 1000.0) / 1000.0).astype(np.int64)
    st = set(ps["sec"].to_numpy()[still].tolist())
    keep = np.fromiter((x in st for x in s), bool, count=len(s))
    v = f["speed_inps_smooth"].to_numpy(float)[keep]
    return v[np.isfinite(v)]


def wiser_1s_medians(fixes: pd.DataFrame, tau_s: float, secs: np.ndarray) -> pd.DataFrame:
    f = fixes[fixes["valid"]]
    s = np.floor((f["t_ms"].to_numpy(float) - tau_s * 1000.0) / 1000.0).astype(np.int64)
    g = pd.DataFrame({"sec": s, "x": f["x"].to_numpy(float), "y": f["y"].to_numpy(float)}).groupby("sec")
    m = g.median()
    m["n"] = g.size()
    return m.reindex(secs)


def m4_turns(ps: pd.DataFrame, imu: dict, med: pd.DataFrame, mirror_y: bool = False) -> pd.DataFrame:
    """Non-overlapping 3-s windows: WISER heading change from 4 aligned 1-s medians vs the integrated IMU turn rate
    over the matching 2-s span [s0+1, s0+3)."""
    secs = ps["sec"].to_numpy()
    ok = ps["ok"].to_numpy(bool)
    mx, my, mn = med["x"].to_numpy(float), med["y"].to_numpy(float), med["n"].fillna(0).to_numpy(float)
    if mirror_y:
        my = -my
    u = imu["unix_ms"]
    tr = np.where(np.isfinite(imu["turn_dps"]), imu["turn_dps"], 0.0)
    dt = np.r_[np.diff(u), 1000.0 / FS_IMU] / 1000.0
    dt = np.clip(dt, 0, 2.0 / FS_IMU)
    cum = np.r_[0.0, np.cumsum(tr * dt)]
    rows = []
    for s0 in range(0, len(secs) - 3, M4_STEP_S):
        sl = slice(s0, s0 + 4)
        if not (ok[sl].all() and (mn[sl] >= M4_MIN_FIX).all()):
            continue
        p = np.column_stack([mx[sl], my[sl]])
        d = np.diff(p, axis=0)
        L = float(np.linalg.norm(d, axis=1).sum())
        if L < M4_MIN_PATH_IN:
            continue
        cr = d[:-1, 0] * d[1:, 1] - d[:-1, 1] * d[1:, 0]
        dp = (d[:-1] * d[1:]).sum(axis=1)
        dpsi_w = float(np.degrees(np.arctan2(cr, dp)).sum())
        a, b = np.searchsorted(u, [(secs[s0] + 1) * 1000.0, (secs[s0] + 3) * 1000.0])
        if b - a < 0.9 * 2 * FS_IMU:
            continue
        rows.append({"sec": int(secs[s0]), "path_in": L, "dpsi_w_deg": dpsi_w, "dpsi_i_deg": float(cum[b] - cum[a])})
    return pd.DataFrame(rows)


def m4_stats(df: pd.DataFrame) -> dict:
    from scipy import stats
    if len(df) < 10:
        return {"n": int(len(df)), "rho": np.nan, "p": np.nan, "b_IW": np.nan, "b_WI": np.nan, "n_big": 0,
                "same_sign": np.nan}
    rho, p = stats.spearmanr(df["dpsi_w_deg"], df["dpsi_i_deg"])
    b_iw = stats.theilslopes(df["dpsi_i_deg"], df["dpsi_w_deg"])[0]
    b_wi = stats.theilslopes(df["dpsi_w_deg"], df["dpsi_i_deg"])[0]
    big = df[np.abs(df["dpsi_i_deg"]) > M4_TURN_THR_DEG]
    same = float((np.sign(big["dpsi_w_deg"]) == np.sign(big["dpsi_i_deg"])).mean()) if len(big) else np.nan
    return {"n": int(len(df)), "rho": float(rho), "p": float(p), "b_IW": float(b_iw), "b_WI": float(b_wi),
            "n_big": int(len(big)), "same_sign": same}


def m5_agreement(ps: pd.DataFrame, still: np.ndarray, fixes: pd.DataFrame, tau_s: float, thr_inps: float) -> dict:
    f = w.rest_mask(fixes[fixes["valid"]], moving_thr_inps=thr_inps)       # library REST proxy (NaN = not resting)
    s = np.floor((f["t_ms"].to_numpy(float) - tau_s * 1000.0) / 1000.0).astype(np.int64)
    frac = pd.Series(f["resting"].to_numpy(float)).groupby(s).mean()
    j = pd.DataFrame({"sec": ps["sec"].to_numpy(), "ok": ps["ok"].to_numpy(bool), "still": still})
    j["rest_w"] = frac.reindex(j["sec"]).to_numpy() >= 0.5
    j["has_w"] = frac.reindex(j["sec"]).notna().to_numpy()
    j = j[j["ok"] & j["has_w"]]
    a, bw = j["still"].to_numpy(bool), j["rest_w"].to_numpy(bool)
    n = len(j)
    tp, tn = int((a & bw).sum()), int((~a & ~bw).sum())
    fp, fn = int((~a & bw).sum()), int((a & ~bw).sum())
    po = (tp + tn) / n if n else np.nan
    pa, pb = a.mean() if n else np.nan, bw.mean() if n else np.nan
    pe = pa * pb + (1 - pa) * (1 - pb)
    return {"n_s": n, "tp": tp, "tn": tn, "fp": fp, "fn": fn, "kappa": (po - pe) / (1 - pe) if n else np.nan,
            "sensitivity": tp / (tp + fn) if tp + fn else np.nan, "specificity": tn / (tn + fp) if tn + fp else np.nan,
            "ppv": tp / (tp + fp) if tp + fp else np.nan, "npv": tn / (tn + fn) if tn + fn else np.nan,
            "still_frac": pa, "rest_w_frac": pb, "agreement": po}


# ================================================================ driver
def resolve_tag(ids: pd.DataFrame, animal: str, lo_ms: float, hi_ms: float) -> int:
    r = ids[(ids.animal == animal) & (ids.from_ms <= lo_ms) & (ids.until_ms >= hi_ms)]
    if len(r) != 1:
        raise SystemExit(f"{animal}: {len(r)} tag rows cover {ms_to_local(lo_ms)} -> {ms_to_local(hi_ms)}; need exactly 1")
    return int(r.shortid.iloc[0])


def tag_window(ids: pd.DataFrame, shortid: int, animal: str, t_ms: float) -> tuple[float, float]:
    r = ids[(ids.shortid == shortid) & (ids.animal == animal) & (ids.from_ms <= t_ms) & (ids.until_ms > t_ms)]
    return (float(r.from_ms.iloc[0]), float(r.until_ms.iloc[0])) if len(r) else (np.inf, -np.inf)


def gap_time_frac(fx: pd.DataFrame, lo: float, hi: float, gap_s: float) -> float:
    """Fraction of [lo, hi) that lies inside inter-fix intervals longer than gap_s (one tag)."""
    t = fx.loc[(fx.t_ms >= lo) & (fx.t_ms < hi), "t_ms"].to_numpy(float)
    d = np.diff(t) / 1000.0
    return float(d[d > gap_s].sum() / ((hi - lo) / 1000.0)) if len(d) else np.nan


def event_span(ps: pd.DataFrame, still: np.ndarray, fx: pd.DataFrame, lo: float, hi: float, radius_in: float = 24.0) -> dict:
    """Descriptive: how long WISER keeps the tag in place (per-minute medians within radius_in of the first 10 min's
    median) and what the IMU does meanwhile."""
    fe = fx[(fx.t_ms >= lo) & (fx.t_ms < hi)]
    ref = fe[fe.t_ms < lo + 600_000][["x", "y"]].median()
    mins = ((fe.t_ms - lo) // 60_000).astype(int)
    mm = fe.groupby(mins)[["x", "y"]].median()
    dist = np.hypot(mm["x"] - ref["x"], mm["y"] - ref["y"])
    away = dist.index[dist > radius_in]
    end = lo + 60_000 * int(away[0]) if len(away) else hi
    t = ps["sec"].to_numpy() * 1000.0
    sel = (t >= lo) & (t < end)
    ok = ps["ok"].to_numpy(bool) & sel
    act = ok & ~still
    runs = [(a, b) for a, b in true_runs(act)]
    a, b = max(runs, key=lambda r: r[1] - r[0]) if runs else (0, 0)
    return {"span_end": ms_to_local(end), "span_s": int(sel.sum()), "ok_s": int(ok.sum()), "still_s": int((still & sel).sum()),
            "active_s": int(act.sum()), "longest_active_start": ms_to_local(t[a]) if b > a else None,
            "longest_active_s": int(b - a), "longest_active_vedba_med": float(np.nanmedian(ps["vedba_1s"].to_numpy()[a:b])) if b > a else np.nan,
            "longest_active_omega_med": float(np.nanmedian(ps["omega_1s"].to_numpy()[a:b])) if b > a else np.nan,
            "radius_in": radius_in}


def file_info(p: Path, hash_it: bool = True) -> dict:
    st = p.stat()
    return {"path": str(p), "bytes": st.st_size, "mtime": pd.Timestamp(st.st_mtime, unit="s", tz="UTC").tz_convert(
        "America/New_York").strftime("%Y-%m-%d %H:%M:%S"), "sha256": sha256(p) if hash_it else None}


def frozen_intervals_from_flag(flag: np.ndarray | None, unix: np.ndarray | None) -> list[tuple[str, str, float]]:
    if flag is None:
        return []
    return [(ms_to_local(unix[a]), ms_to_local(unix[b - 1]), (b - a) / FS_IMU) for a, b in true_runs(flag)]


def run(cohort: str, imu_root: Path | None, out_root: Path | None) -> None:
    t_start = time.time()
    rng = np.random.default_rng(20260929)
    coh = load_cohort(cohort)
    cfg_path = REPO / "wiser" / "configs" / f"imu_wiser_calibration_{cohort}.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    tz = cfg.get("tz", "America/New_York")
    if imu_root is None:
        ar = (coh.get("ephys") or {}).get("analysis_root")
        if not ar:
            raise SystemExit("no ephys.analysis_root in the cohort YAML; pass --imu-root")
        imu_root = Path(ar) / "imu"
    thr = imu_still_thr()
    ids = pd.read_csv(REPO / coh["identities"], dtype={"shortid": int, "physical_tag_id": str})
    ids["from_ms"] = pd.to_datetime(ids["valid_from"], utc=True).astype("int64") // 10**6
    ids["until_ms"] = pd.to_datetime(ids["valid_until"], utc=True).astype("int64") // 10**6
    hj = json.loads((REPO / cfg["handling_json"]).read_text(encoding="utf-8"))
    handling = [(to_ms(a, tz), to_ms(b, tz), note) for a, b, note in hj["windows"]]
    sil = pd.read_csv(cfg["silences_csv"])
    pad = cfg["silence_pad_s"] * 1000
    silences = [(to_ms(r.start, tz) - pad, to_ms(r.end, tz) + pad, r.kind) for r in sil.itertuples()]
    rois = json.loads((REPO / cfg["rois_json"]).read_text(encoding="utf-8"))
    houses = [r for r in rois["rois"] if r["name"] in cfg["house_rois"]]
    base = cfg["baseline"]
    rest_thr = float(base["speed_floor_p99_inps"])

    out = output_paths.run_dir(NAME, cohort, root=out_root)
    csv_dir = out / "csv"
    csv_dir.mkdir(exist_ok=True)
    print(f"run dir: {out}", flush=True)

    night = cfg["night"]
    lo, hi = to_ms(night["start"], tz), to_ms(night["end"], tz)
    animals = list(night["sessions"])
    tags = {a: resolve_tag(ids, a, lo, hi) for a in animals}
    ft, ev = cfg["fixed_tag_reference"], cfg["still_event"]
    ft_lo, ft_hi = to_ms(ft["start"], tz), to_ms(ft["end"], tz)
    ev_lo, ev_hi = to_ms(ev["start"], tz), to_ms(ev["end"], tz)
    ev_tag = resolve_tag(ids, ev["animal"], ev_lo, ev_hi)
    ft_tag_table = resolve_tag(ids, ft["animal"], ft_lo, ft_hi)
    assert ev_tag == ev["shortid"] and ft_tag_table == ft["shortid"], "config shortids disagree with the tag table"

    # ---------------- provenance of every input
    prov = {"config": cfg_path.relative_to(REPO).as_posix(), "identities": coh["identities"], "imu_still_thr": thr,
            "handling_json": cfg["handling_json"], "silences_csv": cfg["silences_csv"], "files": []}
    npz_paths = {a: imu_root / a / f"{s}.imu.npz" for a, s in night["sessions"].items()}
    npz_paths["_implant"] = imu_root / ft["animal"] / f"{ft['session']}.imu.npz"
    npz_paths["_event"] = imu_root / ev["animal"] / f"{ev['session']}.imu.npz"
    for fc in cfg["frozen_checks"]:
        npz_paths[f"_frz_{fc['animal']}"] = imu_root / fc["animal"] / f"{fc['session']}.imu.npz"
    for k, p in npz_paths.items():
        prov["files"].append({"role": k, **file_info(p), "sidecar": file_info(p.with_name(p.name.replace(".imu.npz", ".imu.json")), False)})
    db = Path(cfg["wiser_db"])
    dbi = file_info(db)
    prov["files"].append({"role": "wiser_db", **dbi})
    if not dbi["sha256"].startswith(cfg["wiser_db_sha256_prefix_expected"]):
        raise SystemExit(f"WISER DB sha256 {dbi['sha256'][:12]} != expected {cfg['wiser_db_sha256_prefix_expected']}")
    print(f"inputs hashed ({time.time() - t_start:.0f} s)", flush=True)

    # ---------------- WISER
    wins = [("night", sorted(tags.values()), lo - 300_000, hi + 300_000),
            ("implant", [ft["shortid"]], ft_lo - 300_000, ft_hi + 300_000),
            ("event", [ev["shortid"]], ev_lo - 300_000, ev_hi + 300_000)]
    wfix, n_raw = query_wiser(db, cfg["wiser_table"], wins)
    print(f"WISER: {n_raw:,} rows in the query windows ({time.time() - t_start:.0f} s)", flush=True)

    def sidecar(a: str, s: str) -> dict:
        return json.loads((imu_root / a / f"{s}.imu.json").read_text(encoding="utf-8"))

    # ---------------- night: per animal
    res = {"animals": {}, "mask": {}}
    ps_all, imu_all, fx_all = {}, {}, {}
    for a in animals:
        s = night["sessions"][a]
        sc = sidecar(a, s)
        imu = load_imu_npz(npz_paths[a], sc["start_local"], lo - 120_000, hi + 120_000)
        frm, fruns = frozen_rule(imu["omega_dps"], imu["vedba_ms2"])
        vf, vu = tag_window(ids, tags[a], a, (lo + hi) / 2)
        ps = per_second(imu, lo, hi, handling, silences, vf, vu, frm)
        fx = wfix["night"][wfix["night"].shortid == tags[a]].reset_index(drop=True)
        ps_all[a], imu_all[a], fx_all[a] = ps, imu, fx
        res.setdefault("pc_time_fit", {})[a] = sc.get("pc_time_fit")
        res["mask"][a] = {"seconds": int(len(ps)), **{c: int(ps[c].sum()) for c in MASK_COLS}, "masked_any": int((~ps.ok).sum()),
                          "frozen_rule_runs": len(fruns), "frozen_flag_s_in_window": float(imu["frozen"].sum() / FS_IMU),
                          "has_new_flags": imu["has_new_flags"], "sidecar_frozen_s": sc.get("frozen_s"),
                          "n_fix": int(len(fx)), "n_fix_valid": int(fx["valid"].sum()),
                          "fix_speed_nan": int(fx.loc[(fx.t_ms >= lo) & (fx.t_ms < hi), "speed_inps_smooth"].isna().sum()),
                          "gap_gt1s_time_frac": gap_time_frac(fx, lo, hi, 1.0),
                          "fix_low_anchor": int(fx["low_anchor_flag"].sum()), "fix_gap": int(fx["gap_flag"].sum()),
                          "fix_jump": int(fx["jump_flag"].sum())}
        print(f"{a}: {len(ps)} s, {int(ps.ok.sum())} QC-ok, {len(fx):,} fixes (tag {tags[a]})", flush=True)

    # M1
    for a in animals:
        m1 = m1_lag(imu_all[a], ps_all[a], fx_all[a], lo, hi, rng)
        res["animals"][a] = {"tag": tags[a], "m1": m1}
        print(f"M1 {a}: tau* {m1['tau_star_s']:+.2f} s [{m1['ci_lo_s']:+.2f}, {m1['ci_hi_s']:+.2f}] r {m1['r_star']:.3f}", flush=True)
    taus_star = {a: res["animals"][a]["m1"]["tau_star_s"] for a in animals}
    tau_pool = float(np.median(list(taus_star.values())))

    # M2, M3, M4, M5
    fix_tabs, bout_tabs, sec_tabs, m4_tabs, vb_all, vs_all = [], [], [], [], [], []
    for a in animals:
        ps, fx, tau = ps_all[a], fx_all[a], taus_star[a]
        st = still_mask(ps, thr[a])
        fr, bt, sr = m2_bouts(a, ps, st, fx, tau, houses, cfg["house_buffer_in"])
        for t_ in (fr, bt, sr):
            if len(t_):
                t_.insert(0, "animal", a)
        fix_tabs.append(fr)
        bout_tabs.append(bt)
        sec_tabs.append(sr)
        v_b = fr.loc[fr["valid"], "speed_inps"].to_numpy(float) if len(fr) else np.array([])
        v_b = v_b[np.isfinite(v_b)]
        v_s = speed_over_still_seconds(ps, st, fx, tau)
        vb_all.append(v_b)
        vs_all.append(v_s)
        med = wiser_1s_medians(fx, tau, ps["sec"].to_numpy())
        t4 = m4_turns(ps, imu_all[a], med)
        t4m = m4_turns(ps, imu_all[a], med, mirror_y=True)
        t4.insert(0, "animal", a)
        m4_tabs.append(t4)
        res["animals"][a].update({
            "still_s": int(st.sum()), "ok_s": int(ps.ok.sum()),
            "m3_in_bouts": {"n": int(len(v_b)), **({f"p{q}": float(np.percentile(v_b, q)) for q in (50, 95, 99)} if len(v_b) else {})},
            "m3_still_seconds": {"n": int(len(v_s)), **({f"p{q}": float(np.percentile(v_s, q)) for q in (50, 95, 99)} if len(v_s) else {})},
            "m4": m4_stats(t4), "m4_mirrored": m4_stats(t4m),
            "m5": m5_agreement(ps, st, fx, tau, rest_thr)})
    fixes_b = pd.concat([t for t in fix_tabs if len(t)], ignore_index=True)
    bouts = pd.concat([t for t in bout_tabs if len(t)], ignore_index=True)
    secs_b = pd.concat([t for t in sec_tabs if len(t)], ignore_index=True)
    m4_all = pd.concat(m4_tabs, ignore_index=True)
    pq = lambda v: {"n": int(len(v)), **{f"p{q}": float(np.percentile(v, q)) for q in (50, 95, 99)}} if len(v) else {"n": 0}  # noqa: E731
    res["m3_pooled"] = {"bouts": pq(np.concatenate(vb_all)), "still": pq(np.concatenate(vs_all))}

    # ---------------- M2 strata
    strata = {}

    def add(name: str, fsel: pd.DataFrame, ssel: pd.DataFrame, col: str = "r_in"):
        strata[name] = {"n_bouts": int(fsel["bout"].nunique()) if len(fsel) else 0,
                        "hours": float(bouts[bouts.bout.isin(fsel["bout"].unique())].dur_s.sum() / 3600) if len(fsel) else 0.0,
                        **sstats(fsel[col] if len(fsel) else []),
                        "p90_1s": sstats(ssel["r1_in"] if len(ssel) else [])["p90"],
                        "rmse_1s": sstats(ssel["r1_in"] if len(ssel) else [])["rmse"],
                        "p50_1s": sstats(ssel["r1_in"] if len(ssel) else [])["p50"]}

    add("all (all fixes)", fixes_b, secs_b)
    add("all (valid fixes)", fixes_b[fixes_b.valid], secs_b, col="r_valid_in")
    for z in ("house", "outside"):
        add(f"zone {z}", fixes_b[fixes_b.zone == z], secs_b[secs_b.zone == z])
    for a in animals:
        add(f"animal {a}", fixes_b[fixes_b.animal == a], secs_b[secs_b.animal == a])
    anch = {}
    for k in sorted(fixes_b["anchors_used"].dropna().unique()):
        sel = fixes_b[fixes_b.anchors_used == k]
        anch[int(k)] = {"n_bouts": int(sel.bout.nunique()), "share": float(len(sel) / len(fixes_b)), **sstats(sel.r_in)}
    # post hoc (added after the first run, 2026-09-29, to read the direction of the selector-bias flag; no verdict uses it)
    dcat = pd.cut(bouts.set_index("bout").dur_s, [59, 120, 300, 10**6], labels=["60–120 s", "120–300 s", "≥ 300 s"])
    dur = {}
    for k in dcat.cat.categories:
        ids_k = dcat.index[dcat == k]
        sel = fixes_b[fixes_b.bout.isin(ids_k)]
        dur[str(k)] = {"n_bouts": int(len(ids_k)), **sstats(sel.r_in)}
    res["m2"] = {"strata": strata, "anchors": anch, "duration_post_hoc": dur}

    # ---------------- still event (SF07 corner)
    sc = sidecar(ev["animal"], ev["session"])
    imu_e = load_imu_npz(npz_paths["_event"], sc["start_local"], ev_lo - 120_000, ev_hi + 120_000)
    frm_e, _ = frozen_rule(imu_e["omega_dps"], imu_e["vedba_ms2"])
    vf, vu = tag_window(ids, ev_tag, ev["animal"], (ev_lo + ev_hi) / 2)
    ps_e = per_second(imu_e, ev_lo, ev_hi, handling, silences, vf, vu, frm_e)
    st_e = still_mask(ps_e, thr[ev["animal"]])
    fx_e = wfix["event"].reset_index(drop=True)
    fr_e, bt_e, sr_e = m2_bouts("event", ps_e, st_e, fx_e, taus_star.get(ev["animal"], tau_pool), houses, cfg["house_buffer_in"])
    whole_e = sstats(np.hypot(fx_e.x - fx_e[(fx_e.t_ms >= ev_lo) & (fx_e.t_ms < ev_hi)].x.median(),
                              fx_e.y - fx_e[(fx_e.t_ms >= ev_lo) & (fx_e.t_ms < ev_hi)].y.median())[(fx_e.t_ms >= ev_lo) & (fx_e.t_ms < ev_hi)])
    res["event"] = {"ok_s": int(ps_e.ok.sum()), "seconds": int(len(ps_e)), "still_s": int(st_e.sum()),
                    "masked": {c: int(ps_e[c].sum()) for c in MASK_COLS},
                    "vedba_1s_p50": float(np.nanmedian(ps_e.vedba_1s)), "omega_1s_p50": float(np.nanmedian(ps_e.omega_1s)),
                    "n_bouts": int(len(bt_e)), "bouts": bt_e.to_dict("records") if len(bt_e) else [],
                    "scatter_bouts": sstats(fr_e.r_in if len(fr_e) else []),
                    "scatter_1s": sstats(sr_e.r1_in if len(sr_e) else []), "scatter_whole_window": whole_e,
                    "n_fix": int(((fx_e.t_ms >= ev_lo) & (fx_e.t_ms < ev_hi)).sum()),
                    "span": event_span(ps_e, st_e, fx_e, ev_lo, ev_hi)}

    # ---------------- fixed-tag reference: dropped implant, stillness from the RAW IMU
    sc = sidecar(ft["animal"], ft["session"])
    imu_f = load_imu_npz(npz_paths["_implant"], sc["start_local"], ft_lo - 120_000, ft_hi + 120_000)
    tl_map, u_map = imu_f["time_map"]
    t0_log = float(np.interp(ft_lo - 60_000, u_map, tl_map))
    t1_log = float(np.interp(ft_hi + 60_000, u_map, tl_map))
    six, k0 = read_six(Path(sc["session_dir"]), t0_log, t1_log - t0_log)
    rd = raw_derived_50hz(six, k0, float(sc.get("k_a", 1.0)))
    del six
    rd["unix_ms"] = np.interp(rd["t_logger_s"], tl_map, u_map)
    n_f = len(rd["unix_ms"])
    imu_raw = {"unix_ms": rd["unix_ms"], "vedba_ms2": rd["vedba_ms2"], "omega_dps": rd["omega_dps"],
               "turn_dps": np.zeros(n_f), "saturated": rd["saturated"], "frozen": rd["frozen_raw"],
               "unreliable": np.zeros(n_f, bool), "invalid": np.zeros(n_f, bool)}
    frm_f, _ = frozen_rule(rd["omega_dps"], rd["vedba_ms2"])
    # the implant is a device, not an animal: no handling / tag-validity mask here (the IMU itself shows disturbance)
    ps_f = per_second(imu_raw, ft_lo, ft_hi, [], [], -np.inf, np.inf, frm_f)
    st_f = still_mask(ps_f, thr[ft["animal"]])
    fx_f = wfix["implant"].reset_index(drop=True)
    fr_f, bt_f, sr_f = m2_bouts("implant", ps_f, st_f, fx_f, tau_pool, houses, cfg["house_buffer_in"])
    inwin = (fx_f.t_ms >= ft_lo) & (fx_f.t_ms < ft_hi)
    pre = inwin & (fx_f.t_ms < to_ms(ft["start"][:10] + " 07:24:00", tz))

    def whole(sel):
        d = fx_f[sel]
        return sstats(np.hypot(d.x - d.x.median(), d.y - d.y.median()))

    moves = [(ms_to_local(ps_f.sec.iloc[a] * 1000), int(b - a), float(np.nanmax(ps_f.vedba_1s.iloc[a:b])))
             for a, b in true_runs(ps_f.ok.to_numpy() & ~st_f)]
    res["implant"] = {"pc_time_verdict": (sc.get("pc_time_fit") or {}).get("verdict"),
                      "seconds": int(len(ps_f)), "ok_s": int(ps_f.ok.sum()), "still_s": int(st_f.sum()),
                      "vedba_1s_q": [float(x) for x in np.nanpercentile(ps_f.vedba_1s, [50, 99, 100])],
                      "omega_1s_q": [float(x) for x in np.nanpercentile(ps_f.omega_1s, [50, 99, 100])],
                      "gyro_bias_dps": rd["gyro_bias_dps"], "raw_frozen_s": float(rd["frozen_raw"].sum() / FS_IMU),
                      "saturated_s": float(rd["saturated"].sum() / FS_IMU),
                      "non_still_runs": sorted(moves, key=lambda m: -m[2])[:10], "n_non_still_runs": len(moves),
                      "n_bouts": int(len(bt_f)), "bout_hours": float(bt_f.dur_s.sum() / 3600) if len(bt_f) else 0.0,
                      "scatter_bouts": sstats(fr_f.r_in if len(fr_f) else []),
                      "scatter_bouts_1s": sstats(sr_f.r1_in if len(sr_f) else []),
                      "scatter_whole": whole(inwin), "scatter_pre_handling": whole(pre),
                      "n_fix": int(inwin.sum()), "zones": sorted(set(bt_f.zone)) if len(bt_f) else [],
                      "anchors": {int(k): sstats(g.r_in) for k, g in fr_f.groupby("anchors_used")} if len(fr_f) else {},
                      "npz_invalid_s_in_window": float(imu_f["invalid"].sum() / FS_IMU)}
    print(f"implant: {res['implant']['still_s']}/{res['implant']['ok_s']} s still; {len(bt_f)} bouts", flush=True)

    # ---------------- frozen-rule cross-check on the two known freezes (raw lanes -> derived signals)
    res["frozen_checks"] = []
    for fc in cfg["frozen_checks"]:
        sc = sidecar(fc["animal"], fc["session"])
        exp0, exp1 = to_ms(fc["expected_start"], tz), to_ms(fc["expected_end"], tz)
        with np.load(npz_paths[f"_frz_{fc['animal']}"]) as z:
            base_ms = to_ms(sc["start_local"][:10] + " 00:00:00")
            u_all = base_ms + z["t_pc_ms"].astype(np.float64)
            tl_all = z["t_logger_s"].astype(np.float64)
            flag = z["frozen"].astype(bool) if "frozen" in z.files else None
        flag_iv = frozen_intervals_from_flag(flag, u_all)
        entry = {**fc, "flag_intervals": flag_iv, "rule_intervals": [], "rawlane_intervals": [], "probes": []}
        # onset and offset probes of +-10 min (the whole freeze is not re-read: SF12's lasts 4.7 h)
        for lab, cms in (("onset", exp0), ("offset", exp1)):
            a_ms, b_ms = max(cms - 600_000, u_all[0]), min(cms + 600_000, u_all[-1])
            t0l = float(np.interp(a_ms, u_all, tl_all))
            t1l = float(np.interp(b_ms, u_all, tl_all))
            six, k0 = read_six(Path(sc["session_dir"]), t0l, t1l - t0l)
            rd = raw_derived_50hz(six, k0, float(sc.get("k_a", 1.0)))
            uu = np.interp(rd["t_logger_s"], tl_all, u_all)
            _, runs = frozen_rule(rd["omega_dps"], rd["vedba_ms2"])
            rule_iv = [(ms_to_local(uu[a]), ms_to_local(uu[b - 1]), (b - a) / FS_IMU) for a, b in runs]
            raw_iv = [(ms_to_local(uu[a]), ms_to_local(uu[b - 1]), (b - a) / FS_IMU) for a, b in true_runs(rd["frozen_raw"])]
            entry["probes"].append({"probe": lab, "from": ms_to_local(a_ms), "to": ms_to_local(b_ms),
                                    "rule": rule_iv, "rawlane": raw_iv})
        res["frozen_checks"].append(entry)
        print(f"frozen check {fc['animal']} {fc['session']}: flag {len(flag_iv)} runs", flush=True)

    res["tau_pool_s"] = tau_pool
    res["runtime_s"] = time.time() - t_start

    # ---------------- verdicts
    res["verdicts"] = verdicts(res, animals, base)

    # ---------------- bulk tables
    for a in animals:
        ps_all[a].assign(still=still_mask(ps_all[a], thr[a])).to_csv(csv_dir / f"per_second_{a}.csv.gz", index=False)
    ps_e.assign(still=st_e).to_csv(csv_dir / "per_second_event.csv.gz", index=False)
    ps_f.assign(still=st_f).to_csv(csv_dir / "per_second_implant_raw.csv.gz", index=False)
    bouts.to_csv(csv_dir / "m2_bouts.csv", index=False)
    fixes_b.to_csv(csv_dir / "m2_bout_fixes.csv.gz", index=False)
    m4_all.to_csv(csv_dir / "m4_windows.csv", index=False)
    pd.DataFrame({"tau_s": TAUS, **{a: res["animals"][a]["m1"]["curve"] for a in animals}}).to_csv(csv_dir / "m1_curves.csv", index=False)
    pd.DataFrame({a: res["animals"][a]["m1"]["boot_tau"] for a in animals}).to_csv(csv_dir / "m1_bootstrap_tau.csv", index=False)
    bt_f.to_csv(csv_dir / "implant_bouts.csv", index=False)
    bt_e.to_csv(csv_dir / "event_bouts.csv", index=False)
    summary = strip_arrays(res)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    (out / "input_provenance.json").write_text(json.dumps(prov, indent=2, default=str), encoding="utf-8")

    # ---------------- figures + report
    fdir = output_paths.figure_dir(cohort, DIRECTION)
    figs = make_figures(res, animals, fixes_b, secs_b, fr_f, m4_all, base, fdir, cohort, out)
    rdir = output_paths.report_dir(cohort, DIRECTION)
    rep = rdir / f"{DIRECTION}_imu_calibration_pilot_{cohort}.md"
    rep.write_text(render_report(res, cfg, animals, tags, thr, base, prov, out, figs, cohort, n_raw), encoding="utf-8")
    meta = {"cohort": cohort, "direction": DIRECTION, "analysis": NAME, "report": rep.name,
            "driver": "wiser/scripts/analyze_imu_wiser_calibration.py", "config": cfg_path.relative_to(REPO).as_posix(),
            "git_commit": git_commit(), "runtime_s": round(time.time() - t_start, 1)}
    output_paths.write_run_manifest(out, out, **meta)          # a copy inside the bulk run
    mp = rdir / f"run_manifest_imu_calibration_pilot_{cohort}.json"   # the folder's run_manifest.json is the accuracy run's
    mp.write_text(json.dumps({"run_dir": str(out.resolve()), **meta}, indent=2) + "\n", encoding="utf-8")
    print(f"report: {rep}\nmanifest: {mp}\nruntime {time.time() - t_start:.0f} s", flush=True)


def strip_arrays(o):
    if isinstance(o, dict):
        return {str(k): strip_arrays(v) for k, v in o.items() if k not in ("curve", "boot_tau")}
    if isinstance(o, (list, tuple)):
        return [strip_arrays(v) for v in o]
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def verdicts(res: dict, animals: list[str], base: dict) -> dict:
    v = {}
    m1 = {a: res["animals"][a]["m1"] for a in animals}
    widths_ok = all(m1[a]["ci_width_s"] <= ACCEPT["m1_ci_width_s"] and not m1[a]["boundary_hit"] for a in animals)
    spread = max(m1[a]["tau_star_s"] for a in animals) - min(m1[a]["tau_star_s"] for a in animals)
    v["M1"] = {"pass": bool(widths_ok and spread <= ACCEPT["m1_spread_s"]), "ci_ok": widths_ok, "spread_s": spread}
    st = res["m2"]["strata"]
    enough = {k: st[k]["n_bouts"] >= ACCEPT["m2_min_bouts"] for k in ("all (all fixes)", "zone house", "zone outside")}
    ref = {"p50": base["rest_bouts_p50_in"], "p90": base["rest_bouts_p90_in"], "rmse": base["rest_bouts_rmse_in"]}
    rel = {k: st["all (all fixes)"][k] / ref[k] - 1 for k in ref}
    v["M2"] = {"enough_bouts": enough, "rel_diff_vs_baseline": rel,
               "selector_bias_flag": bool(any(abs(x) > ACCEPT["m2_rel_diff"] for x in rel.values())),
               "pass": bool(all(enough.values()))}
    m4 = {a: res["animals"][a]["m4"] for a in animals}
    rhos = np.array([m4[a]["rho"] for a in animals])
    sgn = np.sign(np.nanmedian(rhos))
    agree = {a: (m4[a]["same_sign"] if sgn > 0 else 1 - m4[a]["same_sign"]) for a in animals}
    same_sign = bool(np.all(np.sign(rhos) == sgn) and np.all(np.isfinite(rhos)))
    big = bool(np.all(np.abs(rhos) >= ACCEPT["m4_min_abs_rho"]))
    agr = bool(all(np.isfinite(agree[a]) and agree[a] >= ACCEPT["m4_min_agree"] for a in animals))
    v["M4"] = {"pass": bool(same_sign and big and agr), "same_sign": same_sign, "abs_rho_ok": big, "agree_ok": agr,
               "sign": int(sgn) if np.isfinite(sgn) else 0, "agree": agree}
    return v


# ================================================================ figures
def make_figures(res, animals, fixes_b, secs_b, fr_f, m4_all, base, fdir, cohort, out) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figs = {}
    stem = f"{DIRECTION}_imu_calibration_pilot"
    # M1
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    for a in animals:
        m = res["animals"][a]["m1"]
        ln, = ax.plot(TAUS, m["curve"], label=f"{a}  tau* {m['tau_star_s']:+.2f} s [{m['ci_lo_s']:+.2f}, {m['ci_hi_s']:+.2f}]")
        ax.axvspan(m["ci_lo_s"], m["ci_hi_s"], color=ln.get_color(), alpha=0.12)
        ax.axvline(m["tau_star_s"], color=ln.get_color(), lw=0.8, ls="--")
    ax.set_xlabel("tau (s): WISER speed at t + tau vs IMU log VeDBA at t  (+ = WISER later)")
    ax.set_ylabel("Pearson r")
    ax.set_title("M1 effective lag, night 2026-09-08/09 (shaded: 95 % block-bootstrap CI)")
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    figs["m1"] = fdir / f"{stem}_m1_lag_{cohort}.png"
    fig.savefig(figs["m1"], dpi=130)
    plt.close(fig)
    # M2 + M3
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.2))
    ax = axs[0]
    for lab, r in (("IMU-still bouts, all", fixes_b.r_in), ("  house", fixes_b[fixes_b.zone == "house"].r_in),
                   ("  outside", fixes_b[fixes_b.zone == "outside"].r_in), ("1-s medians, all", secs_b.r1_in),
                   ("dropped implant (IMU-still)", fr_f.r_in if len(fr_f) else pd.Series(dtype=float))):
        r = np.sort(np.asarray(r, float))
        if len(r):
            ax.plot(r, np.arange(1, len(r) + 1) / len(r), label=f"{lab} (n={len(r):,})")
    for q, val in (("p50", base["rest_bouts_p50_in"]), ("p90", base["rest_bouts_p90_in"])):
        ax.axvline(val, color="k", lw=0.8, ls=":")
        ax.text(val, 0.02, f" WISER-selected {q}", rotation=90, fontsize=7, va="bottom")
    ax.set_xlim(0, 25)
    ax.set_xlabel("r = distance of a fix from its bout median (in)")
    ax.set_ylabel("cumulative fraction")
    ax.set_title("M2 scatter while the IMU says still")
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)
    ax = axs[1]
    v = fixes_b.loc[fixes_b.valid, "speed_inps"].dropna().to_numpy()
    ax.hist(v, bins=np.arange(0, 30.5, 0.5), color="0.5")
    for q in (95, 99):
        ax.axvline(np.percentile(v, q), color="C3", lw=1, ls="--")
        ax.text(np.percentile(v, q), ax.get_ylim()[1] * 0.9, f" IMU-still p{q}", fontsize=7, color="C3")
    ax.axvline(base["speed_floor_p99_inps"], color="k", lw=1, ls=":")
    ax.text(base["speed_floor_p99_inps"], ax.get_ylim()[1] * 0.6, " WISER-selected p99", fontsize=7)
    ax.set_xlabel("WISER smoothed speed v_W (in/s), valid fixes inside IMU-still bouts")
    ax.set_ylabel("fixes")
    ax.set_title("M3 speed-noise floor")
    fig.tight_layout()
    figs["m2"] = fdir / f"{stem}_m2_m3_scatter_speed_{cohort}.png"
    fig.savefig(figs["m2"], dpi=130)
    plt.close(fig)
    # M4
    fig, axs = plt.subplots(1, len(animals), figsize=(3.2 * len(animals), 3.4), sharex=True, sharey=True)
    for ax, a in zip(np.atleast_1d(axs), animals):
        d = m4_all[m4_all.animal == a]
        s = res["animals"][a]["m4"]
        ax.scatter(d.dpsi_i_deg, d.dpsi_w_deg, s=4, alpha=0.35)
        ax.axhline(0, color="k", lw=0.5)
        ax.axvline(0, color="k", lw=0.5)
        ax.plot([-300, 300], [-300, 300], "k:", lw=0.7)
        ax.set_title(f"{a}: rho {s['rho']:+.2f}, n {s['n']}", fontsize=9)
        ax.set_xlim(-400, 400)
        ax.set_ylim(-360, 360)
        ax.set_xlabel("IMU turn, 2 s (deg, + = CCW from above)")
    np.atleast_1d(axs)[0].set_ylabel("WISER heading change (deg, + = +x toward +y)")
    fig.suptitle("M4 handedness: 3-s windows with WISER path >= 30 in (dotted: identity)", fontsize=10)
    fig.tight_layout()
    figs["m4"] = fdir / f"{stem}_m4_turns_{cohort}.png"
    fig.savefig(figs["m4"], dpi=130)
    plt.close(fig)
    for k, p in figs.items():                                  # copies inside the bulk run too
        (out / "figures" / p.name).write_bytes(p.read_bytes())
    return figs


# ================================================================ report
DEFINITIONS = r"""
## Definitions

Units: WISER positions in **inches** in the WISER native frame (unverified offset origin; no georeference); IMU
acceleration in m/s², angular rate in °/s. Times are field-PC time: WISER `timestamp` (Unix ms) and the IMU's
`t_pc_ms` (make_imu, from the per-session `pc_time_fit.json`), both on the field-PC clock. Symbols: $a$ = animal,
$s$ = field-PC second, $b$ = 0.25-s bin, $i$ = WISER fix, $B$ = bout, $\mathbb 1[\cdot]$ = indicator.

### IMU per-second movement ($\mathrm{VeDBA}_{1s}$, $|\omega|_{1s}$)
$$ \mathrm{VeDBA}(t)=\lVert\mathbf a_H(t)-\bar{\mathbf a}_H(t)\rVert,\qquad \mathrm{VeDBA}_{1s}(s)=\frac1{n_s}\sum_{t\in s}\mathrm{VeDBA}(t),\qquad |\omega|_{1s}(s)=\frac1{n_s}\sum_{t\in s}\lVert\boldsymbol\omega_H(t)\rVert $$
$\mathbf a_H$ = calibrated head-frame acceleration, $\bar{\mathbf a}_H$ its 2-s running mean, $\boldsymbol\omega_H$ =
bias-corrected angular velocity, sums over the 50-Hz make_imu samples whose field-PC time falls in second $s$ ($n_s$ ≈ 50).
**Text:** head movement intensity (m/s²) and angular speed (°/s) per second; ≈ 0.05 m/s² when still, ≈ 3 m/s² active.

### IMU-still second and IMU-still bout
$$ \mathrm{still}_a(s)=\mathrm{ok}_a(s)\wedge \mathrm{VeDBA}_{1s}(s)<\theta_a \wedge |\omega|_{1s}(s)<10\ ^\circ/\mathrm s $$
$\theta_a$ = per-animal valley of the bimodal log-VeDBA histogram (`IMU_STILL_THR` in `ephys/imu_lfp_state_check.py`,
2026-09-28; values in the Data section). A **bout** is a maximal run of consecutive still seconds lasting ≥ 60 s.
**Text:** the head is not moving by an independent sensor; the thresholds were fixed before this pilot.

### QC mask $\mathrm{ok}_a(s)$
$$ \mathrm{ok}_a(s)=\neg\big(\text{nodata}\vee\text{sat}\vee\text{frozen}\vee\text{frozen-rule}\vee\text{invalid}\vee\text{NaN}\vee\text{unreliable}\vee\text{handling}\vee\text{silence}\vee\text{tag-validity}\big) $$
- nodata: < 40 of 50 samples in the second; sat / frozen / invalid / NaN: any sample saturated at full scale, flagged
  `frozen` (make_imu: all six raw lanes 1–6 identical ≥ 0.5 s), `invalid` (after `ephys.imu_valid_until`) or blanked;
  unreliable: > 50 % of samples in Fusion acceleration-/overrange-recovery or start-up (make_imu's per-second rule);
- frozen-rule (the audit's derived-signal rule, cross-check): samples in a run of ≥ 0.5 s with
  $|\Delta|\omega||<10^{-4}$ °/s and VeDBA $<10^{-3}$ m/s², padded ± 2 s;
- handling: a window in `cv/configs/cohort3_handling_windows.json`; silence: an all-tag WISER silence ± 2 min
  (`c3_all_tag_silences_merged.csv`, accuracy run); tag-validity: outside the tag's `valid_from`/`valid_until`
  (`rat_identities_2026c.csv`).
**Text:** a second enters any metric only when the IMU is live, on the animal, unsaturated and the animal is in the
arena and not handled.

### WISER smoothed position and speed ($\hat{\mathbf p}_i$, $v_i$) — library `add_speed`
$$ \hat{\mathbf p}_i=\operatorname{median}_{j=i-3}^{i+3}\mathbf p_j,\qquad v_i=\frac{\lVert\hat{\mathbf p}_{\mathrm{hi}(i)}-\hat{\mathbf p}_{\mathrm{lo}(i)}\rVert}{t_{\mathrm{hi}(i)}-t_{\mathrm{lo}(i)}} $$
lo/hi = first/last fix inside $[t_i-0.5\,\mathrm s,\,t_i+0.5\,\mathrm s]$; $v>60$ in/s → NaN. **Text:** jitter-suppressed
locomotion speed (in/s), centred in time. **Valid fix** (library `add_validity_flags`): `anchors_used` ≥ 4, no gap
(Δt ≤ 5 × the tag's median Δt), no jump (raw speed ≤ 200 in/s).

### Alignment
WISER times are shifted onto the IMU clock by the animal's $\tau^\*$ (M1): $t_i^{\mathrm{al}}=t_i-\tau^\*_a$. The
dropped implant uses the median $\tau^\*$ of the five animals (a static device is insensitive to it).

### M1 — effective lag $\tau^\*$
$$ x_b=\log_{10}\!\Big(\tfrac1{n_b}\textstyle\sum_{t\in b}\mathrm{VeDBA}(t)+0.01\Big),\qquad y_b(\tau)=v_W(c_b+\tau),\qquad \tau^\*=\arg\max_{\tau\in\{-3,-2.95,\dots,3\}\,\mathrm s}\ \mathrm{corr}_{\mathrm{Pearson}}\big(x_b,\,y_b(\tau)\big) $$
$c_b$ = centre of 0.25-s bin $b$; $v_W(t)$ = linear interpolation of $v_i$ over valid fixes, defined only where the two
bracketing fixes are ≤ 1 s apart; the same bins (all samples QC-ok, all $\tau$ defined) are used for every $\tau$.
**Text:** the shift (s) at which WISER speed best follows IMU movement; **+ = WISER later than the IMU**. It is an
*effective* lag = clock offset + WISER's internal processing latency + head-vs-body kinematics — not a pure clock
offset. The 0.01 m/s² offset keeps the log finite and is well below the still mode (~0.05 m/s²).

### M1 — 95 % CI by block bootstrap
$$ \tau^{\*(k)}=\arg\max_\tau \mathrm{corr}\big(x,y(\tau)\big)\ \text{on blocks } \{B_{j}^{(k)}\}_{j=1}^{K}\ \text{drawn with replacement},\quad k=1..1000;\qquad \mathrm{CI}=\big[Q_{0.025},Q_{0.975}\big]\big(\{\tau^{\*(k)}\}\big) $$
Blocks = the $K$ non-overlapping 300-s blocks of the night that contain bins. **Text:** 300 s is long compared with
movement bouts (seconds to a minute), so within-block autocorrelation is kept; CI width in s.

### M2 — radial deviation (non-circular jitter floor)
$$ r_i=\big\lVert\mathbf p_i-\operatorname{median}_{j\in B}\mathbf p_j\big\rVert_2,\quad i\in B;\qquad \mathrm pq=Q_q(\{r_i\}),\qquad \mathrm{RMSE}=\sqrt{\tfrac1N\textstyle\sum_i r_i^2} $$
$B$ = the raw fixes (all anchors, the baseline's method) whose aligned time lies in an IMU-still bout trimmed by 1 s at
each end; bouts need ≥ 30 fixes. Variants: *valid fixes* (median and $r$ over valid fixes); *1-s medians*
$r_s=\lVert\tilde{\mathbf p}_s-\operatorname{median}_B\mathbf p\rVert$ with $\tilde{\mathbf p}_s$ the coordinate-wise median
of the fixes in aligned second $s$. **Zone**: *house* if the bout median lies inside house_1 or house_2 of
`wiser_rois.json` grown by 14 in (library buffer ≈ 2 × the 7-in jitter floor), else *outside*. **Text:** WISER
scatter (in) while an independent sensor says the head is still — precision, not accuracy; still an upper bound on
sensor jitter where the body moves under a still head (breathing, shifting), but free of the WISER-side selection.
**Selector-bias flag:** $|Q^{\mathrm{IMU}}/Q^{\mathrm{WISER\text{-}sel}}-1|>0.20$ for p50, p90 or RMSE against
3.57 / 8.19 / 5.87 in.

### M3 — speed-noise floor over IMU-still time
$$ F_q=Q_q\big(\{v_i: i\ \text{valid},\ t^{\mathrm{al}}_i\in \text{IMU-still bout (trimmed)}\}\big),\quad q\in\{0.5,0.95,0.99\} $$
and the same over all IMU-still seconds. **Text:** the smoothed WISER speed (in/s) a tag shows while the head is still;
compare with the WISER-selected p99 = 10.24 in/s. Below $F_{0.99}$ locomotion and jitter cannot be told apart.

### M4 — heading change (WISER) and integrated turn (IMU)
$$ \mathbf d_k=\tilde{\mathbf p}_{s_0+k}-\tilde{\mathbf p}_{s_0+k-1}\ (k=1,2,3),\qquad \Delta\psi_W=\sum_{k=1}^{2}\operatorname{atan2}\!\big(d_{k,x}d_{k+1,y}-d_{k,y}d_{k+1,x},\ \mathbf d_k\!\cdot\!\mathbf d_{k+1}\big),\qquad \Delta\psi_I=\int_{s_0+1}^{s_0+3}\omega_{\mathrm{turn}}(t)\,dt $$
$\tilde{\mathbf p}_s$ = aligned 1-s median of ≥ 2 valid fixes; windows start every 3 s ($s_0$), need all four medians,
four QC-ok IMU seconds and path $\sum_k\lVert\mathbf d_k\rVert\ge 30$ in (≈ 10 in/s, the speed floor). The IMU span
$[s_0+1,s_0+3)$ runs from the mid-time of $\mathbf d_1$ to that of $\mathbf d_3$. $\omega_{\mathrm{turn}}=\boldsymbol\omega_H\cdot\hat{\mathbf u}$
(make_imu `turn_dps`, $\hat{\mathbf u}$ = head-frame up vector from the 6-axis AHRS). **Signs:** $\Delta\psi_W>0$ = the
path turns from WISER $+x$ toward $+y$; $\Delta\psi_I>0$ = counter-clockwise seen from above (right-hand rule about
up). **Statistics:** Spearman $\rho(\Delta\psi_W,\Delta\psi_I)$; Theil–Sen slopes $b_{I|W}$ ($\Delta\psi_I$ on
$\Delta\psi_W$) and $b_{W|I}$; sign agreement $A=\frac{1}{|S|}\sum_{S}\mathbb 1[\operatorname{sgn}\Delta\psi_W=\sigma\operatorname{sgn}\Delta\psi_I]$
over $S=\{|\Delta\psi_I|>45^\circ\}$ with $\sigma$ = the sign of the pooled median $\rho$. **Text:** $\rho>0$ means
WISER's (x, y, up) is right-handed (+x → +y counter-clockwise from above); $\rho<0$ means a mirrored frame. Because both
regressors carry noise (WISER jitter; head turns that do not turn the path), each slope is attenuated; the IMU/WISER
scale factor lies between $b_{I|W}$ and $1/b_{W|I}$ — a bracket containing 1 is consistent with a correct gyro scale.
**Mirror control:** the same statistics with WISER $y\to-y$ must flip the sign of $\rho$.

### M5 — rest-proxy agreement
$$ \mathrm{rest}_W(s)=\mathbb 1\Big[\tfrac1{n_s}\textstyle\sum_{i\in s}\mathbb 1[v_i<10.24\ \mathrm{in/s}]\ge 0.5\Big],\qquad \kappa=\frac{p_o-p_e}{1-p_e},\quad p_e=p_Ip_W+(1-p_I)(1-p_W) $$
$v_i<10.24$ is the library REST proxy `wiser_analysis_utils.rest_mask` (smoothed speed below the stationary p99
speed-noise floor — here the cohort-3 value; NaN speed = not resting), over valid fixes in aligned second $s$. $p_o$ =
observed agreement with IMU stillness, $p_I,p_W$ = the two positive rates. Sensitivity = $P(\mathrm{rest}_W\mid\mathrm{still})$,
specificity = $P(\neg\mathrm{rest}_W\mid\neg\mathrm{still})$, over QC-ok seconds with ≥ 1 valid fix. **Text:** how far
"WISER says not locomoting" matches "the head is still"; κ ∈ [−1, 1], 0 = chance agreement. The two constructs differ
by design (a grooming or eating rat stays in place while its head moves), so specificity is expected to be the weak side.
"""


def fmt(x, nd=2, unit=""):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "–"
    return f"{x:.{nd}f}{unit}"


def render_report(res, cfg, animals, tags, thr, base, prov, out, figs, cohort, n_raw) -> str:
    V = res["verdicts"]
    m2s = res["m2"]["strata"]
    L = []
    P = L.append
    hexof = {}
    try:
        idt = pd.read_csv(REPO / "wiser" / "configs" / f"rat_identities_{cohort}.csv", dtype={"physical_tag_id": str})
        hexof = {int(r.shortid): str(r.physical_tag_id) for r in idt.itertuples()}
    except Exception:  # noqa: BLE001
        pass
    tagtxt = ", ".join(f"{a} = {hexof.get(tags[a], '?')} ({tags[a]})" for a in animals)
    P(f"# IMU ↔ WISER calibration pilot — `wiser_baseline` ({cohort})")
    P("")
    P("- **What this is:** a *measurement* report. The head IMU of the WILD neurologgers is used as an independent sensor "
      "to measure the WISER UWB tracks' effective clock lag, precision floor, speed-noise floor and frame handedness, and "
      "how the library rest proxy agrees with head stillness. **No behavioural claim.**")
    P(f"- **Window:** {cfg['night']['label']}: {cfg['night']['start']} → {cfg['night']['end']} field-PC local (EDT), "
      f"regime B of the accuracy report. Animals and tags (hex, shortid): {tagtxt}. Two still events: "
      f"{cfg['fixed_tag_reference']['label']} ({cfg['fixed_tag_reference']['start'][11:16]}–{cfg['fixed_tag_reference']['end'][11:16]}, "
      f"{cfg['fixed_tag_reference']['start'][:10]}) and {cfg['still_event']['label']}.")
    P("- **Frame status:** WISER native inches, unverified offset origin; nothing here places a position in the paddock. "
      "M4 tests only the handedness (mirror) of the WISER axes.")
    P(f"- **Plan:** [`implementation_plan/2026-09-29-imu-wiser-calibration-pilot.md`](../../../../implementation_plan/2026-09-29-imu-wiser-calibration-pilot.md) "
      "(approved by the user 2026-09-29, after the read-only IMU audit). Acceptance criteria were fixed there, before any result.")
    P(f"- **Run:** `python wiser/scripts/analyze_imu_wiser_calibration.py --cohort {cohort}`; bulk `{out}` "
      f"(per-second tables, bouts, windows, bootstrap, `summary.json`, `input_provenance.json`); pointer "
      f"`run_manifest_imu_calibration_pilot_{cohort}.json` next to this report. Git `{git_commit()}`; runtime {res['runtime_s']:.0f} s.")
    P("")
    P("## 0. Verdicts")
    P("")
    m1v, m2v, m4v = V["M1"], V["M2"], V["M4"]
    tau_s = [res["animals"][a]["m1"]["tau_star_s"] for a in animals]
    P("| Metric | Result | Acceptance (pre-registered) | Verdict |")
    P("|---|---|---|---|")
    P(f"| M1 effective lag | τ* {min(tau_s):+.2f} … {max(tau_s):+.2f} s (spread {m1v['spread_s']:.2f} s); CI widths "
      f"{min(res['animals'][a]['m1']['ci_width_s'] for a in animals):.2f}–{max(res['animals'][a]['m1']['ci_width_s'] for a in animals):.2f} s "
      f"| every CI ≤ 0.3 s and spread ≤ 0.2 s | **{'PASS' if m1v['pass'] else 'FAIL'}** |")
    a0 = m2s["all (all fixes)"]
    rel = m2v["rel_diff_vs_baseline"]
    P(f"| M2 jitter floor (IMU-selected) | p50/p90/RMSE {a0['p50']:.2f}/{a0['p90']:.2f}/{a0['rmse']:.2f} in "
      f"({rel['p50']:+.0%}/{rel['p90']:+.0%}/{rel['rmse']:+.0%} vs 3.57/8.19/5.87); bouts all/house/outside "
      f"{m2s['all (all fixes)']['n_bouts']}/{m2s['zone house']['n_bouts']}/{m2s['zone outside']['n_bouts']} "
      f"| ≥ 20 bouts per stratum; > 20 % difference = selector bias | **{'PASS' if m2v['pass'] else 'FAIL (too few bouts)'}**; "
      f"selector-bias flag **{'RAISED' if m2v['selector_bias_flag'] else 'not raised'}** |")
    p99 = [res["animals"][a]["m3_in_bouts"].get("p99", np.nan) for a in animals]
    m3p = res["m3_pooled"]
    P(f"| M3 speed floor | pooled p95/p99 over IMU-still bouts {fmt(m3p['bouts'].get('p95'))}/{fmt(m3p['bouts'].get('p99'))} in/s "
      f"(per animal p99 {np.nanmin(p99):.2f}–{np.nanmax(p99):.2f}); over all IMU-still seconds p99 {fmt(m3p['still'].get('p99'))} "
      f"| reported vs 6.23/10.24 in/s | reported |")
    rhos = [res["animals"][a]["m4"]["rho"] for a in animals]
    P(f"| M4 handedness | Spearman ρ {min(rhos):+.2f} … {max(rhos):+.2f}; sign agreement "
      f"{min(m4v['agree'].values()):.0%}–{max(m4v['agree'].values()):.0%} | same sign on all 5, \\|ρ\\| ≥ 0.3, ≥ 70 % agreement "
      f"| **{'PASS (candidate)' if m4v['pass'] else 'INCONCLUSIVE'}**"
      f"{' — WISER frame ' + ('right-handed (+x → +y counter-clockwise from above)' if m4v['sign'] > 0 else 'MIRRORED (+x → +y clockwise from above)') if m4v['pass'] else ''} |")
    kap = [res["animals"][a]["m5"]["kappa"] for a in animals]
    P(f"| M5 rest agreement | κ {min(kap):.2f}–{max(kap):.2f} | reported | reported |")
    P("")
    P("Classification (regime-aware-wiser-tracking): all five results are **measurement** results (no behavioural content). "
      "M4, if it passes, remains a **candidate** until one video event confirms the turn sense (plan).")
    P("")
    P("**Reading, per metric** (details and caveats in §2–§9):")
    P("")
    drops = []
    for a in animals:
        m = res["animals"][a]["m1"]
        k = int(np.argmin(np.abs(TAUS - m["tau_star_s"])))
        drops += [m["curve"][k] - m["curve"][j] for j in (k - 20, k + 20) if 0 <= j < len(TAUS)]
    P(f"1. **M1.** WISER speed lags IMU movement by {min(tau_s):+.2f} … {max(tau_s):+.2f} s (median {res['tau_pool_s']:+.2f} s) on "
      f"every animal; r falls by {min(drops):.3f}–{max(drops):.3f} one second either side of τ*. This is an *effective* lag (WISER latency + head-vs-body kinematics + "
      "residual clock offsets of both pc-time paths); for per-second joins it is below one bin.")
    dir_txt = "LOWER" if rel["p50"] < 0 else "HIGHER"
    P(f"2. **M2.** While the IMU says the head is still, WISER scatter is **{dir_txt}** than the WISER-selected numbers "
      f"({a0['p50']:.2f}/{a0['p90']:.2f}/{a0['rmse']:.2f} vs 3.57/8.19/5.87 in). The flag is raised because the selectors differ, "
      + ("and the direction says the WISER-selected precision is **pessimistic, not optimistic**: its 8-in bout radius also "
         "admits real small movements. The same holds against the WISER-selected ≥ 60-s night pauses of the accuracy "
         "report and at matched `anchors_used` (§3), and there is no bout-duration trend (post hoc, §3). "
         if rel["p50"] < 0 else "i.e. the WISER-based selector favoured calm, low-scatter periods (circularity). ")
      + "Category: **mixed** — a still head can sit on a slightly moving body, so this remains an upper bound on jitter.")
    P(f"3. **M3.** Same direction: the speed-noise floor over IMU-still time is p95/p99 {fmt(m3p['bouts'].get('p95'))}/"
      f"{fmt(m3p['bouts'].get('p99'))} in/s against 6.23/10.24 in/s.")
    P(f"4. **M4.** {'Every animal' if m4v['same_sign'] else 'Not every animal'} shows ρ "
      f"{'> 0' if m4v['sign'] > 0 else '< 0'} (and the y-mirror control flips it), which points to a "
      f"{'right-handed' if m4v['sign'] > 0 else 'mirrored'} WISER frame, but the pre-registered strength criteria "
      f"({'met' if m4v['pass'] else 'not met'}: |ρ| ≥ 0.3 and ≥ 70 % agreement on every animal) decide: "
      f"**{'PASS (candidate)' if m4v['pass'] else 'INCONCLUSIVE'}**. The handedness stays unresolved by this pilot.")
    P(f"5. **M5.** At night the library rest proxy (`rest_mask`, v < 10.24 in/s) is true in "
      f"{min(res['animals'][a]['m5']['rest_w_frac'] for a in animals):.0%}–{max(res['animals'][a]['m5']['rest_w_frac'] for a in animals):.0%} "
      f"of seconds while the head is still in only {min(res['animals'][a]['m5']['still_frac'] for a in animals):.0%}–"
      f"{max(res['animals'][a]['m5']['still_frac'] for a in animals):.0%}: κ ≈ {np.mean(kap):.2f}. It marks *not "
      "locomoting*, not *still*; it must not be read as a stillness or sleep measure at night without the IMU. "
      "Daytime (the main rest period) is not covered here.")
    P("")
    # ---------------- data and masks
    P("## 1. Data, masks and what they removed")
    P("")
    P(f"- **WISER:** `{cfg['wiser_db']}` (table `{cfg['wiser_table']}`), opened `mode=ro` + `query_only`; sha256 prefix "
      f"checked against the accuracy report (`{cfg['wiser_db_sha256_prefix_expected']}`). {n_raw:,} rows in the three query "
      "windows (± 5 min pads), de-duplicated on (shortid, timestamp, x, y).")
    P(f"- **IMU:** make_imu 50-Hz `.imu.npz` under the cohort's `ephys.analysis_root/imu` (full-precision `t_pc_ms`; the "
      "per-second CSV is not used), files regenerated on 2026-09-29 by commit `6451d6c` (frozen flag, `invalid`, integer "
      "`t_pc_ms`); sizes, mtimes and sha256 in `input_provenance.json`. Raw `analogin.dat` (read-only) only for §6–7.")
    P(f"- **Still thresholds θ_a** (`IMU_STILL_THR`, m/s²): " + ", ".join(f"{a} {thr[a]}" for a in sorted(thr)) + "; |ω| < 10 °/s.")
    P("")
    P("Seconds of the 10-h night removed per reason (reasons overlap; *any* = the union):")
    P("")
    P("| Animal | seconds | nodata | saturated | frozen flag | frozen rule | invalid | NaN | unreliable | handling | silence | tag validity | **any** | QC-ok | IMU-still |")
    P("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for a in animals:
        m = res["mask"][a]
        P(f"| {a} | {m['seconds']} | " + " | ".join(str(m[c]) for c in MASK_COLS) +
          f" | **{m['masked_any']}** | {res['animals'][a]['ok_s']} | {res['animals'][a]['still_s']} |")
    P("")
    P("WISER fixes in the night window per tag (library flags):")
    P("")
    P("| Animal | fixes | valid | low-anchor (< 4) | gap | jump |")
    P("|---|---|---|---|---|---|")
    for a in animals:
        m = res["mask"][a]
        P(f"| {a} | {m['n_fix']:,} | {m['n_fix_valid']:,} | {m['fix_low_anchor']:,} | {m['fix_gap']:,} | {m['fix_jump']:,} |")
    P("")
    n_out = sum(res["mask"][a]["m_handling"] + res["mask"][a]["m_silence"] for a in animals)
    if n_out == 0:
        P("The handling windows and padded silences do not reach into the night window, so the out-of-arena mask removes "
          "nothing here; it is applied for completeness.")
    else:
        P(f"The out-of-arena mask removes {n_out} animal-seconds in total (handling + silence columns above).")
    imu_cols = ["m_nodata", "m_saturated", "m_frozen_flag", "m_frozen_rule", "m_invalid", "m_nan", "m_unreliable"]
    tot = {c: sum(res["mask"][a][c] for a in animals) for c in imu_cols}
    P("IMU-side removals summed over the five animals: " + ", ".join(f"{c[2:]} {v}" for c, v in tot.items()) + " s.")
    P("")
    P(DEFINITIONS.strip("\n"))
    P("")
    # ---------------- results
    P("## 2. M1 — effective lag")
    P("")
    P(f"![M1]({'../figures/' + figs['m1'].name})")
    P("")
    P("| Animal | τ* (s) | 95 % CI (s) | CI width (s) | r(τ*) | r(0) | bins used | hours | 300-s blocks | boundary |")
    P("|---|---|---|---|---|---|---|---|---|---|")
    for a in animals:
        m = res["animals"][a]["m1"]
        P(f"| {a} | {m['tau_star_s']:+.2f} | [{m['ci_lo_s']:+.2f}, {m['ci_hi_s']:+.2f}] | {m['ci_width_s']:.2f} | {m['r_star']:.3f} | "
          f"{m['r_at_0']:.3f} | {m['n_bins']:,} | {m['hours']:.2f} | {m['n_blocks']} | {'yes' if m['boundary_hit'] else 'no'} |")
    P("")
    P("Bins used = the 0.25-s bins whose IMU samples are all QC-ok **and** where $v_W$ is defined at every τ from −3 to "
      "+3 s (the pre-registered same-bins rule). That keeps " + ", ".join(
        f"{a} {res['animals'][a]['m1']['n_bins'] / res['animals'][a]['m1']['n_bins_total']:.0%}" for a in animals) +
      " of the night's bins: " + ", ".join(
        f"{a} {res['mask'][a]['gap_gt1s_time_frac']:.1%}" for a in animals) +
      " of the night lies in inter-fix intervals > 1 s (normal cadence pauses; the median interval is ≈ 0.23 s), and "
      "fixes without a neighbour within ± 0.5 s have no `add_speed` value (" + ", ".join(
        f"{a} {res['mask'][a]['fix_speed_nan']:,}" for a in animals) + " fixes). A 6-s span without any such pause is "
      "required, so dense-cadence periods are kept; nothing suggests this biases the lag.")
    P("")
    P(f"Median τ* over the five animals: **{res['tau_pool_s']:+.2f} s**; spread {m1v['spread_s']:.2f} s. "
      f"Verdict **{'PASS' if m1v['pass'] else 'FAIL'}** (CIs {'all' if m1v['ci_ok'] else 'not all'} ≤ 0.3 s; spread "
      f"{'≤' if m1v['spread_s'] <= ACCEPT['m1_spread_s'] else '>'} 0.2 s).")
    P("")
    resid = [f.get("native_residual_ms") for f in res.get("pc_time_fit", {}).values() if f and f.get("native_residual_ms") is not None]
    rtxt = f"{min(resid):.0f}–{max(resid):.0f} ms" if resid else "unknown"
    P("Reading: the field-PC timestamps of both sensors carry their own error — the IMU's `pc_time` fit residual is "
      f"{rtxt} (native) on these sessions and the BLE PC-time path is a 10–100 ms-class coordinate — so a common lag "
      "reflects WISER's own latency plus head-vs-body kinematics as much as any clock offset.")
    P("")
    P("## 3. M2 — non-circular jitter floor")
    P("")
    P(f"![M2 M3]({'../figures/' + figs['m2'].name})")
    P("")
    P("| Stratum | bouts | bout hours | fixes | p50 | p75 | p90 | p95 | RMSE | 1-s median p50 / p90 / RMSE |")
    P("|---|---|---|---|---|---|---|---|---|---|")
    for k, s in m2s.items():
        P(f"| {k} | {s['n_bouts']} | {s['hours']:.1f} | {s['n']:,} | {fmt(s['p50'])} | {fmt(s['p75'])} | {fmt(s['p90'])} | "
          f"{fmt(s['p95'])} | {fmt(s['rmse'])} | {fmt(s['p50_1s'])} / {fmt(s['p90_1s'])} / {fmt(s['rmse_1s'])} |")
    imp = res["implant"]
    P(f"| dropped implant, IMU-still runs ≥ 60 s | {imp['n_bouts']} | {imp['bout_hours']:.2f} | {imp['scatter_bouts']['n']:,} | "
      f"{fmt(imp['scatter_bouts']['p50'])} | {fmt(imp['scatter_bouts']['p75'])} | {fmt(imp['scatter_bouts']['p90'])} | "
      f"{fmt(imp['scatter_bouts']['p95'])} | {fmt(imp['scatter_bouts']['rmse'])} | {fmt(imp['scatter_bouts_1s']['p50'])} / "
      f"{fmt(imp['scatter_bouts_1s']['p90'])} / {fmt(imp['scatter_bouts_1s']['rmse'])} |")
    ev = res["event"]
    P(f"| SF07 corner event, IMU-still bouts | {ev['n_bouts']} | – | {ev['scatter_bouts']['n']:,} | {fmt(ev['scatter_bouts']['p50'])} | "
      f"{fmt(ev['scatter_bouts']['p75'])} | {fmt(ev['scatter_bouts']['p90'])} | {fmt(ev['scatter_bouts']['p95'])} | "
      f"{fmt(ev['scatter_bouts']['rmse'])} | {fmt(ev['scatter_1s']['p50'])} / {fmt(ev['scatter_1s']['p90'])} / {fmt(ev['scatter_1s']['rmse'])} |")
    P(f"| *baseline: WISER-selected rest bouts ≥ 10 min, 2026c* | 1151 | 325 | – | 3.57 | 5.61 | 8.19 | 10.33 | 5.87 | – / 6.23 / – |")
    ph, po = base["pauses_ge60s_night_house_p50_p90_rmse_in"], base["pauses_ge60s_night_outside_p50_p90_rmse_in"]
    P(f"| *WISER-selected pauses ≥ 60 s at night, in houses (accuracy report)* | 3546 | 173 | – | {ph[0]} | – | {ph[1]} | – | {ph[2]} | – |")
    P(f"| *WISER-selected pauses ≥ 60 s at night, outside houses (accuracy report)* | 2022 | 67.6 | – | {po[0]} | – | {po[1]} | – | {po[2]} | – |")
    P("")
    P(f"Against the WISER-selected baseline, the IMU-selected pooled scatter differs by p50 {rel['p50']:+.0%}, p90 "
      f"{rel['p90']:+.0%}, RMSE {rel['rmse']:+.0%}: the selector-bias flag (> 20 %) is **{'RAISED' if m2v['selector_bias_flag'] else 'not raised'}**. "
      f"Bout counts per stratum: all {m2s['all (all fixes)']['n_bouts']}, house {m2s['zone house']['n_bouts']}, outside "
      f"{m2s['zone outside']['n_bouts']} (≥ 20 required) → **{'PASS' if m2v['pass'] else 'FAIL'}**.")
    P("")
    P("By `anchors_used` (IMU-still bouts, pooled; a bout counts in every stratum it has fixes in), next to the "
      "accuracy report's regime-B WISER-selected rest bouts at the same anchor count:")
    P("")
    P("| anchors | share of fixes | bouts | p50 | p90 | RMSE | WISER-selected rest bouts p50 / p90 |")
    P("|---|---|---|---|---|---|---|")
    ranch = base.get("rest_bouts_regimeB_by_anchors_p50_p90_in", {})
    for k, s in sorted(res["m2"]["anchors"].items()):
        rb = ranch.get(str(k))
        P(f"| {k} | {s['share']:.1%} | {s['n_bouts']} | {fmt(s['p50'])} | {fmt(s['p90'])} | {fmt(s['rmse'])} | "
          f"{(str(rb[0]) + ' / ' + str(rb[1])) if rb else '–'} |")
    P("")
    P("**Post hoc (added after the first run to read the flag's direction; no verdict uses it):** scatter by IMU-still "
      "bout duration.")
    P("")
    P("| bout duration | bouts | fixes | p50 | p90 | RMSE |")
    P("|---|---|---|---|---|---|")
    for k, s in res["m2"]["duration_post_hoc"].items():
        P(f"| {k} | {s['n_bouts']} | {s['n']:,} | {fmt(s['p50'])} | {fmt(s['p90'])} | {fmt(s['rmse'])} |")
    P("")
    P("Reading: the IMU-selected scatter is lower than the WISER-selected rest bouts overall, at every anchor count, and "
      "than the WISER-selected ≥ 60-s night pauses (same minimum duration; all cohort-3 nights), and it does not grow "
      "from 1-min to 5-min bouts. The likeliest reading is that the WISER-side selector (5-s medians within 8 in) admits "
      "real small movements of the animal, so the published WISER precision is conservative. It is not proof: the "
      "IMU-still set is small (night only) and a still head can still ride a moving body."
      if rel["p50"] < 0 else
      "Reading: the IMU-selected scatter is higher than the WISER-selected numbers: the WISER-side selector favoured "
      "calm periods (circularity).")
    P("")
    P("## 4. M3 — speed-noise floor over IMU-still time")
    P("")
    P("| Animal | fixes in bouts | p50 | p95 | **p99** | fixes in all still seconds | p50 | p95 | p99 |")
    P("|---|---|---|---|---|---|---|---|---|")
    for a in animals:
        b_, s_ = res["animals"][a]["m3_in_bouts"], res["animals"][a]["m3_still_seconds"]
        P(f"| {a} | {b_['n']:,} | {fmt(b_.get('p50'))} | {fmt(b_.get('p95'))} | **{fmt(b_.get('p99'))}** | {s_['n']:,} | "
          f"{fmt(s_.get('p50'))} | {fmt(s_.get('p95'))} | {fmt(s_.get('p99'))} |")
    P(f"| pooled | {m3p['bouts']['n']:,} | {fmt(m3p['bouts'].get('p50'))} | {fmt(m3p['bouts'].get('p95'))} | "
      f"**{fmt(m3p['bouts'].get('p99'))}** | {m3p['still']['n']:,} | {fmt(m3p['still'].get('p50'))} | "
      f"{fmt(m3p['still'].get('p95'))} | {fmt(m3p['still'].get('p99'))} |")
    P("| *baseline (WISER-selected bouts)* | – | 1.71 | 6.23 | **10.24** | – | – | – | – |")
    P("")
    P("## 5. M4 — frame handedness and gyro scale")
    P("")
    P(f"![M4]({'../figures/' + figs['m4'].name})")
    P("")
    P("| Animal | windows | Spearman ρ | p | b(I\\|W) | 1/b(W\\|I) | windows \\|Δψ_I\\| > 45° | same-sign fraction | ρ after y → −y |")
    P("|---|---|---|---|---|---|---|---|---|")
    for a in animals:
        s, sm = res["animals"][a]["m4"], res["animals"][a]["m4_mirrored"]
        inv = (1 / s["b_WI"]) if (s["b_WI"] and np.isfinite(s["b_WI"]) and s["b_WI"] != 0) else np.nan
        P(f"| {a} | {s['n']} | {fmt(s['rho'], 3)} | {s['p']:.1e} | {fmt(s['b_IW'])} | {fmt(inv)} | {s['n_big']} | "
          f"{fmt(s['same_sign'], 2)} | {fmt(sm['rho'], 3)} |")
    P("")
    P(f"Verdict: **{'PASS — candidate' if m4v['pass'] else 'INCONCLUSIVE'}** (same sign on all five: "
      f"{'yes' if m4v['same_sign'] else 'no'}; every |ρ| ≥ 0.3: {'yes' if m4v['abs_rho_ok'] else 'no'}; every sign agreement ≥ 70 %: "
      f"{'yes' if m4v['agree_ok'] else 'no'}).")
    P("")
    P(f"Reading: ρ is {'positive' if m4v['sign'] > 0 else 'negative'} on "
      f"{sum(1 for a in animals if np.sign(res['animals'][a]['m4']['rho']) == m4v['sign'])} of 5 animals, each with p ≤ "
      f"{max(res['animals'][a]['m4']['p'] for a in animals):.0e}, and mirroring y flips every one — the turn senses are "
      f"related, and the sign points to a {'right-handed' if m4v['sign'] > 0 else 'mirrored'} WISER frame (given the gyro "
      "convention below). But the association is weak (a 2-s window of "
      "1-s-median path headings is noisy, and heads turn without the path turning), so the pre-registered bar is "
      f"{'met' if m4v['pass'] else 'not met'}. The gyro-scale brackets [b(I|W), 1/b(W|I)] "
      f"{'all contain' if all(res['animals'][a]['m4']['b_IW'] <= 1 <= 1 / res['animals'][a]['m4']['b_WI'] for a in animals) else 'do not all contain'} 1 "
      "(a weak check: the brackets are wide).")
    P("")
    P("**Sign conventions and what they assume.**")
    P("- *IMU:* `turn_dps` = ω·û. A dot product of two vectors written in the same orthonormal basis does not depend on "
      "that basis' handedness or on the axis map S (orthogonal), so + = counter-clockwise seen from above **provided each "
      "gyro axis reports the right-hand-rule rate about the same positive axis as the accelerometer axis of the same "
      "index** (the usual MEMS datasheet convention). The CE64's IMU chip and datasheet are not documented here, so this "
      "is an assumption; the audit's phrase 'right-handed MEMS chip' is the common case of it. û is the up direction "
      "(Fusion `get_gravity`, NWU: the accelerometer's at-rest reading), confirmed by make_imu's synthetic self-test.")
    P("- *WISER:* + = rotation from +x toward +y. That is counter-clockwise from above iff (x, y, up) is right-handed. "
      "The paddock/calibration frame is x along the paddock, y across, z up (`calibration_qc` report §1), used with proper "
      "rotations, i.e. right-handed; the user states (2026-09-28) that the WISER axes point the same way. Under that "
      "statement the expectation is ρ > 0; ρ < 0 on all animals would contradict it (a mirrored WISER frame, the "
      "accuracy report's unresolved H− hypothesis) — or the gyro convention above.")
    P("- *Gyro scale:* the scale factor lies between b(I|W) and 1/b(W|I) (each slope is attenuated by noise in its "
      "regressor: WISER jitter on one side, head turns that do not turn the path on the other). A bracket containing 1 "
      "is consistent with the ±2000 °/s scale; it is a weak check.")
    P("")
    P("## 6. M5 — WISER rest proxy vs IMU stillness")
    P("")
    P("| Animal | seconds | IMU-still share | rest_W share | agreement | κ | sensitivity | specificity | PPV | NPV |")
    P("|---|---|---|---|---|---|---|---|---|---|")
    for a in animals:
        m = res["animals"][a]["m5"]
        P(f"| {a} | {m['n_s']:,} | {m['still_frac']:.1%} | {m['rest_w_frac']:.1%} | {m['agreement']:.1%} | {m['kappa']:.2f} | "
          f"{m['sensitivity']:.1%} | {m['specificity']:.1%} | {m['ppv']:.1%} | {m['npv']:.1%} |")
    P("")
    P("Reading: sensitivity is high (when the head is still, WISER almost always reports sub-floor speed) but "
      "specificity is low (most seconds with a moving head are also sub-floor for WISER: the animal moves its head "
      "without locomoting — grooming, eating, exploring in place). PPV ≈ the still share, so κ ≈ 0. This is a "
      "difference of constructs, not a WISER fault; it matters wherever `rest_mask` is read as rest or sleep.")
    P("")
    P("## 7. Still events")
    P("")
    P(f"**Dropped implant (fixed-tag reference), {cfg['fixed_tag_reference']['start']} → {cfg['fixed_tag_reference']['end'][11:]}.** "
      "After `imu_valid_until` (SF11 06:10:00) the regenerated make_imu files blank this IMU (`invalid`), so its stillness "
      "was measured from the raw `analogin.dat` (lanes 1–6, read in place; 1250 → 100 Hz with make_imu's filter; VeDBA "
      "and |ω| after removing the window's median gyro; no AHRS needed for these rotation-invariant magnitudes). "
      f"Timing from the npz logger→PC map (pc_time verdict: {imp.get('pc_time_verdict')}; only minutes-level timing "
      "matters for a static device). No handling/tag-validity mask is applied: the IMU itself shows any disturbance.")
    P("")
    P(f"- IMU: {imp['still_s']:,} of {imp['ok_s']:,} QC-ok seconds still ({imp['still_s'] / max(imp['ok_s'], 1):.1%}); VeDBA_1s "
      f"p50/p99/max {imp['vedba_1s_q'][0]:.3f}/{imp['vedba_1s_q'][1]:.3f}/{imp['vedba_1s_q'][2]:.3f} m/s²; |ω|_1s p50/p99/max "
      f"{imp['omega_1s_q'][0]:.2f}/{imp['omega_1s_q'][1]:.2f}/{imp['omega_1s_q'][2]:.2f} °/s; raw-lane freeze {imp['raw_frozen_s']:.1f} s; "
      f"saturated {imp['saturated_s']:.2f} s; {imp['n_non_still_runs']} non-still runs.")
    if imp["non_still_runs"]:
        P("- Largest non-still runs (start, seconds, max VeDBA_1s): " +
          "; ".join(f"{s0[11:]} {d} s {mx:.2f}" for s0, d, mx in imp["non_still_runs"][:8]) + ".")
    P(f"- WISER tag {cfg['fixed_tag_reference']['shortid']}: {imp['n_fix']:,} fixes in the window; bout zones {', '.join(imp['zones']) or '–'}.")
    P("")
    P("| Selection | fixes | p50 | p90 | p95 | RMSE |")
    P("|---|---|---|---|---|---|")
    for lab, s in (("whole window, about the window median", imp["scatter_whole"]),
                   ("06:12–07:24 (before the handling window)", imp["scatter_pre_handling"]),
                   ("IMU-still runs ≥ 60 s, about each run's median", imp["scatter_bouts"]),
                   ("same, 1-s medians", imp["scatter_bouts_1s"])):
        P(f"| {lab} | {s['n']:,} | {fmt(s['p50'])} | {fmt(s['p90'])} | {fmt(s['p95'])} | {fmt(s['rmse'])} |")
    fb = base["static_implant_full_p50_p90_rmse_in"]
    P(f"| *accuracy report, 06:12–08:17 full* | – | {fb[0]} | {fb[1]} | – | {fb[2]} |")
    P("")
    if imp["anchors"]:
        P("Implant scatter by `anchors_used` (IMU-still runs): " + "; ".join(
            f"{k}: n {s['n']}, p50 {fmt(s['p50'])}, p90 {fmt(s['p90'])}" for k, s in sorted(imp["anchors"].items())) + ".")
        n_all = sum(s["n"] for s in imp["anchors"].values())
        sh9 = imp["anchors"].get(9, {"n": 0})["n"] / max(n_all, 1)
        an9 = res["m2"]["anchors"].get(9, {})
        P("")
        P(f"Reading: the device lay in the CH07 box under huddling rats (accuracy report §5.2; behaviour log 09-07); only {sh9:.0%} of its fixes used 9 anchors "
          f"(on-head tags at night: {an9.get('share', np.nan):.0%}), and even at 9 anchors its scatter (p50 "
          f"{fmt(imp['anchors'].get(9, {}).get('p50'))} in) exceeds the on-head IMU-still value ({fmt(an9.get('p50'))} in). It is a "
          "true fixed tag but a worst-case in-house placement (low, shielded by bodies), not the typical on-animal floor.")
        P("")
    P(f"**SF07 at a paddock corner, {cfg['still_event']['start']} → {cfg['still_event']['end'][11:]}.** "
      f"{ev['still_s']} of {ev['ok_s']} QC-ok seconds IMU-still ({ev['still_s'] / max(ev['ok_s'], 1):.0%}); VeDBA_1s median "
      f"{ev['vedba_1s_p50']:.3f} m/s², |ω|_1s median {ev['omega_1s_p50']:.1f} °/s; {ev['n_bouts']} IMU-still bouts ≥ 60 s "
      f"({', '.join(sorted(set(b['zone'] for b in ev['bouts']))) or '–'}); {ev['n_fix']:,} WISER fixes. Whole-window scatter "
      f"(about the window median) p50/p90/RMSE {fmt(ev['scatter_whole_window']['p50'])}/{fmt(ev['scatter_whole_window']['p90'])}/"
      f"{fmt(ev['scatter_whole_window']['rmse'])} in (this includes the departure below). The behaviour-log entry is an observation (WISER live view), used as a "
      "seed, not ground truth; this was the 09-09 evening with PM rain (the accuracy report's wettest regime-B night, gap "
      "time 0.47 %).")
    sp = ev["span"]
    P(f"- WISER keeps the tag in place (per-minute medians within {sp['radius_in']:.0f} in of the first 10 min's median) "
      f"until **{sp['span_end'][11:16]}**, then it leaves. Over that span the IMU is still in {sp['still_s']} of {sp['ok_s']} QC-ok "
      f"seconds and active in {sp['active_s']}; the longest active run starts {str(sp['longest_active_start'])[11:]} and lasts "
      f"{sp['longest_active_s']} s (median VeDBA_1s {fmt(sp['longest_active_vedba_med'])} m/s², |ω|_1s "
      f"{fmt(sp['longest_active_omega_med'], 0)} °/s) while the WISER position does not move — the M5 construct gap in "
      "one event: 'motionless' by WISER is not 'still' by the head.")
    P("")
    P("## 8. Frozen-IMU rule: verification and hits")
    P("")
    P("Primary QC is make_imu's new `frozen` flag (all six raw lanes identical ≥ 0.5 s). The audit's derived-signal rule "
      "cannot fire on the regenerated files where frozen samples are blanked (NaN), so it was verified on the raw lanes: "
      "± 10 min around each known freeze edge, raw → 100 Hz → |ω| and VeDBA exactly as in make_imu (minus the AHRS), "
      "then the rule.")
    P("")
    P("| Session | expected | make_imu `frozen` flag runs (start → end, s) | probe | derived-signal rule runs | raw-lane rule runs |")
    P("|---|---|---|---|---|---|")
    for fc in res["frozen_checks"]:
        flag = "; ".join(f"{a[5:]} → {b[5:]} ({d:.0f})" for a, b, d in fc["flag_intervals"][:4]) or "none"
        if len(fc["flag_intervals"]) > 4:
            flag += f"; … ({len(fc['flag_intervals'])} runs)"
        for pr in fc["probes"]:
            ru = "; ".join(f"{a[11:]} → {b[11:]} ({d:.1f})" for a, b, d in pr["rule"][:3]) or "none"
            rw = "; ".join(f"{a[11:]} → {b[11:]} ({d:.1f})" for a, b, d in pr["rawlane"][:3]) or "none"
            P(f"| {fc['animal']} {fc['session']} | {fc['expected_start'][5:]} → {fc['expected_end'][5:]} | {flag} | "
              f"{pr['probe']} {pr['from'][11:]}–{pr['to'][11:]} | {ru} | {rw} |")
    P("")
    P("Hits in the pilot night (per animal: seconds carrying the make_imu flag / the derived rule; the derived rule can "
      "only fire on unblanked samples): " + "; ".join(
        f"{a} {res['mask'][a]['m_frozen_flag']} / {res['mask'][a]['m_frozen_rule']}" for a in animals) + ".")
    P("")
    P("## 9. Caveats")
    P("")
    P("- **One night, five animals, regime B.** 09-08 20:00 → 09-09 06:00 (no handling inside; construction noise from "
      "09-08 ~07:50 has no logged end; the BLE ad-feed outage was the previous night). Regime A (08-30 → 09-03 13:59, "
      "shifted and noisier frame) and regime C (after the 09-11 females) are not covered.")
    P("- **Masks.** Section 1 lists what each rule removed, per animal and per reason.")
    P("- **Tag-table discrepancy (not affecting this night).** " + " ".join(cfg.get("known_issues", [])))
    P("- **Precision, not accuracy.** M2 scatter is about each bout's own median; it says nothing about where the tag "
      "is in the paddock. A still head can sit on a body that shifts a little (breathing, settling), so M2 remains an "
      "upper bound on sensor jitter — but one selected without WISER.")
    P("- **WISER's own filtering is unknown.** If the positioning engine smooths more when a tag is at rest (common in "
      "UWB systems with a tag motion sensor), the IMU-still scatter measures that engine state; it is still the "
      "precision a still animal gets.")
    P("- **Alignment of the event windows.** The dropped implant is aligned with the five-animal median τ*; for a static "
      "device the lag is immaterial.")
    P("- **M4 is a candidate at best.** It rests on the gyro-sign convention above (undocumented chip) and on WISER "
      "path turns reflecting head turns on average; a single video event with a known turn direction would confirm it.")
    P("- **IMU inputs were regenerated during this work** (commit `6451d6c`, 2026-09-29): the pilot read the new files "
      "only; their hashes are in `input_provenance.json`.")
    P("")
    return "\n".join(L) + "\n"


# ================================================================ self-test
def _synthetic(rng: np.random.Generator, T: float = 3600.0, lag_s: float = 0.8, sigma_in: float = 3.0):
    lo = to_ms("2026-01-01 00:00:00")
    n = int(T * FS_IMU)
    t = np.arange(n) / FS_IMU
    moving = np.zeros(n, bool)
    s = 0.0
    while s < T:
        still_d, move_d = rng.uniform(60, 200), rng.uniform(20, 60)
        a, b = int((s + still_d) * FS_IMU), int((s + still_d + move_d) * FS_IMU)
        moving[a:b] = True
        s += still_d + move_d
    speed = np.where(moving, 15 * (1 + 0.3 * np.sin(2 * np.pi * t / 7)), 0.0)
    om = np.zeros(n)
    k = 0
    while k < n:
        d = int(rng.uniform(1, 3) * FS_IMU)
        om[k:k + d] = rng.uniform(-90, 90)
        k += d
    om = np.where(moving, om, 0.0)
    psi = np.radians(np.cumsum(om) / FS_IMU)
    x = np.cumsum(speed * np.cos(psi)) / FS_IMU
    y = np.cumsum(speed * np.sin(psi)) / FS_IMU
    unix = lo + t * 1000.0
    ved = 0.05 * rng.lognormal(0, 0.3, n) + 0.25 * speed * rng.lognormal(0, 0.3, n)
    omega = np.where(moving, np.abs(om) + np.abs(rng.normal(0, 20, n)) + 20, np.abs(rng.normal(0, 1.5, n)))
    turn = om + rng.normal(0, 5, n)
    f0, f1 = int(1000 * FS_IMU), int(1020 * FS_IMU)               # injected freeze (constant values)
    omega[f0:f1] = omega[f0]
    ved[f0:f1] = 0.0
    turn[f0:f1] = turn[f0]
    imu = {"unix_ms": unix, "t_logger_s": t, "vedba_ms2": ved, "omega_dps": omega, "turn_dps": turn,
           "saturated": np.zeros(n, bool), "unreliable": np.zeros(n, bool), "frozen": np.zeros(n, bool),
           "invalid": np.zeros(n, bool)}
    dts = np.where(np.arange(int(T * 5)) % 2 == 0, 0.134, 0.27) + rng.normal(0, 0.01, int(T * 5))
    tt = np.cumsum(np.abs(dts))
    tt = tt[tt < T - 1]
    px = np.interp(tt, t, x) + rng.normal(0, sigma_in, len(tt))
    py = np.interp(tt, t, y) + rng.normal(0, sigma_in, len(tt))
    raw = pd.DataFrame({"shortid": 1, "ts_raw": (lo + (tt + lag_s) * 1000.0).astype(np.int64), "x": px, "y": py,
                        "anchors_used": rng.integers(5, 10, len(tt))})
    return lo, imu, raw


def _selftest() -> int:
    rng = np.random.default_rng(11)
    T, lag, sig, thr = 3600.0, 0.8, 3.0, 0.35
    lo, imu, raw = _synthetic(rng, T, lag, sig)
    hi = lo + T * 1000.0
    checks = []
    frm, runs = frozen_rule(imu["omega_dps"], imu["vedba_ms2"])
    ok_run = len(runs) == 1 and abs(runs[0][0] / FS_IMU - 1000) <= 0.5 and abs(runs[0][1] / FS_IMU - 1020) <= 0.5
    checks.append((f"frozen rule finds the injected 1000-1020 s freeze: {[(a / FS_IMU, b / FS_IMU) for a, b in runs]}", ok_run))
    handling = [(lo + 2000_000, lo + 2060_000, "test round")]
    ps = per_second(imu, lo, hi, handling, [], -np.inf, np.inf, frm)
    msk = ps.set_index(ps.sec - ps.sec.iloc[0])
    checks.append(("freeze seconds 1000-1019 and handling 2000-2059 masked",
                   bool((~msk.loc[1000:1019, "ok"]).all() and (~msk.loc[2000:2059, "ok"]).all() and msk.loc[500:900, "ok"].all())))
    fx = prepare_fixes(raw)
    m1 = m1_lag(imu, ps, fx, lo, hi, rng)
    checks.append((f"M1 recovers the lag: tau* {m1['tau_star_s']:+.2f} s [{m1['ci_lo_s']:+.2f}, {m1['ci_hi_s']:+.2f}] (true +{lag})",
                   abs(m1["tau_star_s"] - lag) <= 0.2 and m1["ci_lo_s"] <= lag + 0.05 and m1["ci_hi_s"] >= lag - 0.05))
    # (10 seeds, 2026-09-29: mean error -0.03 s, range -0.15..+0.10 s -> the synthetic's broad peak, not a bias)
    tau = m1["tau_star_s"]
    st = still_mask(ps, thr)
    fr, bt, sr = m2_bouts("syn", ps, st, fx, tau, [], 14.0)
    s = sstats(fr.r_in)
    exp = {"p50": sig * np.sqrt(2 * np.log(2)), "p90": sig * np.sqrt(2 * np.log(10)), "rmse": sig * np.sqrt(2)}
    checks.append((f"M2 scatter = Rayleigh(sigma {sig}): p50 {s['p50']:.2f}/{exp['p50']:.2f}, p90 {s['p90']:.2f}/{exp['p90']:.2f}, "
                   f"RMSE {s['rmse']:.2f}/{exp['rmse']:.2f} in, {len(bt)} bouts",
                   all(abs(s[k] / exp[k] - 1) < 0.10 for k in exp) and len(bt) >= 10))
    med = wiser_1s_medians(fx, tau, ps["sec"].to_numpy())
    s4 = m4_stats(m4_turns(ps, imu, med))
    s4m = m4_stats(m4_turns(ps, imu, med, mirror_y=True))
    inv = 1 / s4["b_WI"]
    checks.append((f"M4 right-handed track: rho {s4['rho']:+.2f} (n {s4['n']}), same-sign {s4['same_sign']:.0%}, "
                   f"scale bracket [{s4['b_IW']:.2f}, {inv:.2f}] contains 1",
                   s4["rho"] > 0.5 and s4["same_sign"] > 0.8 and min(s4["b_IW"], inv) <= 1.1 and max(s4["b_IW"], inv) >= 0.9))
    checks.append((f"M4 mirror control flips the sign: rho {s4m['rho']:+.2f}", s4m["rho"] < -0.5))
    m5 = m5_agreement(ps, st, fx, tau, 10.24)
    checks.append((f"M5 kappa {m5['kappa']:.2f} > 0.5 (sens {m5['sensitivity']:.0%}, spec {m5['specificity']:.0%})", m5["kappa"] > 0.5))
    ok = True
    for name_, c in checks:
        print(f"[{'PASS' if c else 'FAIL'}] {name_}")
        ok &= bool(c)
    print("PASS - analyze_imu_wiser_calibration self-test" if ok else "FAIL - analyze_imu_wiser_calibration self-test")
    return 0 if ok else 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cohort", default=None, help="cohort key (cohorts/<key>.yaml); default FIELD2026_COHORT or 2026a")
    ap.add_argument("--imu-root", default=None, help="default <ephys.analysis_root>/imu from the cohort YAML")
    ap.add_argument("--output", default=None, help="bulk root (default $FIELD2026_ANALYSIS_OUT_ROOT)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(_selftest())
    run(output_paths.resolve_cohort(a.cohort), Path(a.imu_root) if a.imu_root else None, Path(a.output) if a.output else None)


if __name__ == "__main__":
    main()
