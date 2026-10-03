r"""WISER failure audit with the head IMU as the stillness truth (cohort 2026c).

Plan: implementation_plan/2026-10-02-wiser-failure-audit.md (approved by the user 2026-10-02, "搞吧").
Report (full Definitions section): results/<cohort>/wiser_baseline/reports/wiser_baseline_failure_audit_<cohort>.md

The UWB tag and the IMU are both on the head, so while the head IMU is still the tag is still and ANY WISER displacement
is WISER error. While the animal moves, physical plausibility and the IMU activity state are the (weaker) truth.

  certified stillness  gate-v2 strict windows (100 Hz) where they exist; elsewhere S50 = the same rule on the 50-Hz
                       make_imu record (accelerometer rebuilt from the Fusion quaternion + earth linear acceleration,
                       ellipsoid self-calibrated as the A3 chain); windows merged into segments (gap <= 2 s without
                       movement), >= 30 s primary, >= 10 s secondary, 1 s trimmed at both ends
  Q1                   per segment, truth = median raw fix: jitter, 10-s / 60-s drift, crazy-drift events, jumps, fake
                       speed, fake path per minute
  Q2                   the same metrics after B1 / B2 / B2' (position-only, tuned values of the smoothing pilot); V1 / V2
                       (IMU stillness inside) reported as "removed by construction"
  Q3                   nights: impossible speed (> 100 in/s), jumps with a quiet IMU, onset/offset lag vs the IMU
  Q4                   rain vs calm ratios, 10-min block bootstrap, anchors x zone standardisation
  Q5                   the bar for V6

Inputs (all read-only): WISER fix caches (built once from the SQLite copy, mode=ro, by build_imu_wiser_cache.wiser_night),
make_imu 50-Hz npz, the gate-v2 strict windows, weather CSVs on F:. Existing scripts are imported, never modified.

Usage:
  python wiser/scripts/analyze_wiser_failure_audit.py --cohort 2026c [--workers 5]
  python wiser/scripts/analyze_wiser_failure_audit.py --report-only <run_dir>    # re-score / re-render from saved tables
  python wiser/scripts/analyze_wiser_failure_audit.py --selftest                 # synthetic data, no field data
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
import analyze_imu_wiser_calibration as C  # noqa: E402  (masks, per-second IMU table, helpers; unmodified)
import analyze_wiser_imu_smoothing as P  # noqa: E402  (B1/B2/B2'/V1/V2 smoothers, IMU states; unmodified)
import build_imu_wiser_cache as B  # noqa: E402  (A2 WISER fix cache writer; unmodified)
import analyze_imu_attitude_gate_v2 as GV2  # noqa: E402  (strict still-window kernel, video lookup; unmodified)
import analyze_wiser_ins_fusion as V4  # noqa: E402  (ellipsoid accelerometer fit; unmodified)
from cohorts import load_cohort  # noqa: E402

try:
    from numba import njit
except Exception:  # noqa: BLE001
    def njit(*a, **k):
        if a and callable(a[0]):
            return a[0]
        return lambda f: f

DIRECTION = "wiser_baseline"
NAME = "wiser_failure_audit"
STEM = f"{DIRECTION}_failure_audit"
G = 9.81
FS = 50.0
METHODS = ["raw", "B1", "B2", "B2p", "B2pb", "V1", "V2"]
POS_ONLY = ["raw", "B1", "B2", "B2p"]
LABEL = {"raw": "raw fixes", "B1": "B1 median-7", "B2": "B2 robust CV", "B2p": "B2′ (+drift, p)", "B2pb": "B2′ p+b",
         "V1": "V1 ZUPT (IMU)", "V2": "V2 IMU-switched q (IMU)"}
ANCHOR_BINS = ["9", "8", "7", "<=6"]


def log_to(fh, msg: str) -> None:
    print(msg, flush=True)
    if fh is not None:
        fh.write(msg + "\n")
        fh.flush()


# ====================================================================================================== config/context
def load_cfg(cohort: str, path: str | None = None) -> dict:
    cp = Path(path) if path else REPO / "wiser" / "configs" / f"wiser_failure_audit_{cohort}.json"
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    cfg["_path"] = str(cp)
    cfg["_cohort"] = cohort
    return cfg


def context(cfg: dict) -> dict:
    tz = cfg["tz"]
    coh = load_cohort(cfg["_cohort"])
    ids = pd.read_csv(REPO / coh["identities"], dtype={"shortid": int, "physical_tag_id": str})
    ids["from_ms"] = pd.to_datetime(ids["valid_from"], utc=True).astype("int64") // 10**6
    ids["until_ms"] = pd.to_datetime(ids["valid_until"], utc=True).astype("int64") // 10**6
    hj = json.loads((REPO / cfg["handling_json"]).read_text(encoding="utf-8"))
    handling_raw = [(C.to_ms(a, tz), C.to_ms(b, tz), note) for a, b, note in hj["windows"]]
    pad = float(cfg["handling_pad_s"]) * 1000
    handling = [(a - pad, b + pad, n) for a, b, n in handling_raw]
    sil = pd.read_csv(cfg["silences_csv"])
    spad = float(cfg["silence_pad_s"]) * 1000
    silences = [(C.to_ms(r.start, tz) - spad, C.to_ms(r.end, tz) + spad, r.kind) for r in sil.itertuples()]
    adc = [(C.to_ms(wd["on_from"], tz), C.to_ms(wd["off_at"], tz), wd["animal"])
           for wd in ((coh.get("ephys") or {}).get("adc_lane") or {}).get("on_windows", [])]
    rois = json.loads((REPO / cfg["rois_json"]).read_text(encoding="utf-8"))
    houses = [r for r in rois["rois"] if r["name"] in cfg["house_rois"]]
    scfg = json.loads((REPO / cfg["smoothing_config"]).read_text(encoding="utf-8"))
    tuned = scfg["tuned"]
    table = {int(k): v for k, v in tuned["anchor_sigma"].items()}
    pb = json.loads((REPO / cfg["ins_fusion_config"]).read_text(encoding="utf-8"))["phase_b"]
    flagged = set()
    for ff in ((coh.get("ephys") or {}).get("field_flags") or []):
        txt = str(ff.get("flag", "")).lower()
        if ff.get("pc_time") is False or "exclude" in txt:
            for s in ff.get("sessions", []):
                flagged.add((ff["animal"], s))
    return {"tz": tz, "coh": coh, "ids": ids, "handling": handling, "handling_raw": handling_raw, "silences": silences,
            "adc": adc, "houses": houses, "thr": C.imu_still_thr(), "tuned": tuned, "table": table, "taus": scfg["tau_star_s"],
            "pb": pb, "flagged": flagged, "scfg": scfg}


# ====================================================================================================== small helpers
def ms_local(ms: float, tz: str = "America/New_York", frac: bool = False) -> str:
    ts = pd.Timestamp(int(round(ms)), unit="ms", tz="UTC").tz_convert(tz)
    return ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if frac else ts.strftime("%Y-%m-%d %H:%M:%S")


def qrot_T(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    """v_head = R(q)^T v_world for unit quaternions q = [w, x, y, z] (head -> world, imufusion convention)."""
    w = q[:, 0]
    qv = -q[:, 1:4]
    t = 2.0 * np.cross(qv, v)
    return v + w[:, None] * t + np.cross(qv, t)


def anchor_bin(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, float)
    return np.where(a >= 9, "9", np.where(a >= 8, "8", np.where(a >= 7, "7", "<=6")))


def zone_of(x: float, y: float, houses: list, buf: float) -> str:
    if not (np.isfinite(x) and np.isfinite(y)):
        return "unknown"
    for roi in houses:
        _, inb = W._rect_membership(np.array([x]), np.array([y]), roi, buf)
        if bool(inb[0]):
            return roi["name"]
    return "outside"


def zone2(z: str) -> str:
    return "house" if str(z).startswith("house") else ("outside" if z == "outside" else "unknown")


# ====================================================================================================== numba kernels
@njit(cache=True)
def _roll_median(t, x, y, c, half, minfix, ox, oy, on):
    """Coordinate-wise median of the points with t in [c_k - half, c_k + half) for sorted centres c (t sorted)."""
    n = t.shape[0]
    i0 = 0
    i1 = 0
    bx = np.empty(max(n, 1))
    by = np.empty(max(n, 1))
    for k in range(c.shape[0]):
        lo = c[k] - half
        hi = c[k] + half
        while i0 < n and t[i0] < lo:
            i0 += 1
        if i1 < i0:
            i1 = i0
        while i1 < n and t[i1] < hi:
            i1 += 1
        m = i1 - i0
        on[k] = m
        if m < minfix or m == 0:
            ox[k] = np.nan
            oy[k] = np.nan
            continue
        for j in range(m):
            bx[j] = x[i0 + j]
            by[j] = y[i0 + j]
        ox[k] = np.median(bx[:m])
        oy[k] = np.median(by[:m])


def roll_median(t: np.ndarray, p: np.ndarray, centers: np.ndarray, half: float, minfix: int) -> tuple[np.ndarray, np.ndarray]:
    c = np.ascontiguousarray(centers, np.float64)
    ox, oy = np.empty(len(c)), np.empty(len(c))
    on = np.zeros(len(c), np.int64)
    if len(c):
        _roll_median(np.ascontiguousarray(t, np.float64), np.ascontiguousarray(p[:, 0], np.float64),
                     np.ascontiguousarray(p[:, 1], np.float64), c, float(half), int(minfix), ox, oy, on)
    return np.column_stack([ox, oy]), on


def interp_track(t: np.ndarray, p: np.ndarray, g: np.ndarray, max_gap: float) -> np.ndarray:
    """Linear interpolation of the track at times g, NaN unless g lies inside an inter-fix gap <= max_gap (or on a fix)."""
    if len(t) < 2:
        return np.full((len(g), 2), np.nan)
    j = np.searchsorted(t, g, side="right")
    jj = np.clip(j, 1, len(t) - 1)
    ok = (j > 0) & (j < len(t)) & ((t[jj] - t[jj - 1]) <= max_gap)
    ok |= np.isin(g, t)
    out = np.column_stack([np.interp(g, t, p[:, 0]), np.interp(g, t, p[:, 1])])
    out[~ok] = np.nan
    return out


def speed_grid(t: np.ndarray, p: np.ndarray, a: float, b: float, step: float, max_gap: float) -> tuple[np.ndarray, np.ndarray]:
    """1-s centred speed v(g) = |p(g + 0.5) - p(g - 0.5)| / 1 s on a grid of step s inside [a + 0.5, b - 0.5]."""
    if b - a < 1.0:
        return np.zeros(0), np.zeros(0)
    g = np.arange(a + 0.5, b - 0.5 + 1e-9, step)
    pa = interp_track(t, p, g - 0.5, max_gap)
    pb = interp_track(t, p, g + 0.5, max_gap)
    return g, np.hypot(*(pb - pa).T) / 1.0


def path_rate(t: np.ndarray, p: np.ndarray, a: float, b: float, max_gap: float) -> tuple[float, float, float]:
    """Path length of the 1-s resampled track inside [a, b] (in), the seconds it covers, and in per minute."""
    s = np.arange(math.ceil(a), math.floor(b) + 1e-9, 1.0)
    if len(s) < 2:
        return np.nan, 0.0, np.nan
    q = interp_track(t, p, s, max_gap)
    d = np.hypot(*np.diff(q, axis=0).T)
    v = np.isfinite(d)
    sec = float(v.sum())
    path = float(d[v].sum())
    return path, sec, (path / (sec / 60.0) if sec > 0 else np.nan)


def find_jumps(t: np.ndarray, p: np.ndarray, thr: float, dt_max: float) -> np.ndarray:
    """Indices k of consecutive pairs (k, k+1) with |p[k+1] - p[k]| > thr and t[k+1] - t[k] <= dt_max."""
    if len(t) < 2:
        return np.zeros(0, np.int64)
    d = np.hypot(*np.diff(p, axis=0).T)
    return np.flatnonzero((d > thr) & (np.diff(t) <= dt_max))


def runs_at_least(mask: np.ndarray, min_len: int) -> list:
    return [(a, b) for a, b in C.true_runs(mask) if b - a >= min_len]


# ====================================================================================================== weather
def load_weather(cfg: dict) -> pd.DataFrame:
    wc = cfg["weather"]
    df = pd.read_csv(wc["cloud_csv"], encoding="utf-8-sig")

    def col(prefix):
        for c in df.columns:
            if c.startswith(prefix):
                return c
        raise KeyError(prefix)
    out = pd.DataFrame({
        "t_local": pd.to_datetime(df[col("Date")], utc=True).dt.tz_convert(cfg["tz"]).dt.tz_localize(None),
        "rain_rate": pd.to_numeric(df[col("Rain Rate")], errors="coerce"),
        "daily_rain": pd.to_numeric(df[col("Daily Rain")], errors="coerce"),
        "wind": pd.to_numeric(df[col("Wind Speed")], errors="coerce"),
        "gust": pd.to_numeric(df[col("Wind Gust")], errors="coerce"),
        "rh": pd.to_numeric(df[col("Humidity")], errors="coerce"),
        "temp": pd.to_numeric(df[col("Outdoor Temperature")], errors="coerce"),
        "dew": pd.to_numeric(df[col("Dew Point")], errors="coerce")})
    out = out.dropna(subset=["t_local"]).drop_duplicates("t_local").sort_values("t_local").reset_index(drop=True)
    inc = out["daily_rain"].diff()
    out["rain_inc"] = np.where(inc < 0, out["daily_rain"], inc.fillna(0.0)).clip(min=0)
    out["t_ms"] = [C.to_ms(str(t), cfg["tz"]) for t in out["t_local"]]
    return out


def local_daily_rain(cfg: dict, date: str) -> float:
    p = Path(cfg["weather"]["local_dir"]) / f"AWN-F8B3B78DEAC9_{date}.csv"
    if not p.exists():
        return np.nan
    d = pd.read_csv(p, encoding="latin-1")
    c = [x for x in d.columns if x.startswith("Daily Rain")]
    v = pd.to_numeric(d[c[0]], errors="coerce") if c else pd.Series(dtype=float)
    return float(v.max()) if len(v.dropna()) else np.nan


def period_weather(wx: pd.DataFrame, lo_ms: float, hi_ms: float, prior_h: float) -> dict:
    sel = (wx.t_ms > lo_ms) & (wx.t_ms <= hi_ms)
    w = wx[sel]
    pri = wx[(wx.t_ms > lo_ms - prior_h * 3.6e6) & (wx.t_ms <= lo_ms)]
    return {"rain_mm": float(w.rain_inc.sum()), "rain_mm_rate_integral": float((w.rain_rate.fillna(0) * 5 / 60).sum()),
            "rain_min": float(5 * (w.rain_rate.fillna(0) > 0).sum()), "rain_prior_mm": float(pri.rain_inc.sum()),
            "wind_mean_mph": float(w.wind.mean()), "gust_p95_mph": float(w.gust.quantile(0.95)), "gust_max_mph": float(w.gust.max()),
            "rh_mean": float(w.rh.mean()), "rh_min": float(w.rh.min()), "rh_max": float(w.rh.max()),
            "dewpoint_depression_mean_c": float((w.temp - w.dew).mean()), "temp_mean_c": float(w.temp.mean()), "n_rows": int(len(w))}


def raining_at(wx: pd.DataFrame, t_ms: np.ndarray, row_s: float) -> np.ndarray:
    """True when the nearest 5-min weather row (within row_s) reports a rain rate > 0 (alignment ~5 min, unverified)."""
    tw = wx.t_ms.to_numpy(float)
    rr = wx.rain_rate.fillna(0).to_numpy(float)
    j = np.clip(np.searchsorted(tw, t_ms), 1, len(tw) - 1)
    jn = np.where(np.abs(tw[j] - t_ms) < np.abs(tw[j - 1] - t_ms), j, j - 1)
    return (rr[jn] > 0) & (np.abs(tw[jn] - t_ms) <= row_s * 1000)


# ====================================================================================================== A2 fix caches
def period_cache_key(pkey: str) -> str:
    return pkey


def ensure_fix_caches(cfg: dict, ctx: dict, fh=None) -> pd.DataFrame:
    """Write missing <root>/<period>/<SFxx>.csv.gz with build_imu_wiser_cache.wiser_night (window +- margin); never overwrite."""
    fc = cfg["fix_cache"]
    root = Path(fc["root"])
    m = float(fc["margin_s"]) * 1000
    tz = ctx["tz"]
    db = Path(cfg["wiser_db"])
    rows, dbi = [], None
    for pkey, p in cfg["periods"].items():
        od = root / period_cache_key(pkey)
        need = [a for a in cfg["animals"] if not (od / f"{a}.csv.gz").exists()]
        if not need:
            continue
        if dbi is None:
            dbi = C.file_info(db)
            if not dbi["sha256"].startswith(cfg["wiser_db_sha256_prefix_expected"]):
                raise SystemExit(f"WISER DB sha256 {dbi['sha256'][:12]} != expected {cfg['wiser_db_sha256_prefix_expected']}")
        lo, hi = C.to_ms(p["start"], tz), C.to_ms(p["end"], tz)
        tags = {a: C.resolve_tag(ctx["ids"], a, lo, hi) for a in need}
        fr, st = B.wiser_night(db, cfg["wiser_table"], tags, lo - m, hi + m, ctx["handling_raw"], ctx["silences"], ctx["adc"],
                               ctx["ids"], tz)
        od.mkdir(parents=True, exist_ok=True)
        for a, f in fr.items():
            pth = od / f"{a}.csv.gz"
            if pth.exists():
                continue
            f.to_csv(pth, index=False)
            inw = (f.t_ms >= lo) & (f.t_ms < hi)
            rows.append({"period": pkey, "animal": a, "shortid": tags[a], "path": str(pth), "rows": len(f), "rows_in_window": int(inw.sum()),
                         "dup_groups_all_tags": st["dup_groups"], "rows_dropped_all_tags": st["rows_dropped"], "db": str(db),
                         "db_sha256": dbi["sha256"], "window_local": json.dumps([C.ms_to_local(lo - m, tz), C.ms_to_local(hi + m, tz)]),
                         "m_handling": int(f.m_handling[inw].sum()), "m_silence": int(f.m_silence[inw].sum()),
                         "m_tag_validity": int(f.m_tag_validity[inw].sum()), "m_adc_lane": int(f.m_adc_lane[inw].sum()),
                         "bytes": pth.stat().st_size, "git_commit": C.git_commit(), "writer": "wiser/scripts/analyze_wiser_failure_audit.py"})
            log_to(fh, f"A2 cache written {pkey} {a}: {len(f):,} fixes ({int(inw.sum()):,} in the window)")
    idx = pd.DataFrame(rows)
    if len(idx):
        ip = root / fc["index"]
        if ip.exists():
            old = pd.read_csv(ip)
            idx = pd.concat([old[~old.path.isin(idx.path)], idx], ignore_index=True)
        idx.to_csv(ip, index=False)
        readme = root / "README.md"
        mark = "<!-- failure-audit caches (analyze_wiser_failure_audit.py) -->"
        txt = readme.read_text(encoding="utf-8") if readme.exists() else ""
        if mark not in txt:
            with open(readme, "a", encoding="utf-8") as f:
                f.write(f"\n\n{mark}\n**Failure-audit periods** (`wiser/scripts/analyze_wiser_failure_audit.py`, 2026-10-02, same function "
                        f"`build_imu_wiser_cache.wiser_night`, same columns, window +- 10 min, never overwriting): `night_20260903`, "
                        f"`night_20260905`, `night_20260906`, `night_20260907`, `night_20260909`, `day_20260905`, `day_20260907`, "
                        f"`day_20260910`. Index: `{fc['index']}`.\n")
    return idx


# ====================================================================================================== IMU
def sessions_for(cfg: dict, ctx: dict, animal: str, lo: float, hi: float) -> list:
    out = []
    for js in sorted((Path(cfg["imu_root"]) / animal).glob("*.imu.json")):
        s = js.name[:-len(".imu.json")]
        if (animal, s) in ctx["flagged"]:
            continue
        j = json.loads(js.read_text(encoding="utf-8"))
        if not j.get("start_local") or not j.get("duration_s"):
            continue
        s0 = C.to_ms(str(j["start_local"])[:23], ctx["tz"])
        s1 = s0 + float(j["duration_s"]) * 1000
        if s1 > lo and s0 < hi:
            out.append({"session": s, "start_local": str(j["start_local"]), "npz": str(js.with_name(f"{s}.imu.npz")),
                        "pc_time": str((j.get("pc_time_fit") or {}).get("verdict") if isinstance(j.get("pc_time_fit"), dict) else j.get("pc_time"))})
    return out


IMU_KEYS = ("omega_dps", "vedba_ms2", "turn_dps", "up_head", "quat_wxyz", "lin_acc_earth_ms2", "saturated", "unreliable", "frozen", "invalid")


def load_imu(sessions: list, lo: float, hi: float, tz: str) -> dict:
    parts = []
    for s in sessions:
        base = C.to_ms(s["start_local"][:10] + " 00:00:00", tz)
        with np.load(s["npz"]) as z:
            if "t_pc_ms" not in z.files:
                continue
            u = base + z["t_pc_ms"].astype(np.float64)
            m = (u >= lo) & (u < hi)
            if not m.any():
                continue
            d = {"unix_ms": u[m]}
            for k in IMU_KEYS:
                d[k] = z[k][m] if k in z.files else np.zeros(int(m.sum()), bool)
            parts.append(d)
    if not parts:
        return {"unix_ms": np.zeros(0), **{k: np.zeros(0) for k in IMU_KEYS}, "n_sessions": 0}
    parts.sort(key=lambda d: d["unix_ms"][0])
    out = {k: np.concatenate([d[k] for d in parts]) for k in parts[0]}
    o = np.argsort(out["unix_ms"], kind="stable")
    out = {k: v[o] for k, v in out.items()}
    for k in ("omega_dps", "vedba_ms2", "turn_dps"):
        out[k] = out[k].astype(np.float64)
    for k in ("saturated", "unreliable", "frozen", "invalid"):
        out[k] = out[k].astype(bool)
    out["n_sessions"] = len(parts)
    return out


def sample_valid(imu: dict, ctx: dict, animal: str, lo: float, hi: float, vf: float, vu: float, handling=None,
                 use_silence: bool = True, use_adc: bool = True) -> np.ndarray:
    u = imu["unix_ms"]
    if not len(u):
        return np.zeros(0, bool)
    fin = (np.isfinite(imu["omega_dps"]) & np.isfinite(imu["vedba_ms2"]) & np.isfinite(imu["quat_wxyz"]).all(axis=1)
           & np.isfinite(imu["lin_acc_earth_ms2"]).all(axis=1))
    frz, _ = C.frozen_rule(imu["omega_dps"], imu["vedba_ms2"])
    v = fin & ~imu["saturated"] & ~imu["frozen"] & ~imu["invalid"] & ~imu["unreliable"] & ~frz & (u >= lo) & (u < hi)
    v &= ~C.in_any(u, ctx["handling"] if handling is None else handling)
    if use_silence:
        v &= ~C.in_any(u, ctx["silences"])
    if use_adc:
        v &= ~C.in_any(u, [w_ for w_ in ctx["adc"] if w_[2] == animal])
    v &= (u >= vf) & (u < vu)
    return v


def per_second_states(imu: dict, ctx: dict, animal: str, lo: float, hi: float, vf: float, vu: float) -> pd.DataFrame:
    """Pilot per-second table on [lo, hi): QC ok, still (VeDBA_1s < theta_a and omega_1s < 10 deg/s), stride-band fraction,
    state 0 unusable / 1 still / 2 active / 3 locomoting (tuned theta_l, rho_l of the smoothing pilot)."""
    loco = ctx["tuned"]["loco"]
    if not len(imu["unix_ms"]):
        secs = np.arange(int(lo // 1000), int(-(-hi // 1000)), dtype=np.int64)
        return pd.DataFrame({"sec": secs, "ok": False, "still": False, "state": np.zeros(len(secs), np.int8),
                             "vedba_1s": np.nan, "omega_1s": np.nan, "sbf": np.nan})
    frz, _ = C.frozen_rule(imu["omega_dps"], imu["vedba_ms2"])
    ps = C.per_second(imu, lo, hi, ctx["handling"], ctx["silences"], vf, vu, frz)
    t_mid = (ps["sec"].to_numpy() + 0.5) * 1000.0
    ps["m_adc"] = C.in_any(t_mid, [w_ for w_ in ctx["adc"] if w_[2] == animal])
    ps["ok"] = ps["ok"] & ~ps["m_adc"]
    ps["still"] = C.still_mask(ps, ctx["thr"][animal])
    ps["sbf"] = P.stride_band_fraction(imu["unix_ms"], imu["lin_acc_earth_ms2"][:, 2].astype(np.float64),
                                       ps["sec"].to_numpy().astype(float))
    ps["state"] = P.imu_state(ps, loco["theta_l"], loco["rho_l"])
    return ps[["sec", "ok", "still", "state", "vedba_1s", "omega_1s", "sbf"]]


# ====================================================================================================== still windows
def rebuilt_acc(imu: dict) -> np.ndarray:
    """Head-frame specific force a_H = R(q)^T (a_earth_lin + g z) (m/s^2): Fusion's earth acceleration is the rotated
    (k_a-scaled, bias-free) accelerometer minus 1 g, so this returns that accelerometer."""
    q = imu["quat_wxyz"].astype(np.float64)
    lin = imu["lin_acc_earth_ms2"].astype(np.float64)
    return qrot_T(q, lin + np.array([0.0, 0.0, G]))


def fit_acc_cal(a: np.ndarray, om: np.ndarray, valid: np.ndarray, scfg: dict, pb: dict) -> dict:
    """Ellipsoid a_cal = D (a - o) on the 0.5-s quasi-static windows (A3 chain rule, V4.fit_ellipsoid with the V4 priors)."""
    wl = int(round(float(scfg["qs_win_s"]) * FS))
    nw = len(a) // wl
    if nw == 0:
        return {"method": "none", "D": [1.0, 1.0, 1.0], "o": [0.0, 0.0, 0.0], "n": 0}
    A = np.where(valid[:, None], a, 0.0)[:nw * wl].reshape(nw, wl, 3)
    Wm = np.where(valid, om, np.inf)[:nw * wl].reshape(nw, wl)
    bad = ~valid[:nw * wl].reshape(nw, wl).all(axis=1)
    q = (np.median(Wm, axis=1) < float(scfg["qs_omega_dps"])) & (A.std(axis=1).max(axis=1) < float(scfg["qs_acc_sd"])) & ~bad
    if q.sum() < int(scfg["qs_min_windows"]):
        return {"method": "none", "D": [1.0, 1.0, 1.0], "o": [0.0, 0.0, 0.0], "n": int(q.sum())}
    e = V4.fit_ellipsoid(A.mean(axis=1)[q], pb)
    return {"method": "ellipsoid", **e}


def strict_rule_windows(t_ms: np.ndarray, a: np.ndarray, om: np.ndarray, cand_sample: np.ndarray, scfg: dict, fs: float,
                        use_mag: bool = True) -> np.ndarray:
    """Gate-v2 strict rule on any regular stream: 0.1-s block means, candidate blocks (all samples candidate, every sample
    |w| < omega_max), greedy windows with every block direction within dir_max of the window mean and | |mean| - g | <
    mag_tol g, >= min_window_s. Returns [t_start, t_end) in ms (end = last sample + 1/fs)."""
    bl = int(round(float(scfg["block_s"]) * fs))
    nb = len(a) // bl
    if nb == 0:
        return np.zeros((0, 2))
    cont = np.r_[False, np.diff(t_ms) < 1.5 * 1000.0 / fs]
    M = a[:nb * bl].reshape(nb, bl, 3).mean(axis=1)
    nrm = np.linalg.norm(M, axis=1, keepdims=True)
    U = M / np.where(nrm > 0, nrm, 1.0)
    cand = (cand_sample[:nb * bl] & cont[:nb * bl]).reshape(nb, bl).all(axis=1)
    cand &= np.where(np.isfinite(om[:nb * bl]), om[:nb * bl], np.inf).reshape(nb, bl).max(axis=1) < float(scfg["omega_max_dps"])
    tol = float(scfg["mag_tol_g"])
    mlo, mhi = (G * (1 - tol), G * (1 + tol)) if use_mag else (0.0, np.inf)
    os_, oe_ = np.empty(nb, np.int64), np.empty(nb, np.int64)
    cnt = GV2._strict_kernel(np.ascontiguousarray(M), np.ascontiguousarray(U), cand, math.cos(float(scfg["dir_max_deg"]) * math.pi / 180.0),
                             mlo, mhi, int(round(float(scfg["min_window_s"]) / float(scfg["block_s"]))), os_, oe_)
    s, e = os_[:cnt] * bl, oe_[:cnt] * bl
    return np.column_stack([t_ms[s], t_ms[e - 1] + 1000.0 / fs]) if cnt else np.zeros((0, 2))


def s50_windows(imu: dict, valid: np.ndarray, scfg: dict, pb: dict) -> tuple[np.ndarray, np.ndarray, dict]:
    """S50 (primary 50-Hz rule) and the literal up_head-sweep check variant."""
    if not len(imu["unix_ms"]):
        return np.zeros((0, 2)), np.zeros((0, 2)), {"method": "none", "n": 0}
    a = rebuilt_acc(imu)
    a = np.where(np.isfinite(a), a, 0.0)
    om = imu["omega_dps"]
    cal = fit_acc_cal(a, om, valid, scfg, pb)
    acal = (a - np.asarray(cal["o"])) * np.asarray(cal["D"])
    w_main = strict_rule_windows(imu["unix_ms"], acal, om, valid, scfg, FS, use_mag=True)
    up = np.where(np.isfinite(imu["up_head"]), imu["up_head"], 0.0).astype(np.float64) * G
    lin_ok = np.linalg.norm(np.where(np.isfinite(imu["lin_acc_earth_ms2"]), imu["lin_acc_earth_ms2"], 99.0), axis=1) < float(scfg["mag_tol_g"]) * G
    w_up = strict_rule_windows(imu["unix_ms"], up, om, valid & lin_ok, scfg, FS, use_mag=False)
    return w_main, w_up, cal


def strict_csv_windows(sw: pd.DataFrame, animal: str, gv2_period: str, lo: float, hi: float, excl: list) -> np.ndarray:
    d = sw[(sw.animal == animal) & (sw.period == gv2_period)]
    Wd = d[["t_start_ms", "t_end_ms"]].to_numpy(float)
    Wd = Wd[(Wd[:, 0] >= lo) & (Wd[:, 1] <= hi)]
    keep = np.ones(len(Wd), bool)
    for a, b, *_ in excl:
        keep &= ~((Wd[:, 0] < b) & (Wd[:, 1] > a))
    return Wd[keep]


def merge_segments(win: np.ndarray, imu: dict, valid: np.ndarray, thr_a: float, scfg: dict) -> pd.DataFrame:
    """Merge still windows across gaps <= merge_gap_s whose 50-Hz samples are all valid, |w| < gap_omega_max_dps and
    VeDBA < theta_a (no movement able to translate the head), with no missing samples."""
    cols = ["t0", "t1", "dur_s", "n_win", "still_s", "cover"]
    if not len(win):
        return pd.DataFrame(columns=cols)
    win = win[np.argsort(win[:, 0])]
    u = imu["unix_ms"]
    okg = valid & (np.nan_to_num(imu["omega_dps"], nan=np.inf) < float(scfg["gap_omega_max_dps"])) & (np.nan_to_num(imu["vedba_ms2"], nan=np.inf) < thr_a)
    bad_cs = np.r_[0, np.cumsum(~okg)]
    gmax = float(scfg["merge_gap_s"]) * 1000
    segs = []
    s0, e0, n, still = win[0, 0], win[0, 1], 1, win[0, 1] - win[0, 0]
    for a, b in win[1:]:
        gap = a - e0
        ok = False
        if gap <= gmax:
            i0, i1 = np.searchsorted(u, [e0, a])
            nexp = gap / (1000.0 / FS)
            ok = (bad_cs[i1] - bad_cs[i0] == 0) and (i1 - i0) >= nexp - 1.5
        if ok:
            e0 = max(e0, b)
            n += 1
            still += b - a
        else:
            segs.append((s0, e0, n, still))
            s0, e0, n, still = a, b, 1, b - a
    segs.append((s0, e0, n, still))
    S = pd.DataFrame(segs, columns=["t0", "t1", "n_win", "still_ms"])
    S["dur_s"] = (S.t1 - S.t0) / 1000.0
    S["still_s"] = S.still_ms / 1000.0
    S["cover"] = S.still_s / S.dur_s
    return S[cols]


def time_overlap(A: np.ndarray, Bw: np.ndarray, lo: float, hi: float, step: float = 100.0) -> dict:
    g = np.arange(lo, hi, step)

    def mask(Wn):
        m = np.zeros(len(g), bool)
        if len(Wn):
            i0 = np.searchsorted(g, Wn[:, 0])
            i1 = np.searchsorted(g, Wn[:, 1])
            d = np.zeros(len(g) + 1, np.int64)
            np.add.at(d, i0, 1)
            np.add.at(d, i1, -1)
            m = np.cumsum(d)[:-1] > 0
        return m
    ma, mb = mask(A), mask(Bw)
    inter = float((ma & mb).sum())
    return {"a_min": ma.sum() * step / 6e4, "b_min": mb.sum() * step / 6e4, "recall": inter / max(mb.sum(), 1),
            "precision": inter / max(ma.sum(), 1), "iou": inter / max((ma | mb).sum(), 1)}


def seg_agreement(SA: pd.DataFrame, SB: pd.DataFrame, min_s: float, overlap: float) -> dict:
    """Fraction of B's >= min_s segments covered >= overlap by A's >= min_s segments (and vice versa)."""
    A = SA[SA.dur_s >= min_s][["t0", "t1"]].to_numpy(float)
    Bs = SB[SB.dur_s >= min_s][["t0", "t1"]].to_numpy(float)

    def cov(X, Y):
        if not len(X):
            return np.nan
        if not len(Y):
            return 0.0
        hits = 0
        for a, b in X:
            ov = np.clip(np.minimum(Y[:, 1], b) - np.maximum(Y[:, 0], a), 0, None).sum()
            hits += ov >= overlap * (b - a)
        return hits / len(X)
    return {"n_a": int(len(A)), "n_b": int(len(Bs)), "b_covered_by_a": cov(Bs, A), "a_covered_by_b": cov(A, Bs)}


# ====================================================================================================== WISER
def load_fixes(cfg: dict, pkey: str, animal: str, lo: float, hi: float, tau_s: float) -> pd.DataFrame:
    p = Path(cfg["fix_cache"]["root"]) / period_cache_key(pkey) / f"{animal}.csv.gz"
    f = pd.read_csv(p)
    m = float(cfg["fix_cache"]["margin_s"]) * 1000
    f = f[(f.t_ms >= lo - m) & (f.t_ms < hi + m)].sort_values("t_ms").reset_index(drop=True)
    f["t_al_ms"] = f["t_ms"].astype(np.float64) - tau_s * 1000.0
    return f


def smooth_tracks(fx: pd.DataFrame, ps_ext: pd.DataFrame, ctx: dict, lo: float) -> tuple[dict, np.ndarray]:
    """All methods at the fix times (in, WISER frame). B1/B2/B2' are IMU-free; V1/V2 use the pilot IMU states."""
    tu = ctx["tuned"]
    t = (fx["t_al_ms"].to_numpy(float) - lo) / 1000.0
    z = fx[["x", "y"]].to_numpy(float)
    A = fx["anchors_used"].to_numpy(float)
    r2 = P.r2_from_anchors(A, ctx["table"])
    st_mid, st_at = P.step_states(fx["t_al_ms"].to_numpy(float), ps_ext["sec"].to_numpy(), ps_ext["state"].to_numpy(np.int8))
    vis = np.ones(len(t), bool)
    b2, b2p = tu["B2"], tu["B2p"]
    base = {"q": b2p["q"], "tb": b2p["tb"], "sb": b2p["sb"], "mrej": b2["mrej"]}
    cfgs = [{"q": b2["q"], "mrej": b2["mrej"]}, dict(base), {**base, "sv": tu["V1"]["sv"]}, {**base, "mult": tuple(tu["V2"]["mult"])}]
    Pk, Bk, _ = P.kf_run(t, z, r2, [vis], [st_mid], [st_at], cfgs)
    tr = {"raw": z, "B1": P.b1_full(z), "B2": Pk[0], "B2p": Pk[1], "B2pb": Pk[1] + Bk[1], "V1": Pk[2], "V2": Pk[3]}
    return tr, t


# ====================================================================================================== Q1/Q2 segment scoring
def score_segment(t: np.ndarray, tracks: dict, truth: np.ndarray, ts: float, te: float, mc: dict, methods: list) -> tuple[dict, list, list, dict]:
    """t (s, sorted) and tracks[m] (n, 2) restricted to the trimmed segment [ts, te). Returns per-method metrics, crazy-drift
    events (dicts with grid indices), jumps (method, k) and 0.25-s fake speeds per method."""
    res, events, jumps, speeds = {}, [], [], {}
    dur = te - ts
    hs, hl = mc["roll_short_s"] / 2.0, mc["roll_long_s"] / 2.0
    c10 = np.arange(ts + hs, te - hs + 1e-9, 1.0)
    c60 = np.arange(ts + hl, te - hl + 1e-9, 1.0) if dur >= mc["roll_long_min_seg_s"] else np.zeros(0)
    for m in methods:
        p = tracks[m]
        r = np.hypot(p[:, 0] - truth[0], p[:, 1] - truth[1])
        m10, _ = roll_median(t, p, c10, hs, mc["roll_short_min_fix"])
        d10 = np.hypot(m10[:, 0] - truth[0], m10[:, 1] - truth[1])
        if len(c60):
            m60, _ = roll_median(t, p, c60, hl, mc["roll_long_min_fix"])
            d60 = np.hypot(m60[:, 0] - truth[0], m60[:, 1] - truth[1])
        else:
            d60 = np.zeros(0)
        cr = runs_at_least(np.nan_to_num(d10, nan=-1.0) >= mc["crazy_in"], int(mc["crazy_min_s"]))
        for a, b in cr:
            events.append({"method": m, "c0": float(c10[a]), "c1": float(c10[b - 1]), "dur_s": int(b - a),
                           "size_in": float(np.nanmax(d10[a:b])), "mean_in": float(np.nanmean(d10[a:b]))})
        jk = find_jumps(t, p, mc["jump_in"], mc["jump_dt_s"])
        jumps.extend((m, int(k)) for k in jk)
        _, v = speed_grid(t, p, ts, te, mc["speed_grid_s"], mc["speed_max_gap_s"])
        v = v[np.isfinite(v)]
        speeds[m] = v.astype(np.float32)
        path, psec, prate = path_rate(t, p, ts, te, mc["speed_max_gap_s"])
        fin10 = np.isfinite(d10)
        res[m] = {"rms_in": float(np.sqrt(np.mean(r ** 2))) if len(r) else np.nan, "p50_in": float(np.median(r)) if len(r) else np.nan,
                  "p90_in": float(np.percentile(r, 90)) if len(r) else np.nan, "max_in": float(r.max()) if len(r) else np.nan,
                  "sd_x": float(np.std(p[:, 0])) if len(r) else np.nan, "sd_y": float(np.std(p[:, 1])) if len(r) else np.nan,
                  "drift10_in": float(np.nanmax(d10)) if fin10.any() else np.nan, "drift10_p50_in": float(np.nanmedian(d10)) if fin10.any() else np.nan,
                  "n10": int(fin10.sum()),
                  "drift60_in": float(np.nanmax(d60)) if np.isfinite(d60).any() else np.nan,
                  "crazy_n": int(len(cr)), "crazy_s": int(sum(b - a for a, b in cr)),
                  "crazy_max_in": float(max((np.nanmax(d10[a:b]) for a, b in cr), default=np.nan)),
                  "jumps": int(len(jk)), "speed_p50": float(np.percentile(v, 50)) if len(v) else np.nan,
                  "speed_p95": float(np.percentile(v, 95)) if len(v) else np.nan, "speed_p99": float(np.percentile(v, 99)) if len(v) else np.nan,
                  "n_speed": int(len(v)), "path_in": path, "path_s": psec, "path_in_per_min": prate}
        res[m]["_d10"] = d10
        res[m]["_c10"] = c10
    return res, events, jumps, speeds


# ====================================================================================================== Q3 motion side
def state_lookup(ps: pd.DataFrame):
    secs = ps["sec"].to_numpy(np.int64)
    s0 = int(secs[0]) if len(secs) else 0
    ok = ps["ok"].to_numpy(bool)
    still = ps["still"].to_numpy(bool) & ok
    st = np.where(ok, ps["state"].to_numpy(np.int8), 0)

    def f(sec):
        i = np.asarray(sec, np.int64) - s0
        inb = (i >= 0) & (i < len(secs))
        ii = np.clip(i, 0, max(len(secs) - 1, 0))
        if not len(secs):
            z = np.zeros(len(i), bool)
            return z, z, np.zeros(len(i), np.int8)
        return np.where(inb, ok[ii], False), np.where(inb, still[ii], False), np.where(inb, st[ii], 0).astype(np.int8)
    return f


def motion_night(fx: pd.DataFrame, t: np.ndarray, tracks: dict, ps: pd.DataFrame, lo: float, hi: float, mo: dict, mc: dict,
                 houses: list, buf: float, methods: list, block_s: float = 600.0) -> dict:
    """Impossible-speed events, jumps classified by the IMU (+- 1 s), and onset/offset lags, per method, on [lo, hi)."""
    look = state_lookup(ps)
    lo_s, hi_s = 0.0, (hi - lo) / 1000.0
    sec_of = lambda tt: np.floor((np.asarray(tt) * 1000.0 + lo) / 1000.0).astype(np.int64)  # noqa: E731
    A = fx["anchors_used"].to_numpy(float)
    raw = tracks["raw"]
    ok_s, _, _ = look(ps["sec"].to_numpy(np.int64))
    ok_hours = float(ok_s.sum()) / 3600.0
    ev_rows, jump_rows, on_rows = [], [], []
    inwin = (t >= lo_s) & (t < hi_s)
    step = mc["speed_grid_s"]
    for m in methods:
        p = tracks[m]
        g, v = speed_grid(t, p, lo_s, hi_s, step, mc["speed_max_gap_s"])
        okg, _, _ = look(sec_of(g))
        hit = np.nan_to_num(v, nan=0.0) > mo["impossible_inps"]
        hit &= okg
        rr = C.true_runs(hit)
        merged = []
        for a, b in rr:
            if merged and (a - merged[-1][1]) * step <= mo["event_merge_s"]:
                merged[-1] = (merged[-1][0], b)
            else:
                merged.append((a, b))
        for a, b in merged:
            t0, t1 = g[a], g[b - 1]
            ss = np.arange(sec_of(t0 - 0.5), sec_of(t1 + 0.5) + 1)
            so, sst, sstate = look(ss)
            i0, i1 = np.searchsorted(t, [t0 - 0.5, t1 + 0.5])
            mx = np.nanmedian(raw[i0:i1, 0]) if i1 > i0 else np.nan
            my = np.nanmedian(raw[i0:i1, 1]) if i1 > i0 else np.nan
            ev_rows.append({"method": m, "t0_ms": lo + t0 * 1000, "t1_ms": lo + t1 * 1000, "dur_s": float(t1 - t0 + step),
                            "vmax_inps": float(np.nanmax(v[a:b])), "imu_all_ok": bool(so.all()), "imu_still_frac": float(sst.mean()),
                            "imu_loco_frac": float((sstate == 3).mean()), "imu_any_still": bool(sst.any()),
                            "anchors_min": float(A[i0:i1].min()) if i1 > i0 else np.nan,
                            "anchors_med": float(np.median(A[i0:i1])) if i1 > i0 else np.nan, "zone": zone_of(mx, my, houses, buf)})
        jk = find_jumps(t, p, mc["jump_in"], mc["jump_dt_s"])
        jk = jk[inwin[jk] & inwin[np.minimum(jk + 1, len(t) - 1)]]
        for k in jk:
            tm = 0.5 * (t[k] + t[k + 1])
            s = sec_of(tm)
            ss = np.arange(s - mo["jump_imu_pm_s"], s + mo["jump_imu_pm_s"] + 1)
            so, sst, sstate = look(ss)
            ok_here, _, _ = look(np.array([s]))
            cls = "imu_unknown" if not so.all() else ("imu_quiet" if sst.all() else "imu_active")
            jump_rows.append({"method": m, "t_ms": lo + tm * 1000, "size_in": float(np.hypot(*(p[k + 1] - p[k]))),
                              "dt_s": float(t[k + 1] - t[k]), "anchors_a": float(A[k]), "anchors_b": float(A[k + 1]),
                              "anchors_min": float(min(A[k], A[k + 1])), "imu_class": cls, "imu_loco": bool((sstate == 3).any()),
                              "sec_ok": bool(ok_here[0]), "zone": zone_of(raw[k, 0], raw[k, 1], houses, buf)})
    # ---- onsets / offsets from the per-second IMU states
    secs = ps["sec"].to_numpy(np.int64)
    _, _, stt = look(secs)
    on_rows = onset_offset(stt, secs, t, tracks, A, lo, lo_s, hi_s, mo, houses, buf, methods)
    blk = ((secs * 1000.0 - lo) // (block_s * 1000.0)).astype(np.int64)
    blocks = pd.DataFrame({"block": blk, "ok": ok_s}).groupby("block").agg(ok_s=("ok", "sum"), n_s=("ok", "size")).reset_index()
    ev, jp = pd.DataFrame(ev_rows), pd.DataFrame(jump_rows)
    if len(ev):
        ev["block"] = ((ev.t0_ms - lo) // (block_s * 1000.0)).astype(np.int64)
    if len(jp):
        jp["block"] = ((jp.t_ms - lo) // (block_s * 1000.0)).astype(np.int64)
    return {"events": ev, "jumps": jp, "onsets": pd.DataFrame(on_rows), "blocks": blocks, "ok_hours": ok_hours}


def onset_offset(stt: np.ndarray, secs: np.ndarray, t: np.ndarray, tracks: dict, A: np.ndarray, lo: float, lo_s: float, hi_s: float,
                 mo: dict, houses: list, buf: float, methods: list) -> list:
    """Onset/offset agreement anchored on IMU still runs (pilot 1-s rule, >= still_run_min_s, states 0 unusable / 1 still /
    2 active / 3 locomoting).
    onset : a still run [a, b) followed by a first locomoting second s_L in [b, b + loco_search_s) with no still or unusable
            second in [b, s_L); reference = median track over [b - ref_s, b - 1); WISER departure t_d = first time the
            centred 3-s median is >= depart_in from it. early = t_d < b - lag_ok (WISER moved while the head was still),
            before_loco = t_d < s_L - lag_ok, on_time = |t_d - s_L| <= lag_ok, late = t_d > s_L + lag_ok, censored = none
            within s_L + lag_window_s.
    offset: a still run [a, b) preceded by a last locomoting second s_L in [a - loco_search_s, a) with no still or unusable
            second in (s_L, a); reference = median track over [a + 1, a + ref_s); settle t_s = last time (+ grid step) in
            [s_L - lag_window_s, a + ref_s - 1.5] the 3-s median is >= depart_in from it. late = t_s - a > lag_ok (WISER still
            away although the head is still), else on_time; no_displacement = never that far."""
    rows = []
    minr, look_s, ref_s = int(mo["still_run_min_s"]), int(mo["loco_search_s"]), float(mo["ref_s"])
    hw, L, ok_lag = mo["median_win_s"] / 2.0, mo["lag_window_s"], mo["lag_ok_s"]
    rel = lambda i: (secs[i] * 1000.0 - lo) / 1000.0  # noqa: E731
    long_runs = [(a, b) for a, b in C.true_runs(stt == 1) if b - a >= minr]
    in_long = np.zeros(len(stt), bool)
    for a, b in long_runs:
        in_long[a:b] = True
    for a, b in long_runs:
        sL = None
        for j in range(b, min(b + look_s, len(stt))):
            if stt[j] == 0 or in_long[j]:
                break
            if stt[j] == 3:
                sL = j
                break
        sL2 = None
        for j in range(a - 1, max(a - look_s, 0) - 1, -1):
            if stt[j] == 0 or in_long[j]:
                break
            if stt[j] == 3:
                sL2 = j
                break
        for kind, s_loco in (("onset", sL), ("offset", sL2)):
            if s_loco is None:
                continue
            ra, rb, rl = rel(a) if a < len(secs) else np.nan, rel(b) if b < len(secs) else rel(b - 1) + 1.0, rel(s_loco)
            if not (lo_s + ref_s <= ra and rb <= hi_s - ref_s):
                continue
            if kind == "onset":
                r0, r1 = np.searchsorted(t, [rb - ref_s, rb - 1.0])
                gg = np.arange(rb - ref_s + hw, rl + L + 1e-9, 0.25)
            else:
                r0, r1 = np.searchsorted(t, [ra + 1.0, ra + ref_s])
                gg = np.arange(rl - L, ra + ref_s - hw + 1e-9, 0.25)
            for m in methods:
                p = tracks[m]
                base = {"kind": kind, "method": m, "still_start_ms": lo + ra * 1000, "still_end_ms": lo + rb * 1000,
                        "loco_ms": lo + rl * 1000, "still_run_s": int(b - a)}
                if r1 - r0 < mo["ref_min_fix"]:
                    rows.append({**base, "status": "no_reference"})
                    continue
                ref = np.median(p[r0:r1], axis=0)
                m3, _ = roll_median(t, p, gg, hw, mo["median_min_fix"])
                far = np.nan_to_num(np.hypot(m3[:, 0] - ref[0], m3[:, 1] - ref[1]), nan=-1.0) >= mo["depart_in"]
                j = np.flatnonzero(far)
                if kind == "onset":
                    if not len(j):
                        st, lag_l, lag_w = "censored", np.nan, np.nan
                    else:
                        td = gg[j[0]]
                        lag_l, lag_w = td - rl, td - rb
                        st = ("early" if td < rb - ok_lag else "before_loco" if td < rl - ok_lag else
                              "on_time" if td <= rl + ok_lag else "late")
                    rows.append({**base, "status": st, "lag_loco_s": lag_l, "lag_still_s": lag_w, "wake_to_loco_s": rl - rb})
                else:
                    if not len(j):
                        st, lag_l, lag_w = "no_displacement", np.nan, np.nan
                    else:
                        ts_ = gg[j[-1]] + 0.25
                        lag_l, lag_w = ts_ - (rl + 1.0), ts_ - ra
                        st = "late" if lag_w > ok_lag else "on_time"
                    rows.append({**base, "status": st, "lag_loco_s": lag_l, "lag_still_s": lag_w, "loco_to_still_s": ra - (rl + 1.0)})
                k0, k1 = np.searchsorted(t, [min(ra, rl) - ref_s, max(rb, rl) + ref_s])
                rows[-1]["anchors_med"] = float(np.median(A[k0:k1])) if k1 > k0 else np.nan
                rows[-1]["zone"] = zone_of(*np.median(tracks["raw"][r0:r1], axis=0), houses, buf)
    return rows


# ====================================================================================================== one animal-period
_CTX = {}


def _ctx(cfg: dict) -> dict:
    key = cfg["_path"]
    if key not in _CTX:
        _CTX[key] = context(cfg)
    return _CTX[key]


def process(job: dict) -> dict:
    """Everything for one animal and one period; writes tracks / per-second states / speeds into the run dir."""
    t_job = time.time()
    cfg, animal, pkey, out = job["cfg"], job["animal"], job["pkey"], Path(job["out"])
    ctx = _ctx(cfg)
    tz = ctx["tz"]
    p = cfg["periods"][pkey]
    sc, mc, mo = cfg["still"], cfg["metrics"], cfg["motion"]
    lo, hi = C.to_ms(p["start"], tz), C.to_ms(p["end"], tz)
    ext = float(cfg["fix_cache"]["margin_s"]) * 1000
    tau = float(ctx["taus"][animal])
    sid = C.resolve_tag(ctx["ids"], animal, lo, hi)
    vf, vu = C.tag_window(ctx["ids"], sid, animal, (lo + hi) / 2)
    info = {"animal": animal, "period": pkey, "set": p["set"], "kind": p["kind"], "shortid": sid, "tau_s": tau}
    # ---- IMU
    sess = sessions_for(cfg, ctx, animal, lo - ext, hi + ext)
    imu = load_imu(sess, lo - ext, hi + ext, tz)
    info["sessions"] = ";".join(s["session"] for s in sess)
    info["pc_time"] = ";".join(s["pc_time"] for s in sess)
    valid = sample_valid(imu, ctx, animal, lo, hi, vf, vu)
    ps_ext = per_second_states(imu, ctx, animal, lo - ext, hi + ext, vf, vu)
    ps = ps_ext[(ps_ext.sec >= lo // 1000) & (ps_ext.sec < -(-hi // 1000))].reset_index(drop=True)
    ps.to_csv(out / "imu_seconds" / f"{animal}_{pkey}.csv.gz", index=False)
    info.update({"imu_seconds": int(len(ps)), "imu_ok_s": int(ps.ok.sum()), "imu_still1s_s": int((ps.ok & ps.still).sum()),
                 "imu_valid_50hz_s": float(valid.sum() / FS)})
    # ---- still windows -> segments
    w_s50, w_up, cal = s50_windows(imu, valid, sc, ctx["pb"])
    info.update({"acc_cal": cal.get("method"), "acc_cal_n": cal.get("n"), "acc_cal_o": json.dumps([round(x, 3) for x in cal.get("o", [])]),
                 "acc_cal_D": json.dumps([round(x, 4) for x in cal.get("D", [])])})
    wins = {"s50": w_s50, "s50_up": w_up}
    if p.get("strict_period"):
        sw = pd.read_csv(cfg["strict_windows_csv"])
        excl = ctx["handling"] + ctx["silences"] + [w_ for w_ in ctx["adc"] if w_[2] == animal] + [(-np.inf, vf, "tag"), (vu, np.inf, "tag")]
        wins["strict"] = strict_csv_windows(sw, animal, p["strict_period"], lo, hi, excl)
    primary = "strict" if "strict" in wins else "s50"
    thr_a = float(ctx["thr"][animal])
    win_rows, seg_tabs = [], {}
    for src, wv in wins.items():
        win_rows.append(pd.DataFrame({"animal": animal, "period": pkey, "source": src, "t0_ms": wv[:, 0] if len(wv) else [],
                                      "t1_ms": wv[:, 1] if len(wv) else []}))
        S = merge_segments(wv, imu, valid, thr_a, sc)
        S.insert(0, "source", src)
        seg_tabs[src] = S
        info[f"win_{src}_min"] = float(((wv[:, 1] - wv[:, 0]).sum() if len(wv) else 0) / 6e4)
        info[f"seg30_{src}_min"] = float(S[S.dur_s >= sc["min_seg_s"]].dur_s.sum() / 60) if len(S) else 0.0
    # ---- WISER + smoothers
    fx = load_fixes(cfg, pkey, animal, lo, hi, tau)
    tracks, t = smooth_tracks(fx, ps_ext, ctx, lo)
    A = fx["anchors_used"].to_numpy(float)
    np.savez_compressed(out / "tracks" / f"{animal}_{pkey}.npz", t_ms=fx["t_ms"].to_numpy(np.int64), t_al_ms=fx["t_al_ms"].to_numpy(float),
                        anchors=A.astype(np.int8), **{m: tracks[m].astype(np.float32) for m in METHODS})
    inwin = (t >= 0) & (t < (hi - lo) / 1000.0)
    info.update({"n_fix": int(inwin.sum()), "fix_rate_hz": float(inwin.sum() / ((hi - lo) / 1000.0)),
                 "anchors_le6_frac": float((A[inwin] <= 6).mean()) if inwin.any() else np.nan,
                 "anchors_9_frac": float((A[inwin] >= 9).mean()) if inwin.any() else np.nan})
    # ---- score segments
    seg_rows, met_rows, fix_rows, ev_rows, jump_rows = [], [], [], [], []
    spd = {m: [] for m in METHODS}
    spd_idx = {m: [] for m in METHODS}
    trim = float(sc["trim_s"])
    houses, buf = ctx["houses"], float(cfg["house_buffer_in"])
    for src, S in seg_tabs.items():
        S = S[S.dur_s >= sc["min_seg_s_secondary"]].reset_index(drop=True)
        for i, r in S.iterrows():
            seg_id = f"{animal}|{pkey}|{src}|{i:05d}"
            ts, te = (r.t0 - lo) / 1000.0 + trim, (r.t1 - lo) / 1000.0 - trim
            i0, i1 = np.searchsorted(t, [ts, te])
            n = int(i1 - i0)
            row = {"seg_id": seg_id, "animal": animal, "period": pkey, "set": p["set"], "kind": p["kind"], "source": src,
                   "primary": src == primary, "t0_ms": r.t0, "t1_ms": r.t1, "dur_s": r.dur_s, "dur_trim_s": te - ts, "n_win": int(r.n_win),
                   "cover": r.cover, "n_fix": n, "fix_rate_hz": n / max(te - ts, 1e-9), "ge30": bool(r.dur_s >= sc["min_seg_s"]),
                   "hour": int(pd.Timestamp(ms_local(0.5 * (r.t0 + r.t1), tz)).hour), "block": int((0.5 * (r.t0 + r.t1) - lo) // (cfg["bootstrap"]["block_s"] * 1000))}
            if n < mc["min_fix_truth"]:
                row.update({"scored": False})
                seg_rows.append(row)
                continue
            tt = t[i0:i1]
            Aseg = A[i0:i1]
            trk = {m: tracks[m][i0:i1] for m in METHODS}
            truth = np.median(trk["raw"], axis=0)
            hi_a = Aseg >= mc["truth_alt_min_anchors"]
            truth_alt = np.median(trk["raw"][hi_a], axis=0) if hi_a.sum() >= mc["min_fix_truth"] else np.array([np.nan, np.nan])
            zd = zone_of(truth[0], truth[1], houses, buf)
            row.update({"scored": True, "truth_x": truth[0], "truth_y": truth[1], "truth_alt_shift_in": float(np.hypot(*(truth_alt - truth))),
                        "zone_detail": zd, "zone": zone2(zd), "anchors_med": float(np.median(Aseg)), "anchors_le6_frac": float((Aseg <= 6).mean()),
                        "anchor_bin": str(anchor_bin([np.median(Aseg)])[0])})
            seg_rows.append(row)
            res, evs, jps, speeds = score_segment(tt, trk, truth, ts, te, mc, METHODS)
            for m in METHODS:
                met_rows.append({"seg_id": seg_id, "method": m, **{k: v for k, v in res[m].items() if not k.startswith("_")}})
            for e in evs:
                g0, g1 = e["c0"] - mc["roll_short_s"] / 2, e["c1"] + mc["roll_short_s"] / 2
                k0, k1 = np.searchsorted(tt, [g0, g1])
                ev_rows.append({"seg_id": seg_id, "animal": animal, "period": pkey, "set": p["set"], "kind": p["kind"], "source": src,
                                "primary": src == primary, "ge30": row["ge30"], "method": e["method"],
                                "start_ms": lo + g0 * 1000, "end_ms": lo + g1 * 1000, "dur_s": e["dur_s"], "size_in": e["size_in"],
                                "mean_in": e["mean_in"], "anchors_med": float(np.median(Aseg[k0:k1])) if k1 > k0 else np.nan,
                                "anchors_le6_frac": float((Aseg[k0:k1] <= 6).mean()) if k1 > k0 else np.nan,
                                "zone_detail": zd, "zone": zone2(zd), "hour": row["hour"], "block": row["block"],
                                "seg_dur_s": r.dur_s, "truth_x": truth[0], "truth_y": truth[1]})
            for m, k in jps:
                jump_rows.append({"seg_id": seg_id, "animal": animal, "period": pkey, "set": p["set"], "kind": p["kind"], "source": src,
                                  "primary": src == primary, "ge30": row["ge30"], "method": m, "t_ms": lo + 0.5 * (tt[k] + tt[k + 1]) * 1000,
                                  "size_in": float(np.hypot(*(trk[m][k + 1] - trk[m][k]))), "dt_s": float(tt[k + 1] - tt[k]),
                                  "anchors_min": float(min(Aseg[k], Aseg[k + 1])), "zone": zone2(zd), "block": row["block"]})
            if src == primary:
                fr = {"seg_id": seg_id, "t_al_ms": (lo + tt * 1000).round(1), "anchors": Aseg.astype(int)}
                for m in METHODS:
                    fr[f"r_{m}"] = np.hypot(trk[m][:, 0] - truth[0], trk[m][:, 1] - truth[1]).round(3)
                fix_rows.append(pd.DataFrame(fr))
                k_seg = len(fix_rows) - 1
                for m in METHODS:
                    spd[m].append(speeds[m])
                    spd_idx[m].append(np.full(len(speeds[m]), k_seg, np.int32))
    seg_df = pd.DataFrame(seg_rows)
    if fix_rows:
        seg_ids = [fr_["seg_id"].iloc[0] for fr_ in fix_rows]
        np.savez_compressed(out / "speeds" / f"{animal}_{pkey}.npz", seg_ids=np.array(seg_ids),
                            **{m: np.concatenate(spd[m]) for m in METHODS}, **{f"idx_{m}": np.concatenate(spd_idx[m]) for m in METHODS})
    # ---- motion side (nights)
    motion = None
    if p["kind"] == "night":
        motion = motion_night(fx, t, tracks, ps, lo, hi, mo, mc, houses, buf, METHODS, float(cfg["bootstrap"]["block_s"]))
        for k in ("events", "jumps", "onsets", "blocks"):
            if len(motion[k]):
                motion[k].insert(0, "kind_period", p["kind"])
                motion[k].insert(0, "set", p["set"])
                motion[k].insert(0, "period", pkey)
                motion[k].insert(0, "animal", animal)
        info["motion_ok_hours"] = motion["ok_hours"]
    info["runtime_s"] = round(time.time() - t_job, 1)
    return {"info": info, "segments": seg_df, "metrics": pd.DataFrame(met_rows), "events": pd.DataFrame(ev_rows),
            "jumps": pd.DataFrame(jump_rows), "fixes": pd.concat(fix_rows, ignore_index=True) if fix_rows else pd.DataFrame(),
            "windows": pd.concat(win_rows, ignore_index=True), "motion": motion}


def _process_safe(job: dict) -> dict:
    try:
        return process(job)
    except Exception as e:  # noqa: BLE001
        import traceback
        return {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc(), "animal": job["animal"], "pkey": job["pkey"]}


# ====================================================================================================== validation of S50
def validate_job(job: dict) -> dict:
    cfg, animal, vkey = job["cfg"], job["animal"], job["vkey"]
    ctx = _ctx(cfg)
    tz = ctx["tz"]
    vp = cfg["validation_periods"][vkey]
    lo, hi = C.to_ms(vp["start"], tz), C.to_ms(vp["end"], tz)
    sid = C.resolve_tag(ctx["ids"], animal, lo, hi)
    vf, vu = C.tag_window(ctx["ids"], sid, animal, (lo + hi) / 2)
    sess = sessions_for(cfg, ctx, animal, lo - 60_000, hi + 60_000)
    imu = load_imu(sess, lo - 60_000, hi + 60_000, tz)
    # gate v2's exclusions: handling windows without pad, frozen chip, IMU validity; no silence / ADC exclusion
    valid = sample_valid(imu, ctx, animal, lo, hi, vf, vu, handling=ctx["handling_raw"], use_silence=False, use_adc=False)
    w_s50, w_up, cal = s50_windows(imu, valid, cfg["still"], ctx["pb"])
    sw = pd.read_csv(cfg["strict_windows_csv"])
    st = strict_csv_windows(sw, animal, vkey, lo, hi, [])
    out = []
    thr_a = float(ctx["thr"][animal])
    S_st = merge_segments(st, imu, valid, thr_a, cfg["still"])
    for name, wv in (("S50", w_s50), ("S50_up", w_up)):
        ov = time_overlap(wv, st, lo, hi)
        S = merge_segments(wv, imu, valid, thr_a, cfg["still"])
        row = {"period": vkey, "animal": animal, "rule": name, **ov, "n_win": int(len(wv)), "n_strict": int(len(st)), "acc_cal": cal.get("method"),
               "acc_cal_o": json.dumps([round(x, 3) for x in cal.get("o", [])])}
        for ms in (cfg["still"]["min_seg_s"], cfg["still"]["min_seg_s_secondary"]):
            ag = seg_agreement(S, S_st, ms, cfg["still"]["validation_seg_overlap"])
            row.update({f"seg{int(ms)}_n_rule": ag["n_a"], f"seg{int(ms)}_n_strict": ag["n_b"],
                        f"seg{int(ms)}_strict_covered": ag["b_covered_by_a"], f"seg{int(ms)}_rule_covered": ag["a_covered_by_b"]})
            sa = S[S.dur_s >= ms][["t0", "t1"]].to_numpy(float)
            sb = S_st[S_st.dur_s >= ms][["t0", "t1"]].to_numpy(float)
            so = time_overlap(sa, sb, lo, hi)
            row.update({f"seg{int(ms)}_time_recall": so["recall"], f"seg{int(ms)}_time_precision": so["precision"],
                        f"seg{int(ms)}_rule_min": so["a_min"], f"seg{int(ms)}_strict_min": so["b_min"]})
        out.append(row)
    return {"rows": out}


def _validate_safe(job: dict) -> dict:
    try:
        return validate_job(job)
    except Exception as e:  # noqa: BLE001
        import traceback
        return {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc(), "animal": job["animal"], "vkey": job["vkey"]}


# ====================================================================================================== compute run
def run_compute(cfg: dict, workers: int) -> Path:
    t_start = time.time()
    out = output_paths.run_dir(NAME, cfg["_cohort"])
    for d in ("imu_seconds", "tracks", "speeds", "tables"):
        (out / d).mkdir(exist_ok=True)
    fh = open(out / "log.txt", "w", encoding="utf-8")

    def log(msg):
        log_to(fh, msg)
    log(f"run dir {out}; git {C.git_commit()}; config {cfg['_path']}")
    ctx = context(cfg)
    ensure_fix_caches(cfg, ctx, fh)
    vjobs = [{"cfg": cfg, "animal": a, "vkey": k} for k in cfg["validation_periods"] if not k.startswith("_") for a in cfg["animals"]]
    jobs = [{"cfg": cfg, "animal": a, "pkey": k, "out": str(out)} for k in cfg["periods"] for a in cfg["animals"]]
    vrows, results = [], []
    with ProcessPoolExecutor(max_workers=max(1, workers)) as ex:
        for r in ex.map(_validate_safe, vjobs):
            if "error" in r:
                log(f"VALIDATION ERROR {r['animal']} {r['vkey']}: {r['error']}\n{r['trace']}")
                continue
            vrows.extend(r["rows"])
        V = pd.DataFrame(vrows)
        V.to_csv(out / "tables" / "still_rule_validation.csv", index=False)
        for rule, g in V.groupby("rule"):
            log(f"validation {rule}: time recall median {g.recall.median():.3f} (min {g.recall.min():.3f}), precision median "
                f"{g.precision.median():.3f}; >=30-s segment time recall {g.seg30_time_recall.median():.3f}, precision {g.seg30_time_precision.median():.3f}")
        log(f"validation done ({time.time() - t_start:.0f} s)")
        for r in ex.map(_process_safe, jobs):
            if "error" in r:
                log(f"ERROR {r['animal']} {r['pkey']}: {r['error']}\n{r['trace']}")
                continue
            i = r["info"]
            log(f"{i['animal']} {i['period']}: {i['n_fix']:,} fixes, IMU ok {i['imu_ok_s'] / 3600:.2f} h, still >=30 s "
                f"{i.get('seg30_' + ('strict' if 'seg30_strict_min' in i else 's50') + '_min', 0):.1f} min, acc cal {i['acc_cal']} ({i['acc_cal_n']}), "
                f"sessions {i['sessions']}, {i['runtime_s']} s")
            results.append(r)
    T = {}
    for key in ("segments", "metrics", "events", "jumps", "fixes", "windows"):
        parts = [r[key] for r in results if r[key] is not None and len(r[key])]
        T[key] = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    info = pd.DataFrame([r["info"] for r in results])
    mot = {k: pd.concat([r["motion"][k] for r in results if r["motion"] is not None and len(r["motion"][k])], ignore_index=True)
           for k in ("events", "jumps", "onsets", "blocks")}
    tb = out / "tables"
    info.to_csv(tb / "periods_info.csv", index=False)
    T["segments"].to_csv(tb / "segments.csv", index=False)
    T["metrics"].to_csv(tb / "segment_metrics.csv.gz", index=False)
    T["events"].to_csv(tb / "crazy_events.csv", index=False)
    T["jumps"].to_csv(tb / "still_jumps.csv.gz", index=False)
    T["fixes"].to_csv(tb / "still_fixes.csv.gz", index=False)
    T["windows"].to_csv(tb / "still_windows.csv.gz", index=False)
    mot["events"].to_csv(tb / "motion_events.csv", index=False)
    mot["jumps"].to_csv(tb / "motion_jumps.csv.gz", index=False)
    mot["onsets"].to_csv(tb / "onsets_offsets.csv", index=False)
    mot["blocks"].to_csv(tb / "motion_blocks.csv", index=False)
    wx = load_weather(cfg)
    wrows = []
    for pkey, p in cfg["periods"].items():
        lo, hi = C.to_ms(p["start"], ctx["tz"]), C.to_ms(p["end"], ctx["tz"])
        wrows.append({"period": pkey, "set": p["set"], "kind": p["kind"], "start": p["start"], "end": p["end"], "user_note": p.get("user_note", ""),
                      **period_weather(wx, lo, hi, float(cfg["weather"]["prior_h"]))})
    WP = pd.DataFrame(wrows)
    WP["local_daily_rain_mm"] = np.nan
    for d in sorted({p["start"][:10] for p in cfg["periods"].values()} | {p["end"][:10] for p in cfg["periods"].values()}):
        lo_d, hi_d = C.to_ms(d + " 00:00:00", ctx["tz"]), C.to_ms(d + " 00:00:00", ctx["tz"]) + 86_400_000
        WP.loc[len(WP)] = {"period": f"calendar day {d}", "set": "", "kind": "day-total", "start": d, "end": d, "user_note": "",
                           **period_weather(wx, lo_d, hi_d, 0.0), "local_daily_rain_mm": local_daily_rain(cfg, d)}
    WP.to_csv(tb / "weather_periods.csv", index=False)
    sw = Path(cfg["strict_windows_csv"])
    prov = {"config": Path(cfg["_path"]).relative_to(REPO).as_posix(), "git_commit": C.git_commit(),
            "wiser_db": str(cfg["wiser_db"]), "fix_cache_root": cfg["fix_cache"]["root"],
            "strict_windows_csv": {**C.file_info(sw, hash_it=True)}, "weather_cloud_csv": C.file_info(Path(cfg["weather"]["cloud_csv"]), hash_it=True),
            "imu_sessions": info[["animal", "period", "sessions", "pc_time"]].to_dict("records"),
            "smoothing_tuned_from": cfg["smoothing_config"], "runtime_compute_s": round(time.time() - t_start, 1)}
    (out / "input_provenance.json").write_text(json.dumps(prov, indent=2, default=str), encoding="utf-8")
    log(f"compute done ({time.time() - t_start:.0f} s)")
    fh.close()
    return out


# ====================================================================================================== aggregation
DRIFT_EDGES = np.arange(0.0, 150.0 + 1e-9, 0.1)     # values beyond the last edge fall into the last bin (medians unaffected)
SPEED_EDGES = np.arange(0.0, 200.0 + 1e-9, 0.05)


def load_tables(out: Path) -> dict:
    tb = out / "tables"
    T = {"info": pd.read_csv(tb / "periods_info.csv"), "S": pd.read_csv(tb / "segments.csv"), "M": pd.read_csv(tb / "segment_metrics.csv.gz"),
         "E": pd.read_csv(tb / "crazy_events.csv"), "J": pd.read_csv(tb / "still_jumps.csv.gz"), "F": pd.read_csv(tb / "still_fixes.csv.gz"),
         "V": pd.read_csv(tb / "still_rule_validation.csv"), "WP": pd.read_csv(tb / "weather_periods.csv")}
    for k, f in (("ME", "motion_events.csv"), ("MJ", "motion_jumps.csv.gz"), ("ON", "onsets_offsets.csv"), ("MB", "motion_blocks.csv")):
        p = tb / f
        try:
            T[k] = pd.read_csv(p)
        except Exception:  # noqa: BLE001  (empty table)
            T[k] = pd.DataFrame()
    return T


def load_speeds(out: Path, S: pd.DataFrame) -> dict:
    """method -> (segment row index into S (int64), speed (float32)) for the primary segments."""
    pos = pd.Series(np.arange(len(S)), index=S["seg_id"])
    acc = {m: ([], []) for m in METHODS}
    for f in sorted((out / "speeds").glob("*.npz")):
        with np.load(f) as z:
            ids = pos.reindex(z["seg_ids"]).to_numpy()
            for m in METHODS:
                if m in z.files:
                    idx = z[f"idx_{m}"]
                    acc[m][0].append(ids[idx].astype(np.int64))
                    acc[m][1].append(z[m].astype(np.float32))
    return {m: (np.concatenate(a) if a else np.zeros(0, np.int64), np.concatenate(v) if v else np.zeros(0, np.float32)) for m, (a, v) in acc.items()}


def still_summary(Sg: pd.DataFrame, M: pd.DataFrame, F: pd.DataFrame, SP: dict, method: str, Sall: pd.DataFrame) -> dict:
    ids = set(Sg["seg_id"])
    m = M[(M.method == method) & M.seg_id.isin(ids)]
    r = F.loc[F.seg_id.isin(ids), f"r_{method}"].to_numpy(float)
    hours = Sg["dur_trim_s"].sum() / 3600.0
    rows_sel = np.flatnonzero(Sall["seg_id"].isin(ids).to_numpy())
    si, sv = SP[method]
    v = sv[np.isin(si, rows_sel)] if len(si) else np.zeros(0)
    q = lambda x, p: float(np.percentile(x, p)) if len(x) else np.nan  # noqa: E731
    return {"method": method, "n_seg": int(len(Sg)), "still_h": hours, "n_fix": int(len(r)),
            "rms_in": float(np.sqrt(np.mean(r ** 2))) if len(r) else np.nan, "p50_in": q(r, 50), "p90_in": q(r, 90), "p99_in": q(r, 99),
            "drift10_med": float(m.drift10_in.median()), "drift10_p90": float(m.drift10_in.quantile(0.9)),
            "drift10_max": float(m.drift10_in.max()), "drift60_med": float(m.drift60_in.median()), "drift60_p90": float(m.drift60_in.quantile(0.9)),
            "n_seg60": int(m.drift60_in.notna().sum()),
            "crazy_n": int(m.crazy_n.sum()), "crazy_per_h": float(m.crazy_n.sum() / hours) if hours else np.nan,
            "crazy_frac": float(m.crazy_s.sum() / Sg["dur_trim_s"].sum()) if hours else np.nan,
            "jumps_n": int(m.jumps.sum()), "jumps_per_h": float(m.jumps.sum() / hours) if hours else np.nan,
            "speed_p50": q(v, 50), "speed_p95": q(v, 95), "speed_p99": q(v, 99),
            "path_in_per_min": float(m.path_in.sum() / (m.path_s.sum() / 60.0)) if m.path_s.sum() else np.nan}


def group_table(S: pd.DataFrame, M: pd.DataFrame, F: pd.DataFrame, SP: dict, by: list, methods: list,
                Sall: pd.DataFrame | None = None) -> pd.DataFrame:
    """Still summaries per group of S. Sall = the segment table whose row positions the speed index SP refers to (the full
    segments table, as passed to load_speeds); fix 2026-10-03: it was S itself (the subset being grouped), so the per-group
    speed quantiles read the wrong segments' speeds (plan implementation_plan/2026-10-03-wiser-v1b-zupt.md)."""
    Sall = S if Sall is None else Sall
    rows = []
    for key, g in S.groupby(by, dropna=False):
        key = key if isinstance(key, tuple) else (key,)
        for m in methods:
            rows.append({**dict(zip(by, key)), **still_summary(g, M, F, SP, m, Sall)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- bootstrap
def boot_counts(K: int, n_boot: int, rng: np.random.Generator) -> np.ndarray:
    """Row 0 = ones (point estimate); rows 1..n_boot = block resampling counts (with replacement)."""
    idx = rng.integers(0, K, size=(n_boot, K))
    flat = (idx + np.arange(n_boot)[:, None] * K).ravel()
    c = np.bincount(flat, minlength=n_boot * K).reshape(n_boot, K).astype(np.float64)
    return np.vstack([np.ones((1, K)), c])


def hist_q(H: np.ndarray, edges: np.ndarray, q: float) -> np.ndarray:
    cum = np.cumsum(H, axis=-1)
    tot = cum[..., -1:]
    j = np.argmax(cum >= q * tot, axis=-1)
    mid = 0.5 * (edges[:-1] + edges[1:])
    out = mid[np.minimum(j, len(mid) - 1)]
    return np.where(tot[..., 0] > 0, out, np.nan)


def block_arrays(S: pd.DataFrame, M: pd.DataFrame, F: pd.DataFrame, SP: dict, method: str, Sall: pd.DataFrame) -> dict:
    """Per-block sufficient statistics of one set (S = its primary >= 30-s segments) for one method."""
    S = S.copy()
    S["bkey"] = S["animal"] + "|" + S["period"] + "|" + S["block"].astype(str)
    keys = sorted(S["bkey"].unique())
    kpos = {k: i for i, k in enumerate(keys)}
    K = len(keys)
    zi = {"house": 0, "outside": 1}
    seg_b = S.set_index("seg_id")["bkey"].map(kpos)
    seg_z = S.set_index("seg_id")["zone"].map(lambda z: zi.get(z, 1))
    m = M[(M.method == method) & M.seg_id.isin(seg_b.index)].copy()
    m["b"] = m.seg_id.map(seg_b).astype(int)
    m["z"] = m.seg_id.map(seg_z).astype(int)
    dur = S.set_index("seg_id")["dur_trim_s"]
    m["dur"] = m.seg_id.map(dur)
    seg_a = S.set_index("seg_id")["anchor_bin"].astype(str).map({b: i for i, b in enumerate(ANCHOR_BINS)}).fillna(len(ANCHOR_BINS) - 1).astype(int)
    m["s"] = m.seg_id.map(seg_a).astype(int) * 2 + m["z"]          # segment stratum = segment median anchors bin x zone
    A = {"K": K, "keys": keys}
    NS = len(ANCHOR_BINS) * 2
    bi, si_ = m.b.to_numpy(), m.s.to_numpy()

    def strat(v):
        o = np.zeros((K, NS))
        np.add.at(o, (bi, si_), np.asarray(v, float))
        return o
    A["hours_s"] = strat(m.dur / 3600.0)
    A["crazy_st"] = strat(m.crazy_n)
    A["jumps_st"] = strat(m.jumps)
    A["hours"] = A["hours_s"].sum(axis=1)
    A["crazy"] = A["crazy_st"].sum(axis=1)
    A["jumps"] = A["jumps_st"].sum(axis=1)
    A["crazy_s"] = np.bincount(m.b, weights=m.crazy_s, minlength=K)
    A["dur_s"] = np.bincount(m.b, weights=m.dur, minlength=K)
    A["path"] = np.bincount(m.b, weights=m.path_in.fillna(0), minlength=K)
    A["path_s"] = np.bincount(m.b, weights=m.path_s.fillna(0), minlength=K)
    d = m.dropna(subset=["drift10_in"])
    jd = np.clip(np.searchsorted(DRIFT_EDGES, d.drift10_in.to_numpy(), side="right") - 1, 0, len(DRIFT_EDGES) - 2)
    Hs = np.zeros((K, NS, len(DRIFT_EDGES) - 1), np.float32)
    np.add.at(Hs, (d.b.to_numpy(), d.s.to_numpy(), jd), 1.0)
    A["drift_hs"] = Hs
    f = F[F.seg_id.isin(seg_b.index)]
    fb = f.seg_id.map(seg_b).to_numpy(int)
    fz = f.seg_id.map(seg_z).to_numpy(int)
    fa = pd.Series(anchor_bin(f.anchors.to_numpy())).map({b: i for i, b in enumerate(ANCHOR_BINS)}).to_numpy(int)
    r2 = f[f"r_{method}"].to_numpy(float) ** 2
    A["sr"] = np.column_stack([np.bincount(fb, weights=r2, minlength=K), np.bincount(fb, minlength=K).astype(float)])
    srs = np.zeros((K, len(ANCHOR_BINS) * 2, 2))
    s_idx = fa * 2 + fz
    np.add.at(srs, (fb, s_idx, 0), r2)
    np.add.at(srs, (fb, s_idx, 1), 1.0)
    A["srs"] = srs
    rows_sel = np.flatnonzero(Sall["seg_id"].isin(seg_b.index).to_numpy())
    si, sv = SP[method]
    sel = np.isin(si, rows_sel)
    seg_of_row = Sall["seg_id"].to_numpy()
    vb = pd.Series(seg_of_row[si[sel]]).map(seg_b).to_numpy(int)
    js = np.clip(np.searchsorted(SPEED_EDGES, sv[sel], side="right") - 1, 0, len(SPEED_EDGES) - 2)
    HS = np.zeros((K, len(SPEED_EDGES) - 1), np.float32)
    np.add.at(HS, (vb, js), 1.0)
    A["speed_h"] = HS
    return A


def _mm3(cnt: np.ndarray, X: np.ndarray) -> np.ndarray:
    """cnt (n, K) times X (K, a, b) -> (n, a, b) with one BLAS matmul."""
    K, a, b = X.shape
    return (cnt.astype(X.dtype) @ X.reshape(K, a * b)).reshape(-1, a, b).astype(np.float64)


def set_stats(A: dict, cnt: np.ndarray) -> dict:
    o = {}
    sr = cnt @ A["sr"]
    o["rms"] = np.sqrt(sr[:, 0] / np.maximum(sr[:, 1], 1e-12))
    o["srs"] = _mm3(cnt, A["srs"])
    o["drift_hs"] = _mm3(cnt, A["drift_hs"])
    o["drift_med"] = hist_q(o["drift_hs"].sum(axis=1), DRIFT_EDGES, 0.5)
    h = cnt @ A["hours"]
    o["hours"] = h
    o["crazy_rate"] = (cnt @ A["crazy"]) / np.maximum(h, 1e-12)
    o["crazy_frac"] = (cnt @ A["crazy_s"]) / np.maximum(cnt @ A["dur_s"], 1e-12)
    o["jump_rate"] = (cnt @ A["jumps"]) / np.maximum(h, 1e-12)
    o["hours_s"] = cnt @ A["hours_s"]
    o["crazy_st"] = cnt @ A["crazy_st"]
    o["jumps_st"] = cnt @ A["jumps_st"]
    o["speed_p95"] = hist_q((cnt.astype(np.float32) @ A["speed_h"]).astype(np.float64), SPEED_EDGES, 0.95)
    o["path_rate"] = (cnt @ A["path"]) / np.maximum((cnt @ A["path_s"]) / 60.0, 1e-12)
    return o


def _zone_of_strata(X: np.ndarray) -> np.ndarray:
    """(n, 8, ...) segment strata (anchor bin x zone) -> (n, 2, ...) zones."""
    return np.stack([X[:, 0::2].sum(axis=1), X[:, 1::2].sum(axis=1)], axis=1)


def ci(x: np.ndarray) -> tuple[float, float, float]:
    """Point estimate (row 0) and the 2.5 / 97.5 percentiles of the bootstrap rows."""
    b = x[1:]
    b = b[np.isfinite(b)]
    return float(x[0]), (float(np.percentile(b, 2.5)) if len(b) else np.nan), (float(np.percentile(b, 97.5)) if len(b) else np.nan)


def compare_sets(Ar: dict, Ac: dict, n_boot: int, rng: np.random.Generator) -> list:
    """Rain/calm ratios with block-bootstrap CIs; raw and standardised (anchors x zone for the per-fix RMS, zone for the
    segment / event metrics: rain strata re-weighted to the calm weights)."""
    cr, cc = boot_counts(Ar["K"], n_boot, rng), boot_counts(Ac["K"], n_boot, rng)
    R, Cc = set_stats(Ar, cr), set_stats(Ac, cc)
    rows = []

    def add(metric, num, den, std="none"):
        with np.errstate(divide="ignore", invalid="ignore"):
            e, lo, hi = ci(num / den)
        rows.append({"metric": metric, "std": std, "standardised": std != "none", "rain": float(num[0]), "calm": float(den[0]),
                     "ratio": e, "lo": lo, "hi": hi})
    for k in ("rms", "drift_med", "crazy_rate", "crazy_frac", "jump_rate", "speed_p95", "path_rate"):
        add(k, R[k], Cc[k])
    # per-fix RMS standardised over the fix's anchors x zone (strata present in both sets)
    tr, tc = R["srs"], Cc["srs"]
    okm = (tr[..., 1] > 0) & (tc[..., 1] > 0)
    w = np.where(okm, tc[..., 1], 0.0)
    w = w / np.maximum(w.sum(axis=1, keepdims=True), 1e-12)
    msr = np.where(okm, tr[..., 0] / np.maximum(tr[..., 1], 1e-12), 0.0)
    msc = np.where(okm, tc[..., 0] / np.maximum(tc[..., 1], 1e-12), 0.0)
    add("rms", np.sqrt((w * msr).sum(axis=1)), np.sqrt((w * msc).sum(axis=1)), "anchors×zone")
    # segment / event metrics standardised by zone and by segment anchors x zone (rain strata re-weighted to calm weights)
    for label, conv in (("zone", _zone_of_strata), ("anchors×zone", lambda X: X)):
        hr, hc = conv(R["hours_s"]), conv(Cc["hours_s"])
        ok_ = (hr > 0) & (hc > 0)
        ws = np.where(ok_, hc, 0.0)
        ws = ws / np.maximum(ws.sum(axis=1, keepdims=True), 1e-12)
        for k, kst in (("crazy_rate", "crazy_st"), ("jump_rate", "jumps_st")):
            rr_ = np.where(ok_, conv(R[kst]) / np.maximum(hr, 1e-12), 0.0)
            rc_ = np.where(ok_, conv(Cc[kst]) / np.maximum(hc, 1e-12), 0.0)
            add(k, (ws * rr_).sum(axis=1), (ws * rc_).sum(axis=1), label)
        Hr, Hc = conv(R["drift_hs"]), conv(Cc["drift_hs"])
        nr, nc = Hr.sum(axis=2), Hc.sum(axis=2)
        okd = (nr > 0) & (nc > 0)
        wc_ = np.where(okd, nc, 0.0)
        wc_ = wc_ / np.maximum(wc_.sum(axis=1, keepdims=True), 1e-12)
        fac_r = np.where(okd, wc_ / np.maximum(nr, 1e-12), 0.0)
        fac_c = np.where(okd, wc_ / np.maximum(nc, 1e-12), 0.0)
        add("drift_med", hist_q((Hr * fac_r[:, :, None]).sum(axis=1), DRIFT_EDGES, 0.5),
            hist_q((Hc * fac_c[:, :, None]).sum(axis=1), DRIFT_EDGES, 0.5), label)
    # within-stratum ratios: per-fix RMS by the fix's anchors; drift / crazy rate by the segment's median anchors
    for ai, ab in enumerate(ANCHOR_BINS):
        nr_ = tr[:, ai * 2:(ai + 1) * 2, :].sum(axis=1)
        nc_ = tc[:, ai * 2:(ai + 1) * 2, :].sum(axis=1)
        if nr_[0, 1] > 0 and nc_[0, 1] > 0:
            add(f"rms_anchors_{ab}", np.sqrt(nr_[:, 0] / np.maximum(nr_[:, 1], 1e-12)), np.sqrt(nc_[:, 0] / np.maximum(nc_[:, 1], 1e-12)))
        Hr_ = R["drift_hs"][:, ai * 2:(ai + 1) * 2].sum(axis=1)
        Hc_ = Cc["drift_hs"][:, ai * 2:(ai + 1) * 2].sum(axis=1)
        if Hr_[0].sum() >= 5 and Hc_[0].sum() >= 5:
            add(f"drift_med_seganchors_{ab}", hist_q(Hr_, DRIFT_EDGES, 0.5), hist_q(Hc_, DRIFT_EDGES, 0.5))
            hr_ = R["hours_s"][:, ai * 2:(ai + 1) * 2].sum(axis=1)
            hc_ = Cc["hours_s"][:, ai * 2:(ai + 1) * 2].sum(axis=1)
            add(f"crazy_rate_seganchors_{ab}", R["crazy_st"][:, ai * 2:(ai + 1) * 2].sum(axis=1) / np.maximum(hr_, 1e-12),
                Cc["crazy_st"][:, ai * 2:(ai + 1) * 2].sum(axis=1) / np.maximum(hc_, 1e-12))
    return rows


def motion_block_arrays(MB: pd.DataFrame, ME: pd.DataFrame, MJ: pd.DataFrame, method: str, periods: list) -> dict:
    B_ = MB[MB.period.isin(periods)].copy()
    B_["bkey"] = B_["animal"] + "|" + B_["period"] + "|" + B_["block"].astype(str)
    keys = sorted(B_["bkey"].unique())
    kpos = {k: i for i, k in enumerate(keys)}
    K = len(keys)
    okh = np.bincount(B_.bkey.map(kpos), weights=B_.ok_s / 3600.0, minlength=K)

    def cnt(df):
        if not len(df):
            return np.zeros(K)
        d = df[(df.method == method) & df.period.isin(periods)]
        bk = (d["animal"] + "|" + d["period"] + "|" + d["block"].astype(str)).map(kpos).dropna().astype(int)
        return np.bincount(bk, minlength=K).astype(float)
    ev = cnt(ME)
    qj = cnt(MJ[MJ.imu_class == "imu_quiet"]) if len(MJ) else np.zeros(K)
    aj = cnt(MJ[MJ.sec_ok]) if len(MJ) else np.zeros(K)
    return {"K": K, "okh": okh, "imp": ev, "qj": qj, "aj": aj}


def compare_motion(Ar: dict, Ac: dict, n_boot: int, rng: np.random.Generator) -> list:
    cr, cc = boot_counts(Ar["K"], n_boot, rng), boot_counts(Ac["K"], n_boot, rng)
    rows = []
    for k, name in (("imp", "impossible_speed_rate"), ("qj", "imu_quiet_jump_rate"), ("aj", "jump_rate_all")):
        num = (cr @ Ar[k]) / np.maximum(cr @ Ar["okh"], 1e-12)
        den = (cc @ Ac[k]) / np.maximum(cc @ Ac["okh"], 1e-12)
        with np.errstate(divide="ignore", invalid="ignore"):
            e, lo, hi = ci(num / den)
        rows.append({"metric": name, "std": "none", "standardised": False, "rain": float(num[0]), "calm": float(den[0]), "ratio": e, "lo": lo, "hi": hi})
    return rows


# ---------------------------------------------------------------- the analysis (reads only the saved tables)
def raining_segments(S: pd.DataFrame, F: pd.DataFrame) -> pd.Series:
    fr = F.groupby("seg_id")["raining"].mean()
    return S["seg_id"].map(fr).fillna(0.0)


def analyze(out: Path, cfg: dict, fh=None) -> dict:
    t0 = time.time()
    T = load_tables(out)
    S, Mt, F, E, J = T["S"], T["M"], T["F"], T["E"], T["J"]
    for c in ("primary", "scored", "ge30"):
        S[c] = S[c].astype(bool)
    wx = load_weather(cfg)
    WP = T["WP"]
    if "local_daily_rain_mm" not in WP.columns or WP["local_daily_rain_mm"].isna().all():
        WP["local_daily_rain_mm"] = [local_daily_rain(cfg, str(r.start)[:10]) if r.kind == "day-total" else np.nan for r in WP.itertuples()]
        WP.to_csv(out / "tables" / "weather_periods.csv", index=False)
    F["raining"] = raining_at(wx, F["t_al_ms"].to_numpy(float), float(cfg["weather"]["row_s"]))
    F = F.merge(S[["seg_id", "animal", "period", "set", "kind", "zone", "block", "ge30"]], on="seg_id", how="left")
    S["rain_frac"] = raining_segments(S, F)
    SP = load_speeds(out, S)
    Sp = S[S.primary & S.scored]
    Sp30 = Sp[Sp.ge30]
    res = {"cfg_path": cfg["_path"], "run_dir": str(out)}
    tb = out / "tables"
    # ---- coverage
    info = T["info"]
    cov = []
    for (pk, a), g in info.groupby(["period", "animal"]):
        s = Sp[(Sp.period == pk) & (Sp.animal == a)]
        cov.append({"period": pk, "animal": a, "set": g.set.iloc[0], "kind": g.kind.iloc[0], "imu_ok_h": float(g.imu_ok_s.iloc[0] / 3600),
                    "still30_h": float(s[s.ge30].dur_s.sum() / 3600), "still10_h": float(s.dur_s.sum() / 3600),
                    "n_fix": int(g.n_fix.iloc[0]), "fix_rate_hz": float(g.fix_rate_hz.iloc[0]), "anchors_le6_frac": float(g.anchors_le6_frac.iloc[0]),
                    "anchors_9_frac": float(g.anchors_9_frac.iloc[0]), "acc_cal": g.acc_cal.iloc[0], "sessions": g.sessions.iloc[0]})
    COV = pd.DataFrame(cov)
    COV.to_csv(tb / "summary_coverage.csv", index=False)
    # ---- Q1 / Q2 tables
    # Sall = S: the speed index SP holds row positions of the full segments table (load_speeds(out, S)); fix 2026-10-03
    tabs = {"period": group_table(Sp30, Mt, F, SP, ["set", "kind", "period"], METHODS, S),
            "setkind": group_table(Sp30, Mt, F, SP, ["set", "kind"], METHODS, S),
            "set": group_table(Sp30, Mt, F, SP, ["set"], METHODS, S),
            "animal": group_table(Sp30, Mt, F, SP, ["set", "animal"], ["raw", "B2p"], S),
            "zone": group_table(Sp30, Mt, F, SP, ["set", "kind", "zone"], ["raw", "B2p"], S),
            "segbin": group_table(Sp30, Mt, F, SP, ["set", "anchor_bin"], ["raw", "B2p"], S),
            "hour": group_table(Sp30, Mt, F, SP, ["set", "kind", "hour"], ["raw", "B2p"], S),
            "ge10": group_table(Sp, Mt, F, SP, ["set", "kind"], POS_ONLY, S)}
    for k, v in tabs.items():
        v.to_csv(tb / f"summary_still_{k}.csv", index=False)
    F30 = F[F.ge30.astype(bool)].copy()
    F30["abin"] = anchor_bin(F30.anchors.to_numpy())
    fixbin = F30.groupby(["set", "abin"]).agg(n=("r_raw", "size"), rms_raw=("r_raw", lambda x: float(np.sqrt(np.mean(x ** 2)))),
                                              p90_raw=("r_raw", lambda x: float(np.percentile(x, 90))),
                                              rms_B2p=("r_B2p", lambda x: float(np.sqrt(np.mean(x ** 2))))).reset_index()
    fixbin["share"] = fixbin.n / fixbin.groupby("set").n.transform("sum")
    fixbin.to_csv(tb / "summary_fix_by_anchors.csv", index=False)
    tabs["fixbin"] = fixbin
    Ep = E[(E.method == "raw") & E.primary.astype(bool) & E.ge30.astype(bool)].copy() if len(E) else E
    res["truth_alt_shift_med"] = float(Sp30.truth_alt_shift_in.median())
    res["truth_alt_shift_p90"] = float(Sp30.truth_alt_shift_in.quantile(0.9))
    # strict vs S50 sensitivity on the strict periods
    stp = [k for k, p in cfg["periods"].items() if p.get("strict_period")]
    sens = []
    for src in ("strict", "s50", "s50_up"):
        g = S[S.period.isin(stp) & S.scored & S.ge30 & (S.source == src)]
        if not len(g):
            continue
        for m in ("raw", "B2p"):
            mm = Mt[Mt.seg_id.isin(set(g.seg_id)) & (Mt.method == m)]
            hours = g.dur_trim_s.sum() / 3600
            sens.append({"source": src, "method": m, "n_seg": len(g), "still_h": hours, "rms_seg_med": float(mm.rms_in.median()),
                         "drift10_med": float(mm.drift10_in.median()), "drift10_p90": float(mm.drift10_in.quantile(0.9)),
                         "crazy_per_h": float(mm.crazy_n.sum() / hours), "jumps_per_h": float(mm.jumps.sum() / hours),
                         "path_in_per_min": float(mm.path_in.sum() / (mm.path_s.sum() / 60))})
    SENS = pd.DataFrame(sens)
    SENS.to_csv(tb / "summary_strict_vs_s50.csv", index=False)
    # ---- Q3 motion (nights)
    ME, MJ, ON, MB = T["ME"], T["MJ"], T["ON"], T["MB"]
    nights = [k for k, p in cfg["periods"].items() if p["kind"] == "night"]
    mrows = []
    okh = MB.groupby("period").ok_s.sum() / 3600 if len(MB) else pd.Series(dtype=float)
    for pk in nights:
        oh = float(okh.get(pk, np.nan))
        for m in METHODS:
            ev = ME[(ME.period == pk) & (ME.method == m)] if len(ME) else pd.DataFrame(columns=["imu_still_frac", "imu_loco_frac", "anchors_min"])
            jp = MJ[(MJ.period == pk) & (MJ.method == m) & MJ.sec_ok.astype(bool)] if len(MJ) else pd.DataFrame(columns=["imu_class", "anchors_min"])
            nq = int((jp.imu_class == "imu_quiet").sum())
            mrows.append({"period": pk, "set": cfg["periods"][pk]["set"], "method": m, "ok_h": oh, "imp_n": len(ev), "imp_per_h": len(ev) / oh,
                          "imp_still_n": int((ev.imu_still_frac > 0.5).sum()), "imp_loco_n": int((ev.imu_loco_frac > 0).sum()),
                          "imp_le6_frac": float((ev.anchors_min <= 6).mean()) if len(ev) else np.nan,
                          "jumps_n": len(jp), "jumps_per_h": len(jp) / oh, "qjumps_n": nq, "qjumps_per_h": nq / oh,
                          "ajumps_per_h": float((jp.imu_class == "imu_active").sum() / oh),
                          "jumps_le6_frac": float((jp.anchors_min <= 6).mean()) if len(jp) else np.nan})
    MOT = pd.DataFrame(mrows)
    MOT.to_csv(tb / "summary_motion_by_night.csv", index=False)
    mset = MOT.groupby(["set", "method"]).agg(ok_h=("ok_h", "sum"), imp_n=("imp_n", "sum"), jumps_n=("jumps_n", "sum"),
                                               qjumps_n=("qjumps_n", "sum"), imp_still_n=("imp_still_n", "sum"),
                                               imp_loco_n=("imp_loco_n", "sum")).reset_index()
    for k in ("imp", "jumps", "qjumps"):
        mset[f"{k}_per_h"] = mset[f"{k}_n"] / mset.ok_h
    mset.to_csv(tb / "summary_motion_by_set.csv", index=False)
    JB = JZ = pd.DataFrame()
    if len(MJ):
        mj = MJ[(MJ.method == "raw") & MJ.sec_ok.astype(bool)].copy()
        mj["abin"] = anchor_bin(mj.anchors_min.to_numpy())
        mj["zone2"] = mj.zone.map(zone2)
        JB = mj.groupby(["set", "abin", "imu_class"]).size().unstack(fill_value=0).reset_index()
        JB.to_csv(tb / "summary_motion_jumps_by_anchors.csv", index=False)
        JZ = mj.groupby(["set", "zone2", "imu_class"]).size().unstack(fill_value=0).reset_index()
        JZ.to_csv(tb / "summary_motion_jumps_by_zone.csv", index=False)
    if len(ON):
        on = ON[ON.status != "no_reference"]
        OS = on.groupby(["set", "kind", "method", "status"]).size().unstack(fill_value=0)
        OS["n"] = OS.sum(axis=1)
        OS = OS.reset_index()
        OL = on.groupby(["set", "kind", "method"]).agg(lag_loco_med=("lag_loco_s", "median"), lag_still_med=("lag_still_s", "median"),
                                                      lag_still_p90=("lag_still_s", lambda x: float(np.nanpercentile(x, 90)) if x.notna().any() else np.nan),
                                                      n=("status", "size")).reset_index()
        OS.to_csv(tb / "summary_onsets_status.csv", index=False)
        OL.to_csv(tb / "summary_onsets_lags.csv", index=False)
    else:
        OS = OL = pd.DataFrame()
    # ---- Q4 bootstrap
    bc = cfg["bootstrap"]
    rng = np.random.default_rng(int(bc["seed"]))
    q4 = []
    for cname, kind in (("pooled", None), ("night", "night"), ("day", "day")):
        sel = Sp30 if kind is None else Sp30[Sp30.kind == kind]
        for m in ("raw", "B2p"):
            r_, c_ = sel[sel.set == "rain"], sel[sel.set == "calm"]
            if not len(r_) or not len(c_):
                continue
            Ar, Ac = block_arrays(r_, Mt, F, SP, m, S), block_arrays(c_, Mt, F, SP, m, S)
            for row in compare_sets(Ar, Ac, int(bc["n_boot"]), rng):
                q4.append({"comparison": cname, "method": m, "n_blocks_rain": Ar["K"], "n_blocks_calm": Ac["K"], **row})
    rs = Sp30[Sp30.set == "rain"]
    for m in ("raw", "B2p"):
        a_, b_ = rs[rs.rain_frac >= 0.5], rs[rs.rain_frac < 0.5]
        if len(a_) >= 5 and len(b_) >= 5:
            Ar, Ac = block_arrays(a_, Mt, F, SP, m, S), block_arrays(b_, Mt, F, SP, m, S)
            for row in compare_sets(Ar, Ac, int(bc["n_boot"]), rng):
                if "anchors_" not in row["metric"]:
                    q4.append({"comparison": "raining_now_vs_wet", "method": m, "n_blocks_rain": Ar["K"], "n_blocks_calm": Ac["K"], **row})
    if len(MB):
        rn = [k for k in nights if cfg["periods"][k]["set"] == "rain"]
        cn = [k for k in nights if cfg["periods"][k]["set"] == "calm"]
        for m in ("raw", "B2p"):
            Ar, Ac = motion_block_arrays(MB, ME, MJ, m, rn), motion_block_arrays(MB, ME, MJ, m, cn)
            for row in compare_motion(Ar, Ac, int(bc["n_boot"]), rng):
                q4.append({"comparison": "night_motion", "method": m, "n_blocks_rain": Ar["K"], "n_blocks_calm": Ac["K"], **row})
    Q4 = pd.DataFrame(q4)
    Q4.to_csv(tb / "summary_rain_vs_calm_bootstrap.csv", index=False)

    def pick(comp, metric, std, m="raw"):
        r = Q4[(Q4.comparison == comp) & (Q4.metric == metric) & (Q4["std"] == std) & (Q4.method == m)] if len(Q4) else Q4
        return r.iloc[0].to_dict() if len(r) else None
    parts = {}
    for metric in ("crazy_rate", "drift_med"):
        pr, nr = pick("pooled", metric, "none"), pick("night", metric, "none")
        ps_, ns_ = pick("pooled", metric, "anchors×zone"), pick("night", metric, "anchors×zone")
        parts[metric] = {"raw_up": bool(pr and nr and pr["lo"] > 1 and nr["lo"] > 1),
                         "std_up": bool(ps_ and ns_ and ps_["lo"] > 1 and ns_["lo"] > 1),
                         "raw_down": bool(pr and nr and pr["hi"] < 1 and nr["hi"] < 1)}
    if any(v["raw_up"] and v["std_up"] for v in parts.values()):
        verdict = "CONFIRMED"
    elif any(v["raw_up"] for v in parts.values()):
        verdict = "CONFIRMED, LARGELY VIA FEWER ANCHORS (the anchors × zone–standardised CI reaches 1)"
    elif any(v["raw_down"] for v in parts.values()):
        verdict = "NOT CONFIRMED (the rain periods drift less)"
    else:
        verdict = "NOT CONFIRMED"
    res["q4_verdict"], res["q4_verdict_parts"] = verdict, parts
    # ---- worst crazy-drift events (raw, primary >= 30-s segments), topped up with the largest sub-threshold 10-s drifts
    worst = pd.DataFrame()
    nw = int(cfg["n_worst_events"])
    ev_list = Ep.sort_values(["size_in", "dur_s"], ascending=False).head(nw).copy() if len(Ep) else pd.DataFrame()
    if len(ev_list):
        ev_list["etype"] = "event"
    if len(ev_list) < nw:
        ev_ids = set(Ep.seg_id) if len(Ep) else set()
        mm = Mt[(Mt.method == "raw") & Mt.seg_id.isin(set(Sp30.seg_id)) & ~Mt.seg_id.isin(ev_ids)].nlargest(nw - len(ev_list), "drift10_in")
        near = []
        for r in mm.itertuples():
            sg = S[S.seg_id == r.seg_id].iloc[0]
            lo_p = C.to_ms(cfg["periods"][sg.period]["start"], cfg["tz"])
            with np.load(out / "tracks" / f"{sg.animal}_{sg.period}.npz") as z:
                ta = z["t_al_ms"]
                sel = (ta >= sg.t0_ms + 1000 * cfg["still"]["trim_s"]) & (ta < sg.t1_ms - 1000 * cfg["still"]["trim_s"])
                tt = (ta[sel] - lo_p) / 1000.0
                pr_ = z["raw"][sel].astype(float)
                an = z["anchors"][sel].astype(float)
            ts_, te_ = tt[0], tt[-1]
            cc_ = np.arange(ts_ + 5.0, te_ - 5.0 + 1e-9, 1.0)
            m10, _ = roll_median(tt, pr_, cc_, 5.0, int(cfg["metrics"]["roll_short_min_fix"]))
            d10 = np.hypot(m10[:, 0] - sg.truth_x, m10[:, 1] - sg.truth_y)
            j = int(np.nanargmax(d10))
            thr_run = cfg["metrics"]["crazy_in"] if d10[j] >= cfg["metrics"]["crazy_in"] else 0.5 * d10[j]
            half = np.nan_to_num(d10, nan=0.0) >= thr_run
            a_, b_ = j, j + 1
            while a_ > 0 and half[a_ - 1]:
                a_ -= 1
            while b_ < len(half) and half[b_]:
                b_ += 1
            etype = (f"short (≥ {cfg['metrics']['crazy_in']:.0f} in for < {cfg['metrics']['crazy_min_s']} s)" if d10[j] >= cfg["metrics"]["crazy_in"]
                     else f"near (< {cfg['metrics']['crazy_in']:.0f} in)")
            g0, g1 = cc_[a_] - 5.0, cc_[b_ - 1] + 5.0
            k0, k1 = np.searchsorted(tt, [g0, g1])
            near.append({"seg_id": r.seg_id, "animal": sg.animal, "period": sg.period, "set": sg.set, "kind": sg.kind, "method": "raw",
                         "start_ms": lo_p + g0 * 1000, "end_ms": lo_p + g1 * 1000, "dur_s": int(b_ - a_), "size_in": float(d10[j]),
                         "anchors_med": float(np.median(an[k0:k1])) if k1 > k0 else np.nan,
                         "anchors_le6_frac": float((an[k0:k1] <= 6).mean()) if k1 > k0 else np.nan, "zone_detail": sg.zone_detail,
                         "zone": sg.zone, "seg_dur_s": sg.dur_s, "etype": etype})
        ev_list = pd.concat([ev_list, pd.DataFrame(near)], ignore_index=True)
    if len(ev_list):
        worst = ev_list.copy()
        vc = cfg["video"]
        chans = sorted({c for v in vc["channels_by_zone"].values() for c in v})
        cfgv = {"human_checks": {"channels": chans, "video_root": vc["root"]}, "tz": cfg["tz"]}
        vids = []
        for r in worst.itertuples():
            v = GV2.video_lookup(float(r.start_ms), cfgv)
            zc = vc["channels_by_zone"].get(r.zone_detail, vc["channels_by_zone"]["outside"])
            vids.append("; ".join(f"{c}: {v.get(c, 'n/a')}" for c in zc))
        worst["start_local"] = [ms_local(x, cfg["tz"]) for x in worst.start_ms]
        worst["end_local"] = [ms_local(x, cfg["tz"]) for x in worst.end_ms]
        worst["video"] = vids
        worst.to_csv(tb / "worst_crazy_events.csv", index=False)
    res["runtime_analyze_s"] = round(time.time() - t0, 1)
    (out / "summary.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    log_to(fh, f"analysis done ({res['runtime_analyze_s']} s); Q4 verdict: {verdict}")
    return {"res": res, "S": S, "Sp": Sp, "Sp30": Sp30, "M": Mt, "F": F, "E": E, "Ep": Ep, "J": J, "SP": SP, "COV": COV, "tabs": tabs,
            "SENS": SENS, "MOT": MOT, "mset": mset, "OS": OS, "OL": OL, "Q4": Q4, "worst": worst, "V": T["V"], "WP": T["WP"], "info": info,
            "ME": ME, "MJ": MJ, "ON": ON, "JB": JB, "JZ": JZ}


# ====================================================================================================== figures
COL = {"raw": "#7f7f7f", "B1": "#1f77b4", "B2": "#2ca02c", "B2p": "#d62728", "B2pb": "#ff9896", "V1": "#9467bd", "V2": "#8c564b"}


def make_figures(A: dict, cfg: dict, out: Path, fdir: Path, cohort: str) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figs = {}
    order = list(cfg["periods"])
    short = {k: ("D " if p["kind"] == "day" else "N ") + k.split("_")[1][4:6] + "-" + k.split("_")[1][6:8] + (" (rain)" if p["set"] == "rain" else "")
             for k, p in cfg["periods"].items()}
    # 1) still error by period and method
    tp = A["tabs"]["period"]
    fig, axs = plt.subplots(3, 1, figsize=(11, 9), sharex=True)
    meths = POS_ONLY
    x = np.arange(len(order))
    wdt = 0.8 / len(meths)
    for ax, col, lab in zip(axs, ("rms_in", "crazy_per_h", "path_in_per_min"),
                            ("per-fix RMS distance from truth (in)", "crazy-drift events per still-hour", "fake path (in per min of stillness)")):
        for i, m in enumerate(meths):
            v = [float(tp[(tp.period == k) & (tp.method == m)][col].iloc[0]) if len(tp[(tp.period == k) & (tp.method == m)]) else np.nan for k in order]
            ax.bar(x + (i - (len(meths) - 1) / 2) * wdt, v, wdt, color=COL[m], label=LABEL[m])
        ax.set_ylabel(lab)
        nc = sum(1 for k in order if cfg["periods"][k]["set"] == "calm")
        ax.axvline(nc - 0.5, color="k", ls="--", lw=0.8)
        ax.grid(axis="y", alpha=0.3)
    axs[0].legend(ncol=4, fontsize=8, loc="upper left")
    axs[-1].set_xticks(x)
    axs[-1].set_xticklabels([short[k] for k in order], rotation=30, ha="right")
    axs[0].set_title("WISER during certified head stillness (segments ≥ 30 s; truth = segment median); left of the dashed line calm-dry, right rain")
    fig.tight_layout()
    p = fdir / f"{STEM}_still_by_period_{cohort}.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    figs["still_by_period"] = p.name
    # 2) rain effect forest plot
    Q4 = A["Q4"]
    if len(Q4):
        q = Q4[(Q4.method == "raw") & ~Q4.metric.str.contains("anchors_") & Q4["std"].isin(["none", "anchors×zone"])].copy()
        comps = [c for c in ("pooled", "night", "day", "raining_now_vs_wet", "night_motion") if c in set(q.comparison)]
        mets = [m for m in ("rms", "drift_med", "crazy_rate", "crazy_frac", "jump_rate", "speed_p95", "path_rate",
                            "impossible_speed_rate", "imu_quiet_jump_rate", "jump_rate_all") if m in set(q.metric)]
        rows = [(c, m) for c in comps for m in mets if len(q[(q.comparison == c) & (q.metric == m)])]
        fig, ax = plt.subplots(figsize=(8, 0.32 * len(rows) + 1.5))
        for i, (c, m) in enumerate(rows):
            for std, mk, off in ((False, "o", -0.12), (True, "s", 0.12)):
                r = q[(q.comparison == c) & (q.metric == m) & (q.standardised == std)]
                if not len(r):
                    continue
                r = r.iloc[0]
                if not (np.isfinite(r.ratio) and r.ratio > 0):
                    ax.text(1.0, i + off, "  calm = 0 → undefined", fontsize=6, va="center")
                    continue
                lo_e = max(r.ratio - r.lo, 0) if np.isfinite(r.lo) else 0.0
                hi_e = max(r.hi - r.ratio, 0) if np.isfinite(r.hi) else 0.0
                ax.errorbar([r.ratio], [i + off], xerr=[[lo_e], [hi_e]], fmt=mk, color="k" if not std else "#d62728",
                            mfc="k" if not std else "none", ms=4, lw=1)
        ax.axvline(1.0, color="gray", lw=0.8)
        ax.set_yticks(range(len(rows)))
        ax.set_yticklabels([f"{c}: {m}" for c, m in rows], fontsize=8)
        ax.invert_yaxis()
        ax.set_xscale("log")
        ax.set_xlabel("rain / calm ratio (95 % 10-min block-bootstrap CI); ● raw, □ standardised over anchors × zone")
        ax.grid(axis="x", alpha=0.3)
        fig.tight_layout()
        p = fdir / f"{STEM}_rain_effect_{cohort}.png"
        fig.savefig(p, dpi=130)
        plt.close(fig)
        figs["rain_effect"] = p.name
    # 3) strata
    fb, tz_, th = A["tabs"]["fixbin"], A["tabs"]["zone"], A["tabs"]["hour"]
    fig, axs = plt.subplots(1, 3, figsize=(14, 4))
    for j, s in enumerate(("calm", "rain")):
        g = fb[fb.set == s].set_index("abin").reindex(ANCHOR_BINS)
        axs[0].bar(np.arange(4) + (j - 0.5) * 0.4, g.rms_raw, 0.4, label=f"{s}", color="#1f77b4" if s == "calm" else "#ff7f0e")
        for k, (v, sh) in enumerate(zip(g.rms_raw, g.share)):
            if np.isfinite(v):
                axs[0].text(k + (j - 0.5) * 0.4, v, f"{100 * sh:.0f}%", ha="center", va="bottom", fontsize=7)
    axs[0].set_xticks(range(4))
    axs[0].set_xticklabels(ANCHOR_BINS)
    axs[0].set_xlabel("anchors_used of the fix")
    axs[0].set_ylabel("per-fix RMS from truth (in), raw")
    axs[0].set_yscale("log")
    axs[0].legend(title="label = share of still fixes", fontsize=8)
    lab, val, cc = [], [], []
    for s in ("calm", "rain"):
        for k in ("night", "day"):
            for z in ("house", "outside"):
                g = tz_[(tz_.set == s) & (tz_.kind == k) & (tz_.zone == z) & (tz_.method == "raw")]
                if len(g):
                    lab.append(f"{s} {k}\n{z}\n({g.still_h.iloc[0]:.1f} h)")
                    val.append(g.crazy_per_h.iloc[0])
                    cc.append("#1f77b4" if s == "calm" else "#ff7f0e")
    axs[1].bar(range(len(val)), val, color=cc)
    axs[1].set_xticks(range(len(val)))
    axs[1].set_xticklabels(lab, fontsize=7)
    axs[1].set_ylabel("crazy-drift events per still-hour (raw)")
    for s, k, mk in (("calm", "night", "o-"), ("calm", "day", "s-"), ("rain", "night", "o--"), ("rain", "day", "s--")):
        g = th[(th.set == s) & (th.kind == k) & (th.method == "raw") & (th.still_h >= 0.25)].copy()
        if len(g):
            hh = (g.hour.astype(int) + (24 if k == "night" else 0) * (g.hour.astype(int) < 12)).to_numpy()
            o = np.argsort(hh)
            axs[2].plot(hh[o], g.crazy_per_h.to_numpy()[o], mk, label=f"{s} {k}", color="#1f77b4" if s == "calm" else "#ff7f0e", ms=4)
    axs[2].set_xlabel("local hour (night hours after midnight shown as 24+)")
    axs[2].set_ylabel("crazy-drift events per still-hour (raw)")
    axs[2].legend(fontsize=8)
    fig.tight_layout()
    p = fdir / f"{STEM}_strata_{cohort}.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    figs["strata"] = p.name
    # 4) examples: the 2 worst calm and the 2 worst rain crazy-drift events
    Ep, S = A["Ep"], A["S"]
    if len(Ep):
        ex = pd.concat([Ep[Ep.set == "calm"].nlargest(2, "size_in"), Ep[Ep.set == "rain"].nlargest(2, "size_in")])
        fig, axs = plt.subplots(len(ex), 1, figsize=(11, 2.4 * len(ex)))
        axs = np.atleast_1d(axs)
        for ax, r in zip(axs, ex.itertuples()):
            sg = S[S.seg_id == r.seg_id].iloc[0]
            with np.load(out / "tracks" / f"{r.animal}_{r.period}.npz") as z:
                ta = z["t_al_ms"]
                sel = (ta >= sg.t0_ms + 1000) & (ta < sg.t1_ms - 1000)
                tt = (ta[sel] - sg.t0_ms) / 1000.0
                tru = np.array([sg.truth_x, sg.truth_y])
                draw = np.hypot(*(z["raw"][sel].astype(float) - tru).T)
                db2 = np.hypot(*(z["B2p"][sel].astype(float) - tru).T)
                m10, _ = roll_median(tt, z["raw"][sel].astype(float), tt, 5.0, 10)
            ax.plot(tt, draw, ".", ms=2, color=COL["raw"], label="raw fix")
            ax.plot(tt, np.hypot(*(m10 - tru).T), "-", color="k", lw=1, label="raw 10-s median")
            ax.plot(tt, db2, "-", color=COL["B2p"], lw=1, label="B2′")
            ax.axhline(cfg["metrics"]["crazy_in"], color="orange", ls="--", lw=0.8)
            ax.set_ylim(0, max(40, np.nanpercentile(draw, 99.5) * 1.1))
            ax.set_ylabel("in from truth")
            ax.set_title(f"{r.animal} {short[r.period]} {ms_local(sg.t0_ms, cfg['tz'])} + {sg.dur_s:.0f} s still, zone {r.zone_detail}, "
                         f"event {r.size_in:.0f} in for {r.dur_s} s", fontsize=9)
        axs[0].legend(fontsize=8, ncol=3, loc="upper right")
        axs[-1].set_xlabel("s since segment start (IMU certifies the head still throughout)")
        fig.tight_layout()
        p = fdir / f"{STEM}_examples_{cohort}.png"
        fig.savefig(p, dpi=130)
        plt.close(fig)
        figs["examples"] = p.name
    # 5) motion side
    MOT, OS = A["MOT"], A["OS"]
    if len(MOT):
        nights = [k for k in order if cfg["periods"][k]["kind"] == "night"]
        fig, axs = plt.subplots(1, 3, figsize=(15, 4))
        x = np.arange(len(nights))
        for i, m in enumerate(POS_ONLY):
            v = [float(MOT[(MOT.period == k) & (MOT.method == m)].imp_per_h.iloc[0]) for k in nights]
            axs[0].bar(x + (i - 1.5) * 0.2, v, 0.2, color=COL[m], label=LABEL[m])
        axs[0].set_xticks(x)
        axs[0].set_xticklabels([short[k] for k in nights], rotation=30, ha="right", fontsize=8)
        axs[0].set_ylabel("impossible-speed events (> 100 in/s) per IMU-ok hour")
        axs[0].legend(fontsize=7)
        mr = MOT[MOT.method == "raw"].set_index("period").reindex(nights)
        axs[1].bar(x, mr.qjumps_per_h, color="#d62728", label="IMU quiet ± 1 s (certain failure)")
        axs[1].bar(x, mr.ajumps_per_h, bottom=mr.qjumps_per_h, color="#aaaaaa", label="IMU active")
        axs[1].set_xticks(x)
        axs[1].set_xticklabels([short[k] for k in nights], rotation=30, ha="right", fontsize=8)
        axs[1].set_ylabel("raw jumps > 30 in in ≤ 0.35 s per IMU-ok hour")
        axs[1].legend(fontsize=7)
        if len(OS):
            cats = ["early", "before_loco", "on_time", "late", "censored", "no_displacement"]
            lab, bottoms = [], None
            rows = []
            for kind in ("onset", "offset"):
                for s in ("calm", "rain"):
                    for m in ("raw", "B2p"):
                        g = OS[(OS.kind == kind) & (OS.set == s) & (OS.method == m)]
                        if len(g):
                            rows.append((f"{kind}\n{s} {m}\n(n={int(g.n.iloc[0])})", g.iloc[0]))
            cmap = {"early": "#d62728", "before_loco": "#ff9896", "on_time": "#2ca02c", "late": "#ff7f0e", "censored": "#cccccc", "no_displacement": "#eeeeee"}
            bottoms = np.zeros(len(rows))
            for ccat in cats:
                v = np.array([float(r_.get(ccat, 0)) / float(r_["n"]) if ccat in r_ else 0.0 for _, r_ in rows])
                if v.sum() == 0:
                    continue
                axs[2].bar(range(len(rows)), v, bottom=bottoms, color=cmap[ccat], label=ccat)
                bottoms += v
            axs[2].set_xticks(range(len(rows)))
            axs[2].set_xticklabels([r_[0] for r_ in rows], fontsize=6)
            axs[2].set_ylabel("fraction of IMU still-run onsets / offsets")
            axs[2].legend(fontsize=6, loc="upper right")
        fig.tight_layout()
        p = fdir / f"{STEM}_motion_{cohort}.png"
        fig.savefig(p, dpi=130)
        plt.close(fig)
        figs["motion"] = p.name
    return figs


def publish(A: dict, cfg: dict, out: Path, fh=None) -> None:
    cohort = cfg["_cohort"]
    fdir = output_paths.figure_dir(cohort, DIRECTION)
    figs = make_figures(A, cfg, out, fdir, cohort)
    for f in figs.values():
        try:
            import shutil
            shutil.copy2(fdir / f, out / "figures" / f)
        except Exception:  # noqa: BLE001
            pass
    rdir = output_paths.report_dir(cohort, DIRECTION)
    rep = rdir / f"{STEM}_{cohort}.md"
    meta = {"cohort": cohort, "direction": DIRECTION, "analysis": NAME, "report": rep.name, "driver": "wiser/scripts/analyze_wiser_failure_audit.py",
            "config": Path(cfg["_path"]).relative_to(REPO).as_posix(), "plan": "implementation_plan/2026-10-02-wiser-failure-audit.md",
            "git_commit": C.git_commit(), "figures": sorted(figs.values())}
    rep.write_text(render_report(A, cfg, out, figs, meta), encoding="utf-8")
    output_paths.write_run_manifest(out, out, **meta)
    mp = rdir / f"run_manifest_failure_audit_{cohort}.json"
    mp.write_text(json.dumps({"run_dir": str(out.resolve()), **meta}, indent=2) + "\n", encoding="utf-8")
    log_to(fh, f"report {rep}\nmanifest {mp}")


DEFINITIONS = r"""
## Definitions

All positions are WISER **inches in the unverified offset frame** (no physical/directional claim is made; only distances,
which are frame-invariant). Times are field-PC local (EDT). Symbols: $k$ indexes the fixes of one tag, $\mathbf z_k$ = raw
fix (in), $\hat{\mathbf p}_k$ = a method's position at fix $k$ (raw: $\hat{\mathbf p}_k=\mathbf z_k$), $t_k$ = fix time
aligned to the IMU clock, $t_k = t_k^{\text{WISER}} - \tau^*$ with $\tau^*$ = 0.20 / 0.15 / 0.10 / 0.20 / 0.15 s
(SF07 / 08 / 09 / 10 / 12); $\sigma$ = a still segment, $[t_\sigma^0+1\,\text{s},\,t_\sigma^1-1\,\text{s})$ its trimmed span,
$K_\sigma$ its fixes, $D_\sigma$ its trimmed duration.

### Rebuilt accelerometer and S50 (50-Hz certified stillness)
$$ \mathbf a^H = R(\mathbf q)^{\top}\big(\mathbf a^{E}_{\text{lin}} + g\,\hat{\mathbf z}\big),\qquad
   \mathbf a^{\text{cal}} = D\,(\mathbf a^H - \mathbf o) $$
where $\mathbf q$ = make_imu Fusion quaternion (head → world), $\mathbf a^{E}_{\text{lin}}$ = its earth-frame linear
acceleration (m/s²), $g$ = 9.81 m/s², $D=\mathrm{diag}(d_x,d_y,d_z)$ and $\mathbf o$ fitted per animal-period by
`fit_ellipsoid` (Huber, priors $d_i = 1\pm0.05$, $o_i = 0\pm0.5$ m/s²) on 0.5-s windows with median $|\boldsymbol\omega|<10$ °/s
and every per-axis SD $<0.15$ m/s². **Text:** the accelerometer that Fusion saw, recovered exactly from its outputs, then
self-calibrated like the A3 chain. **S50 windows:** 0.1-s block means $\bar{\mathbf a}_b$ of $\mathbf a^{\text{cal}}$; a
block is a candidate when all its samples are QC-valid and every $|\boldsymbol\omega| < 3$ °/s; a window $W$ grows block by
block while
$$ \max_{b\in W}\angle(\bar{\mathbf a}_b,\ \bar{\mathbf a}_W) < 0.3^\circ \quad\text{and}\quad \big|\,\lVert\bar{\mathbf a}_W\rVert - g\,\big| < 0.03\,g ,$$
kept when ≥ 1 s. Same thresholds as the gate-v2 strict rule (100 Hz), which is used where it exists.

### Still segment
Consecutive windows $W_i, W_{i+1}$ are merged when the gap $g_i = t^0_{W_{i+1}} - t^1_{W_i} \le 2$ s and every 50-Hz sample
in the gap is QC-valid with $|\boldsymbol\omega| < 20$ °/s and VeDBA $< \theta_a$ (per-animal still threshold, 0.31–0.39
m/s², `IMU_STILL_THR`) with no missing sample. **Text:** a gap too short and too quiet for the head to translate. Primary:
segments with $t^1_\sigma - t^0_\sigma \ge 30$ s; secondary ≥ 10 s. Coverage = window time / segment time.

### Truth of a still segment ($\mathbf c_\sigma$)
$$ \mathbf c_\sigma = \big(\operatorname{med}_{k\in K_\sigma} z_{k,x},\ \operatorname{med}_{k\in K_\sigma} z_{k,y}\big) $$
**Text:** the head does not move, so the tag position is one constant point; its best WISER estimate is the coordinate-wise
median of the raw fixes. Because it is itself WISER, any error that persists for most of the segment is absorbed into it:
every drift number below is a **lower bound**. Sensitivity: the median of the ≥ 8-anchor fixes ($\mathbf c'_\sigma$),
reported as $\lVert \mathbf c'_\sigma - \mathbf c_\sigma\rVert$.

### Per-fix distance, jitter RMS and quantiles
$$ r_k = \lVert \hat{\mathbf p}_k - \mathbf c_\sigma \rVert,\qquad \mathrm{RMS} = \Big(\tfrac{1}{N}\textstyle\sum_k r_k^2\Big)^{1/2} $$
pooled over all fixes of the group (in); p50 / p90 / p99 are quantiles of $r_k$. **Text:** how far a single fix is from
where the still head is. Range $[0,\infty)$; 0 = perfect.

### Rolling-median drift ($d^{(L)}$)
$$ \mathbf m^{(L)}(c) = \operatorname{med}_{k:\,t_k\in[c-L/2,\,c+L/2)} \hat{\mathbf p}_k,\qquad
   d^{(L)}_\sigma = \max_{c} \lVert \mathbf m^{(L)}(c) - \mathbf c_\sigma \rVert $$
centres $c$ every 1 s with the window wholly inside the trimmed segment and ≥ 10 ($L$ = 10 s) or ≥ 60 ($L$ = 60 s) fixes;
$d^{(60)}$ only for segments ≥ 120 s. **Text:** the worst slow offset that survives 10-s / 60-s median averaging — what
WISER says about where a still rat is, at the time scales used by behaviour analyses (in).

### Crazy-drift event
A maximal run of consecutive 1-s centres with $\lVert \mathbf m^{(10)}(c) - \mathbf c_\sigma\rVert \ge 12$ in lasting
≥ 10 s; size = the run's maximum distance; duration = number of centres (s); span reported as [first centre − 5 s, last
centre + 5 s]. Rate = events / still-hour; crazy time fraction = event seconds / still seconds. **Text:** WISER places a
still rat ≥ 1 ft away for ≥ 10 s (12 in ≈ 3–4 × the 9-anchor per-axis SD; given by the user).

### Jump
A consecutive fix pair with $\lVert\hat{\mathbf p}_{k+1}-\hat{\mathbf p}_k\rVert > 30$ in and $t_{k+1}-t_k \le 0.35$ s
(> 86 in/s implied). Rate per still-hour (Q1) or per IMU-ok hour (Q3).

### Fake speed and fake path
$$ v(t) = \lVert \tilde{\mathbf p}(t+0.5) - \tilde{\mathbf p}(t-0.5)\rVert / 1\,\text{s},\qquad
   \Pi = \frac{\sum_s \lVert \tilde{\mathbf p}(s+1) - \tilde{\mathbf p}(s)\rVert}{N_s/60} $$
$\tilde{\mathbf p}$ = linear interpolation of $\hat{\mathbf p}$ between fixes, defined only inside inter-fix gaps ≤ 1 s;
$t$ on a 0.25-s grid, $s$ on the integer-second grid, both inside the trimmed segment; $N_s$ = valid 1-s steps.
**Text:** during certified stillness the true speed and path are 0, so every in/s and every inch per minute is invented
by the tracker (in/s; in/min).

### Impossible-speed event (Q3)
A run of 0.25-s grid points with $v(t) > 100$ in/s (2.5 m/s; user criterion) in QC-ok IMU seconds, runs merged across
≤ 1 s; per IMU-ok hour; labelled by the IMU states of the seconds it covers.

### IMU states (per second, the smoothing pilot's rule)
QC-ok = no missing samples / saturation / frozen chip / invalid / Fusion recovery / handling ± 5 min / silence / ADC lane /
tag limits; still = $\overline{\text{VeDBA}}_{1s} < \theta_a$ and $\overline{|\boldsymbol\omega|}_{1s} < 10$ °/s;
locomoting = not still, $\overline{\text{VeDBA}}_{1s} \ge 3.93$ m/s² and stride-band fraction (4–7 Hz / 1–20 Hz of the
vertical linear acceleration, 2-s window) ≥ 0.10; else active. A jump is **IMU-quiet** when every second in
$[\lfloor t\rfloor-1, \lfloor t\rfloor+1]$ is QC-ok and still (a still head cannot jump 30 in: certain WISER failure).

### Onset / offset agreement (Q3)
Onset: an IMU still run $[a,b)$ ≥ 10 s followed by a first locomoting second $s_L$ within 60 s (no other ≥ 10-s still run
or unusable second in between); reference $\mathbf r = \operatorname{med}\{\hat{\mathbf p}_k: t_k\in[b-10,b-1)\}$ (≥ 10
fixes); departure $t_d$ = first time the centred 3-s median is ≥ 12 in from $\mathbf r$; classes early ($t_d < b-2$ s:
WISER moved while the head was still), before-loco ($t_d < s_L-2$), on-time ($|t_d-s_L|\le 2$), late ($t_d>s_L+2$),
censored (none within $s_L+20$ s). Offset: a still run preceded within 60 s by a last locomoting second $s_L$;
$\mathbf r$ = median over $[a+1, a+10)$; settle $t_s$ = last time the 3-s median is ≥ 12 in from $\mathbf r$ (+0.25 s);
late when $t_s - a > 2$ s (WISER still ≥ 1 ft away although the head is certified still), else on-time;
no-displacement when never ≥ 12 in away.

### Smoothers (Q2)
B1 = centred 7-sample coordinate-wise median (library `add_speed`); B2 = robust constant-velocity Kalman filter + RTS
smoother per axis, per-fix noise from `anchors_used`, χ² gate + Huber IRLS; B2′ = B2 with an AR(1) measurement drift
$b$ ($\tau_b$ = 15 s, $\sigma_b$ = 2.5 in), track = position state $p$ (the drift-free estimate; $p+b$ reported as B2′p+b);
V1 = B2′ + zero-velocity pseudo-measurement in IMU-still seconds; V2 = B2′ with process noise × (1, 0.01, 0.3, 10) by IMU
state. Parameters = the smoothing pilot's tuned values (unchanged). All run on every fix of the period ± 10 min.

### Rain / calm ratio and block bootstrap (Q4)
$$ \rho = \frac{\theta(\text{rain})}{\theta(\text{calm})},\qquad
   \theta^{*(b)} = \theta\big(\{\text{blocks drawn with replacement within each set}\}\big),\ b=1..1000 $$
$\theta$ = a statistic (pooled RMS, median segment drift, events per still-hour, …); blocks = 10 min of one animal-period
(segments by midpoint, fixes by segment); CI = 2.5–97.5 % of $\rho^{*}$. Medians and the speed p95 use 0.1-in / 0.05-in/s
histograms. **Standardised (anchors × zone):** per-fix RMS $\theta_{\text{std}} = (\sum_s w_s\,\overline{r^2}_{s})^{1/2}$
over strata $s$ = the fix's anchors_used {9, 8, 7, ≤ 6} × zone {house, outside}, $w_s$ = the calm share of fixes; event
rates $\sum_s w_s\,\lambda_s$ and the median drift (histograms re-weighted, $\sum_s w_s H_s/n_s$) over strata $s$ = the
segment's median anchors_used × zone, $w_s$ = the calm share of still-hours (rates) or segments (drift); both sets on the
strata present in both. Zone-only versions use the two zones. **Verdict rule (pre-registered):** confirmed if the
crazy-drift-rate or median-drift ratio CI lies above 1 pooled and nights-only and also after the anchors × zone
standardisation; "largely via fewer anchors" if only raw.

### Zone
house_1 / house_2 when the truth (or reference) point lies inside the ROI of `wiser/configs/wiser_rois.json` grown by
14 in; else outside (WISER frame — membership only, no physical claim).
"""


def _f(x, nd: int = 1) -> str:
    try:
        if x is None or not np.isfinite(float(x)):
            return "–"
    except (TypeError, ValueError):
        return str(x)
    return f"{float(x):.{nd}f}"


def _r(df: pd.DataFrame, **kw):
    if df is None or not len(df):
        return None
    m = np.ones(len(df), bool)
    for k, v in kw.items():
        m &= (df[k] == v).to_numpy()
    return df[m].iloc[0] if m.any() else None


def _pct(x, nd: int = 0) -> str:
    return "–" if x is None or not np.isfinite(float(x)) else f"{100 * float(x):.{nd}f} %"


def _ratio(r) -> str:
    if r is None:
        return "–"
    if not np.isfinite(r["calm"]) or r["calm"] == 0:
        return f"calm 0 → undefined (rain {_f(r['rain'], 2)})"
    return f"{_f(r['ratio'], 2)} [{_f(r['lo'], 2)}, {_f(r['hi'], 2)}]"


def pooled_calm_rain(A: dict, methods: list) -> pd.DataFrame:
    rows = []
    for s in ("calm", "rain"):
        g = A["Sp30"][A["Sp30"].set == s]
        for m in methods:
            rows.append({"set": s, **still_summary(g, A["M"], A["F"], A["SP"], m, A["S"])})
    return pd.DataFrame(rows)


def render_report(A: dict, cfg: dict, out: Path, figs: dict, meta: dict) -> str:
    res, tabs, Q4 = A["res"], A["tabs"], A["Q4"]
    cohort = cfg["_cohort"]
    sk = tabs["setkind"]
    PC = pooled_calm_rain(A, METHODS)
    PC.to_csv(out / "tables" / "summary_still_pooled_set.csv", index=False)
    rc, rr = _r(PC, set="calm", method="raw"), _r(PC, set="rain", method="raw")
    bc, br = _r(PC, set="calm", method="B2p"), _r(PC, set="rain", method="B2p")
    COV, V, WP, info = A["COV"], A["V"], A["WP"], A["info"]
    Sp30 = A["Sp30"]
    house_share = float((Sp30.zone == "house").mean())
    house_h = Sp30.groupby("zone").dur_trim_s.sum() / 3600
    v50 = V[(V.rule == "S50") & (V.b_min > 0) & (V.a_min > 0)]
    vup = V[(V.rule == "S50_up") & (V.b_min > 0)]
    mset, MOT, OS, OL = A["mset"], A["MOT"], A["OS"], A["OL"]
    mr_c, mr_r = _r(mset, set="calm", method="raw"), _r(mset, set="rain", method="raw")
    fb = tabs["fixbin"]
    q = lambda comp, met, std="none", m="raw": _r(Q4, comparison=comp, metric=met, std=std, method=m)  # noqa: E731
    Ep = A["Ep"]
    n_ev_c = int((Ep.set == "calm").sum()) if len(Ep) else 0
    n_ev_r = int((Ep.set == "rain").sum()) if len(Ep) else 0
    ev_b2p = A["E"][(A["E"].method == "B2p") & A["E"].primary.astype(bool) & A["E"].ge30.astype(bool)] if len(A["E"]) else A["E"]
    n_b2p_c, n_b2p_r = int((ev_b2p.set == "calm").sum()), int((ev_b2p.set == "rain").sum())
    cov_kind = COV.groupby(["set", "kind"]).agg(ok=("imu_ok_h", "sum"), s30=("still30_h", "sum"), s10=("still10_h", "sum")).reset_index()
    cov_kind["f30"] = cov_kind.s30 / cov_kind.ok
    cov_kind["f10"] = cov_kind.s10 / cov_kind.ok
    fcn = _r(cov_kind, set="calm", kind="night")
    fcd = _r(cov_kind, set="calm", kind="day")
    on_c = _r(OS, set="calm", kind="onset", method="raw")
    off_c = _r(OS, set="calm", kind="offset", method="raw")
    on_r = _r(OS, set="rain", kind="onset", method="raw")
    off_r = _r(OS, set="rain", kind="offset", method="raw")
    fb9c, fb9r = _r(fb, set="calm", abin="9"), _r(fb, set="rain", abin="9")
    fb6c, fb6r = _r(fb, set="calm", abin="<=6"), _r(fb, set="rain", abin="<=6")
    JB = A["JB"]
    q_le6_c = float(JB[(JB.set == "calm") & (JB.abin == "<=6")].imu_quiet.sum() / max(JB[JB.set == "calm"].imu_quiet.sum(), 1)) if len(JB) else np.nan
    q_le6_r = float(JB[(JB.set == "rain") & (JB.abin == "<=6")].imu_quiet.sum() / max(JB[JB.set == "rain"].imu_quiet.sum(), 1)) if len(JB) else np.nan
    q_7_r = float(JB[(JB.set == "rain") & (JB.abin == "7")].imu_quiet.sum() / max(JB[JB.set == "rain"].imu_quiet.sum(), 1)) if len(JB) else np.nan
    verdict = res["q4_verdict"]
    L = []
    w = L.append
    w(f"# WISER failure audit with the head IMU as the stillness truth (cohort {cohort})\n")
    w(f"**Step 1 of the new evaluation** — approved by the user 2026-10-02 (\"搞吧\"). Plan "
      f"[`implementation_plan/2026-10-02-wiser-failure-audit.md`](../../../../implementation_plan/2026-10-02-wiser-failure-audit.md) "
      f"(3 amendments: two before any audit number, one post hoc on the Q4 standardisation — §6); driver `wiser/scripts/analyze_wiser_failure_audit.py` "
      f"(`--selftest` ALL PASS, 19 checks; the per-group still tables' speed quantiles were corrected on 2026-10-03, "
      f"[`implementation_plan/2026-10-03-wiser-v1b-zupt.md`](../../../../implementation_plan/2026-10-03-wiser-v1b-zupt.md)); "
      f"config `wiser/configs/wiser_failure_audit_{cohort}.json`; bulk `{out}`; git `{meta['git_commit']}`. "
      f"Audit only: nothing is tuned, accepted or promoted here.\n")
    # ---------------------------------------------------------------- executive summary
    w("## Executive summary\n")
    w(f"1. **Truth:** {Sp30.dur_trim_s.sum() / 3600:.0f} h of head stillness certified by the IMU in ≥ 30-s segments (calm-dry {rc['still_h']:.1f} h, rain {rr['still_h']:.1f} h; "
      f"{house_share * 100:.0f} % of the segments lie in the two houses). The 50-Hz rule reproduces the 100-Hz strict windows (time recall {v50.recall.median():.2f}, precision {v50.precision.median():.2f}).")
    w(f"2. **Jitter (Q1):** while the head is still, raw fixes sit **{rc['rms_in']:.1f} in RMS** from the still position on calm-dry periods (p90 {rc['p90_in']:.1f}, p99 {rc['p99_in']:.1f} in) "
      f"and **{rr['rms_in']:.1f} in** in the rain periods (p99 {rr['p99_in']:.1f} in); ≤ 6-anchor fixes {fb6c['rms_raw']:.0f} in vs 9-anchor {fb9c['rms_raw']:.1f} in.")
    w(f"3. **Drift (Q1):** slow drift is small and crazy drift rare: the worst 10-s median of a segment strays median **{rc['drift10_med']:.1f} in** (p90 {rc['drift10_p90']:.1f}), "
      f"the 60-s median {rc['drift60_med']:.1f} in; ≥ 12 in for ≥ 10 s happened **{rc['crazy_n']} times in {rc['still_h']:.0f} calm still-hours** ({rc['crazy_per_h']:.2f}/h) "
      f"and {rr['crazy_n']} times in {rr['still_h']:.0f} rain still-hours ({rr['crazy_per_h']:.2f}/h). WISER does not wander far from a still rat — it jitters and jumps.")
    w(f"4. **Jumps and fake motion (Q1):** a still tag jumps > 30 in within ≤ 0.35 s **{rc['jumps_per_h']:.0f}/h** (rain {rr['jumps_per_h']:.0f}/h) and accrues "
      f"**{rc['path_in_per_min']:.0f} in of fake path per minute** (fake speed p95 {rc['speed_p95']:.1f} in/s).")
    w(f"5. **Smoothers (Q2):** B2′ cuts the still error to {bc['rms_in']:.1f} in RMS, fake path to {bc['path_in_per_min']:.0f} in/min, p95 speed to {bc['speed_p95']:.1f} in/s and removes every jump, "
      f"but **not the slow drift** (10-s drift {bc['drift10_med']:.1f} in vs raw {rc['drift10_med']:.1f}; 60-s {bc['drift60_med']:.1f} vs {rc['drift60_med']:.1f} in); in the rain it creates more ≥ 12-in excursions than raw ({n_b2p_r} vs {n_ev_r}).")
    fr_ = lambda r, c: float(r.get(c, 0)) / float(r["n"]) if r is not None and float(r["n"]) > 0 else np.nan  # noqa: E731
    w(f"6. **Motion side (Q3, nights):** raw WISER produces {mr_c['imp_per_h']:.1f} impossible-speed (> 100 in/s) events/h calm, {mr_r['imp_per_h']:.1f}/h rain, and {mr_c['jumps_per_h']:.0f} / {mr_r['jumps_per_h']:.0f} jumps/h, "
      f"{mr_c['qjumps_per_h']:.0f} / {mr_r['qjumps_per_h']:.0f} per h with a quiet IMU (certain failures; {q_le6_c * 100:.0f} % / {q_le6_r * 100:.0f} % from ≤ 6-anchor fixes); "
      f"**B2/B2′ remove all of them**. WISER almost never moves while the head is still (early onsets {_pct(fr_(on_c, 'early'))} calm / {_pct(fr_(on_r, 'early'))} rain) "
      f"or stays away after it stops (late settles {_pct(fr_(off_c, 'late'))} / {_pct(fr_(off_r, 'late'))}); its departure lags the first locomoting second by > 2 s in "
      f"{_pct(fr_(on_c, 'late'))} of onsets (ambiguous: WISER latency vs time to walk 1 ft).")
    rq = q("pooled", "rms")
    rqs = q("pooled", "rms", "anchors×zone")
    jq = q("pooled", "jump_rate")
    dq, dqs = q("pooled", "drift_med"), q("pooled", "drift_med", "anchors×zone")
    dnow = q("raining_now_vs_wet", "drift_med")
    w(f"7. **Rain (Q4): {verdict}** by the pre-registered rule — but modest in size: median 10-s drift {dq['rain']:.1f} vs {dq['calm']:.1f} in (×{dq['ratio']:.2f}, "
      f"anchors × zone ×{dqs['ratio']:.2f} [{dqs['lo']:.2f}, {dqs['hi']:.2f}]), ×{dnow['ratio']:.1f} ({dnow['rain']:.1f} in) in minutes when it was actually raining; "
      f"per-fix RMS ×{rq['ratio']:.2f} (standardised ×{rqs['ratio']:.2f}), jumps ×{jq['ratio']:.1f}; crazy drift {n_ev_r} vs {n_ev_c} events. Much of it goes through lost anchors "
      f"(9-anchor share {fb9r['share'] * 100:.0f} % vs {fb9c['share'] * 100:.0f} %); humidity, location and a 3-episode rain sample are confounded.")
    w(f"8. **The bar for V6 (Q5):** in still time an IMU constraint can at most remove what B2′ leaves — **{bc['rms_in']:.1f} in RMS, {bc['path_in_per_min']:.0f} in/min fake path, "
      f"{bc['drift10_med']:.1f} in 10-s drift** (calm) — on {fcn['f30'] * 100:.0f} % of the night and {fcd['f30'] * 100:.0f} % of the day (≥ 30-s stillness); on the motion side B2′ leaves nothing of the measured failure types.\n")
    # ---------------------------------------------------------------- 1 data
    w("## 1. Periods, data and weather\n")
    w("Periods were decided with the user before the plan; field-PC local time. IMU-ok hours = 5 animals summed after every exclusion "
      "(handling windows ± 5 min, all-tag WISER silences ± 2 min, the logger's own ADC-lane windows, tag limits, IMU QC). "
      "Weather recomputed from the AWN cloud export (5-min rows): rain = increments of the console's daily-rain counter (rate integral in brackets).\n")
    w("| set | period | window | IMU-ok h | still ≥ 30 s h | fixes | 9-anchor | ≤ 6-anchor | rain mm | rain min | rain prev. 12 h | wind mean / gust p95 / max (mph) | RH mean (min–max) | T − Td (°C) |")
    w("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for pk, p in cfg["periods"].items():
        cg = COV[COV.period == pk]
        wr = _r(WP, period=pk)
        w(f"| {p['set']} | `{pk}` | {p['start'][5:16]} → {p['end'][5:16]} | {cg.imu_ok_h.sum():.1f} | {cg.still30_h.sum():.1f} | {cg.n_fix.sum():,} | "
          f"{_pct(np.average(cg.anchors_9_frac, weights=cg.n_fix))} | {_pct(np.average(cg.anchors_le6_frac, weights=cg.n_fix), 1)} | "
          f"{_f(wr['rain_mm'])} ({_f(wr['rain_mm_rate_integral'])}) | {_f(wr['rain_min'], 0)} | {_f(wr['rain_prior_mm'])} | "
          f"{_f(wr['wind_mean_mph'])} / {_f(wr['gust_p95_mph'])} / {_f(wr['gust_max_mph'])} | {_f(wr['rh_mean'], 0)} ({_f(wr['rh_min'], 0)}–{_f(wr['rh_max'], 0)}) | "
          f"{_f(wr['dewpoint_depression_mean_c'])} |")
    w("")
    w("The user's rain figures check out (09-03 night 18.4 mm by rate integral / 20.1 mm by counter; 09-09 night 7.2 / 7.1 mm; 09-10 day 0 mm during, "
      "12.2 mm in the previous 12 h). Every night, calm or rain, is near saturation (RH ≈ 90–98 %, dew-point depression ≤ 1.6 °C → dew), so humidity "
      "does not separate the sets; wind is light everywhere at night. The 09-10 day ends at ≈ 14:40 for the IMU (ADC-lane sessions quarantined from 14:43, "
      "`cohorts/2026c.yaml ephys.adc_lane`), and the AM rounds cut 08:00–09:55 on 09-05 and 08:00–09:20 on 09-07.\n")
    # ---------------------------------------------------------------- 2 stillness
    w("## 2. Certified stillness: rule and validation\n")
    w("The strict gate-v2 windows (100 Hz; ≥ 1 s, accelerometer-direction sweep < 0.3°, ‖|ā| − g‖ < 0.03 g, |ω| < 3 °/s; **no WISER veto** — it "
      "would be circular here) are used on `day_20260908` / `night_20260908`. Elsewhere **S50**: the head-frame accelerometer is rebuilt exactly from "
      "the make_imu Fusion quaternion and earth linear acceleration, ellipsoid self-calibrated per animal-period like the A3 chain (amendment 1), and the same "
      "rule is applied on 0.1-s blocks. Windows are merged across gaps ≤ 2 s with no movement (every 50-Hz sample |ω| < 20 °/s and VeDBA < θ_a) into segments; "
      "1 s is trimmed at both ends.\n")
    w(f"**Validation** on the four gate-v2 periods (19 of 20 animal-periods; SF12 `day_20260911` has no make_imu npz for its field-flagged session "
      f"`3_20260911_094747.706`): S50 time recall **{v50.recall.median():.3f}** (min {v50.recall.min():.3f}, {v50.loc[v50.recall.idxmin(), 'animal']} "
      f"`{v50.loc[v50.recall.idxmin(), 'period']}`), precision **{v50.precision.median():.3f}** "
      f"(min {v50.precision.min():.3f}); within ≥ 30-s segments time recall {v50.seg30_time_recall.median():.3f}, precision {v50.seg30_time_precision.median():.3f}. "
      f"The literal `up_head`-sweep variant fails (recall {vup.recall.median():.2f}): Fusion's gravity estimate wanders more than 0.3° per second, so it is not used. "
      "Without the self-calibration the magnitude test rejected most still time (prototype recall 0.31 / 0.41), because make_imu calibrates the accelerometer with a scalar only.\n")
    SENS = A["SENS"]
    if len(SENS):
        w("Sensitivity on the two strict periods — the audit metrics do not depend on the rule (raw / B2′):\n")
        w("| still source | segments ≥ 30 s | still h | median segment RMS (in) | 10-s drift median / p90 (in) | crazy/h | jumps/h | fake path (in/min) |")
        w("|---|---|---|---|---|---|---|---|")
        for src in ("strict", "s50", "s50_up"):
            a_, b_ = _r(SENS, source=src, method="raw"), _r(SENS, source=src, method="B2p")
            if a_ is None:
                continue
            w(f"| {src} | {int(a_['n_seg'])} | {a_['still_h']:.1f} | {_f(a_['rms_seg_med'], 2)} / {_f(b_['rms_seg_med'], 2)} | {_f(a_['drift10_med'], 2)} / {_f(a_['drift10_p90'], 2)} | "
              f"{_f(a_['crazy_per_h'], 3)} | {_f(a_['jumps_per_h'])} | {_f(a_['path_in_per_min'], 0)} / {_f(b_['path_in_per_min'], 0)} |")
        w("")
    w(f"**Where the truth exists:** certified stillness ≥ 30 s covers {_pct(fcd['f30'])} of the IMU-ok day and {_pct(fcn['f30'])} of the IMU-ok night (≥ 10 s: "
      f"{_pct(fcd['f10'])} / {_pct(fcn['f10'])}); **{house_share * 100:.0f} %** of the ≥ 30-s segments ({house_h.get('house', 0):.1f} h of "
      f"{house_h.sum():.1f} h) lie in the house ROIs (+ 14 in). Long stillness outside is rare ({house_h.get('outside', 0):.1f} h), so every Q1/Q2 number "
      f"below describes WISER **at the houses**; median fix rate in the segments {Sp30.fix_rate_hz.median():.2f} Hz (p5 {Sp30.fix_rate_hz.quantile(0.05):.2f} Hz: "
      "no dropout during stillness). Truth sensitivity: the "
      f"≥ 8-anchor median lies {res['truth_alt_shift_med']:.2f} in (p90 {res['truth_alt_shift_p90']:.2f} in) from the all-fix median.\n")
    # ---------------------------------------------------------------- 3 Q1
    w("## 3. Q1 — How bad is WISER during certified stillness?\n")
    w(f"**Verdict:** WISER **jitters and jumps but rarely drifts far** from a still rat. On calm-dry periods a single fix is {rc['rms_in']:.1f} in RMS "
      f"from the still position and 1 % of fixes are > {rc['p99_in']:.0f} in away; a 10-s median strays ≤ {rc['drift10_med']:.1f} in (median segment), "
      f"≥ 12 in for ≥ 10 s only {rc['crazy_n']} times in {rc['still_h']:.0f} still-hours. The rain periods are worse on every metric.\n")
    w("Raw WISER, primary segments ≥ 30 s (truth = segment median; all distances in in, speeds in/s):\n")
    w("| set | kind | segments | still h | per-fix RMS | p50 | p90 | p99 | 10-s drift med / p90 / max | 60-s drift med / p90 | crazy-drift /h (n) | crazy time | jumps /h | fake speed p50 / p95 / p99 | fake path in/min |")
    w("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for s in ("calm", "rain"):
        for k in ("day", "night"):
            r = _r(sk, set=s, kind=k, method="raw")
            if r is None:
                continue
            w(f"| {s} | {k} | {int(r['n_seg'])} | {r['still_h']:.1f} | **{r['rms_in']:.2f}** | {r['p50_in']:.2f} | {r['p90_in']:.2f} | {r['p99_in']:.1f} | "
              f"{r['drift10_med']:.2f} / {r['drift10_p90']:.2f} / {r['drift10_max']:.1f} | {_f(r['drift60_med'], 2)} / {_f(r['drift60_p90'], 2)} | "
              f"{r['crazy_per_h']:.3f} ({int(r['crazy_n'])}) | {_pct(r['crazy_frac'], 2)} | {r['jumps_per_h']:.0f} | {r['speed_p50']:.1f} / {r['speed_p95']:.1f} / {r['speed_p99']:.1f} | {r['path_in_per_min']:.0f} |")
    w("")
    w("By `anchors_used` of the fix (per-fix RMS from truth, raw and B2′; share = fraction of still fixes):\n")
    w("| anchors | calm share | calm RMS raw / p90 / B2′ | rain share | rain RMS raw / p90 / B2′ |")
    w("|---|---|---|---|---|")
    for ab in ANCHOR_BINS:
        c_, r_ = _r(fb, set="calm", abin=ab), _r(fb, set="rain", abin=ab)
        w(f"| {ab} | {_pct(c_['share'])} | {c_['rms_raw']:.1f} / {c_['p90_raw']:.1f} / {c_['rms_B2p']:.1f} | {_pct(r_['share'])} | {r_['rms_raw']:.1f} / {r_['p90_raw']:.1f} / {r_['rms_B2p']:.1f} |")
    w("")
    ta = tabs["animal"]
    w("By animal (raw; calm | rain): " + "; ".join(
        f"{a} {_f(_r(ta, set='calm', animal=a, method='raw')['rms_in'])} | {_f(_r(ta, set='rain', animal=a, method='raw')['rms_in'])} in RMS, "
        f"{_f(_r(ta, set='calm', animal=a, method='raw')['jumps_per_h'], 0)} | {_f(_r(ta, set='rain', animal=a, method='raw')['jumps_per_h'], 0)} jumps/h"
        for a in cfg["animals"]) + " — no animal stands out; the error is the tag at the place, not the animal.\n")
    tz_ = tabs["zone"]
    zc_h, zc_o = _r(tz_, set="calm", kind="night", zone="house", method="raw"), _r(tz_, set="calm", kind="night", zone="outside", method="raw")
    zr_h, zr_o = _r(tz_, set="rain", kind="night", zone="house", method="raw"), _r(tz_, set="rain", kind="night", zone="outside", method="raw")
    if zc_o is not None and zc_h is not None:
        w(f"By zone (nights, raw): calm house {zc_h['rms_in']:.1f} in RMS / {zc_h['jumps_per_h']:.0f} jumps/h ({zc_h['still_h']:.1f} h) vs outside {zc_o['rms_in']:.1f} in / "
          f"{zc_o['jumps_per_h']:.0f} jumps/h ({zc_o['still_h']:.1f} h)"
          + (f"; rain house {zr_h['rms_in']:.1f} / {zr_h['jumps_per_h']:.0f} vs outside {zr_o['rms_in']:.1f} / {zr_o['jumps_per_h']:.0f} ({zr_o['still_h']:.1f} h)" if zr_o is not None else "")
          + ". Days have no outside stillness to compare.\n")
    th = tabs["hour"]
    thr_ = th[(th.method == "raw") & (th.still_h >= 0.5)]
    cd_h = thr_[(thr_.set == "calm") & (thr_.kind == "day")]
    rd_h = thr_[(thr_.set == "rain") & (thr_.kind == "day")].set_index("hour")
    if len(cd_h) and len(rd_h):
        early_h = rd_h[rd_h.index <= 10]
        late_h = rd_h[rd_h.index >= 12]
        w(f"By local hour (raw, hours with ≥ 0.5 still-h): calm days stay within {cd_h.rms_in.min():.1f}–{cd_h.rms_in.max():.1f} in RMS and "
          f"{cd_h.jumps_per_h.min():.0f}–{cd_h.jumps_per_h.max():.0f} jumps/h; the **wet day 09-10 is bad only in the morning** "
          f"({', '.join(f'{int(h_):02d} h {r_.rms_in:.1f} in / {r_.jumps_per_h:.0f} jumps/h' for h_, r_ in early_h.iterrows())}) and calm-like from noon "
          f"({', '.join(f'{int(h_):02d} h {r_.rms_in:.1f} / {r_.jumps_per_h:.0f}' for h_, r_ in late_h.iterrows())}) — WISER recovers as the paddock dries. "
          "Rain nights are worst in the evening hours of the rain (`tables/summary_still_hour.csv`).\n")
    w("**What it implies for the IMU:** during stillness the IMU's job is to stop jitter and jumps from becoming fake motion and to pin the "
      "position; there is little slow drift for it to correct (the median 10-s excursion is ≈ 1.5 in, below the 4–7-in jitter floor).\n")
    if "still_by_period" in figs:
        w(f"![Still error by period](../figures/{figs['still_by_period']})\n")
    if "strata" in figs:
        w(f"![Strata](../figures/{figs['strata']})\n")
    if "examples" in figs:
        w(f"![Worst crazy-drift examples](../figures/{figs['examples']})\n")
    # ---------------------------------------------------------------- 4 Q2
    w("## 4. Q2 — What do the position-only smoothers leave?\n")
    w(f"**Verdict:** B2′ (and B2) remove most of the jitter and **all** jumps and fake speed tails, but leave the slow drift where it was "
      f"(10-s drift −{(1 - bc['drift10_med'] / rc['drift10_med']) * 100:.0f} %, 60-s drift {('+' if bc['drift60_med'] > rc['drift60_med'] else '−')}"
      f"{abs(bc['drift60_med'] / rc['drift60_med'] - 1) * 100:.0f} %) and, in the rain, follow sustained low-anchor clusters into more ≥ 12-in excursions than the raw 10-s median "
      f"({n_b2p_r} vs {n_ev_r} events; calm {n_b2p_c} vs {n_ev_c}). V1 / V2 use the IMU's own stillness, so their still-period numbers are "
      "**what an IMU stillness constraint removes by construction**, not evidence.\n")
    w("Pooled primary segments ≥ 30 s (calm-dry | rain):\n")
    w("| method | per-fix RMS | p90 | p99 | 10-s drift med / p90 | 60-s drift med / p90 | crazy-drift /h (n) | jumps /h | fake speed p95 | fake path in/min |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for m in METHODS:
        c_, r_ = _r(PC, set="calm", method=m), _r(PC, set="rain", method=m)
        tag = " *(IMU, circular)*" if m in ("V1", "V2") else ""
        w(f"| {LABEL[m]}{tag} | {c_['rms_in']:.2f} \\| {r_['rms_in']:.2f} | {c_['p90_in']:.2f} \\| {r_['p90_in']:.2f} | {c_['p99_in']:.1f} \\| {r_['p99_in']:.1f} | "
          f"{c_['drift10_med']:.2f} / {c_['drift10_p90']:.2f} \\| {r_['drift10_med']:.2f} / {r_['drift10_p90']:.2f} | {_f(c_['drift60_med'], 2)} / {_f(c_['drift60_p90'], 2)} \\| "
          f"{_f(r_['drift60_med'], 2)} / {_f(r_['drift60_p90'], 2)} | {c_['crazy_per_h']:.3f} ({int(c_['crazy_n'])}) \\| {r_['crazy_per_h']:.3f} ({int(r_['crazy_n'])}) | "
          f"{c_['jumps_per_h']:.1f} \\| {r_['jumps_per_h']:.1f} | {c_['speed_p95']:.2f} \\| {r_['speed_p95']:.2f} | {c_['path_in_per_min']:.0f} \\| {r_['path_in_per_min']:.0f} |")
    w("")
    w(f"Residual after B2′ as a share of raw (calm): RMS {bc['rms_in'] / rc['rms_in'] * 100:.0f} %, p99 {bc['p99_in'] / rc['p99_in'] * 100:.0f} %, "
      f"fake path {bc['path_in_per_min'] / rc['path_in_per_min'] * 100:.0f} %, fake speed p95 {bc['speed_p95'] / rc['speed_p95'] * 100:.0f} %, "
      f"10-s drift {bc['drift10_med'] / rc['drift10_med'] * 100:.0f} %, 60-s drift {bc['drift60_med'] / rc['drift60_med'] * 100:.0f} %, jumps 0 %. "
      f"B1 (the library median) keeps {_r(PC, set='calm', method='B1')['rms_in'] / rc['rms_in'] * 100:.0f} % of the RMS and "
      f"{_r(PC, set='calm', method='B1')['path_in_per_min'] / rc['path_in_per_min'] * 100:.0f} % of the fake path. B2′'s `p + b` (the WISER-measurement predictor) is worse than its `p`, as "
      "it should be (b carries the measured wander).\n")
    w("**What it implies for the IMU:** a position-only smoother already does the easy part (outliers, jitter). What it cannot do is decide *when* the "
      "rat is still — it keeps 1.4–1.5 in of jitter and ≈ 27 in/min of fake path in every still minute and cannot tell a slow WISER excursion from a slow "
      "walk. That decision is exactly what the IMU provides.\n")
    # ---------------------------------------------------------------- 5 Q3
    w("## 5. Q3 — WISER failure while the animal moves (nights)\n")
    w(f"**Verdict:** the motion-side failures are **short outliers**, not lost tracks: {mr_c['imp_per_h']:.2f} (calm) / {mr_r['imp_per_h']:.2f} (rain) impossible-speed "
      f"events and {mr_c['jumps_per_h']:.0f} / {mr_r['jumps_per_h']:.0f} jumps per IMU-ok hour in raw WISER, of which {mr_c['qjumps_per_h']:.1f} / {mr_r['qjumps_per_h']:.1f} per hour "
      "happen with a quiet IMU (certain failures). Every smoother removes the impossible speeds; B2 / B2′ remove every jump. WISER almost never moves "
      f"while the head is still (early onsets {_pct(fr_(on_c, 'early'))} / {_pct(fr_(on_r, 'early'))}) or stays ≥ 1 ft away after it stops (late settles "
      f"{_pct(fr_(off_c, 'late'))} / {_pct(fr_(off_r, 'late'))}); late departures after the first locomoting second ({_pct(fr_(on_c, 'late'))} / {_pct(fr_(on_r, 'late'))}) "
      "cannot be separated from the time a rat needs to walk 1 ft.\n")
    w("| night | set | IMU-ok h | impossible-speed /h raw (n) | … with IMU still (n) | … with ≥ 1 loco s (n) | ≤ 6 anchors | B1 / B2 / B2′ | jumps /h raw | IMU-quiet jumps /h | jumps ≤ 6 anchors | B1 jumps /h | B2′ jumps /h |")
    w("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for pk in [k for k, p in cfg["periods"].items() if p["kind"] == "night"]:
        r = _r(MOT, period=pk, method="raw")
        b1, b2, b2p = _r(MOT, period=pk, method="B1"), _r(MOT, period=pk, method="B2"), _r(MOT, period=pk, method="B2p")
        w(f"| `{pk}` | {r['set']} | {r['ok_h']:.1f} | {r['imp_per_h']:.2f} ({int(r['imp_n'])}) | {int(r['imp_still_n'])} | {int(r['imp_loco_n'])} | {_pct(r['imp_le6_frac'])} | "
          f"{b1['imp_per_h']:.2f} / {b2['imp_per_h']:.2f} / {b2p['imp_per_h']:.2f} | {r['jumps_per_h']:.0f} | {r['qjumps_per_h']:.1f} | {_pct(r['jumps_le6_frac'])} | "
          f"{b1['jumps_per_h']:.2f} | {b2p['jumps_per_h']:.2f} |")
    w("")
    w(f"IMU-quiet jumps come from ≤ 6-anchor fixes in {q_le6_c * 100:.0f} % (calm) / {q_le6_r * 100:.0f} % (rain) of cases ({q_7_r * 100:.0f} % from 7-anchor fixes in the rain). "
      "Jumps by zone and anchors: `tables/summary_motion_jumps_by_*.csv`.\n")
    w("**Onset / offset agreement** (IMU still runs ≥ 10 s with locomotion within 60 s; amendment 2):\n")
    w("| set | kind | n | early (WISER moves while the head is still) | before first loco s | on time ± 2 s | late > 2 s | censored / no displacement | median lag to loco (s) |")
    w("|---|---|---|---|---|---|---|---|---|")
    for s in ("calm", "rain"):
        for k in ("onset", "offset"):
            for m in ("raw", "B2p"):
                r = _r(OS, set=s, kind=k, method=m)
                lg = _r(OL, set=s, kind=k, method=m)
                if r is None:
                    continue
                n = float(r["n"])
                g = lambda c: _pct(float(r[c]) / n if c in r.index else 0.0)  # noqa: E731
                w(f"| {s} | {k} {LABEL[m]} | {int(n)} | {g('early') if k == 'onset' else '–'} | {g('before_loco') if k == 'onset' else '–'} | {g('on_time')} | {g('late')} | "
                  f"{g('censored') if k == 'onset' else g('no_displacement')} | {_f(lg['lag_loco_med'], 2) if lg is not None else '–'} |")
    w("")
    w(f"Most onsets are censored (WISER stays within 12 in for 20 s after the first locomoting second — consistent with activity in place, e.g. inside the house) "
      f"and most offsets show no ≥ 12-in approach in the last 20 s, so the transitions are small. Where WISER does depart, it does so a median "
      f"{_f(_r(OL, set='calm', kind='onset', method='raw')['lag_loco_med'], 1)} s after the first locomoting second (calm) — the 1-s IMU state and a 12-in criterion "
      "cannot separate WISER latency from the time the rat needs to translate 1 ft. B2′ cannot see the head stop either, and V1/V2 depart later "
      "because their zero-velocity update holds the position while the IMU is still.\n")
    w("**What it implies for the IMU:** on the motion side the measured failure types are already handled by position-only smoothing; the IMU could only "
      "add value there by bridging real gaps or constraining heading, which this audit does not measure (gaps were not scored).\n")
    if "motion" in figs:
        w(f"![Motion side](../figures/{figs['motion']})\n")
    # ---------------------------------------------------------------- 6 Q4
    w("## 6. Q4 — Is \"rain → more drift\" confirmed?\n")
    w(f"**Verdict (pre-registered rule): {verdict}.**\n")
    dz_ = q("pooled", "drift_med", "zone")
    if dz_ is not None:
        w(f"*Amendment 3 (post hoc, after the first Q4 table):* the plan standardised segment metrics by zone only; that is a no-op here (pooled zone-standardised "
          f"median-drift ratio {_ratio(dz_)} = raw) and gave CONFIRMED. The verdict rule asks for anchors × zone, so the segment's median anchors were added "
          "as a stratum; that version decides the verdict above. Both are in `tables/summary_rain_vs_calm_bootstrap.csv`.\n")
    w("Rain / calm ratios, raw WISER, 95 % CIs from 1000 resamples of 10-min blocks within each set. Standardised = rain strata re-weighted to the calm "
      "weights over anchors × zone (the fix's anchors for the per-fix RMS; the segment's median anchors for segment and event metrics); zone-only versions "
      "are in `tables/summary_rain_vs_calm_bootstrap.csv` (they equal the raw ratios: almost all still time is in the houses). \"calm 0 → undefined\": no calm event.\n")
    w("| metric | pooled | pooled, standardised | nights | nights, standardised | days | days, standardised |")
    w("|---|---|---|---|---|---|---|")
    names = {"rms": "per-fix RMS", "drift_med": "median 10-s drift", "crazy_rate": "crazy-drift events / still-h", "crazy_frac": "crazy-drift time share",
             "jump_rate": "jumps / still-h", "speed_p95": "fake speed p95", "path_rate": "fake path in/min"}
    for met, nm in names.items():
        cells = []
        for comp in ("pooled", "night", "day"):
            for std in ("none", "anchors×zone"):
                rr_ = q(comp, met, std)
                cells.append(_ratio(rr_) if (rr_ is not None or std == "none") else "n/a")
        w(f"| {nm} | " + " | ".join(cells) + " |")
    w("")
    w("Within anchor strata (pooled, raw) — per-fix RMS by the fix's anchors: " + "; ".join(
        f"{ab}: {_ratio(q('pooled', f'rms_anchors_{ab}'))}" for ab in ANCHOR_BINS) + "; median 10-s drift by the segment's median anchors: " + "; ".join(
        f"{ab}: {_ratio(q('pooled', f'drift_med_seganchors_{ab}'))}" for ab in ANCHOR_BINS if q('pooled', f'drift_med_seganchors_{ab}') is not None) + ".\n")
    w("Night motion side (per IMU-ok hour): " + "; ".join(
        f"{nm} {_ratio(q('night_motion', met))}" for met, nm in (("impossible_speed_rate", "impossible speed"), ("imu_quiet_jump_rate", "IMU-quiet jumps"),
                                                                 ("jump_rate_all", "all jumps"))) + ".\n")
    rn = Q4[(Q4.comparison == "raining_now_vs_wet") & (Q4.method == "raw") & ~Q4.standardised] if len(Q4) else Q4
    if len(rn):
        w("Inside the rain periods, segments while it was raining (nearest 5-min weather row has rain rate > 0, ≥ 50 % of fixes) vs wet but not raining: "
          + "; ".join(f"{names.get(r['metric'], r['metric'])} {_ratio(r)}" for _, r in rn.iterrows() if r["metric"] in names and r["std"] == "none") + ".\n")
    dq_, dqs_, dnow_ = q("pooled", "drift_med"), q("pooled", "drift_med", "anchors×zone"), q("raining_now_vs_wet", "drift_med")
    dqn_ = q("night", "drift_med", "anchors×zone")
    crs_ = q("pooled", "crazy_rate", "anchors×zone")
    std_ok = bool(dqs_ is not None and dqs_["lo"] > 1)
    w("**Reading:** the user's expectation holds in direction: rain makes WISER noisier on every metric — more jitter, ×3–4 jumps, and more drift "
      f"(median 10-s drift {dq_['rain']:.2f} vs {dq_['calm']:.2f} in, ×{dq_['ratio']:.2f}; p90 {rr['drift10_p90']:.1f} vs {rc['drift10_p90']:.1f} in). Standardising over "
      f"anchors × zone {'keeps' if std_ok else 'shrinks'} the drift effect {'at' if std_ok else 'to'} ×{dqs_['ratio']:.2f} [{dqs_['lo']:.2f}, {dqs_['hi']:.2f}] "
      f"(nights only ×{dqn_['ratio']:.2f} [{dqn_['lo']:.2f}, {dqn_['hi']:.2f}]; medians on a 0.1-in grid, so the lower bound sits on the resolution), and the crazy-drift "
      f"excess to ×{crs_['ratio']:.1f} [{crs_['lo']:.1f}, {crs_['hi']:.1f}]: rain drift happens mostly in segments that have lost anchors. The effect is concentrated "
      f"in the minutes when it is actually raining (median 10-s drift {dnow_['rain']:.1f} in vs {dnow_['calm']:.1f} in when wet but not raining, ×{dnow_['ratio']:.1f}, "
      "also after standardisation). In size it is modest: + "
      f"{dq_['rain'] - dq_['calm']:.1f} in of median drift, below the jitter floor, and ≥ 12-in drifts stay rare ({n_ev_r} events in {rr['still_h']:.0f} rain still-hours). "
      f"The jitter increase likewise goes partly through lost anchors (rain still fixes: 9 anchors {fb9r['share'] * 100:.0f} % vs {fb9c['share'] * 100:.0f} %, ≤ 6 anchors "
      f"{fb6r['share'] * 100:.0f} % vs {fb6c['share'] * 100:.0f} %; standardised RMS ratio ×{rqs['ratio']:.2f} vs raw ×{rq['ratio']:.2f}) and partly within strata. "
      "Wetness, not falling rain alone, matters: the day after the rain is as bad as the rain nights in the morning and recovers by noon (Q1, by local hour).\n")
    w("**Confounds:** (i) only three rain periods (two nights, one wet day) — effectively three weather episodes, so the block CIs (which treat 10-min blocks "
      "as independent within a set and ignore that all five tags share the weather) are optimistic; (ii) humidity/dew is 90–98 % on every night, calm or rain, "
      "so it cannot be separated; (iii) the animals' location differs (rain-night still time is 20 % outside vs 5 % calm); (iv) the rain night 09-03 starts "
      "7 h after the 13:56 PC reboot that began regime B, and its pc_time tails are extrapolated for SF09/SF10/SF12; (v) the rain day 09-10 ends at ≈ 14:40 "
      "(ADC lane), so its hours differ from the calm days; (vi) weather–WISER alignment is ± 5 min (unverified).\n")
    w("**What it implies for the IMU:** in the rain the IMU constraint matters more (more jumps and jitter to suppress, fatter drift tail), but the "
      "dominant lever is anchor loss: any V6 must weight fixes by anchors (as B2/B2′ do) rather than treat rain as a separate regime.\n")
    if "rain_effect" in figs:
        w(f"![Rain effect](../figures/{figs['rain_effect']})\n")
    # ---------------------------------------------------------------- 7 Q5
    w("## 7. Q5 — Size of the opportunity (the bar for V6)\n")
    w("During certified stillness the true position is constant, so an ideal IMU stillness constraint removes **all within-segment variation** (fake path and "
      "speed → 0, error about the segment truth → 0). What is left for it to remove is therefore what B2′ leaves (calm-dry, pooled ≥ 30-s segments):\n")
    w("| metric (calm-dry stillness) | raw | B2′ already removes | left after B2′ = removable by an IMU constraint in principle | V1 / V2 by construction |")
    w("|---|---|---|---|---|")
    v1c, v2c = _r(PC, set="calm", method="V1"), _r(PC, set="calm", method="V2")
    for key, nm, u in (("rms_in", "per-fix RMS", "in"), ("p99_in", "per-fix p99", "in"), ("drift10_med", "10-s drift (median segment)", "in"),
                       ("drift10_p90", "10-s drift p90", "in"), ("speed_p95", "fake speed p95", "in/s"), ("path_in_per_min", "fake path", "in/min"),
                       ("jumps_per_h", "jumps", "/h"), ("crazy_per_h", "crazy drift", "/h")):
        a_, b_ = float(rc[key]), float(bc[key])
        w(f"| {nm} ({u}) | {_f(a_, 2)} | {_f(a_ - b_, 2)} ({_pct((a_ - b_) / a_ if a_ else np.nan)}) | **{_f(b_, 2)}** | {_f(v1c[key], 2)} / {_f(v2c[key], 2)} |")
    w("")
    w(f"Per still hour that is ≈ {bc['path_in_per_min'] * 60 / 39.37:.0f} m of invented path after B2′ (raw {rc['path_in_per_min'] * 60 / 39.37:.0f} m). "
      f"The constraint applies to {_pct(fcn['f30'])} of the IMU-ok night and {_pct(fcd['f30'])} of the day in ≥ 30-s stillness ({_pct(fcn['f10'])} / {_pct(fcd['f10'])} at ≥ 10 s). "
      "On the motion side B2′ already leaves 0 impossible-speed events and 0 jumps per hour, so there is no measured motion-side failure left for an IMU to remove; "
      "its possible contribution there (heading, gap bridging, in-place vs translating) is not measured by this audit.\n")
    w("**The bar:** a V6 that uses the IMU must beat B2′ on certified-still time by removing a meaningful part of **1.4–1.5 in RMS and ≈ 27 in/min of fake "
      "path** (rain: 2.3–2.7 in and ≈ 36 in/min) without adding error in motion, and should be scored against certified-still truth (this audit's segments), "
      "not against held-out WISER fixes. The 10-s drift that B2′ leaves (≈ 1.3–1.4 in calm) is below the jitter floor; it is not a reason to build V6.\n")
    # ---------------------------------------------------------------- 8 worst events
    W_ = A["worst"]
    w("## 8. Worst crazy-drift events — for a human video check\n")
    w(f"All {len(Ep)} raw crazy-drift events in primary ≥ 30-s segments (the rule rarely fires), largest first; the list is topped up to ≈ 20 with the "
      "largest raw 10-s-median excursions of other segments that did not meet the rule (`short`: ≥ 12 in for < 10 s; `near`: < 12 in), with the span where "
      "the 10-s median is ≥ 12 in (± 5 s). Camera = hourly file under `F:\\3rd_rat\\<date>\\<CH>\\` with the offset into it at "
      "the event start, by file-name time (never the OSD; cameras switch to IR at night). house_2 → CH07 in-box + CH06 top-down, house_1 → CH08 + CH05, "
      "outside → CH01/CH02 panoramas. The agent has not looked at any frame.\n")
    if len(W_):
        ts_ = W_.sort_values("start_ms")
        clus, cur = [], [ts_.iloc[0]]
        for _, r in ts_.iloc[1:].iterrows():
            if r.start_ms - cur[-1].start_ms <= 300_000:
                cur.append(r)
            else:
                clus.append(cur)
                cur = [r]
        clus.append(cur)
        multi = [c for c in clus if len({x.animal for x in c}) >= 3]
        for c in multi:
            w(f"**Common-mode cluster:** {len({x.animal for x in c})} tags ({', '.join(sorted({x.animal for x in c}))}) show ≥ 12-in excursions within 5 min of "
              f"{c[0].start_local} while each head is certified still (zones {', '.join(sorted({x.zone_detail for x in c}))}) — a shared cause (anchor "
              "geometry, a person or object near anchors) rather than a tag problem; check the panoramas at that time.\n")
    w("| # | type | animal | period | start → end (field-PC) | size (in) | dur (s) | anchors med (≤ 6 share) | zone | video |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(W_.itertuples(), 1):
        w(f"| {i} | {getattr(r, 'etype', 'event')} | {r.animal} | `{r.period}` | {r.start_local[5:]} → {r.end_local[11:]} | {r.size_in:.1f} | {int(r.dur_s) if np.isfinite(r.dur_s) else '–'} | "
          f"{_f(r.anchors_med, 0)} ({_pct(r.anchors_le6_frac)}) | {r.zone_detail} | {r.video} |")
    w("")
    # ---------------------------------------------------------------- 9 do not do
    w("## 9. Do not do\n")
    for s in ("Do not score a smoother or a fusion only against held-out WISER fixes: that truth drifts with WISER and is floor-dominated. Score against certified-still segments (this audit) and physical plausibility.",
              "Do not read raw WISER path length or speed during rest: a still tag invents ≈ 270 in of path per minute (calm) and ≈ 370 in/min (rain).",
              f"Do not treat a > 30-in jump or a > 100 in/s speed in raw WISER as movement — {mr_c['qjumps_n'] / max(mr_c['jumps_n'], 1) * 100:.0f} % (calm) / "
              f"{mr_r['qjumps_n'] / max(mr_r['jumps_n'], 1) * 100:.0f} % (rain) of the night jumps and {mr_c['imp_still_n'] / max(mr_c['imp_n'], 1) * 100:.0f} % / "
              f"{mr_r['imp_still_n'] / max(mr_r['imp_n'], 1) * 100:.0f} % of the impossible speeds occur while the IMU says still, and B2/B2′ remove them all.",
              "Do not claim that B2′ fixes drift: it leaves the 10-s drift almost unchanged, is slightly worse at 60 s, and in the rain follows low-anchor clusters into more ≥ 12-in excursions than the raw median.",
              "Do not generalise these still-time numbers to the open field: 95–100 % of certified still time is inside the houses.",
              "Do not use the literal `up_head` sweep of the 50-Hz npz as a stillness detector (recall 0.29), and do not apply the 0.03-g magnitude test to make_imu's accelerometer without the ellipsoid self-calibration.",
              "Do not pool rain and calm periods, and do not call rain → drift causal: rain acts mainly through lost anchors, and humidity, location and the 09-03 reboot are confounded.",
              "Do not present V1/V2 still-period gains as evidence for the IMU: they use the IMU stillness that defines the test.",
              "Do not make physical or directional claims from these numbers: distances are in the unverified WISER inch frame (frame-invariant), positions are not georeferenced."):
        w(f"- {s}")
    w("")
    w(DEFINITIONS)
    # ---------------------------------------------------------------- caveats
    w("## Caveats\n")
    for s in ("Truth = the median of the segment's own raw fixes: an error that lasts most of a segment (or a constant bias) is invisible, so drift is a lower bound and absolute accuracy is not measured.",
              f"Still time is ≥ 95 % in the house ROIs; long stillness outside the houses is {house_h.get('outside', 0):.1f} h in total.",
              "The S50 rule keeps ≈ 10 % of time that the 100-Hz strict rule does not (precision 0.90; slow head sag, gyro-bias differences); the audit metrics are unchanged when S50 replaces the strict windows on 09-08.",
              "Per-second IMU states (Q3) use the smoothing pilot's thresholds (locomotion detector TPR 0.75 / FPR 0.15 on its tuning night); onset/offset lags mix WISER latency with the time a rat needs to translate 12 in.",
              "Fix times are aligned by the per-animal τ* (0.10–0.20 s) and 1 s is trimmed at both segment ends; residual lag cannot create 12-in excursions inside a still segment.",
              "Rain contrast: three periods; days vs nights differ in hours (09-10 ends ≈ 14:40); weather alignment ± 5 min; block bootstrap assumes independent 10-min blocks within a set.",
              "Jump counts: a single outlier fix produces two jumps (in and out), so jumps ≈ 2 × outlier fixes; the earlier '0.09 % of fixes during IMU stillness' used a different stillness rule and unit.",
              "B2/B2′/V1/V2 use the smoothing pilot's tuned parameters (tuning night 09-08/09), which overlaps `night_20260908` of this audit; nothing is re-tuned here.",
              "SF12 `day_20260911` (validation only) has no make_imu npz for its field-flagged session; the brief's '203 sessions exist' does not include it."):
        w(f"- {s}")
    w("")
    w("## Files\n")
    w(f"Bulk `{out}`: `tables/` (segments.csv, segment_metrics.csv.gz, still_fixes.csv.gz, crazy_events.csv, still_jumps.csv.gz, motion_events.csv, "
      "motion_jumps.csv.gz, onsets_offsets.csv, motion_blocks.csv, still_windows.csv.gz, still_rule_validation.csv, weather_periods.csv, periods_info.csv, "
      "summary_*.csv, worst_crazy_events.csv), `tracks/<SFxx>_<period>.npz` (every method at every fix), `imu_seconds/`, `speeds/`, `summary.json`, "
      "`input_provenance.json`, logs. Re-score without recomputing: `python wiser/scripts/analyze_wiser_failure_audit.py --report-only <run_dir>`. "
      "New WISER fix caches (8 periods) in `D:\\Field2026_analysis_out\\2026c\\wiser_fix_cache\\` (index `index_failure_audit_2026c.csv`). "
      f"Pointer: `results/{cohort}/wiser_baseline/reports/run_manifest_failure_audit_{cohort}.json`.\n")
    return "\n".join(L) + "\n"


# ====================================================================================================== selftest
def _qmul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    w1, x1, y1, z1 = a.T
    w2, x2, y2, z2 = b.T
    return np.column_stack([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def _qconj(q: np.ndarray) -> np.ndarray:
    return q * np.array([1.0, -1.0, -1.0, -1.0])


def _slerp(q0: np.ndarray, q1: np.ndarray, s: np.ndarray) -> np.ndarray:
    d = float(np.dot(q0, q1))
    if d < 0:
        q1, d = -q1, -d
    th = math.acos(min(1.0, d))
    if th < 1e-9:
        return np.tile(q0, (len(s), 1))
    return (np.sin((1 - s) * th)[:, None] * q0 + np.sin(s * th)[:, None] * q1) / math.sin(th)


def _synthetic_imu(seed: int = 3) -> dict:
    """100-Hz head record: 40 still poses (20 s, random orientations) joined by 4-s slerp turns with linear acceleration;
    raw accelerometer = a_true / D + o; the 50-Hz make_imu-like stream (decimated quaternion, pair-averaged earth linear
    acceleration and |w|) is derived from it."""
    rng = np.random.default_rng(seed)
    fs = 100.0
    poses = rng.normal(size=(40, 4))
    poses /= np.linalg.norm(poses, axis=1, keepdims=True)
    qs, still = [], []
    for i in range(len(poses)):
        qs.append(np.tile(poses[i], (int(20 * fs), 1)))
        still.append(np.ones(int(20 * fs), bool))
        if i + 1 < len(poses):
            s = np.linspace(0, 1, int(4 * fs), endpoint=False)
            qs.append(_slerp(poses[i], poses[i + 1], 3 * s ** 2 - 2 * s ** 3))
            still.append(np.zeros(int(4 * fs), bool))
    q = np.vstack(qs)
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    still = np.concatenate(still)
    n = len(q)
    t100 = 1.79e12 + np.arange(n) * 10.0
    dq = _qmul(_qconj(q[:-1]), q[1:])
    ang = 2 * np.arccos(np.clip(np.abs(dq[:, 0]), -1, 1))
    om = np.r_[ang, ang[-1]] * fs * 180 / math.pi + np.abs(rng.normal(0, 0.3, n))
    lin_w = np.zeros((n, 3))
    mv = ~still
    lin_w[mv, 0] = 2.0 * np.sin(np.arange(mv.sum()) / fs * 2 * math.pi * 1.5)
    a_true = qrot_T(q, lin_w + np.array([0, 0, G])) + rng.normal(0, 0.02, (n, 3))
    D_true, o_true = np.array([1.02, 0.98, 1.0]), np.array([0.3, -0.8, 0.5])
    a_raw = a_true / D_true + o_true
    rot = lambda qq, v: qrot_T(_qconj(qq), v)  # noqa: E731  (R(q) v)
    lin_raw = rot(q, a_raw) - np.array([0, 0, G])
    m = n // 2
    pair = lambda x: x[:2 * m].reshape(m, 2, *x.shape[1:]).mean(axis=1)  # noqa: E731
    imu50 = {"unix_ms": t100[:2 * m:2], "quat_wxyz": q[:2 * m:2], "lin_acc_earth_ms2": pair(lin_raw), "omega_dps": pair(om),
             "up_head": qrot_T(q[:2 * m:2], np.tile([0.0, 0.0, 1.0], (m, 1))), "vedba_ms2": np.where(pair(still.astype(float)) > 0.5, 0.05, 2.0)}
    return {"t100": t100, "a_true": a_true, "om100": om, "still100": still, "imu50": imu50}


def selftest() -> int:
    ok_all = True
    t_start = time.time()

    def check(name, cond, info=""):
        nonlocal ok_all
        ok_all &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {info}", flush=True)

    mc = {"roll_short_s": 10.0, "roll_short_min_fix": 10, "roll_long_s": 60.0, "roll_long_min_fix": 60, "roll_long_min_seg_s": 120.0,
          "crazy_in": 12.0, "crazy_min_s": 10, "jump_in": 30.0, "jump_dt_s": 0.35, "speed_grid_s": 0.25, "speed_max_gap_s": 1.0}
    # ---- 1) a still tag with planted jitter, a slow drift, a crazy-drift event and jumps
    rng = np.random.default_rng(11)
    dt = rng.choice([0.134, 0.268], size=3000, p=[0.45, 0.55])
    t = np.cumsum(dt)
    t = t[t < 400.0]
    n = len(t)
    true = np.array([500.0, 700.0])
    sig = 2.5
    z = true + rng.normal(0, sig, (n, 2))
    drift = (t >= 100) & (t < 160)
    z[drift, 0] += 6.0
    crazy = (t >= 250) & (t < 280)
    z[crazy, 1] += 20.0
    spikes = [int(np.searchsorted(t, s)) for s in (30.0, 60.0, 200.0, 320.0, 350.0)]
    for k in spikes:
        z[k] += np.array([40.0, 0.0])
    truth = np.median(z, axis=0)
    rms_planted = float(np.sqrt(np.mean(np.sum((z - true) ** 2, axis=1))))
    res, evs, jps, spd = score_segment(t, {"raw": z}, truth, 0.0, 400.0, mc, ["raw"])
    r = res["raw"]
    check("jitter: per-fix RMS recovers the planted RMS (5 %)", abs(r["rms_in"] / rms_planted - 1) < 0.05, f"{r['rms_in']:.2f} vs {rms_planted:.2f} in")
    d10, c10 = res["raw"]["_d10"], res["raw"]["_c10"]
    dsel = (c10 >= 110) & (c10 <= 150)
    check("slow drift: 10-s rolling-median distance recovers the planted 6 in (+-1)", abs(np.nanmax(d10[dsel]) - 6.0) < 1.0, f"{np.nanmax(d10[dsel]):.2f} in")
    ev = [e for e in evs if e["method"] == "raw"]
    check("crazy drift: exactly one event", len(ev) == 1, f"{len(ev)}")
    if ev:
        check("crazy drift: size = planted 20 in (+-1.5)", abs(ev[0]["size_in"] - 20.0) < 1.5, f"{ev[0]['size_in']:.2f} in")
        check("crazy drift: duration = planted 30 s (+-3)", abs(ev[0]["dur_s"] - 30) <= 3, f"{ev[0]['dur_s']} s")
    check("jumps: 5 planted 40-in spikes -> 10 jumps (into and out of each)", r["jumps"] == 10, f"{r['jumps']}")
    check("drift (max of 10-s medians) is the crazy event", abs(r["drift10_in"] - 20.0) < 1.5, f"{r['drift10_in']:.2f}")
    z2 = true + rng.normal(0, sig, (n, 2))
    res2, evs2, _, sp2 = score_segment(t, {"raw": z2}, np.median(z2, axis=0), 0.0, 400.0, mc, ["raw"])
    check("clean still tag: no crazy event, no jump", res2["raw"]["crazy_n"] == 0 and res2["raw"]["jumps"] == 0)
    check("clean still tag: 10-s drift below 2 in", res2["raw"]["drift10_in"] < 2.0, f"{res2['raw']['drift10_in']:.2f}")
    check("fake speed of pure jitter > 0 and path rate > 0", res2["raw"]["speed_p50"] > 0 and res2["raw"]["path_in_per_min"] > 0)
    # ---- 2) motion-side detector
    tm = np.arange(0.0, 600.0, 0.25)
    pm = np.tile(np.array([300.0, 300.0]), (len(tm), 1))
    mv = (tm >= 100) & (tm < 200)
    pm[:, 0] += np.clip(tm - 100, 0, 100) * 20.0 / 1.0 * (tm >= 100) - np.clip(tm - 200, 0, None) * 20.0 * (tm >= 200) * 0
    pm[tm >= 200, 0] = 300.0 + 100 * 20.0
    pm += rng.normal(0, 1.5, pm.shape)
    for t0e in (300.0, 450.0):
        e = (tm >= t0e) & (tm < t0e + 1.5)
        pm[e, 1] += 150.0
    lo = 1.8e12
    secs = np.arange(int(lo // 1000), int(lo // 1000) + 600)
    state = np.ones(len(secs), np.int8)
    state[100:200] = 3
    state[445:456] = 2
    ps = pd.DataFrame({"sec": secs, "ok": True, "still": state == 1, "state": state})
    mo = {"impossible_inps": 100.0, "event_merge_s": 1.0, "jump_imu_pm_s": 1, "still_run_min_s": 10, "loco_search_s": 60, "ref_s": 10.0,
          "depart_in": 12.0, "median_win_s": 3.0, "median_min_fix": 3, "ref_min_fix": 10, "lag_window_s": 20.0, "lag_ok_s": 2.0}
    fxm = pd.DataFrame({"anchors_used": np.full(len(tm), 9)})
    mres = motion_night(fxm, tm, {"raw": pm}, ps, lo, lo + 600_000.0, mo, mc, [], 14.0, ["raw"])
    evm = mres["events"]
    check("motion: the 2 planted 150-in excursions are flagged as impossible speed", len(evm) == 2, f"{len(evm)} events")
    clean = evm[(evm.t0_ms >= lo + 99_000) & (evm.t1_ms <= lo + 201_000)] if len(evm) else evm
    check("motion: the clean 20 in/s locomotion is not flagged", len(clean) == 0)
    jm = mres["jumps"]
    nq = int((jm.imu_class == "imu_quiet").sum()) if len(jm) else 0
    na = int((jm.imu_class == "imu_active").sum()) if len(jm) else 0
    check("motion: 4 planted jumps, 2 with a quiet IMU (t = 300 s), 2 with an active IMU (t = 450 s)", len(jm) == 4 and nq == 2 and na == 2,
          f"{len(jm)} jumps, quiet {nq}, active {na}")
    # ---- 3) S50 on a synthetic 50-Hz record vs the strict rule on the 100-Hz original
    syn = _synthetic_imu()
    scfg = {"block_s": 0.1, "dir_max_deg": 0.3, "mag_tol_g": 0.03, "omega_max_dps": 3.0, "min_window_s": 1.0, "qs_win_s": 0.5,
            "qs_omega_dps": 10.0, "qs_acc_sd": 0.15, "qs_min_windows": 50, "merge_gap_s": 2.0, "gap_omega_max_dps": 20.0}
    w_strict = strict_rule_windows(syn["t100"], syn["a_true"], syn["om100"], np.ones(len(syn["t100"]), bool), scfg, 100.0)
    pb = {"ellipsoid_huber_scale": 0.1, "ellipsoid_prior_scale_sd": 0.05, "ellipsoid_prior_offset_sd": 0.5}
    im = syn["imu50"]
    valid = np.ones(len(im["unix_ms"]), bool)
    w50, wup, cal = s50_windows({**im, "saturated": ~valid, "frozen": ~valid, "invalid": ~valid, "unreliable": ~valid}, valid, scfg, pb)
    lo3, hi3 = syn["t100"][0], syn["t100"][-1] + 10
    ov = time_overlap(w50, w_strict, lo3, hi3)
    check("S50 self-calibration recovers the planted offsets (+-0.05 m/s^2)", np.allclose(cal["o"], [0.3, -0.8, 0.5], atol=0.05), f"{np.round(cal['o'], 3)}")
    check("S50 agrees with the strict rule (time recall and precision >= 0.9)", ov["recall"] >= 0.9 and ov["precision"] >= 0.9,
          f"recall {ov['recall']:.3f}, precision {ov['precision']:.3f}, strict {ov['b_min']:.1f} min, S50 {ov['a_min']:.1f} min")
    truth_still = time_overlap(w50, np.array([[a, b] for a, b in zip(syn["t100"][np.r_[0, np.flatnonzero(np.diff(syn['still100'].astype(int)) == 1) + 1]],
                                                                      syn["t100"][np.r_[np.flatnonzero(np.diff(syn['still100'].astype(int)) == -1), len(syn['t100']) - 1]])]), lo3, hi3)
    check("S50 windows lie inside the planted still poses (precision >= 0.98)", truth_still["precision"] >= 0.98, f"{truth_still['precision']:.3f}")
    raw_ = {**im, "saturated": ~valid, "frozen": ~valid, "invalid": ~valid, "unreliable": ~valid}
    a_nc = rebuilt_acc(raw_)
    w_nc = strict_rule_windows(im["unix_ms"], a_nc, im["omega_dps"], valid, scfg, FS)
    ov_nc = time_overlap(w_nc, w_strict, lo3, hi3)
    check("without the self-calibration the magnitude test loses still time (recall drops)", ov_nc["recall"] < ov["recall"],
          f"recall {ov_nc['recall']:.3f} vs {ov['recall']:.3f}")
    # merge rule
    u = np.arange(0, 10_000, 20.0)
    imm = {"unix_ms": u, "omega_dps": np.full(len(u), 1.0), "vedba_ms2": np.full(len(u), 0.05)}
    S1 = merge_segments(np.array([[0.0, 4000.0], [5000.0, 9000.0]]), imm, np.ones(len(u), bool), 0.3, scfg)
    imm2 = {**imm, "omega_dps": np.where((u >= 4400) & (u < 4500), 50.0, 1.0)}
    S2 = merge_segments(np.array([[0.0, 4000.0], [5000.0, 9000.0]]), imm2, np.ones(len(u), bool), 0.3, scfg)
    check("merge: a quiet 1-s gap joins two windows; a head movement in the gap does not", len(S1) == 1 and len(S2) == 2, f"{len(S1)} / {len(S2)}")
    # ---- 4) per-group still tables: the speed quantiles of a single group equal the pooled ones (fix 2026-10-03)
    rq = np.random.default_rng(5)
    Sq = pd.DataFrame({"seg_id": [f"s{i}" for i in range(6)], "set": ["calm"] * 3 + ["rain"] * 3, "dur_trim_s": 60.0})
    Mq = pd.DataFrame([{"seg_id": s, "method": "raw", "drift10_in": 1.0, "drift60_in": np.nan, "crazy_n": 0, "crazy_s": 0, "jumps": 0,
                        "path_in": 10.0, "path_s": 59.0} for s in Sq.seg_id])
    Fq = pd.DataFrame({"seg_id": np.repeat(Sq.seg_id.to_numpy(), 20), "r_raw": rq.gamma(2.0, 1.0, 120)})
    spd_q = [rq.gamma(2.0, 1.0 + 3.0 * i, 200).astype(np.float32) for i in range(6)]       # segment i's speeds differ in scale
    SPq = {"raw": (np.repeat(np.arange(6), 200).astype(np.int64), np.concatenate(spd_q))}
    sub = Sq[Sq.set == "rain"]
    gq = group_table(sub, Mq, Fq, SPq, ["set"], ["raw"], Sq).iloc[0]
    pq = still_summary(sub, Mq, Fq, SPq, "raw", Sq)
    direct = float(np.percentile(np.concatenate(spd_q[3:]), 95))
    old = group_table(sub, Mq, Fq, SPq, ["set"], ["raw"]).iloc[0]          # the pre-fix call (positions of the subset)
    check("group table: a single group's speed p95 equals the pooled one and the direct quantile",
          abs(gq["speed_p95"] - pq["speed_p95"]) < 1e-9 and abs(gq["speed_p95"] - direct) < 1e-6,
          f"grouped {gq['speed_p95']:.4f}, pooled {pq['speed_p95']:.4f}, direct {direct:.4f} (pre-fix call {old['speed_p95']:.4f})")
    print(f"selftest {time.time() - t_start:.1f} s -> {'ALL PASS' if ok_all else 'FAILED'}", flush=True)
    return 0 if ok_all else 1


# ====================================================================================================== main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cohort", default="2026c")
    ap.add_argument("--config", default=None)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--report-only", default=None, help="existing run dir: re-score and re-render from its saved tables")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    cfg = load_cfg(a.cohort, a.config)
    out = Path(a.report_only) if a.report_only else run_compute(cfg, a.workers or int(cfg.get("workers", 5)))
    fh = open(out / "log_report.txt", "a", encoding="utf-8")
    A = analyze(out, cfg, fh)
    publish(A, cfg, out, fh)
    fh.close()


if __name__ == "__main__":
    main()
