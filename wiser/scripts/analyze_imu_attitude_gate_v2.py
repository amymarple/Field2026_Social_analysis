r"""Head-IMU attitude gate v2 (cohort 2026c): strict accelerometer-led still windows, centre-to-centre gravity propagation,
night + day-sleep data, the Phase-0 gate re-tested with unchanged thresholds, and a chained-anchor test of whether the
residual gyro drift is linear in time, a random walk, or rotation-driven. IMU attitude only; WISER is a still-window veto.

Plan: implementation_plan/2026-10-01-imu-attitude-gate-v2.md (approved by the user 2026-10-01 "去吧"; pre-registered before
any computation on the test periods). Follows Phase 0 (change_log/2026-09-30-imu-attitude-phase0.md), whose functions are
imported unchanged (cache loader, Hampel + saturation classes + held-reading reconstruction, 100-Hz gyro chain, BoutSet,
gyro models + Huber fit + bootstrap, Rodrigues propagation, fit_growth).

Inputs (read-only): A1 raw 1250-Hz IMU, A3 100-Hz calibrated IMU and A2 WISER fixes under D:/Field2026_analysis_out/2026c/
(nights: existing V4 caches; days: built once by --build-day-caches with the cache builder's own functions, raw E: and the
pc_time fits on Q: read-only, the WISER SQLite copy opened mode=ro).
Outputs: bulk <OUT_ROOT>/<cohort>/imu_attitude_gate_v2_<ts>/; report results/<cohort>/wiser_baseline/reports/
wiser_baseline_imu_attitude_gate_v2_<cohort>.md (+ figures, pointer run_manifest_imu_attitude_gate_v2_<cohort>.json).

Usage:
  python wiser/scripts/analyze_imu_attitude_gate_v2.py --build-day-caches [--workers 5]
  python wiser/scripts/analyze_imu_attitude_gate_v2.py --cohort 2026c [--roles tuning] [--animals SF09]
  python wiser/scripts/analyze_imu_attitude_gate_v2.py --report-only <run_dir>
  python wiser/scripts/analyze_imu_attitude_gate_v2.py --selftest
"""
from __future__ import annotations

import argparse
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
from numba import njit, prange
from scipy import signal
from scipy.optimize import minimize
from scipy.stats import spearmanr

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "wiser" / "src"))
sys.path.insert(0, str(REPO / "wiser" / "scripts"))
sys.path.append(str(REPO / "ephys"))
import output_paths  # noqa: E402  (wiser shim -> common/output_paths.py)
import analyze_imu_attitude_phase0 as P0  # noqa: E402  (Phase 0; unmodified)
import build_imu_wiser_cache as B  # noqa: E402  (A1 / A2 cache functions; unmodified)
import analyze_wiser_ins_fusion as V4  # noqa: E402  (A3 chain functions; unmodified)
import analyze_imu_wiser_calibration as C  # noqa: E402  (to_ms, in_any, resolve_tag, file_info; unmodified)
from cohorts import load_cohort  # noqa: E402
import make_imu as MI  # noqa: E402
import _common as EC  # noqa: E402

DIRECTION = "wiser_baseline"
NAME = "imu_attitude_gate_v2"
STEM = f"{DIRECTION}_imu_attitude_gate_v2"
G = MI.G
FS_RAW, FS100 = 1250.0, 100.0
DT = 1.0 / FS100
D2R, R2D = math.pi / 180.0, 180.0 / math.pi
ACC_SCALE, GYR_SCALE = P0.ACC_SCALE, P0.GYR_SCALE
VARIANTS = ("L1.0", "L2.0", "L1.0_nf")          # gate variant (>= 1 s, WISER-filtered), >= 2 s, >= 1 s without the WISER filter
log = P0.log
_jd = P0._jd


def to_ms(local: str, tz: str) -> int:
    return C.to_ms(local, tz)


def ms_local(ms: float, tz: str = "America/New_York", frac: bool = True) -> str:
    ts = pd.Timestamp(int(round(ms)), unit="ms", tz="UTC").tz_convert(tz)
    return ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if frac else ts.strftime("%Y-%m-%d %H:%M:%S")


def load_cfg(cohort: str, path: str | None = None) -> tuple[dict, dict]:
    cp = Path(path) if path else REPO / "wiser" / "configs" / f"imu_attitude_gate_v2_{cohort}.json"
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    cfg["_path"] = str(cp)
    cfg["_cohort"] = cohort
    p0cfg = json.loads((REPO / cfg["phase0_config"]).read_text(encoding="utf-8"))
    return cfg, p0cfg


def context(cfg: dict) -> dict:
    tz = cfg["tz"]
    coh = load_cohort(cfg["_cohort"])
    hj = json.loads((REPO / cfg["handling_json"]).read_text(encoding="utf-8"))
    handling = [(to_ms(a, tz), to_ms(b, tz), note) for a, b, note in hj["windows"]]
    ivu = {r["animal"]: to_ms(r["until"], tz) for r in ((coh.get("ephys") or {}).get("imu_valid_until") or [])}
    return {"coh": coh, "handling": handling, "imu_valid_until": ivu, "tz": tz}


# ====================================================================================================== numba kernels
@njit(cache=True)
def _strict_kernel(m, u, cand, cosmax, mlo, mhi, min_blocks, out_s, out_e):
    """Greedy left-to-right still windows on 0.1-s block means m (nb,3) with unit directions u: a window grows while
    every block direction is within acos(cosmax) of the window-mean direction and |window mean| in (mlo, mhi)."""
    nb = m.shape[0]
    cnt = 0
    j = 0
    while j < nb:
        if not cand[j]:
            j += 1
            continue
        n0 = math.sqrt(m[j, 0] ** 2 + m[j, 1] ** 2 + m[j, 2] ** 2)
        if not (mlo < n0 < mhi):
            j += 1
            continue
        s = j
        sx, sy, sz = m[j, 0], m[j, 1], m[j, 2]
        e = j + 1
        while e < nb and cand[e]:
            tx, ty, tz = sx + m[e, 0], sy + m[e, 1], sz + m[e, 2]
            nn = e - s + 1
            mx, my, mz = tx / nn, ty / nn, tz / nn
            mn = math.sqrt(mx * mx + my * my + mz * mz)
            if not (mlo < mn < mhi):
                break
            ok = True
            for jj in range(s, e + 1):
                if (u[jj, 0] * mx + u[jj, 1] * my + u[jj, 2] * mz) / mn < cosmax:
                    ok = False
                    break
            if not ok:
                break
            sx, sy, sz = tx, ty, tz
            e += 1
        if e - s >= min_blocks:
            out_s[cnt] = s
            out_e[cnt] = e
            cnt += 1
        j = e
    return cnt


@njit(cache=True)
def _qrot(q, vx, vy, vz):
    """v' = R(q) v for q = [w, x, y, z] (head -> world)."""
    w, x, y, z = q
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (vx + w * tx + (y * tz - z * ty), vy + w * ty + (z * tx - x * tz), vz + w * tz + (x * ty - y * tx))


@njit(parallel=True, cache=True)
def _chains_kernel(w_rad, a_bias, q0, a_c, t_off, t_c, t_g, dt, out_phi, out_theta):
    """Per anchor i: q from q0[i] at sample a_c[i], integrated q <- q (x) Exp((w - a_bias[i]) dt) with no aiding; at each
    target r (sample t_c[r], head-frame gravity t_g[r]) store the horizontal rotation vector taking e_z to R(q) g (rad) and
    the accumulated rotation (rad). a_bias = 0 except in the exploratory anchor-ZARU variant."""
    na = a_c.shape[0]
    for i in prange(na):
        q = (q0[i, 0], q0[i, 1], q0[i, 2], q0[i, 3])
        k = a_c[i]
        th = 0.0
        b0, b1, b2 = a_bias[i, 0], a_bias[i, 1], a_bias[i, 2]
        for r in range(t_off[i], t_off[i + 1]):
            kend = t_c[r]
            while k < kend:
                rx, ry, rz = (w_rad[k, 0] - b0) * dt, (w_rad[k, 1] - b1) * dt, (w_rad[k, 2] - b2) * dt
                th += math.sqrt(rx * rx + ry * ry + rz * rz)
                q = P0._qmul(q, P0._qexp(rx, ry, rz))
                nq = math.sqrt(q[0] ** 2 + q[1] ** 2 + q[2] ** 2 + q[3] ** 2)
                q = (q[0] / nq, q[1] / nq, q[2] / nq, q[3] / nq)
                k += 1
            ux, uy, uz = _qrot(q, t_g[r, 0], t_g[r, 1], t_g[r, 2])
            un = math.sqrt(ux * ux + uy * uy + uz * uz)
            ux, uy, uz = ux / un, uy / un, uz / un
            sx, sy = -uy, ux
            sn = math.sqrt(sx * sx + sy * sy)
            ang = math.atan2(sn, uz)
            if sn > 1e-15:
                out_phi[r, 0] = sx / sn * ang
                out_phi[r, 1] = sy / sn * ang
            else:
                out_phi[r, 0] = 0.0
                out_phi[r, 1] = 0.0
            out_theta[r] = th


# ====================================================================================================== day caches
def _a3_day_job(job: dict) -> dict:
    """A3-equivalent 100-Hz file for one day A1 window: the V4 after-chain exactly as decided on the tuning night (ref)."""
    try:
        out = Path(job["out"])
        if out.exists():
            return {"path": str(out), "skipped": True, "bytes": out.stat().st_size, **job["meta"]}
        t0 = time.time()
        ref, pb = job["ref"], job["pb"]
        cache = B.load_imu_raw_cache(Path(job["a1"]))
        six, sat, frz = cache["six"], cache["sat"], cache["frozen"]
        x = six.astype(np.float32)
        hx = np.empty_like(x)
        fl = np.zeros(x.shape, bool)
        V4._hampel_lanes(x, sat, int(pb["hampel_half_window"]), float(pb["hampel_nsigma"]),
                         V4.hampel_floor(six, float(pb["hampel_mad_floor_counts"])), hx, fl)
        del x
        fca, fcg = float(ref["fc_hz"]["acc"]), float(ref["fc_hz"]["gyr"])
        scale = np.r_[np.full(3, ACC_SCALE), np.full(3, GYR_SCALE)]
        lp = []
        for l in range(6):
            sos = signal.butter(int(ref["butter_order"]), fca if l < 3 else fcg, fs=FS_RAW, output="sos")
            y = signal.sosfiltfilt(sos, hx[:, l].astype(np.float64) * scale[l])
            lp.append(signal.resample_poly(y, 2, 25))
        del hx
        n100 = min(len(v) for v in lp)
        Bl = np.column_stack([v[:n100] for v in lp])
        del lp
        a_lp, w_lp = Bl[:, :3] @ MI.S, Bl[:, 3:] @ MI.S
        del Bl
        meta1 = json.loads(str(cache["meta_json"]))
        fit = json.loads(str(cache["fit_json"]))
        amp = int(cache["amp0"]) + 200.0 * np.arange(n100)
        t100 = B.local_midnight_ms(meta1["start_local"]) + MI.pc_time_ms(amp, fit)
        dil_a, dil_g = int(math.ceil(2.0 / fca * FS100)), int(math.ceil(2.0 / fcg * FS100))
        frz100 = V4.any_per_100hz(frz, n100)
        sat_acc = V4.any_per_100hz(sat[:, :3].any(axis=1), n100, dil_a)
        sat_gyr = V4.any_per_100hz(sat[:, 3:].any(axis=1), n100, dil_g)
        spikes100 = V4.count_per_100hz(fl.any(axis=1), n100)
        del fl
        bad100 = sat_acc | sat_gyr | frz100
        ws = V4.window_stats(a_lp, w_lp, bad100, int(pb["quasi_static_win_s"] * FS100))
        qsw = (ws["wmed"] < pb["quasi_static_omega_dps"]) & (ws["asd"].max(axis=1) < pb["quasi_static_acc_sd"]) & ~ws["bad"]
        abar = ws["abar"][qsw]
        ell = V4.fit_ellipsoid(abar, pb) if len(abar) >= 50 else None
        k_sc = G / float(np.median(np.linalg.norm(abar, axis=1))) if len(abar) else 1.0
        if ref["acc"]["method"] == "ellipsoid" and ell is not None:
            cal = {"method": "ellipsoid", "D": ell["D"], "o": ell["o"]}
        else:
            cal = {"method": "scalar", "k_a": k_sc}
        qs = V4.quiet_seconds(a_lp, w_lp, bad100)
        tq, wq = qs["t_c"][qs["quiet"]], qs["wmed3"][qs["quiet"]]
        t_s = (t100 - t100[0]) / 1000.0
        if ref["gyro_bias_method"] == "running":
            bias = V4.bias_running(tq, wq, t_s, pb["bias_running_half_s"], pb["bias_min_windows"])
        else:
            bias = V4.bias_block(tq, wq, t_s)
        gscale = float(ref["gyro_scale"])
        a = V4.apply_acc(a_lp.astype(np.float64), cal)
        w = gscale * (w_lp.astype(np.float64) - bias)
        quiet = (np.repeat(qs["quiet"], 100)[:n100] if len(qs["quiet"]) * 100 >= n100 else
                 np.r_[np.repeat(qs["quiet"], 100), np.zeros(n100 - len(qs["quiet"]) * 100, bool)])
        tb = np.arange(0, n100, 6000)
        calib = {"acc": cal, "gyro_bias_method": ref["gyro_bias_method"], "gyro_scale": gscale, "fc_hz": ref["fc_hz"],
                 "bias_nodes_1min": {"t_unix_ms": t100[tb].tolist(), "bias_dps": np.asarray(bias)[tb].tolist()},
                 "hampel": ref["hampel"], "butter_order": ref["butter_order"], "axis_map_S": MI.S.tolist(), "resample": "resample_poly(2, 25)",
                 "decided_on": ref["decided_on"] + "; DAY file: same chain applied by analyze_imu_attitude_gate_v2.py (ellipsoid/bias self-calibrated on this day window)",
                 "acc_fit": {"n_quasi_static_windows": int(len(abar)), "ellipsoid": ell, "scalar_k_a": k_sc}}
        meta = {**job["meta"], "source_a1": str(job["a1"]), "t_clock": "field-PC Unix ms on the IMU clock (tau* NOT applied)",
                "units": {"acc": "m/s^2 head frame", "gyr": "deg/s head frame"}, "git_commit": job["git"],
                "written_local": pd.Timestamp.now(tz=job["tz"]).isoformat(timespec="seconds"),
                "writer": "wiser/scripts/analyze_imu_attitude_gate_v2.py --build-day-caches (V4 A3 chain functions, unmodified)",
                "n_quiet_seconds": int(qs["quiet"].sum())}
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.stem + ".partial.npz")
        np.savez_compressed(tmp, t_unix_ms=t100, acc=a.astype(np.float32), gyr=w.astype(np.float32), sat_acc=sat_acc, sat_gyr=sat_gyr,
                            frozen=frz100, spikes=spikes100, quiet=quiet, calib_json=np.array(json.dumps(calib, default=_jd)),
                            meta_json=np.array(json.dumps(meta, default=_jd)))
        os.replace(tmp, out)
        return {"path": str(out), "bytes": out.stat().st_size, "n100": int(n100), "quiet_frac": float(quiet.mean()),
                "acc_method": cal["method"], "n_qs_windows": int(len(abar)), "elapsed_s": round(time.time() - t0, 1), **job["meta"]}
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}", **job.get("meta", {})}


def build_day_caches(cfg: dict, workers: int, fh=None) -> dict:
    """A1 (raw 1250-Hz lanes), A3-equivalent (100 Hz) and A2 (WISER fixes) for the day periods; never overwrites."""
    tz, dc, cohort = cfg["tz"], cfg["day_cache"], cfg["_cohort"]
    roots = {k: Path(v) for k, v in cfg["cache_roots"].items()}
    raw_root, pct = Path(dc["raw_ephys_root"]), Path(dc["pc_time_root"])
    sidx = pd.read_csv(REPO / "results" / cohort / "ephys_spikes" / "reports" / f"ephys_spikes_session_index_{cohort}.csv")
    coh = load_cohort(cohort)
    macs = {k: v.get("mac") for k, v in ((coh.get("ephys") or {}).get("loggers") or {}).items()}
    git = EC.git_commit()
    out = {"a1": [], "a3": [], "a2": []}
    # ---------------- A1
    jobs = []
    for pkey, p in cfg["periods"].items():
        if p["kind"] != "day":
            continue
        lo, hi = to_ms(p["start"], tz), to_ms(p["end"], tz)
        for a in cfg["animals"]:
            s = p["sessions"][a]
            row = sidx[sidx.session == s]
            if len(row) != 1:
                raise SystemExit(f"{a} {s}: {len(row)} rows in the session index")
            start_local = str(row.start_local.iloc[0])
            session_dir = EC.find_session_dir(raw_root, B.raw_animal(a), s)
            fit = json.loads((pct / a / s / "pc_time_fit.json").read_text(encoding="utf-8"))
            meta = {"cohort": cohort, "animal": a, "raw_animal": B.raw_animal(a), "night": pkey, "night_role": f"day_{p['role']}",
                    "night_window_local": [p["start"], p["end"]], "mac": macs.get(B.raw_animal(a)) or macs.get(a) or session_dir.parent.name,
                    "pc_time_fit_path": str(pct / a / s / "pc_time_fit.json"), "built_by": "analyze_imu_attitude_gate_v2.py --build-day-caches"}
            m = float(dc["margin_s"]) * 1000
            jobs.append((session_dir, fit, start_local, lo - m, hi + m, roots["imu_raw"] / a, s, meta, int(dc["sha_head_bytes"]), tz, False))
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=max(1, workers)) as ex:
        res = list(ex.map(B._imu_job, jobs))
    for r in res:
        if "error" in r:
            raise SystemExit(f"A1 ERROR {r.get('session')}: {r['error']}")
        log(f"A1 {r['animal']} {r['night']} {r['session']}: {r['n']:,} frames {r['window_actual_local'][0]} -> {r['window_actual_local'][1]}, "
            f"sat/lane {r['sat_samples_per_lane']}, frozen {r['frozen_samples']}, {r.get('bytes', 0) / 1e6:.0f} MB"
            f"{' (existing)' if r.get('skipped') else ''}", fh)
        out["a1"].append({k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in r.items()
                          if k in ("animal", "night", "night_role", "session", "session_dir", "mac", "start_local", "k0", "k1", "n",
                                   "window_actual_local", "window_requested_local", "source_bytes", "source_sha256_head",
                                   "sat_samples_per_lane", "frozen_samples", "path", "bytes", "git_commit", "written_local")})
    log(f"A1 day caches: {time.time() - t0:.0f} s", fh)
    idx1 = roots["imu_raw"] / f"index_day_{cohort}.csv"
    new = pd.DataFrame(out["a1"])
    if idx1.exists():
        old = pd.read_csv(idx1)
        new = pd.concat([old[~old.path.isin(new.path)], new], ignore_index=True)
    new.sort_values(["night", "animal"]).to_csv(idx1, index=False)
    # ---------------- A3-equivalent
    ref = json.loads(str(np.load(roots["imu100"] / cfg["animals"][0] / f"{dc['reference_a3_night']}.npz", allow_pickle=True)["calib_json"]))
    pb = json.loads((REPO / "wiser" / "configs" / f"wiser_ins_fusion_{cohort}.json").read_text(encoding="utf-8"))["phase_b"]
    a3jobs = []
    for r in out["a1"]:
        p = cfg["periods"][r["night"]]
        a3jobs.append({"a1": r["path"], "out": str(roots["imu100"] / r["animal"] / f"{r['night']}.npz"), "ref": ref, "pb": pb, "git": git, "tz": tz,
                       "meta": {"animal": r["animal"], "night": r["night"], "role": f"day_{p['role']}", "session": r["session"]}})
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=max(1, min(workers, 5))) as ex:
        res3 = list(ex.map(_a3_day_job, a3jobs))
    for r in res3:
        if "error" in r:
            raise SystemExit(f"A3 ERROR {r.get('animal')} {r.get('night')}: {r['error']}")
        log(f"A3-day {r['animal']} {r['night']}: {r.get('n100', 0):,} samples, quiet {r.get('quiet_frac', float('nan')):.3f}, acc {r.get('acc_method')} "
            f"({r.get('n_qs_windows')} windows), {r['bytes'] / 1e6:.0f} MB" + (" (existing)" if r.get("skipped") else f" in {r.get('elapsed_s')} s"), fh)
        out["a3"].append(r)
    log(f"A3-day caches: {time.time() - t0:.0f} s", fh)
    # ---------------- A2
    ids = pd.read_csv(REPO / coh["identities"], dtype={"shortid": int, "physical_tag_id": str})
    ids["from_ms"] = pd.to_datetime(ids["valid_from"], utc=True).astype("int64") // 10**6
    ids["until_ms"] = pd.to_datetime(ids["valid_until"], utc=True).astype("int64") // 10**6
    hj = json.loads((REPO / cfg["handling_json"]).read_text(encoding="utf-8"))
    handling = [(to_ms(a, tz), to_ms(b, tz), note) for a, b, note in hj["windows"]]
    sil = pd.read_csv(dc["silences_csv"])
    pad = float(dc["silence_pad_s"]) * 1000
    silences = [(to_ms(r.start, tz) - pad, to_ms(r.end, tz) + pad, r.kind) for r in sil.itertuples()]
    adc = [(to_ms(wd["on_from"], tz), to_ms(wd["off_at"], tz), wd["animal"])
           for wd in ((coh.get("ephys") or {}).get("adc_lane") or {}).get("on_windows", [])]
    db = Path(dc["wiser_db"])
    dbi = C.file_info(db)
    if not dbi["sha256"].startswith(dc["wiser_db_sha256_prefix_expected"]):
        raise SystemExit(f"WISER DB sha256 {dbi['sha256'][:12]} != expected {dc['wiser_db_sha256_prefix_expected']}")
    m = float(dc["margin_s"]) * 1000
    for pkey, p in cfg["periods"].items():
        if p["kind"] != "day":
            continue
        lo, hi = to_ms(p["start"], tz), to_ms(p["end"], tz)
        tags = {a: C.resolve_tag(ids, a, lo, hi) for a in cfg["animals"]}
        fr, st = B.wiser_night(db, dc["wiser_table"], tags, lo - m, hi + m, handling, silences, adc, ids, tz)
        od = roots["wiser_fix"] / pkey
        od.mkdir(parents=True, exist_ok=True)
        for a, f in fr.items():
            pth = od / f"{a}.csv.gz"
            existed = pth.exists()
            if not existed:
                f.to_csv(pth, index=False)
            inw = (f.t_ms >= lo) & (f.t_ms < hi)
            out["a2"].append({"night": pkey, "night_role": f"day_{p['role']}", "animal": a, "shortid": tags[a], "path": str(pth), "rows": len(f),
                              "rows_in_window": int(inw.sum()), "dup_groups_all_tags": st["dup_groups"], "rows_dropped_all_tags": st["rows_dropped"],
                              "db": str(db), "db_sha256": dbi["sha256"], "window_local": json.dumps([C.ms_to_local(lo - m, tz), C.ms_to_local(hi + m, tz)]),
                              "m_handling": int(f.m_handling[inw].sum()), "m_silence": int(f.m_silence[inw].sum()),
                              "m_tag_validity": int(f.m_tag_validity[inw].sum()), "m_adc_lane": int(f.m_adc_lane[inw].sum()),
                              "bytes": pth.stat().st_size, "git_commit": git, "existing": existed})
            log(f"A2 {a} {pkey}: {len(f):,} fixes ({int(inw.sum()):,} in the window), masked: handling {int(f.m_handling[inw].sum())}, "
                f"silence {int(f.m_silence[inw].sum())}, tag validity {int(f.m_tag_validity[inw].sum())}{' (existing)' if existed else ''}", fh)
    idx2 = roots["wiser_fix"] / f"index_day_{cohort}.csv"
    new2 = pd.DataFrame(out["a2"])
    if idx2.exists():
        old = pd.read_csv(idx2)
        new2 = pd.concat([old[~old.path.isin(new2.path)], new2], ignore_index=True)
    new2.to_csv(idx2, index=False)
    write_cache_readmes(cfg, out, git)
    return out


README_MARK = "<!-- written by analyze_imu_attitude_gate_v2.py -->"


def write_cache_readmes(cfg: dict, built: dict, git: str) -> None:
    """README.md per cache root (none existed): format + the day files. A README not written by this script is appended to."""
    roots = {k: Path(v) for k, v in cfg["cache_roots"].items()}

    def sz(paths):
        return sum(Path(p).stat().st_size for p in paths if Path(p).exists())
    a1d = [r["path"] for r in built["a1"]]
    a3d = [r["path"] for r in built["a3"]]
    a2d = [r["path"] for r in built["a2"]]
    nights_a1 = sorted(str(p) for p in roots["imu_raw"].glob("SF*/*.npz") if str(p) not in a1d)
    texts = {
        "imu_raw": f"""# A1 cache - raw head-IMU lanes (cohort 2026c)
{README_MARK}

One file per animal and window: `<SFxx>/<session>__<start>_<end>.npz` (stamps = field-PC local time of the first/last frame).
Written by `wiser/scripts/build_imu_wiser_cache.py` (`cache_imu_window`; nights 20:50 -> 05:30, V4 run 2026-09-29) and, for the
**day windows**, by the same function called from `wiser/scripts/analyze_imu_attitude_gate_v2.py --build-day-caches` (2026-10-01,
git {git}). Raw `E:\\3rd_rat_spikes` is read once with an offset (only the window); nothing else reads raw.

| key | dtype / shape | meaning |
|---|---|---|
| `six` | int16 (n, 6) | analogin lanes 1-6 = acc x/y/z, gyro x/y/z, sensor frame, raw counts, 1250 Hz (the IMU itself updates at ~190 Hz, sample-and-hold) |
| `k0`, `amp0` | int | first analogin frame of the window in the session; amplifier sample = 16 k |
| `sat` | bool (n, 6) | abs(raw) >= 32700 per lane |
| `frozen` | bool (n,) | all six lanes repeat >= 0.5 s (hung chip) |
| `fit_json`, `meta_json` | str | the session's pc_time_fit.json verbatim; animal, session, window (requested / actual), sha256 of the first 64 MiB, ... |

Field-PC Unix ms of frame j: `build_imu_wiser_cache.cache_unix_ms(cache)`. Index: `index_2026c.csv` (nights), `index_day_2026c.csv` (days).

**Night files** ({len(nights_a1)}): the 2 nights 2026-09-08/09 and 09-10/11 x SF07 SF08 SF09 SF10 SF12.
**Day files** ({len(a1d)}, {sz(a1d) / 1e6:.0f} MB; `meta_json.night` = `day_<date>`): 2026-09-08 07:50 -> 18:40 and 2026-09-11 09:50 -> 17:40
(day window +- 10 min, clipped to the session); the stamps T0750.../T0950... distinguish them from the night files (T2050...):
""" + "\n".join(f"- `{Path(p).parent.name}/{Path(p).name}`" for p in a1d) + "\n",
        "imu100": f"""# A3 cache - 100-Hz calibrated head-frame IMU (cohort 2026c)
{README_MARK}

`<SFxx>/night_<YYYYMMDD>.npz` written by `wiser/scripts/analyze_wiser_ins_fusion.py` (V4 Phase B, 2026-09-30) and
`<SFxx>/day_<YYYYMMDD>.npz` written by `wiser/scripts/analyze_imu_attitude_gate_v2.py --build-day-caches` (2026-10-01, git {git})
with the **same chain and the same keys** (decided by V4 on the tuning night; copied from the night file's `calib_json`):
A1 counts -> Hampel (half-window 3, 6 sigma, floor 2 counts) -> Butterworth-4 zero-phase 40 Hz (acc and gyro) -> resample_poly(2, 25)
-> head frame (make_imu.S); accelerometer ellipsoid a_cal = D (a - o) self-calibrated on the window's 0.5-s quasi-static windows;
gyro bias b = running median of the quiet-second gyro medians +- 300 s (>= 20); `gyr = 1.03 (w - b)`.

| key | dtype / shape | meaning |
|---|---|---|
| `t_unix_ms` | float64 (n,) | field-PC Unix ms on the IMU clock (tau* not applied); sample i = A1 frame 12.5 i |
| `acc` | float32 (n, 3) | calibrated specific force, head frame (x nose, y left, z up), m/s^2 |
| `gyr` | float32 (n, 3) | 1.03 (w - b), head frame, deg/s |
| `sat_acc`, `sat_gyr` | bool (n,) | raw saturation within the sample's support, dilated 5 samples |
| `frozen` | bool (n,) | hung chip |
| `spikes` | uint8 (n,) | Hampel-replaced raw samples in the support |
| `quiet` | bool (n,) | make_imu 1-s rule (median abs(w) < 10 deg/s, abs(k_a median abs(a) - g) < 0.05 g, not bad), 1-s grid from the array start |
| `calib_json`, `meta_json` | str | acc ellipsoid, bias method + 1-min bias nodes, scale, chain; animal, night/day key, role, session, source A1, writer |

Because the chain is identical, Phase 0's identity b = w_lp - gyr / 1.03 holds for the day files too (checked by the gate-v2 run).
**Day files** ({len(a3d)}, {sz(a3d) / 1e6:.0f} MB): """ + ", ".join(f"`{Path(p).parent.name}/{Path(p).name}`" for p in a3d) + "\n",
        "wiser_fix": f"""# A2 cache - deduplicated WISER fixes per animal (cohort 2026c)
{README_MARK}

`night_<YYYYMMDD>/<SFxx>.csv.gz` written by `wiser/scripts/build_imu_wiser_cache.py` (night +- 10 min) and `day_<YYYYMMDD>/<SFxx>.csv.gz`
written by the same function (`wiser_night`) from `wiser/scripts/analyze_imu_attitude_gate_v2.py --build-day-caches` (2026-10-01, git {git};
day window +- 10 min) from `wiser_working/3rdcohort_Spike_2026_3_4.sqlite` opened mode=ro (sha256 checked). Columns: reportid, shortid,
t_ms (Unix ms UTC, field-PC clock), x, y (in, WISER frame - unverified origin), anchors_used, anchors_list, n_list, dup_n, valid,
speed_inps_smooth, m_handling, m_silence, m_tag_validity, m_adc_lane (dedup: per (tag, timestamp) keep max anchors_used, ties -> min reportid).
Index: `index_2026c.csv` (nights), `index_day_2026c.csv` (days).
**Day files** ({len(a2d)}, {sz(a2d) / 1e6:.1f} MB): """ + ", ".join(f"`{Path(p).parent.name}/{Path(p).name}`" for p in a2d) + "\n",
    }
    for k, txt in texts.items():
        pth = roots[k] / "README.md"
        if pth.exists() and README_MARK not in pth.read_text(encoding="utf-8"):
            with open(pth, "a", encoding="utf-8") as f:
                f.write("\n\n" + txt)
        else:
            pth.write_text(txt, encoding="utf-8")


# ====================================================================================================== still windows
def detect_strict(acc: np.ndarray, omega_a3: np.ndarray, cand_sample: np.ndarray, cfg: dict, min_len_s: float | None = None) -> np.ndarray:
    """Strict still windows (sample indices [s, e)), plan 2.1."""
    st = cfg["strict"]
    bl = int(round(float(st["block_s"]) * FS100))
    nb = len(acc) // bl
    if nb == 0:
        return np.zeros((0, 2), np.int64)
    A = acc[:nb * bl].astype(np.float64).reshape(nb, bl, 3).mean(axis=1)
    U = A / np.linalg.norm(A, axis=1, keepdims=True)
    cand = cand_sample[:nb * bl].reshape(nb, bl).all(axis=1) & (omega_a3[:nb * bl].reshape(nb, bl).max(axis=1) < float(st["omega_max_dps"]))
    tol = float(st["mag_tol_g"])
    mb = int(round(float(min_len_s if min_len_s is not None else st["gate_min_len_s"]) / float(st["block_s"])))
    os_, oe_ = np.empty(nb, np.int64), np.empty(nb, np.int64)
    cnt = _strict_kernel(A, U, cand, math.cos(float(st["dir_max_deg"]) * D2R), G * (1 - tol), G * (1 + tol), mb, os_, oe_)
    return np.column_stack([os_[:cnt], oe_[:cnt]]) * bl


def quasi_static_phase0_rule(acc: np.ndarray, omega: np.ndarray, wlen: int = 50) -> np.ndarray:
    """V4/Phase-0 quasi-static 0.5-s window rule (median |w| < 10 deg/s, per-axis acc SD < 0.15 m/s^2) - selftest contrast."""
    nw = len(acc) // wlen
    W = np.median(omega[:nw * wlen].reshape(nw, wlen), axis=1)
    sd = acc[:nw * wlen].reshape(nw, wlen, 3).std(axis=1).max(axis=1)
    return (W < 10.0) & (sd < 0.15)


def wiser_support(t100: np.ndarray, win: np.ndarray, fx: pd.DataFrame | None, cfg: dict) -> pd.DataFrame:
    """Per window: WISER status (confirmed / contradicted / unavailable), bins, coverage, max deviation, centre (plan 2.2)."""
    wc = cfg["wiser"]
    n = len(win)
    res = {"wiser": np.full(n, "unavailable", dtype=object), "w_bins": np.zeros(n, int), "w_cov": np.zeros(n), "w_maxdev_in": np.full(n, np.nan),
           "w_x": np.full(n, np.nan), "w_y": np.full(n, np.nan)}
    if fx is None or len(fx) == 0 or n == 0:
        return pd.DataFrame(res)
    ok = fx["valid"].astype(bool) & ~fx["m_handling"].astype(bool) & ~fx["m_silence"].astype(bool) & ~fx["m_tag_validity"].astype(bool) & ~fx["m_adc_lane"].astype(bool)
    f = fx[ok]
    sec = (f["t_ms"].to_numpy(np.int64) // 1000)
    g = pd.DataFrame({"sec": sec, "x": f["x"].to_numpy(float), "y": f["y"].to_numpy(float)}).groupby("sec")[["x", "y"]].median()
    secs, X, Y = g.index.to_numpy(np.int64), g["x"].to_numpy(), g["y"].to_numpy()
    pad = float(wc["pad_s"]) * 1000
    for i, (s, e) in enumerate(win):
        lo, hi = t100[s] - pad, t100[e - 1] + 1000.0 / FS100 + pad
        k0, k1 = int(math.floor(lo / 1000)), int(math.ceil(hi / 1000))
        i0, i1 = np.searchsorted(secs, [k0, k1])
        nb = int(i1 - i0)
        cov = nb / max(k1 - k0, 1)
        res["w_bins"][i], res["w_cov"][i] = nb, cov
        if nb >= int(wc["min_bins"]) and cov >= float(wc["min_coverage"]):
            mx, my = float(np.median(X[i0:i1])), float(np.median(Y[i0:i1]))
            dev = float(np.max(np.hypot(X[i0:i1] - mx, Y[i0:i1] - my)))
            res["w_maxdev_in"][i], res["w_x"][i], res["w_y"][i] = dev, mx, my
            res["wiser"][i] = "confirmed" if dev <= float(wc["radius_in"]) else "contradicted"
    return pd.DataFrame(res)


# ====================================================================================================== period loading
def load_fixes(cfg: dict, pkey: str, animal: str) -> pd.DataFrame | None:
    p = Path(cfg["cache_roots"]["wiser_fix"]) / pkey / f"{animal}.csv.gz"
    return pd.read_csv(p) if p.exists() else None


def process_period(animal: str, pkey: str, cfg: dict, p0cfg: dict, ctx: dict, fh=None) -> dict:
    """Load A1/A3, run the Phase-0 gyro chain (with reconstruction), masks, strict still windows + WISER support."""
    t0 = time.time()
    tz = cfg["tz"]
    p = cfg["periods"][pkey]
    lo, hi = to_ms(p["start"], tz), to_ms(p["end"], tz)
    nt = P0.load_night(animal, pkey, p0cfg)
    with np.load(nt["a3_path"], allow_pickle=True) as z:
        sat_acc = z["sat_acc"].astype(bool)
    ch = P0.gyro_chain(nt, p0cfg, do_recon=True)
    t100 = nt["t100"]
    n = len(t100)
    s0 = float(cfg["gyro_fit"]["baseline_gyro_scale"])
    wb_a3 = nt["gyr_a3"] / s0
    bias_exact = ch["w100_norecon"] - wb_a3
    okm = ~(nt["sat_gyr100"] | nt["frozen100"])
    bias_node_err = float(np.nanmax(np.abs(bias_exact[okm] - nt["bias100"][okm]))) if okm.any() else np.nan
    wb = ch["w100"] - bias_exact
    # raw gyro saturation counted per 100-Hz sample (non-dilated): raw frame r belongs to sample floor(r / 12.5)
    sr = np.flatnonzero(ch["sat_gyr_raw"])
    satcnt = np.bincount(np.minimum((sr / 12.5).astype(np.int64), n - 1), minlength=n).astype(np.int32) if len(sr) else np.zeros(n, np.int32)
    inwin = (t100 >= lo) & (t100 < hi)
    hand = C.in_any(t100, ctx["handling"])
    ivu = ctx["imu_valid_until"].get(animal)
    imu_ok = (t100 < ivu) if ivu is not None else np.ones(n, bool)
    valid = inwin & ~nt["frozen100"] & ~hand & imu_ok
    acc = nt["acc100"]
    om_a3 = np.linalg.norm(nt["gyr_a3"], axis=1)
    cand = valid & ~sat_acc & ~nt["sat_gyr100"]
    win = detect_strict(acc, om_a3, cand, cfg, float(cfg["strict"]["gate_min_len_s"]))
    fx = load_fixes(cfg, pkey, animal)
    ws = wiser_support(t100, win, fx, cfg)
    cs_acc = np.vstack([np.zeros((1, 3)), np.cumsum(acc, axis=0)])
    gw = (cs_acc[win[:, 1]] - cs_acc[win[:, 0]]) if len(win) else np.zeros((0, 3))
    gnorm = np.linalg.norm(gw, axis=1, keepdims=True)
    W = pd.DataFrame({"animal": animal, "period": pkey, "role": p["role"], "kind": p["kind"], "s": win[:, 0], "e": win[:, 1],
                      "c": (win[:, 0] + win[:, 1]) // 2, "dur_s": (win[:, 1] - win[:, 0]) / FS100,
                      "t_start_ms": t100[win[:, 0]] if len(win) else np.zeros(0), "t_end_ms": t100[win[:, 1] - 1] + 10.0 if len(win) else np.zeros(0),
                      "acc_mag": (gnorm[:, 0] / np.maximum((win[:, 1] - win[:, 0]), 1)) if len(win) else np.zeros(0)})
    W = pd.concat([W, ws], axis=1)
    W["g_x"], W["g_y"], W["g_z"] = (gw / np.maximum(gnorm, 1e-12)).T if len(win) else (np.zeros(0),) * 3
    # in-window max block deviation (diagnostic)
    R = ch["sat_runs"]
    if len(R):
        R = R.assign(animal=animal, period=pkey, role=p["role"], kind=p["kind"])
        R = R[(R["t_unix_ms"] >= lo) & (R["t_unix_ms"] < hi)].reset_index(drop=True)
    nw = int((W["wiser"] != "contradicted").sum())
    log(f"{animal} {pkey}: n100 {n:,}, valid {valid.mean():.3f}, quiet(A3) {nt['quiet'][valid].mean() if valid.any() else float('nan'):.3f}, strict windows {len(W)} "
        f"(conf {int((W.wiser == 'confirmed').sum())} / contra {int((W.wiser == 'contradicted').sum())} / unavail {int((W.wiser == 'unavailable').sum())}), "
        f"kept {nw}, still time {W['dur_s'].sum() / 60:.1f} min, sat runs {len(R)}, bias-node err max {bias_node_err:.2e}, {time.time() - t0:.1f} s", fh)
    return {"animal": animal, "period": pkey, "role": p["role"], "kind": p["kind"], "lo": lo, "hi": hi, "t100": t100,
            "acc": acc.astype(np.float32), "wb": wb.astype(np.float32), "wb_a3": wb_a3.astype(np.float32), "w_pre": ch["w100_norecon"].astype(np.float32),
            "quiet": nt["quiet"], "valid": valid, "satcnt": satcnt, "W": W, "sat_runs": R, "bias_node_err": bias_node_err,
            "a1_path": str(nt["a1_path"]), "a3_path": str(nt["a3_path"]), "a1_bytes": nt["a1_bytes"], "a3_bytes": nt["a3_bytes"],
            "n100": n, "valid_frac": float(valid.mean())}


def window_set(P: dict, variant: str) -> pd.DataFrame:
    """Windows used by a variant: L1.0 / L2.0 drop WISER-contradicted windows; L1.0_nf keeps them."""
    W = P["W"]
    if variant == "L1.0_nf":
        return W
    W = W[W["wiser"] != "contradicted"]
    if variant == "L2.0":
        W = W[W["dur_s"] >= 2.0 - 1e-9]
    return W


# ====================================================================================================== bouts
def make_bouts(P: dict, variant: str, cfg: dict) -> tuple[pd.DataFrame, dict]:
    """Consecutive windows -> bout table + arrays (plan 2.4)."""
    W = window_set(P, variant).reset_index(drop=True)
    if len(W) < 2:
        return pd.DataFrame(), {}
    s, e, c = W["s"].to_numpy(), W["e"].to_numpy(), W["c"].to_numpy()
    g = W[["g_x", "g_y", "g_z"]].to_numpy()
    bad_cs = np.r_[0, np.cumsum(~P["valid"])]
    nq_cs = np.r_[0, np.cumsum(~P["quiet"])]
    sat_cs = np.r_[0, np.cumsum(P["satcnt"])]
    s0, e0, c0, s1, e1, c1 = s[:-1], e[:-1], c[:-1], s[1:], e[1:], c[1:]
    T_in, T_cc = (s1 - e0) / FS100, (c1 - c0) / FS100
    okspan = (bad_cs[c1] - bad_cs[c0]) == 0
    bc = cfg["bouts"]
    keep = okspan & (T_in >= float(bc["min_s"])) & (T_in <= float(bc["max_s"]))
    idx = np.flatnonzero(keep)
    t100 = P["t100"]
    bt = pd.DataFrame({"animal": P["animal"], "period": P["period"], "role": P["role"], "kind": P["kind"], "variant": variant,
                       "w0": W.index.to_numpy()[idx], "s0": s0[idx], "e0": e0[idx], "c0": c0[idx], "s1": s1[idx], "e1": e1[idx], "c1": c1[idx],
                       "T_in": T_in[idx], "T_cc": T_cc[idx], "active": ((nq_cs[s1] - nq_cs[e0]) > 0)[idx],
                       "t_act": ((nq_cs[c1] - nq_cs[c0]) / FS100)[idx], "n_sat_raw": (sat_cs[c1] - sat_cs[c0])[idx],
                       "t0_rel_s": ((t100[c0] - P["lo"]) / 1000.0)[idx], "t0_ms": t100[c0][idx], "t1_ms": t100[c1][idx],
                       "dur0_s": ((e0 - s0) / FS100)[idx], "dur1_s": ((e1 - s1) / FS100)[idx],
                       "wiser0": W["wiser"].to_numpy()[:-1][idx], "wiser1": W["wiser"].to_numpy()[1:][idx]})
    bt["sat"] = bt["n_sat_raw"] > 0
    bt["dbin"] = P0.bin_label(bt["T_in"].to_numpy(), {"bouts": bc}).astype(str)
    arr = {"cc": np.column_stack([c0[idx], c1[idx]]).astype(np.int64), "edge": np.column_stack([e0[idx], s1[idx]]).astype(np.int64),
           "gs": g[:-1][idx], "ge": g[1:][idx]}
    return bt, arr


def boutset(P: dict, arr: dict, kind: str = "cc", stream: str = "wb") -> P0.BoutSet:
    return P0.BoutSet(P[stream].astype(np.float64), None, arr[kind], arr["gs"], arr["ge"])


def concat_bs(L: list) -> P0.BoutSet:
    o = P0.BoutSet.__new__(P0.BoutSet)
    L = [b for b in L if b.n > 0]
    if not L:
        o.bouts, o.n, o.offs, o.wb, o.acc, o.gs, o.ge = np.zeros((0, 2), np.int64), 0, np.zeros(1, np.int64), np.zeros((0, 3)), None, np.zeros((0, 3)), np.zeros((0, 3))
        return o
    o.bouts = np.concatenate([b.bouts for b in L])
    o.n = int(sum(b.n for b in L))
    o.offs = np.r_[0, np.cumsum(np.concatenate([np.diff(b.offs) for b in L]))].astype(np.int64)
    o.wb = np.concatenate([b.wb for b in L])
    o.acc = None
    o.gs = np.concatenate([b.gs for b in L])
    o.ge = np.concatenate([b.ge for b in L])
    return o


# ====================================================================================================== 2.5 model choice
def fit_stage(tun: dict, bouts: dict, cfg: dict, p0cfg: dict, fh=None) -> dict:
    """Per animal: tuning night + day active no-sat bouts (2 <= T_in <= 15 s, L1.0); 2-fold CV of the registered models;
    pooled selection; full fits; bootstrap of the selected model."""
    gf = cfg["gyro_fit"]
    lo, hi = gf["fit_bout_range_s"]
    models = list(gf["models"])
    cv_err = {m: [] for m in models}
    fits, rows, sets = {}, [], {}
    for animal in cfg["_animals"]:
        bsl, folds = [], []
        for pk, P in tun.items():
            if P["animal"] != animal:
                continue
            bt, arr = bouts[(P["period"], animal, "L1.0")]
            if len(bt) == 0:
                continue
            m = (bt["active"] & ~bt["sat"] & (bt["T_in"] >= lo) & (bt["T_in"] <= hi)).to_numpy()
            if not m.any():
                continue
            bsl.append(boutset(P, arr).take(np.flatnonzero(m)))
            folds.append((np.floor(bt["t0_rel_s"].to_numpy()[m] / float(gf["cv_block_s"])).astype(int) % 2))
        bs = concat_bs(bsl)
        fo = np.concatenate(folds) if folds else np.zeros(0, int)
        sets[animal] = (bs, fo)
        fits[animal] = {}
        can_cv = bs.n > 0 and all((fo != f).sum() >= int(gf["cv_min_train"]) and (fo == f).sum() > 0 for f in (0, 1))
        for m in models:
            held = np.full(bs.n, np.nan)
            if can_cv:
                for f in (0, 1):
                    tr, te = np.flatnonzero(fo != f), np.flatnonzero(fo == f)
                    r = P0.fit_model(m, bs.take(tr), p0cfg)
                    held[te] = P0.bout_errors(bs.take(te), r["M"], r["c"], p0cfg, r["K"])[0]
            cv_err[m].append(held)
            full = P0.fit_model(m, bs, p0cfg) if bs.n >= 5 else {"model": m, "theta": P0.theta0(m, p0cfg), "M": np.eye(3), "c": 0.0, "K": None, "cost": np.nan, "nfev": 0, "ok": False, "n_bouts": bs.n}
            full["cv_median"] = float(np.nanmedian(held)) if np.isfinite(held).any() else np.nan
            full["train_median"] = float(np.median(P0.bout_errors(bs, full["M"], full["c"], p0cfg, full["K"])[0])) if bs.n else np.nan
            fits[animal][m] = full
            rows.append({"animal": animal, "model": m, "n_fit_bouts": bs.n, "cv": bool(can_cv), "cv_median_deg": full["cv_median"],
                         "train_median_deg": full["train_median"], "cost": full["cost"], "nfev": full["nfev"], "ok": full["ok"]})
        base = P0.bout_errors(bs, float(gf["baseline_gyro_scale"]) * np.eye(3), 0.0, p0cfg)[0] if bs.n else np.zeros(0)
        rows.append({"animal": animal, "model": "baseline_1.03", "n_fit_bouts": bs.n, "cv": bool(can_cv), "cv_median_deg": float(np.median(base)) if len(base) else np.nan,
                     "train_median_deg": float(np.median(base)) if len(base) else np.nan, "cost": np.nan, "nfev": 0, "ok": True})
        log(f"  fit {animal}: n={bs.n} (folds {np.bincount(fo, minlength=2).tolist() if len(fo) else [0, 0]}, cv {can_cv})  "
            + "  ".join(f"{m}: cv {fits[animal][m]['cv_median']:.3f} / train {fits[animal][m]['train_median']:.3f}" for m in models)
            + (f"  baseline {np.median(base):.3f}" if len(base) else ""), fh)
    pooled = {m: float(np.nanmedian(np.concatenate(cv_err[m]))) if np.isfinite(np.concatenate(cv_err[m])).any() else np.nan for m in models}
    best = min(models, key=lambda m: (pooled[m] if np.isfinite(pooled[m]) else 1e9))
    cands = [m for m in models if np.isfinite(pooled[m]) and pooled[m] <= pooled[best] + float(gf["cv_tie_deg"])]
    selected = min(cands, key=lambda m: P0.N_PARAMS[m]) if cands else "scalar"
    log(f"  pooled CV medians: {pooled} -> selected {selected}", fh)
    boot = {}
    pb = {**p0cfg, "gyro_fit": {**p0cfg["gyro_fit"], "n_bootstrap": int(gf["n_bootstrap"])}}
    for animal in cfg["_animals"]:
        bs, _ = sets[animal]
        if bs.n < 10:
            boot[animal] = {"theta": np.zeros((0, P0.N_PARAMS[selected])), "lo": np.full(P0.N_PARAMS[selected], np.nan), "hi": np.full(P0.N_PARAMS[selected], np.nan)}
            continue
        tb = time.time()
        th = P0.bootstrap_fit(selected, bs, pb, fits[animal][selected]["theta"])
        boot[animal] = {"theta": th, "lo": np.percentile(th, 2.5, axis=0), "hi": np.percentile(th, 97.5, axis=0)}
        log(f"  bootstrap {animal} ({selected}, {len(th)} draws): {time.time() - tb:.0f} s", fh)
    return {"fits": fits, "pooled_cv": pooled, "selected": selected, "boot": boot, "cv_table": pd.DataFrame(rows),
            "n_fit": {a: int(sets[a][0].n) for a in sets}}


def eval_bouts(P: dict, bt: pd.DataFrame, arr: dict, fits_a: dict, selected: str, cfg: dict, p0cfg: dict) -> pd.DataFrame:
    """Every model's centre-to-centre error, the clipped-stream treatment, the edge-style error, rotation stats."""
    if len(bt) == 0:
        return bt
    bt = bt.copy()
    bs = boutset(P, arr, "cc", "wb")
    s0 = float(cfg["gyro_fit"]["baseline_gyro_scale"])
    bt["e_baseline"] = P0.bout_errors(boutset(P, arr, "cc", "wb_a3"), s0 * np.eye(3), 0.0, p0cfg)[0]
    for m, r in fits_a.items():
        bt[f"e_{m}"] = P0.bout_errors(bs, r["M"], r["c"], p0cfg, r.get("K"))[0]
    r = fits_a[selected]
    e, ev = P0.bout_errors(bs, r["M"], r["c"], p0cfg)
    bt["e_cc"] = e
    bt["ex"], bt["ey"], bt["ez"] = ev[:, 0], ev[:, 1], ev[:, 2]
    bt["e_cc_clipped"] = P0.bout_errors(boutset(P, arr, "cc", "wb_a3"), r["M"], r["c"], p0cfg)[0]
    bt["e_edge"] = P0.bout_errors(boutset(P, arr, "edge", "wb"), r["M"], r["c"], p0cfg)[0]
    st = np.empty((bs.n, 3))
    accbs = P0.BoutSet(P["wb"].astype(np.float64), P["acc"].astype(np.float64), arr["cc"], arr["gs"], arr["ge"])
    P0.bout_stats(accbs.gs, P0.apply_model(accbs.wb, r["M"], r["c"], p0cfg), accbs.acc, accbs.offs, DT, st)
    bt["rot_deg"], bt["mean_ah"], bt["wmax_dps"] = st[:, 0], st[:, 1], st[:, 2]
    wv = P0.apply_model(P["wb"].astype(np.float64), r["M"], r["c"], p0cfg) * R2D * DT
    cs = np.r_[0, np.cumsum(np.linalg.norm(wv, axis=1))]
    bt["inwin_rot_deg"] = (cs[bt["e0"]] - cs[bt["c0"]]) + (cs[bt["c1"]] - cs[bt["s1"]])
    cv = np.vstack([np.zeros((1, 3)), np.cumsum(wv, axis=0)])
    bt["inwin_net_deg"] = np.linalg.norm(cv[bt["e0"]] - cv[bt["c0"]], axis=1) + np.linalg.norm(cv[bt["c1"]] - cv[bt["s1"]], axis=1)
    return bt


# ====================================================================================================== 2.3 floor
def floor_rows(P: dict, M_sel: dict, cfg: dict, p0cfg: dict, variant: str = "L1.0") -> pd.DataFrame:
    fc = cfg["floor"]
    W = window_set(P, variant)
    W = W[W["dur_s"] >= float(fc["min_window_s"])]
    acc = P["acc"].astype(np.float64)
    cs = np.vstack([np.zeros((1, 3)), np.cumsum(acc, axis=0)])
    w_rad = P0.apply_model(P["wb"].astype(np.float64), M_sel["M"], M_sel["c"], p0cfg)
    rows = []
    for s, e, wst in zip(W["s"].to_numpy(), W["e"].to_numpy(), W["wiser"].to_numpy()):
        mid = (s + e) // 2
        rec = {"animal": P["animal"], "period": P["period"], "role": P["role"], "kind": P["kind"], "dur_s": (e - s) / FS100, "wiser": wst}
        for L in fc["L_s"]:
            k = int(round(L * FS100))
            rec[f"phi_{L:g}"] = float(P0.angle_deg(cs[mid] - cs[mid - k], cs[mid + k] - cs[mid])) if (mid - k >= s and mid + k <= e) else np.nan
        g1, g2 = cs[mid] - cs[s], cs[e] - cs[mid]
        rec["phi_half"] = float(P0.angle_deg(g1, g2))
        c1, c2 = (s + mid) // 2, (mid + e) // 2
        out = np.empty((1, 3))
        g1n = g1 / np.linalg.norm(g1)
        P0.propagate_bouts(g1n[None, :], w_rad[c1:c2], np.array([0, c2 - c1], np.int64), DT, out)
        rec["phi_half_prop"] = float(P0.angle_deg(out[0], g2))
        rows.append(rec)
    return pd.DataFrame(rows)


# ====================================================================================================== 2.6 gate
def gate_set(bt: pd.DataFrame, variant: str = "L1.0", role: str = "test") -> pd.DataFrame:
    return bt[(bt["role"] == role) & (bt["variant"] == variant) & bt["active"] & ~bt["sat"]]


def evaluate_gate(g: pd.DataFrame, floor_med: float, cfg: dict, col: str = "e_cc", seed: int | None = None) -> dict:
    gc = cfg["gate"]
    rng = np.random.default_rng(int(gc["seed"]) if seed is None else seed)
    res = {"bins": {}, "animals": {}, "floor_median_deg": floor_med, "n_bouts": int(len(g)), "col": col}
    all_pass = True
    for lab, thr in gc["bins"].items():
        e = g.loc[g["dbin"] == lab, col].to_numpy()
        med = float(np.median(e)) if len(e) else np.nan
        bs = np.array([np.median(rng.choice(e, len(e))) for _ in range(int(gc["n_boot"]))]) if len(e) > 5 else np.array([np.nan])
        res["bins"][lab] = {"threshold_deg": thr, "pooled_median_deg": med, "ci95": [float(np.nanpercentile(bs, 2.5)), float(np.nanpercentile(bs, 97.5))],
                            "n": int(len(e)), "pooled_pass": bool(med <= thr) if len(e) else False,
                            "p90_deg": float(np.percentile(e, 90)) if len(e) else np.nan,
                            "excess_over_floor_deg": med - floor_med if len(e) else np.nan,
                            "at_limit": bool((med - floor_med) < float(gc["floor_excess_deg"])) if len(e) else False}
        all_pass &= res["bins"][lab]["pooled_pass"]
    n_ind = 0
    for a in cfg["_animals"]:
        ga = g[g["animal"] == a]
        ok, rec = True, {}
        for lab, thr in gc["bins"].items():
            e = ga.loc[ga["dbin"] == lab, col].to_numpy()
            med = float(np.median(e)) if len(e) else np.nan
            rec[lab] = {"median_deg": med, "n": int(len(e)), "pass": bool(med <= thr) if len(e) else False}
            ok &= rec[lab]["pass"]
        rec["pass_both"] = bool(ok)
        n_ind += int(ok)
        res["animals"][a] = rec
    res["n_animals_pass"] = n_ind
    res["verdict"] = "PASS" if (all_pass and n_ind >= int(gc["min_animals_pass"])) else "FAIL"
    return res


# ====================================================================================================== 2.7 chains
def thin_anchors(c: np.ndarray, min_gap: int) -> np.ndarray:
    keep, last = [], -10**12
    for i, ci in enumerate(c):
        if ci - last >= min_gap:
            keep.append(i)
            last = ci
    return np.asarray(keep, np.int64)


def next_true(m: np.ndarray) -> np.ndarray:
    """nxt[k] = smallest index >= k with m True (len(m) if none); length len(m) + 1."""
    n = len(m)
    idx = np.where(m, np.arange(n), n)
    return np.r_[np.minimum.accumulate(idx[::-1])[::-1], n]


def chain_records(P: dict, M_sel: dict, cfg: dict, p0cfg: dict, stop_at_sat: bool = True, anchor_min_dur_s: float | None = None,
                  zaru: bool = False) -> pd.DataFrame:
    """Chained-anchor records (plan 2.7). Exploratory (amendment 2): anchor_min_dur_s restricts anchors to windows at least
    that long; zaru=True subtracts the anchor window's own mean calibrated gyro (a zero-rate bias update) for the chain."""
    cc = cfg["chains"]
    W = window_set(P, "L1.0").reset_index(drop=True)
    if len(W) < 2:
        return pd.DataFrame()
    c = W["c"].to_numpy(np.int64)
    g = W[["g_x", "g_y", "g_z"]].to_numpy(np.float64)
    if anchor_min_dur_s is None:
        anc = thin_anchors(c, int(round(float(cc["anchor_min_spacing_s"]) * FS100)))
    else:
        long_ = np.flatnonzero(W["dur_s"].to_numpy() >= anchor_min_dur_s)
        anc = long_[thin_anchors(c[long_], int(round(float(cc["anchor_min_spacing_s"]) * FS100)))] if len(long_) else np.zeros(0, np.int64)
    n = len(P["t100"])
    nb = next_true(~P["valid"])
    ns = next_true(P["satcnt"] > 0) if stop_at_sat else np.full(n + 1, n, np.int64)
    maxk = int(round(float(cc["max_s"]) * FS100))
    a_list, t_list = [], []
    for ia in anc:
        ca = c[ia]
        end = min(ca + maxk, nb[ca], ns[ca], n)
        j1 = int(np.searchsorted(c, end, side="right"))
        tj = np.arange(ia + 1, j1)
        if len(tj):
            a_list.append(ia)
            t_list.append(tj)
    if not a_list:
        return pd.DataFrame()
    a_idx = np.asarray(a_list, np.int64)
    t_off = np.r_[0, np.cumsum([len(t) for t in t_list])].astype(np.int64)
    tj = np.concatenate(t_list)
    w_rad = P0.apply_model(P["wb"].astype(np.float64), M_sel["M"], M_sel["c"], p0cfg)
    q0 = np.stack([P0.q_from_up(g[i]) for i in a_idx])
    a_bias = np.zeros((len(a_idx), 3))
    if zaru:
        sA, eA = W["s"].to_numpy(np.int64)[a_idx], W["e"].to_numpy(np.int64)[a_idx]
        cw = np.vstack([np.zeros((1, 3)), np.cumsum(w_rad, axis=0)])
        a_bias = (cw[eA] - cw[sA]) / (eA - sA)[:, None]
    phi = np.empty((len(tj), 2))
    th = np.empty(len(tj))
    _chains_kernel(w_rad, a_bias, q0, c[a_idx], t_off, c[tj], g[tj], DT, phi, th)
    nq_cs = np.r_[0, np.cumsum(~P["quiet"])]
    sat_cs = np.r_[0, np.cumsum(P["satcnt"])]
    ca_rep = np.repeat(c[a_idx], np.diff(t_off))
    ct = c[tj]
    t100 = P["t100"]
    R = pd.DataFrame({"animal": P["animal"], "period": P["period"], "role": P["role"], "kind": P["kind"],
                      "anchor": np.repeat(a_idx, np.diff(t_off)), "target": tj, "anchor_t_ms": t100[ca_rep],
                      "anchor_rel_s": (t100[ca_rep] - P["lo"]) / 1000.0, "t": (ct - ca_rep) / FS100,
                      "t_act": (nq_cs[ct] - nq_cs[ca_rep]) / FS100, "theta_deg": th * R2D,
                      "phi_x": phi[:, 0] * R2D, "phi_y": phi[:, 1] * R2D, "n_sat_raw": sat_cs[ct] - sat_cs[ca_rep]})
    R["e"] = np.hypot(R["phi_x"], R["phi_y"])
    R["t_still"] = R["t"] - R["t_act"]
    R["chain"] = R["animal"] + "|" + R["period"] + "|" + R["anchor"].astype(str)
    R["zaru"] = bool(zaru)
    if zaru:
        R["anchor_bias_dpm"] = np.repeat(np.linalg.norm(a_bias, axis=1) * R2D * 60.0, np.diff(t_off))
    return R


CHAIN_SPECS = {
    # name: additive terms on top of s0^2; ("p", driver, "sq") = (p * X)^2, ("p", driver, "lin") = p * X;
    # drivers: t = time since anchor (s), ta = active time (s), TH = accumulated rotation (deg)
    "L_t": [("b", "t", "sq")],
    "RW_t": [("q", "t", "lin")],
    "R": [("c", "TH", "sq")],
    "LR_t": [("b", "t", "sq"), ("c", "TH", "sq")],
    "L_a": [("b", "ta", "sq")],
    "RW_a": [("q", "ta", "lin")],
    "LR_a": [("b", "ta", "sq"), ("c", "TH", "sq")],
    "RWR": [("qth", "TH", "lin")],
    "RW_t+R": [("q", "t", "lin"), ("c", "TH", "sq")],
}
CHAIN_START = {"s0": 0.3, "b": 0.01, "q": 0.01, "c": 0.005, "qth": 0.005}


def chain_param_names(name: str) -> list:
    return ["s0"] + [p for p, _, _ in CHAIN_SPECS[name]]


def chain_var(name: str, params: dict, t, ta, TH) -> np.ndarray:
    X = {"t": np.asarray(t, float), "ta": np.asarray(ta, float), "TH": np.asarray(TH, float)}
    v = np.full(len(X["t"]), params["s0"] ** 2)
    for p, d, kind in CHAIN_SPECS[name]:
        v = v + ((params[p] * X[d]) ** 2 if kind == "sq" else params[p] * X[d])
    return v


def rayleigh_ll(e: np.ndarray, var: np.ndarray) -> np.ndarray:
    """Per-record log-likelihood of the 2-D tilt-error magnitude under an isotropic Gaussian with per-axis variance var."""
    e = np.maximum(e, 1e-6)
    return np.log(e) - np.log(var) - e * e / (2.0 * var)


def fit_chain_model(name: str, R: pd.DataFrame) -> dict:
    """Maximum likelihood (Rayleigh) on log-parameters, analytic gradient, L-BFGS-B from three starts."""
    names = chain_param_names(name)
    X = {"t": R["t"].to_numpy(float), "ta": R["t_act"].to_numpy(float), "TH": R["theta_deg"].to_numpy(float)}
    e = np.maximum(R["e"].to_numpy(float), 1e-6)
    e2 = e * e
    terms = CHAIN_SPECS[name]
    n = len(e)

    def fg(lx):
        p = np.exp(lx)
        v = np.full(n, p[0] ** 2)
        dv = [2.0 * p[0] ** 2 * np.ones(n)]                    # dv/dlog(s0)
        for j, (_, d, kind) in enumerate(terms, start=1):
            if kind == "sq":
                c_ = (p[j] * X[d]) ** 2
                v = v + c_
                dv.append(2.0 * c_)
            else:
                c_ = p[j] * X[d]
                v = v + c_
                dv.append(c_)
        v = np.maximum(v, 1e-12)
        nll = float(np.mean(np.log(v) + e2 / (2.0 * v)))        # constant -ln e dropped (added back below)
        w_ = (1.0 / v - e2 / (2.0 * v * v))
        g = np.array([float(np.mean(w_ * d_)) for d_ in dv])
        return nll, g
    x0 = np.log([CHAIN_START[k] for k in names])
    best = None
    for start in (x0, x0 + 1.5, x0 - 1.5):
        r = minimize(fg, start, jac=True, method="L-BFGS-B", bounds=[(-14.0, 6.0)] * len(names), options={"maxiter": 500, "ftol": 1e-12, "gtol": 1e-9})
        if best is None or r.fun < best.fun:
            best = r
    p = np.exp(best.x)
    nll_mean = float(best.fun - np.mean(np.log(e)))
    return {"model": name, "params": dict(zip(names, p.tolist())), "nll_mean": nll_mean, "n": int(n), "k": len(names),
            "aic": float(2 * len(names) + 2 * nll_mean * n), "ok": bool(best.success)}


def chain_ll(name: str, params: dict, R: pd.DataFrame) -> np.ndarray:
    return rayleigh_ll(R["e"].to_numpy(float), chain_var(name, params, R["t"], R["t_act"], R["theta_deg"]))


def block_ids(R: pd.DataFrame, block_s: float) -> np.ndarray:
    key = R["animal"] + "|" + R["period"] + "|" + (R["anchor_rel_s"] // block_s).astype(int).astype(str)
    return pd.factorize(key)[0]


def linearity(tun_R: pd.DataFrame, test_R: pd.DataFrame, cfg: dict, label: str, fh=None, per_animal: bool = False) -> dict:
    """Fit every chain model on the tuning records, held-out test LL, AIC, block-bootstrap CIs of test LL differences."""
    cc = cfg["chains"]
    names = list(cc["models"]) + list(cc["exploratory_models"])
    res = {"label": label, "n_tuning": int(len(tun_R)), "n_test": int(len(test_R)), "fits": {}, "test_ll": {}}
    if len(tun_R) < 30 or len(test_R) < 30:
        return res
    blk = block_ids(test_R, float(cc["boot_block_s"]))
    nb = blk.max() + 1
    cnt_blk = np.bincount(blk, minlength=nb).astype(float)
    rng = np.random.default_rng(int(cc["seed"]))
    W = rng.multinomial(nb, np.full(nb, 1.0 / nb), size=int(cc["n_boot"])).astype(float)
    ll_blk = {}
    for m in names:
        fit = fit_chain_model(m, tun_R)
        ll = chain_ll(m, fit["params"], test_R)
        res["fits"][m] = fit
        res["test_ll"][m] = float(np.mean(ll))
        ll_blk[m] = np.bincount(blk, weights=ll, minlength=nb)
    reg = list(cc["models"])
    order = sorted(reg, key=lambda m: -res["test_ll"][m])
    res["best_registered"] = order[0]
    res["order_registered"] = order

    def dll(a, b):
        d = (W @ (ll_blk[a] - ll_blk[b])) / (W @ cnt_blk)
        return {"diff": res["test_ll"][a] - res["test_ll"][b], "ci95": [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]}
    res["contrasts"] = {"L_t-RW_t": dll("L_t", "RW_t"), "L_a-RW_a": dll("L_a", "RW_a"), "LR_t-RW_t": dll("LR_t", "RW_t"),
                        "LR_a-RW_a": dll("LR_a", "RW_a"), "best-second": dll(order[0], order[1]), "R-L_t": dll("R", "L_t"),
                        "L_a-L_t": dll("L_a", "L_t"), "R-L_a": dll("R", "L_a"), "LR_t-R": dll("LR_t", "R"), "LR_a-R": dll("LR_a", "R")}
    for m in ("LR_t", "LR_a", "RW_t+R"):
        p = res["fits"][m]["params"]
        var = chain_var(m, p, test_R["t"], test_R["t_act"], test_R["theta_deg"]) - p["s0"] ** 2
        rot = (p["c"] * test_R["theta_deg"].to_numpy(float)) ** 2
        res[f"rot_share_{m}"] = float(np.median(rot / np.maximum(var, 1e-12)))
    log(f"  linearity [{label}] tuning n={len(tun_R):,}, test n={len(test_R):,}: test LL " + ", ".join(f"{m} {res['test_ll'][m]:.4f}" for m in names)
        + f"; best registered {order[0]}; L_t-RW_t {res['contrasts']['L_t-RW_t']['diff']:+.4f} {np.round(res['contrasts']['L_t-RW_t']['ci95'], 4).tolist()}", fh)
    return res


def _sig(con: dict, key: str) -> int:
    """+1 / -1 when the block-bootstrap CI of the test-LL difference excludes 0, else 0."""
    lo, hi = con[key]["ci95"]
    return 1 if lo > 0 else (-1 if hi < 0 else 0)


def linearity_verdict(lin: dict, inc: dict) -> str:
    """Amendment 1 (plan, before any real-data run): two separate statements, each requiring CI-separated contrasts.
    SHAPE  linear vs random walk: L_t vs RW_t (clock time) and L_a vs RW_a (active time).
    DRIVER among the linear-shape models L_t (clock time = a bias that also acts while still), L_a (active time), R (rotation):
           a driver is named only if it beats both others with CIs excluding 0; otherwise 'not separable'.
    'linear in time (bias-like)' = SHAPE linear in clock time AND DRIVER = L_t AND increments consistent (median C_inc > null)."""
    if not lin.get("fits"):
        return "not resolved (too few records)"
    con = lin["contrasts"]
    st, sa = _sig(con, "L_t-RW_t"), _sig(con, "L_a-RW_a")
    shape = {1: "linear", -1: "random-walk (sqrt)", 0: "unresolved"}
    sh = f"shape in clock time: {shape[st]} (L_t-RW_t {con['L_t-RW_t']['diff']:+.4f}); in active time: {shape[sa]} (L_a-RW_a {con['L_a-RW_a']['diff']:+.4f})"
    d_at, d_rt, d_ra = _sig(con, "L_a-L_t"), _sig(con, "R-L_t"), _sig(con, "R-L_a")
    if d_rt == 1 and d_ra == 1:
        drv = "rotation (R beats L_t and L_a)"
    elif d_at == 1 and d_ra == -1:
        drv = "active time (L_a beats L_t and R)"
    elif d_at == -1 and d_rt == -1:
        drv = "clock time (L_t beats L_a and R)"
    else:
        drv = f"not separable (L_a-L_t {con['L_a-L_t']['diff']:+.4f}, R-L_t {con['R-L_t']['diff']:+.4f}, R-L_a {con['R-L_a']['diff']:+.4f})"
    c_ok = inc.get("median_C", np.nan) > inc.get("median_null", np.nan)
    cons = f"increments C_inc {inc.get('median_C', np.nan):.2f} vs null {inc.get('median_null', np.nan):.2f}"
    head = "LINEAR IN TIME (bias-like)" if (st == 1 and drv.startswith("clock") and c_ok) else \
        ("RANDOM-WALK-LIKE" if (st == -1 and sa <= 0) or (sa == -1 and st <= 0) else
         ("LINEAR, driven by " + drv.split(" (")[0] if (drv.startswith(("rotation", "active")) and (st == 1 or sa == 1)) else "NOT RESOLVED"))
    return f"{head}; {sh}; driver: {drv}; best registered {lin['best_registered']}; {cons}"


def increment_consistency(R: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, dict]:
    """Per chain: increments of the tilt-error vector between records >= inc_min_spacing_s apart (origin = the anchor, phi = 0)."""
    cc = cfg["chains"]
    rng = np.random.default_rng(int(cc["seed"]) + 5)
    rows = []
    sp = float(cc["inc_min_spacing_s"])
    for ch, g in R.sort_values(["chain", "t"]).groupby("chain", sort=False):
        t = g["t"].to_numpy()
        sel, last = [], 0.0
        for i, ti in enumerate(t):
            if ti - last >= sp:
                sel.append(i)
                last = ti
        if len(sel) < int(cc["inc_min_n"]):
            continue
        ph = np.vstack([[0.0, 0.0], g[["phi_x", "phi_y"]].to_numpy()[sel]])
        d = np.diff(ph, axis=0)
        mag = np.linalg.norm(d, axis=1)
        if mag.sum() <= 0:
            continue
        Cv = float(np.linalg.norm(d.sum(axis=0)) / mag.sum())
        ang = rng.uniform(0, 2 * np.pi, (int(cc["n_null"]), len(mag)))
        nul = np.hypot((mag * np.cos(ang)).sum(axis=1), (mag * np.sin(ang)).sum(axis=1)) / mag.sum()
        u = ph[1:] / np.maximum(np.linalg.norm(ph[1:], axis=1, keepdims=True), 1e-12)
        rows.append({"chain": ch, "animal": g["animal"].iloc[0], "period": g["period"].iloc[0], "role": g["role"].iloc[0], "kind": g["kind"].iloc[0],
                     "n_inc": len(mag), "t_last": float(t[sel[-1]]), "t_act_last": float(g["t_act"].to_numpy()[sel[-1]]), "e_last": float(np.linalg.norm(ph[-1])),
                     "C_inc": Cv, "null_mean": float(nul.mean()), "null_p95": float(np.percentile(nul, 95)),
                     "C_cum": float(np.linalg.norm(u.mean(axis=0)))})
    T = pd.DataFrame(rows)
    if len(T) == 0:
        return T, {"n_chains": 0}
    summ = {"n_chains": int(len(T)), "median_C": float(T["C_inc"].median()), "median_null": float(T["null_mean"].median()),
            "frac_above_null_p95": float((T["C_inc"] > T["null_p95"]).mean()), "median_C_cum": float(T["C_cum"].median())}
    for k, gk in T.groupby("kind"):
        summ[f"{k}_median_C"] = float(gk["C_inc"].median())
        summ[f"{k}_median_null"] = float(gk["null_mean"].median())
        summ[f"{k}_frac_above_null_p95"] = float((gk["C_inc"] > gk["null_p95"]).mean())
        summ[f"{k}_n"] = int(len(gk))
    return T, summ


def bias_residuals(P: dict, M_sel: dict, cfg: dict, p0cfg: dict) -> pd.DataFrame:
    """Mean calibrated gyro over long strict windows: in-sample (A3 bias) and leave-window-out bias (deg/min)."""
    cc = cfg["chains"]
    W = window_set(P, "L1.0")
    W = W[W["dur_s"] >= float(cc["bias_min_window_s"])]
    if len(W) == 0:
        return pd.DataFrame()
    n = len(P["t100"])
    nsec = n // 100
    qsec = P["quiet"][: nsec * 100: 100]
    wq_all = np.median(P["w_pre"][: nsec * 100].astype(np.float64).reshape(nsec, 100, 3), axis=1)
    tq_all = np.arange(nsec) + 0.5
    qi = np.flatnonzero(qsec)
    tq, wq = tq_all[qi], wq_all[qi]
    Mx, cpar = M_sel["M"], M_sel["c"]
    h, mn = float(cc["bias_loo_half_s"]), int(cc["bias_loo_min_n"])
    rows = []
    for _, w in W.iterrows():
        s, e = int(w["s"]), int(w["e"])
        g = np.array([w["g_x"], w["g_y"], w["g_z"]])
        r_in = P0.apply_model(P["wb"][s:e].astype(np.float64).mean(axis=0)[None, :], Mx, cpar, p0cfg)[0] * R2D * 60.0
        tc = 0.5 * (s + e) / FS100
        excl = (tq + 0.5 > s / FS100) & (tq - 0.5 < e / FS100)
        b = None
        for hh in (h, 3 * h, 1e12):
            m = (np.abs(tq - tc) <= hh) & ~excl
            if m.sum() >= mn or hh > 1e11:
                b = np.median(wq[m], axis=0) if m.any() else np.zeros(3)
                break
        r_lo = P0.apply_model((P["w_pre"][s:e].astype(np.float64).mean(axis=0) - b)[None, :], Mx, cpar, p0cfg)[0] * R2D * 60.0
        rec = {"animal": P["animal"], "period": P["period"], "role": P["role"], "kind": P["kind"], "dur_s": (e - s) / FS100}
        for tag, r in (("in", r_in), ("loo", r_lo)):
            par = float(r @ g)
            rec[f"r_{tag}_norm"] = float(np.linalg.norm(r))
            rec[f"r_{tag}_tilt"] = float(np.linalg.norm(r - par * g))
            rec[f"r_{tag}_yaw"] = par
        rows.append(rec)
    return pd.DataFrame(rows)


# ====================================================================================================== 2.9 human checks
_VID_CACHE: dict = {}


def video_lookup(t_ms: float, cfg: dict) -> dict:
    hc = cfg["human_checks"]
    tz = cfg["tz"]
    ts = pd.Timestamp(int(round(t_ms)), unit="ms", tz="UTC").tz_convert(tz).tz_localize(None)
    out = {}
    for chn in hc["channels"]:
        key = (ts.strftime("%Y-%m-%d"), chn)
        if key not in _VID_CACHE:
            d = Path(hc["video_root"]) / key[0] / chn
            rows = []
            if d.is_dir():
                for p in sorted(d.glob(f"{chn}_*.mp4")):
                    parts = p.stem.split("_")
                    try:
                        st = pd.Timestamp(f"{parts[1]} {parts[2].replace('-', ':')}")
                    except Exception:  # noqa: BLE001
                        continue
                    rows.append((st, p.name))
            _VID_CACHE[key] = rows
        rows = _VID_CACHE[key]
        hit = None
        for i, (st, nm) in enumerate(rows):
            nxt = rows[i + 1][0] if i + 1 < len(rows) else st + pd.Timedelta(hours=1, minutes=5)
            if st <= ts < nxt:
                hit = (nm, (ts - st).total_seconds())
                break
        out[chn] = f"{hit[0]} @ {hit[1]:.1f} s" if hit else "n/a"
    return out


def human_checks(allW: pd.DataFrame, sat_all: pd.DataFrame, bt_gate: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    hc = cfg["human_checks"]
    rng = np.random.default_rng(int(hc["seed"]))
    rows = []
    W = allW[(allW["wiser"] != "contradicted") & (allW["dur_s"] >= float(hc["min_still_s"]))]
    for (a, k), g in W.groupby(["animal", "kind"]):
        for i in rng.choice(len(g), size=min(2, len(g)), replace=False):
            r = g.iloc[i]
            rows.append({"type": "strict still window", "animal": a, "period": r["period"], "start_local": ms_local(r["t_start_ms"], cfg["tz"]),
                         "end_local": ms_local(r["t_end_ms"], cfg["tz"]), "detail": f"{r['dur_s']:.1f} s, WISER {r['wiser']}"
                         + (f" at ({r['w_x']:.0f}, {r['w_y']:.0f}) in" if np.isfinite(r["w_x"]) else ""), "t_ms": r["t_start_ms"]})
    if len(sat_all):
        sh = sat_all[sat_all["cls"] == "shake_train"].drop_duplicates(["animal", "period", "train_id"])
        for i in rng.choice(len(sh), size=min(int(hc["n_shake"]), len(sh)), replace=False):
            r = sh.iloc[i]
            rows.append({"type": "shake train (gyro clipped)", "animal": r["animal"], "period": r["period"], "start_local": ms_local(r["t_unix_ms"] - 100, cfg["tz"]),
                         "end_local": ms_local(r["t_unix_ms"] + 100 + 40 * r["train_size"], cfg["tz"]),
                         "detail": f"{int(r['train_size'])} clipped readings, |a|max {r['train_acc_max_g']:.1f} g, net {r['train_net_deg']:.0f} deg", "t_ms": r["t_unix_ms"]})
    if len(bt_gate):
        for _, r in bt_gate.nlargest(int(hc["n_worst"]), "e_cc").iterrows():
            rows.append({"type": "largest-error test bout", "animal": r["animal"], "period": r["period"], "start_local": ms_local(r["t0_ms"], cfg["tz"]),
                         "end_local": ms_local(r["t1_ms"], cfg["tz"]), "detail": f"e {r['e_cc']:.1f} deg, T_in {r['T_in']:.1f} s, rotation {r['rot_deg']:.0f} deg", "t_ms": r["t0_ms"]})
    T = pd.DataFrame(rows)
    if len(T):
        vids = [video_lookup(t, cfg) for t in T["t_ms"]]
        for chn in hc["channels"]:
            T[chn] = [v[chn] for v in vids]
    return T


# ====================================================================================================== run
def run_analysis(cfg: dict, p0cfg: dict, out: Path, roles: list, fh=None) -> dict:
    t_start = time.time()
    ctx = context(cfg)
    animals = cfg["_animals"]
    pkeys = {r: [k for k, p in cfg["periods"].items() if p["role"] == r] for r in ("tuning", "test")}
    S = {"cohort": cfg["_cohort"], "animals": animals, "periods": cfg["periods"], "roles": roles}
    # ---------------- tuning periods
    tun, bouts = {}, {}
    for pk in pkeys["tuning"]:
        for a in animals:
            P = process_period(a, pk, cfg, p0cfg, ctx, fh)
            tun[(pk, a)] = P
            for v in VARIANTS:
                bouts[(pk, a, v)] = make_bouts(P, v, cfg)
    tunk = {f"{k[0]}|{k[1]}": v for k, v in tun.items()}
    fs = fit_stage(tunk, {(k[0], k[1], k[2]): v for k, v in bouts.items()}, cfg, p0cfg, fh)
    sel = fs["selected"]
    sel_fits = {a: fs["fits"][a][sel] for a in animals}
    selection = {"selected_model": sel, "pooled_cv_median_deg": fs["pooled_cv"], "n_fit_bouts": fs["n_fit"],
                 "per_animal": {a: {"M": sel_fits[a]["M"].tolist(), "c": sel_fits[a]["c"], "theta": sel_fits[a]["theta"].tolist(),
                                    "ci95_lo": fs["boot"][a]["lo"].tolist(), "ci95_hi": fs["boot"][a]["hi"].tolist()} for a in animals},
                 "frozen_local": pd.Timestamp.now(tz=cfg["tz"]).isoformat(timespec="seconds"), "test_periods_read": False}
    (out / "selection.json").write_text(json.dumps(selection, indent=1, default=_jd), encoding="utf-8")
    log(f"SELECTION FROZEN ({sel}) -> {out / 'selection.json'} before any test period is read", fh)
    fs["cv_table"].to_csv(out / "model_selection_cv.csv", index=False)
    # ---------------- test periods
    tst = {}
    if "test" in roles:
        for pk in pkeys["test"]:
            for a in animals:
                P = process_period(a, pk, cfg, p0cfg, ctx, fh)
                tst[(pk, a)] = P
                for v in VARIANTS:
                    bouts[(pk, a, v)] = make_bouts(P, v, cfg)
    allP = {**tun, **tst}
    # ---------------- per-bout evaluation
    bt_all = []
    for (pk, a, v), (bt, arr) in bouts.items():
        if len(bt) and (pk, a) in allP:
            bt_all.append(eval_bouts(allP[(pk, a)], bt, arr, fs["fits"][a], sel, cfg, p0cfg))
    bt_all = pd.concat(bt_all, ignore_index=True) if bt_all else pd.DataFrame()
    bt_all.to_csv(out / "bouts_all.csv.gz", index=False)
    allW = pd.concat([P["W"] for P in allP.values()], ignore_index=True)
    allW.to_csv(out / "still_windows.csv.gz", index=False)
    # ---------------- floor
    fl = pd.concat([floor_rows(P, sel_fits[P["animal"]], cfg, p0cfg) for P in allP.values()], ignore_index=True)
    fl.to_csv(out / "floor.csv", index=False)
    gate_role = "test" if "test" in roles else "tuning"
    flg = fl[fl["role"] == gate_role]
    floor_med = float(flg["phi_1"].median()) if len(flg) else np.nan
    floor_p90 = float(flg["phi_1"].quantile(0.9)) if len(flg) else np.nan
    fl_nf = pd.concat([floor_rows(P, sel_fits[P["animal"]], cfg, p0cfg, "L1.0_nf") for P in allP.values()], ignore_index=True)
    fl_nf.to_csv(out / "floor_all_windows.csv", index=False)
    floor_by_wiser = {f"{k}|{w_}": {"n": int(len(x)), "phi_half_median": float(x["phi_half"].median()), "phi_half_prop_median": float(x["phi_half_prop"].median()),
                                    "phi_1_median": float(x["phi_1"].median()), "phi_half_p90": float(x["phi_half"].quantile(0.9))}
                      for (k, w_), x in fl_nf.groupby(["kind", "wiser"])}
    # ---------------- gate
    g = gate_set(bt_all, "L1.0", gate_role)
    gate = evaluate_gate(g, floor_med, cfg)
    gate["role_evaluated"] = gate_role
    log(f"GATE {gate['verdict']} ({gate_role}): " + "; ".join(f"{k} pooled {v['pooled_median_deg']:.2f} (thr {v['threshold_deg']}, n {v['n']})" for k, v in gate["bins"].items())
        + f"; animals passing {gate['n_animals_pass']}/{len(animals)}; floor {floor_med:.3f}", fh)
    info = {}
    variants_info = [("night_only", g[g["kind"] == "night"], "e_cc"), ("day_only", g[g["kind"] == "day"], "e_cc"),
                     ("no_wiser_filter", gate_set(bt_all, "L1.0_nf", gate_role), "e_cc"), ("min_len_2s", gate_set(bt_all, "L2.0", gate_role), "e_cc"),
                     ("edge_style_same_bouts", g, "e_edge"), ("baseline_1.03", g, "e_baseline")] + [(f"model_{m}", g, f"e_{m}") for m in cfg["gyro_fit"]["models"]]
    for nm, gg, col in variants_info:
        info[nm] = evaluate_gate(gg, floor_med, cfg, col)
    tun_gate = evaluate_gate(gate_set(bt_all, "L1.0", "tuning"), float(fl[fl["role"] == "tuning"]["phi_1"].median()) if len(fl) else np.nan, cfg)
    # ---------------- per-bin tables
    tables = {}
    for nm, gg in (("gate", g), ("tuning", gate_set(bt_all, "L1.0", "tuning"))):
        rows = []
        for (a, kd), gk in list(gg.groupby(["animal", "kind"])) + [((a, "pooled"), gg[gg["animal"] == a]) for a in animals] + \
                [(("pooled", kd), gg[gg["kind"] == kd]) for kd in ("night", "day")] + [(("pooled", "pooled"), gg)]:
            for lab in cfg["bouts"]["bin_labels"]:
                gb = gk[gk["dbin"] == lab]
                rows.append({"animal": a, "kind": kd, "dbin": lab, "n": len(gb), **{f"{c}_med": float(gb[c].median()) if len(gb) else np.nan
                                                                                      for c in ["e_cc", "e_edge", "e_baseline", "rot_deg", "T_in", "t_act", "inwin_rot_deg"] + [f"e_{m}" for m in cfg["gyro_fit"]["models"]]},
                             "e_cc_p90": float(gb["e_cc"].quantile(0.9)) if len(gb) else np.nan})
        tables[nm] = pd.DataFrame(rows)
        tables[nm].to_csv(out / f"tilt_by_bin_{nm}.csv", index=False)
    # saturated bouts
    sb = bt_all[(bt_all["variant"] == "L1.0") & bt_all["active"] & bt_all["sat"]]
    sat_bouts = {"n": int(len(sb)), "e_clipped_median": float(sb["e_cc_clipped"].median()) if len(sb) else np.nan,
                 "e_recon_median": float(sb["e_cc"].median()) if len(sb) else np.nan,
                 "by_role": {r: {"n": int(len(x)), "e_clipped_median": float(x["e_cc_clipped"].median()), "e_recon_median": float(x["e_cc"].median())}
                             for r, x in sb.groupby("role")}}
    # drift scaling on the gate set
    ds = {}
    if len(g) > 10:
        ds = {"spearman_e_Tin": float(spearmanr(g["e_cc"], g["T_in"])[0]), "spearman_e_tact": float(spearmanr(g["e_cc"], g["t_act"])[0]),
              "spearman_e_rot": float(spearmanr(g["e_cc"], g["rot_deg"])[0]), "spearman_e_inwin": float(spearmanr(g["e_cc"], g["inwin_rot_deg"])[0]),
              "deg_per_100deg_median": float(np.median(g["e_cc"] / np.maximum(g["rot_deg"], 1e-6) * 100)),
              "deg_per_s_act_median": float(np.median(g["e_cc"] / np.maximum(g["t_act"], 0.01))),
              "inwin_rot_median": float(g["inwin_rot_deg"].median()), "inwin_rot_p90": float(g["inwin_rot_deg"].quantile(0.9)),
              "inwin_net_median": float(g["inwin_net_deg"].median()), "inwin_net_p90": float(g["inwin_net_deg"].quantile(0.9)),
              "e_edge_minus_cc_median": float((g["e_edge"] - g["e_cc"]).median())}
    # rotation-matched comparison with Phase 0's test-night no-saturation bouts (descriptive)
    theta_matched = []
    p0b = Path(cfg["phase0_reference"]["run_dir"]) / "bouts_all.csv"
    edges_th = [0, 50, 100, 200, 400, 800, 1e9]
    if p0b.exists() and len(g):
        b0 = pd.read_csv(p0b)
        b0 = b0[(b0["role"] == "test") & ~b0["sat_gyr"] & ~b0["frozen"] & b0["edge_ok"]]
        for nm, x, ecol, dcol in (("phase0_test_night", b0, "e_cal", "dur_s"), ("v2_night", g[g["kind"] == "night"], "e_cc", "T_in"), ("v2_day", g[g["kind"] == "day"], "e_cc", "T_in")):
            xb = pd.cut(x["rot_deg"], edges_th)
            for iv, xx in x.groupby(xb, observed=True):
                theta_matched.append({"set": nm, "theta_bin": str(iv), "n": int(len(xx)), "e_median": float(xx[ecol].median()),
                                      "e_p90": float(xx[ecol].quantile(0.9)), "dur_median": float(xx[dcol].median()), "rot_median": float(xx["rot_deg"].median())})
            theta_matched.append({"set": nm, "theta_bin": "all", "n": int(len(x)), "e_median": float(x[ecol].median()), "e_p90": float(x[ecol].quantile(0.9)),
                                  "dur_median": float(x[dcol].median()), "rot_median": float(x["rot_deg"].median())})
    pd.DataFrame(theta_matched).to_csv(out / "theta_matched_vs_phase0.csv", index=False)
    # ---------------- chains (linearity)
    recs, recs_sat, biasr = [], [], []
    for P in allP.values():
        recs.append(chain_records(P, sel_fits[P["animal"]], cfg, p0cfg, stop_at_sat=True))
        recs_sat.append(chain_records(P, sel_fits[P["animal"]], cfg, p0cfg, stop_at_sat=False))
        biasr.append(bias_residuals(P, sel_fits[P["animal"]], cfg, p0cfg))
    R = pd.concat([r for r in recs if len(r)], ignore_index=True)
    Rs = pd.concat([r for r in recs_sat if len(r)], ignore_index=True)
    BR = pd.concat([b for b in biasr if len(b)], ignore_index=True) if any(len(b) for b in biasr) else pd.DataFrame()
    R.to_csv(out / "chain_records.csv.gz", index=False)
    BR.to_csv(out / "bias_residuals.csv", index=False)
    log(f"chains: {R['chain'].nunique():,} chains, {len(R):,} records (stop at saturation); {len(Rs):,} records through saturation", fh)
    tR, eR = R[R["role"] == "tuning"], R[R["role"] == (gate_role if gate_role == "test" else "tuning")]
    lin = {"pooled": linearity(tR, eR, cfg, "pooled", fh),
           "day": linearity(tR[tR["kind"] == "day"], eR[eR["kind"] == "day"], cfg, "day", fh),
           "night": linearity(tR[tR["kind"] == "night"], eR[eR["kind"] == "night"], cfg, "night", fh),
           "through_saturation": linearity(Rs[Rs["role"] == "tuning"], Rs[Rs["role"] == eR["role"].iloc[0]] if len(eR) else Rs.iloc[:0], cfg, "through_saturation", fh)}
    lin_animal = {}
    for a in animals:
        ta_, ea_ = tR[tR["animal"] == a], eR[eR["animal"] == a]
        if len(ta_) > 30 and len(ea_) > 30:
            lin_animal[a] = {m: fit_chain_model(m, ta_)["params"] for m in ("L_t", "RW_t", "L_a", "R")}
            lin_animal[a]["test_ll"] = {m: float(np.mean(chain_ll(m, lin_animal[a][m], ea_))) for m in ("L_t", "RW_t", "L_a", "R")}
    incT, inc = increment_consistency(eR, cfg)
    incT.to_csv(out / "chain_increments.csv", index=False)
    verdicts = {k: linearity_verdict(v, inc) for k, v in lin.items()}
    # exploratory (plan amendment 2): anchor-ZARU on identical anchors (windows >= bias_min_window_s): does re-estimating the
    # bias from the anchor's own still window remove the drift?
    zl = float(cfg["chains"]["bias_min_window_s"])
    zrole = eR["role"].iloc[0] if len(eR) else "tuning"
    Zs = {}
    for zf in (False, True):
        zz = [chain_records(P, sel_fits[P["animal"]], cfg, p0cfg, True, zl, zf) for P in allP.values()]
        Zs[zf] = pd.concat([x for x in zz if len(x)], ignore_index=True) if any(len(x) for x in zz) else pd.DataFrame()
    zaru = {"anchor_min_dur_s": zl, "bins": []}
    if len(Zs[False]) and len(Zs[True]):
        pd.concat([Zs[False], Zs[True]], ignore_index=True).to_csv(out / "chain_records_zaru_compare.csv.gz", index=False)
        ze = [0, 10, 30, 60, 120, 300, 600]
        for kd in ("night", "day", "pooled"):
            for zf in (False, True):
                Z = Zs[zf][Zs[zf]["role"] == zrole]
                Z = Z if kd == "pooled" else Z[Z["kind"] == kd]
                b_ = np.digitize(Z["t"].to_numpy(), ze) - 1
                for k in range(len(ze) - 1):
                    m = b_ == k
                    if m.sum() >= 15:
                        zaru["bins"].append({"kind": kd, "variant": "anchor_zaru" if zf else "standard", "t_lo": ze[k], "t_hi": ze[k + 1], "n": int(m.sum()),
                                             "e_median": float(np.median(Z["e"].to_numpy()[m])), "e_p90": float(np.percentile(Z["e"].to_numpy()[m], 90))})
        for zf, nm in ((False, "standard"), (True, "anchor_zaru")):
            Z = Zs[zf]
            zaru[f"lin_{nm}"] = linearity(Z[Z["role"] == "tuning"], Z[Z["role"] == zrole], cfg, f"zaru:{nm}", fh)
            _, zinc = increment_consistency(Z[Z["role"] == zrole], cfg)
            zaru[f"inc_{nm}"] = zinc
            zaru[f"verdict_{nm}"] = linearity_verdict(zaru[f"lin_{nm}"], zinc)
            zaru[f"n_chains_{nm}"] = int(Z[Z["role"] == zrole]["chain"].nunique())
        zaru["anchor_bias_dpm_median"] = float(Zs[True].drop_duplicates("chain")["anchor_bias_dpm"].median())
        log(f"anchor-ZARU (exploratory): standard -> {zaru['verdict_standard'][:60]} | zaru -> {zaru['verdict_anchor_zaru'][:60]}", fh)
    log(f"linearity verdicts: {verdicts}; increments {inc}", fh)
    bias_summ = {}
    if len(BR):
        for key, gk in [("pooled", BR[BR["role"] == eR["role"].iloc[0]])] + [(f"{r}_{k}", x) for (r, k), x in BR.groupby(["role", "kind"])] + \
                [(a, x) for a, x in BR[BR["role"] == eR["role"].iloc[0]].groupby("animal")]:
            bias_summ[key] = {"n": int(len(gk)), **{f"{c}_{q}": float(gk[c].quantile(qq)) for c in ("r_in_tilt", "r_loo_tilt", "r_loo_yaw", "r_loo_norm")
                                                    for q, qq in (("median", 0.5), ("p90", 0.9))},
                              "abs_r_loo_yaw_median": float(gk["r_loo_yaw"].abs().median())}
    # ---------------- growth law
    gc = {"growth": cfg["growth"]}
    gl = P0.fit_growth(g["t_act"].to_numpy(), g["e_cc"].to_numpy(), floor_med, int(len(flg)), gc, floor_p90) if len(g) > 20 else None
    gl_tin = P0.fit_growth(g["T_in"].to_numpy(), g["e_cc"].to_numpy(), floor_med, int(len(flg)), gc, floor_p90) if len(g) > 20 else None
    gcc = {"growth": {**cfg["growth"], "bin_edges_s": cfg["growth"]["chain_bin_edges_s"]}}
    gl_chain = P0.fit_growth(eR["t_act"].to_numpy(), eR["e"].to_numpy(), floor_med, int(len(flg)), gcc, floor_p90) if len(eR) > 100 else None
    gl_chain_t = P0.fit_growth(eR["t"].to_numpy(), eR["e"].to_numpy(), floor_med, int(len(flg)), gcc, floor_p90) if len(eR) > 100 else None
    for nm, x in (("growth_tact", gl), ("growth_Tin", gl_tin), ("growth_chain_tact", gl_chain), ("growth_chain_t", gl_chain_t)):
        if x is not None:
            x["table"].to_csv(out / f"{nm}.csv", index=False)
    # ---------------- saturation runs + human checks
    sat_all = pd.concat([P["sat_runs"] for P in allP.values() if len(P["sat_runs"])], ignore_index=True) if any(len(P["sat_runs"]) for P in allP.values()) else pd.DataFrame()
    sat_all.to_csv(out / "sat_runs.csv.gz", index=False)
    hcT = human_checks(allW, sat_all, g, cfg)
    hcT.to_csv(out / "human_checks.csv", index=False)
    # ---------------- window statistics
    wstats = []
    for (a, pk), Wg in allW.groupby(["animal", "period"]):
        P = allP[(pk, a)]
        wstats.append({"animal": a, "period": pk, "role": P["role"], "kind": P["kind"], "valid_h": float(P["valid"].sum() / FS100 / 3600),
                       "n": int(len(Wg)), "confirmed": int((Wg["wiser"] == "confirmed").sum()), "contradicted": int((Wg["wiser"] == "contradicted").sum()),
                       "unavailable": int((Wg["wiser"] == "unavailable").sum()), "n_ge2s": int((Wg["dur_s"] >= 2).sum()), "n_ge4s": int((Wg["dur_s"] >= 4).sum()),
                       "still_min": float(Wg["dur_s"].sum() / 60), "dur_median_s": float(Wg["dur_s"].median()), "dur_p90_s": float(Wg["dur_s"].quantile(0.9)),
                       "maxdev_median_in": float(Wg["w_maxdev_in"].median()), "acc_mag_dev_median": float((Wg["acc_mag"] - G).abs().median()),
                       "n_bouts_active_L1": int(((bt_all["animal"] == a) & (bt_all["period"] == pk) & (bt_all["variant"] == "L1.0") & bt_all["active"]).sum()),
                       "n_gaps_quasi_still_L1": int(((bt_all["animal"] == a) & (bt_all["period"] == pk) & (bt_all["variant"] == "L1.0") & ~bt_all["active"]).sum()),
                       "bias_node_err_max": P["bias_node_err"]})
    wstats = pd.DataFrame(wstats)
    wstats.to_csv(out / "still_window_stats.csv", index=False)
    floor_summ = {}
    for key, fk in [("pooled_" + gate_role, flg)] + [(f"{r}_{k}", x) for (r, k), x in fl.groupby(["role", "kind"])] + [(f"{gate_role}_{a}", x) for a, x in flg.groupby("animal")]:
        floor_summ[key] = {"n": int(len(fk)), **{f"{c}_{q}": float(fk[c].quantile(qq)) for c in ("phi_1", "phi_2", "phi_half", "phi_half_prop")
                                                  for q, qq in (("median", 0.5), ("p90", 0.9))}}
    # ---------------- config fitted block + provenance + summary
    fitted = {"selection": selection, "gate": {"verdict": gate["verdict"], "role": gate_role, "bins": gate["bins"], "n_animals_pass": gate["n_animals_pass"]},
              "floor_phi1_median_deg": floor_med, "linearity_verdicts": verdicts,
              "growth_tact": ({"A": gl["A"], "B": gl["B"], "p90": gl["p90"]} if gl else None),
              "growth_chain_tact": ({"A": gl_chain["A"], "p90": gl_chain["p90"]} if gl_chain else None),
              "run_dir": str(out), "git_commit": EC.git_commit(), "written": pd.Timestamp.now(tz=cfg["tz"]).isoformat(timespec="seconds")}
    if "test" in roles:
        cp = Path(cfg["_path"])
        cj = json.loads(cp.read_text(encoding="utf-8"))
        cj["fitted"] = json.loads(json.dumps(fitted, default=_jd))
        cp.write_text(json.dumps(cj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    prov = {"periods": {f"{P['animal']}/{P['period']}": {"a1": P["a1_path"], "a1_bytes": P["a1_bytes"], "a3": P["a3_path"], "a3_bytes": P["a3_bytes"],
                                                        "bias_node_err_max_dps": P["bias_node_err"], "n100": P["n100"], "valid_frac": P["valid_frac"]} for P in allP.values()},
            "phase0_config": cfg["phase0_config"], "git_commit": EC.git_commit()}
    (out / "input_provenance.json").write_text(json.dumps(prov, indent=1, default=_jd), encoding="utf-8")
    fits_out = {a: {m: {"theta": fs["fits"][a][m]["theta"].tolist(), "M": fs["fits"][a][m]["M"].tolist(), "c": fs["fits"][a][m]["c"],
                        "cv_median_deg": fs["fits"][a][m]["cv_median"], "train_median_deg": fs["fits"][a][m]["train_median"],
                        "n_bouts": fs["fits"][a][m]["n_bouts"], "ok": fs["fits"][a][m]["ok"]} for m in cfg["gyro_fit"]["models"]}
                | {"bootstrap_selected": {"model": sel, "lo": fs["boot"][a]["lo"].tolist(), "hi": fs["boot"][a]["hi"].tolist()}} for a in animals}
    (out / "fits.json").write_text(json.dumps(fits_out, indent=1, default=_jd), encoding="utf-8")
    S.update({"selected_model": sel, "pooled_cv": fs["pooled_cv"], "fits": fits_out, "cv_table": fs["cv_table"].to_dict(orient="records"),
              "gate": gate, "gate_info": info, "gate_tuning": tun_gate, "floor": floor_summ, "floor_by_wiser": floor_by_wiser, "theta_matched": theta_matched, "floor_gate_median": floor_med, "floor_gate_p90": floor_p90,
              "tables": {k: v.to_dict(orient="records") for k, v in tables.items()}, "window_stats": wstats.to_dict(orient="records"),
              "sat_bouts": sat_bouts, "drift_scaling": ds, "linearity": lin, "linearity_animal": lin_animal, "increments": inc, "verdicts": verdicts, "zaru": zaru,
              "bias": bias_summ,
              "growth": {k: ({"table": x["table"].to_dict(orient="records"), "A": x["A"], "B": x["B"], "p90": x["p90"]} if x else None)
                         for k, x in (("tact", gl), ("Tin", gl_tin), ("chain_tact", gl_chain), ("chain_t", gl_chain_t))},
              "human_checks": hcT.drop(columns=["t_ms"]).to_dict(orient="records") if len(hcT) else [],
              "counts": {"windows": int(len(allW)), "bouts": int(len(bt_all)), "chain_records": int(len(R)), "chains": int(R["chain"].nunique()),
                         "chain_records_through_sat": int(len(Rs))},
              "phase0_reference": cfg["phase0_reference"], "runtime_s": time.time() - t_start, "git_commit": EC.git_commit(), "run_dir": str(out)})
    (out / "summary.json").write_text(json.dumps(S, indent=1, default=_jd), encoding="utf-8")
    # binned chain curves for figures (records too large for summary)
    curves = chain_curves(R, cfg)
    curves.to_csv(out / "chain_curves.csv", index=False)
    return S


def chain_curves(R: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    edges = np.asarray(cfg["growth"]["chain_bin_edges_s"], float)
    rows = []
    for (role, kind), g in list(R.groupby(["role", "kind"])) + [((r, "pooled"), x) for r, x in R.groupby("role")]:
        for xv in ("t", "t_act"):
            b = np.digitize(g[xv].to_numpy(), edges) - 1
            for k in range(len(edges) - 1):
                m = b == k
                if m.sum() >= 15:
                    rows.append({"role": role, "kind": kind, "x": xv, "lo": edges[k], "hi": edges[k + 1], "n": int(m.sum()), "x_med": float(np.median(g[xv].to_numpy()[m])),
                                 "e_med": float(np.median(g["e"].to_numpy()[m])), "e_p90": float(np.percentile(g["e"].to_numpy()[m], 90)),
                                 "rot_med": float(np.median(g["theta_deg"].to_numpy()[m])), "t_med": float(np.median(g["t"].to_numpy()[m])),
                                 "tact_med": float(np.median(g["t_act"].to_numpy()[m]))})
    return pd.DataFrame(rows)


# ====================================================================================================== figures
def make_figures(S_: dict, out: Path, fig_dir: Path, cohort: str) -> list:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figs = []
    animals = S_["animals"]
    labels = ["2-5 s", "5-15 s", "15-40 s", "40-90 s"]
    gt = pd.DataFrame(S_["tables"]["gate"])
    p0ref = S_["phase0_reference"]
    # 1 tilt by bin (gate set): per animal + pooled, night / day / both
    fig, axs = plt.subplots(1, len(animals) + 1, figsize=(3.3 * (len(animals) + 1), 4.2), sharey=True)
    for j, a in enumerate(animals + ["pooled"]):
        ax = axs[j]
        x = np.arange(4)
        for off, kd, col in ((-0.27, "night", "#2c7fb8"), (0.0, "day", "#f39c12"), (0.27, "pooled", "#c0392b")):
            gg = gt[(gt["animal"] == a) & (gt["kind"] == kd)].set_index("dbin").reindex(labels)
            ax.bar(x + off, gg["e_cc_med"], 0.26, color=col, label=f"{kd}" if j == 0 else None)
            for xi, (v, nn) in enumerate(zip(gg["e_cc_med"], gg["n"].fillna(0))):
                if np.isfinite(v):
                    ax.text(xi + off, v, f"{int(nn)}", ha="center", va="bottom", fontsize=6)
        for k, thr in ((0, 1.0), (1, 2.0)):
            ax.plot([k - 0.45, k + 0.45], [thr, thr], color="k", lw=1.5, label="gate" if (j == 0 and k == 0) else None)
        if a == "pooled":
            for k, lab in ((0, "2-5 s"), (1, "5-15 s")):
                ax.plot([k - 0.45, k + 0.45], [p0ref["gate_test_medians_deg"][lab]] * 2, color="#7f7f7f", ls="--", lw=1.2, label="Phase 0 (pooled)" if k == 0 else None)
            ax.legend(fontsize=7)
        ax.axhline(S_["floor_gate_median"], color="#2ca02c", lw=0.8, ls=":")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=8)
        ax.set_title(a, fontsize=10)
        ax.grid(alpha=0.3, axis="y")
    axs[0].set_ylabel("median tilt error, centre-to-centre (deg)")
    axs[0].legend(fontsize=7, loc="upper left")
    fig.suptitle(f"Gate v2 ({S_['gate']['role_evaluated']} periods; strict still windows; no saturation): GATE {S_['gate']['verdict']}  (numbers = bouts; green dotted = floor)", fontsize=10)
    fig.tight_layout()
    p = fig_dir / f"{STEM}_tilt_by_bin_{cohort}.png"
    fig.savefig(p, dpi=130); plt.close(fig); figs.append(p.name)
    # 2 still windows + floor
    W = pd.read_csv(out / "still_windows.csv.gz")
    fl = pd.read_csv(out / "floor.csv")
    bt = pd.read_csv(out / "bouts_all.csv.gz")
    fig, axs = plt.subplots(1, 4, figsize=(18, 4))
    for kd, col in (("night", "#2c7fb8"), ("day", "#f39c12")):
        d = W.loc[W["kind"] == kd, "dur_s"]
        axs[0].hist(np.log10(d), bins=60, alpha=0.6, color=col, label=f"{kd} (n {len(d)})")
    axs[0].set_xlabel("log10 window duration (s)"); axs[0].set_ylabel("windows"); axs[0].legend(fontsize=8); axs[0].set_title("strict still windows")
    ws = pd.DataFrame(S_["window_stats"])
    lab = ws["animal"] + "\n" + ws["period"].str.replace("night_", "N").str.replace("day_", "D")
    bot = np.zeros(len(ws))
    for c_, col in (("confirmed", "#2ca02c"), ("unavailable", "#bbbbbb"), ("contradicted", "#d62728")):
        axs[1].bar(np.arange(len(ws)), ws[c_], bottom=bot, color=col, label=c_)
        bot += ws[c_].to_numpy()
    axs[1].set_xticks(np.arange(len(ws))); axs[1].set_xticklabels(lab, fontsize=5, rotation=90); axs[1].legend(fontsize=7); axs[1].set_title("WISER support per animal-period")
    for c_, col in (("phi_1", "#1f77b4"), ("phi_2", "#ff7f0e"), ("phi_half_prop", "#2ca02c")):
        d = fl[c_].dropna()
        axs[2].hist(np.clip(d, 0, 0.6), bins=60, alpha=0.5, color=col, label=f"{c_} med {d.median():.3f}")
    axs[2].set_xlabel("floor angle (deg, clipped at 0.6)"); axs[2].legend(fontsize=7); axs[2].set_title("floor (windows >= 4 s)")
    g = bt[(bt["variant"] == "L1.0") & bt["active"] & ~bt["sat"]]
    axs[3].hist(np.clip(g["inwin_rot_deg"], 0, 20), bins=60, color="#9467bd")
    axs[3].axvline(p0ref["edge_rot_median_deg"], color="k", ls="--", label=f"Phase-0 edge median {p0ref['edge_rot_median_deg']:.1f} deg")
    axs[3].set_xlabel("rotation inside the two half-windows (deg, clipped 20)"); axs[3].legend(fontsize=7); axs[3].set_title(f"in-window rotation (median {g['inwin_rot_deg'].median():.2f})")
    fig.tight_layout()
    p = fig_dir / f"{STEM}_still_windows_{cohort}.png"
    fig.savefig(p, dpi=130); plt.close(fig); figs.append(p.name)
    # 3 edge effect + drift vs rotation
    gg = g[g["role"] == S_["gate"]["role_evaluated"]]
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.2))
    axs[0].scatter(gg["e_cc"], gg["e_edge"], s=5, alpha=0.4)
    mx = float(np.nanpercentile(np.r_[gg["e_cc"], gg["e_edge"]], 99)) if len(gg) else 1
    axs[0].plot([0, mx], [0, mx], "k--", lw=0.8); axs[0].set_xlim(0, mx); axs[0].set_ylim(0, mx)
    axs[0].set_xlabel("centre-to-centre error (deg)"); axs[0].set_ylabel("edge-style error, same bouts (deg)"); axs[0].set_title("edge effect on strict windows")
    for kd, col in (("night", "#2c7fb8"), ("day", "#f39c12")):
        x = gg[gg["kind"] == kd]
        axs[1].scatter(np.maximum(x["rot_deg"], 0.1), np.maximum(x["e_cc"], 0.005), s=5, alpha=0.4, color=col, label=kd)
        axs[2].scatter(np.maximum(x["t_act"], 0.01), np.maximum(x["e_cc"], 0.005), s=5, alpha=0.4, color=col, label=kd)
    for ax, xl in ((axs[1], "total rotation in bout (deg)"), (axs[2], "active time in bout (s)")):
        ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel(xl); ax.set_ylabel("tilt error (deg)"); ax.legend(fontsize=7); ax.grid(alpha=0.3)
    fig.tight_layout()
    p = fig_dir / f"{STEM}_edge_effect_{cohort}.png"
    fig.savefig(p, dpi=130); plt.close(fig); figs.append(p.name)
    # 4 chain growth
    cv = pd.read_csv(out / "chain_curves.csv")
    role = S_["gate"]["role_evaluated"]
    lin = S_["linearity"]["pooled"]
    fig, axs = plt.subplots(1, 2, figsize=(13, 4.6))
    for j, xv in enumerate(("t", "t_act")):
        ax = axs[j]
        for kd, col in (("night", "#2c7fb8"), ("day", "#f39c12"), ("pooled", "#333333")):
            c_ = cv[(cv["role"] == role) & (cv["kind"] == kd) & (cv["x"] == xv)]
            ax.plot(c_["x_med"], c_["e_med"], "o-", color=col, ms=3, label=f"{kd} median")
            ax.plot(c_["x_med"], c_["e_p90"], "--", color=col, lw=0.8, label=f"{kd} p90" if kd == "pooled" else None)
        if lin.get("fits"):
            pc_ = cv[(cv["role"] == role) & (cv["kind"] == "pooled") & (cv["x"] == xv)]
            for m, col in (("L_t", "#d62728"), ("RW_t", "#9467bd"), ("L_a", "#8c564b"), ("R", "#17becf"), ("LR_t", "#e377c2")):
                v = chain_var(m, lin["fits"][m]["params"], pc_["t_med"].to_numpy(), pc_["tact_med"].to_numpy(), pc_["rot_med"].to_numpy())
                ax.plot(pc_["x_med"], 1.1774 * np.sqrt(v), color=col, lw=1, label=f"{m} (tuning fit) median")
        ax.set_xscale("symlog", linthresh=1); ax.set_yscale("log"); ax.grid(alpha=0.3)
        ax.set_xlabel({"t": "time since anchor t (s)", "t_act": "active time since anchor t_act (s)"}[xv]); ax.set_ylabel("tilt error (deg)")
        ax.legend(fontsize=6)
    fig.suptitle(f"Chained anchors (no reset, <= 10 min, {role} records): best registered model {lin.get('best_registered')}", fontsize=10)
    fig.tight_layout()
    p = fig_dir / f"{STEM}_chain_growth_{cohort}.png"
    fig.savefig(p, dpi=130); plt.close(fig); figs.append(p.name)
    # 5 linearity: increments + bias residuals
    inc = pd.read_csv(out / "chain_increments.csv") if (out / "chain_increments.csv").stat().st_size > 5 else pd.DataFrame()
    br = pd.read_csv(out / "bias_residuals.csv") if (out / "bias_residuals.csv").stat().st_size > 5 else pd.DataFrame()
    fig, axs = plt.subplots(1, 3, figsize=(16, 4.2))
    if len(inc):
        for kd, col in (("night", "#2c7fb8"), ("day", "#f39c12")):
            x = inc[inc["kind"] == kd]
            axs[0].hist(x["C_inc"], bins=30, range=(0, 1), alpha=0.5, color=col, label=f"{kd} C_inc (n {len(x)})")
            axs[0].hist(x["null_mean"], bins=30, range=(0, 1), histtype="step", color=col, ls="--", label=f"{kd} null mean")
        axs[0].set_xlabel("increment direction consistency"); axs[0].legend(fontsize=7)
    if len(br):
        for c_, col in (("r_in_tilt", "#7f7f7f"), ("r_loo_tilt", "#d62728"), ("r_loo_yaw", "#1f77b4")):
            d = br[c_].abs() if c_ == "r_loo_yaw" else br[c_]
            axs[1].hist(np.clip(d, 0, 10), bins=50, alpha=0.5, color=col, label=f"{c_} med {d.median():.2f}")
        axs[1].set_xlabel("gyro residual during still windows >= 10 s (deg/min, clipped 10)"); axs[1].legend(fontsize=7)
    if len(inc):
        axs[2].scatter(inc["t_last"], inc["C_inc"], s=4, alpha=0.4, c=np.where(inc["kind"] == "day", "#f39c12", "#2c7fb8"))
        axs[2].set_xlabel("chain length (s)"); axs[2].set_ylabel("C_inc"); axs[2].grid(alpha=0.3)
    fig.tight_layout()
    p = fig_dir / f"{STEM}_linearity_{cohort}.png"
    fig.savefig(p, dpi=130); plt.close(fig); figs.append(p.name)
    # 6 growth law
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    tt = np.linspace(0, 90, 200)
    ax.plot(tt, 1.1774 * np.sqrt(p0ref["growth_A"]["sigma0_deg"] ** 2 + (p0ref["growth_A"]["k_deg_per_s"] * tt) ** 2), color="#7f7f7f", label="Phase 0 median law")
    ax.plot(tt, np.sqrt(p0ref["growth_p90"]["p0_deg"] ** 2 + (p0ref["growth_p90"]["k90_deg_per_s"] * tt) ** 2), color="#7f7f7f", ls="--", label="Phase 0 p90")
    gr = S_["growth"].get("tact")
    if gr:
        T = pd.DataFrame(gr["table"])
        ax.plot(T["t_mid"], T["med"], "o", color="#c0392b", label="v2 bins (median)")
        ax.plot(T["t_mid"], T["p90"], "s", color="#c0392b", mfc="none", label="v2 bins (p90)")
        ax.plot(tt, 1.1774 * np.sqrt(gr["A"]["sigma0_deg"] ** 2 + (gr["A"]["k_deg_per_s"] * tt) ** 2), color="#c0392b", label="v2 median law")
        if gr["p90"]:
            ax.plot(tt, np.sqrt(gr["p90"]["p0_deg"] ** 2 + (gr["p90"]["k90_deg_per_s"] * tt) ** 2), color="#c0392b", ls="--", label="v2 p90")
    ax.set_xlabel("active time t_act (s)"); ax.set_ylabel("tilt error (deg)"); ax.grid(alpha=0.3); ax.legend(fontsize=7)
    ax.set_title("Attitude-error growth: corrected (strict windows, centre-to-centre) vs Phase 0", fontsize=9)
    fig.tight_layout()
    p = fig_dir / f"{STEM}_growth_law_{cohort}.png"
    fig.savefig(p, dpi=130); plt.close(fig); figs.append(p.name)
    return figs


# ====================================================================================================== report
def _f(x, nd: int = 2) -> str:
    return P0._f(x, nd)


def _ci(b: dict) -> str:
    return f"{_f(b['pooled_median_deg'])} ({_f(b['ci95'][0])}–{_f(b['ci95'][1])})"


def _cache_sizes(cfg: dict) -> dict:
    roots = {k: Path(v) for k, v in cfg["cache_roots"].items()}
    out = {}
    for k, pat in (("imu_raw", "index_day_*.csv"), ("wiser_fix", "index_day_*.csv")):
        rows = []
        for p in roots[k].glob(pat):
            rows.append(pd.read_csv(p))
        out[k] = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    a3 = sorted(roots["imu100"].glob("SF*/day_*.npz"))
    out["imu100"] = pd.DataFrame({"path": [str(p) for p in a3], "bytes": [p.stat().st_size for p in a3]})
    return out


def gate_by_rotation(out: Path, role: str) -> list:
    """Gate bins split by total rotation Θ (descriptive; from bouts_all.csv.gz of the run)."""
    p = out / "bouts_all.csv.gz"
    if not p.exists():
        return []
    b = pd.read_csv(p)
    g = b[(b["role"] == role) & (b["variant"] == "L1.0") & b["active"] & ~b["sat"] & b["dbin"].isin(["2-5 s", "5-15 s"])]
    rows = []
    for lab, gb in g.groupby("dbin"):
        for nm, m in (("<=50", gb["rot_deg"] <= 50), ("50-100", (gb["rot_deg"] > 50) & (gb["rot_deg"] <= 100)), ("100-200", (gb["rot_deg"] > 100) & (gb["rot_deg"] <= 200)),
                      ("200-400", (gb["rot_deg"] > 200) & (gb["rot_deg"] <= 400)), (">400", gb["rot_deg"] > 400), (">100", gb["rot_deg"] > 100)):
            x = gb.loc[m, "e_cc"]
            if len(x):
                rows.append({"dbin": lab, "rot_bin": nm, "n": int(len(x)), "median": float(x.median()), "p90": float(x.quantile(0.9)),
                             "n_animals_with_bouts": int(gb.loc[m, "animal"].nunique())})
    pd.DataFrame(rows).to_csv(out / "gate_by_rotation.csv", index=False)
    return rows


def write_report(S_: dict, figs: list, out: Path, rdir: Path, cohort: str, cfg: dict) -> Path:
    """Report with Definitions (formula + text per derived quantity), every table, and the honest verdicts."""
    G_ = S_["gate"]
    S_["gate_by_rotation"] = gate_by_rotation(out, G_["role_evaluated"])
    p0 = S_["phase0_reference"]
    animals = S_["animals"]
    sel = S_["selected_model"]
    lin = S_["linearity"]
    inc = S_["increments"]
    gl = S_["growth"]
    fl = S_["floor"]
    role = G_["role_evaluated"]
    fkey = f"pooled_{role}"
    L = []
    w = L.append
    v_head = S_["verdicts"]["pooled"].split(";")[0]
    w(f"# Head-IMU attitude gate v2 (cohort {cohort}): strict accelerometer-led still windows, centre-to-centre propagation, day sleep — **GATE {G_['verdict']}**; drift: **{v_head}**")
    w("")
    w(f"- **Status:** pre-registered in [`implementation_plan/2026-10-01-imu-attitude-gate-v2.md`](../../../../implementation_plan/2026-10-01-imu-attitude-gate-v2.md) (user approval 2026-10-01 \"去吧\"; two amendments recorded in the plan before the full run: (1) the two-part linearity verdict, from the synthetic self-test; (2) descriptive/exploratory additions after a tuning-only development pass — no rule, threshold or model choice changed). "
      f"Model choice on the tuning periods (night 2026-09-08/09 + day 2026-09-08) and frozen in `selection.json` before the test periods were read; the gate evaluated once on the test periods (night 2026-09-10/11 + day 2026-09-11) with the Phase-0 thresholds unchanged. IMU attitude only; WISER only as a still-window veto.")
    w("- **Follows:** Phase 0 ([`change_log/2026-09-30-imu-attitude-phase0.md`](../../../../change_log/2026-09-30-imu-attitude-phase0.md), report [`wiser_baseline_imu_attitude_phase0_2026c.md`](wiser_baseline_imu_attitude_phase0_2026c.md) §8), whose functions are imported unchanged.")
    w(f"- **Run:** `python wiser/scripts/analyze_imu_attitude_gate_v2.py --cohort {cohort}`; bulk `{S_['run_dir']}` (`still_windows.csv.gz`, `bouts_all.csv.gz`, `floor.csv`, `model_selection_cv.csv`, `selection.json`, `fits.json`, `chain_records.csv.gz`, `chain_increments.csv`, `chain_curves.csv`, `bias_residuals.csv`, `growth_*.csv`, `sat_runs.csv.gz`, `human_checks.csv`, `summary.json`, `input_provenance.json`, `log.txt`); pointer `run_manifest_imu_attitude_gate_v2_{cohort}.json`; config `wiser/configs/imu_attitude_gate_v2_{cohort}.json` (`fitted` written by this run); git `{S_['git_commit']}`; runtime {S_['runtime_s'] / 60:.1f} min.")
    cs = _cache_sizes(cfg)
    a1b = cs["imu_raw"]["bytes"].sum() if len(cs["imu_raw"]) else 0
    a2b = cs["wiser_fix"]["bytes"].sum() if len(cs["wiser_fix"]) and "bytes" in cs["wiser_fix"] else 0
    a3b = cs["imu100"]["bytes"].sum() if len(cs["imu100"]) else 0
    w(f"- **New day caches** (same roots and formats as the night caches, never overwriting; README.md written in each root): A1 `imu_raw_cache/<SFxx>/<session>__<start>_<end>.npz` ({len(cs['imu_raw'])} files, {a1b / 1e6:.0f} MB, index `index_day_2026c.csv`); "
      f"A3-equivalent `imu100_cache/<SFxx>/day_<date>.npz` ({len(cs['imu100'])} files, {a3b / 1e6:.0f} MB); A2 `wiser_fix_cache/day_<date>/<SFxx>.csv.gz` ({len(cs['wiser_fix'])} files, {a2b / 1e6:.1f} MB, index `index_day_2026c.csv`).")
    w("")
    # ---------------------------------------------------------------- 1 headline
    w("## 1. Headline")
    w("")
    b25, b515 = G_["bins"]["2-5 s"], G_["bins"]["5-15 s"]
    w(f"1. **GATE {G_['verdict']}.** Test night + test day, active strict no-saturation bouts, selected model `{sel}`, median centre-to-centre tilt error: **2–5 s {_ci(b25)}° (n {b25['n']}, threshold 1.0°)** and **5–15 s {_ci(b515)}° (n {b515['n']}, threshold 2.0°)**; "
      f"{G_['n_animals_pass']}/{len(animals)} animals pass both bins (≥ 4 required). Floor ($\\varphi_{{1.0}}$, test pooled median) **{_f(S_['floor_gate_median'], 3)}°**; excess over the floor {_f(b25['excess_over_floor_deg'])}° / {_f(b515['excess_over_floor_deg'])}°"
      + (" — the failing bin(s) are within 0.5° of the floor: **the test is at its limit**." if any((not b['pooled_pass']) and b['at_limit'] for b in G_['bins'].values()) else
         (" (the floor clause does not apply)." if G_["verdict"] == "FAIL" else ".")))
    w(f"   Phase 0 on its own bouts: 1.76° / 3.29° (FAIL). Same thresholds, unchanged.")
    gi = S_["gate_info"]

    def ib(nm):
        x = gi.get(nm)
        if not x:
            return "n/a"
        return f"{_f(x['bins']['2-5 s']['pooled_median_deg'])}° (n {x['bins']['2-5 s']['n']}) / {_f(x['bins']['5-15 s']['pooled_median_deg'])}° (n {x['bins']['5-15 s']['n']}), {x['n_animals_pass']}/{len(animals)} animals, {x['verdict']}"
    w(f"2. **Information only (never the verdict), 2–5 s / 5–15 s:** night-only {ib('night_only')}; day-only {ib('day_only')}; without the WISER filter {ib('no_wiser_filter')}; ≥ 2.0-s windows {ib('min_len_2s')}; "
      f"edge-style propagation on the same bouts {ib('edge_style_same_bouts')}; 1.03 baseline {ib('baseline_1.03')}.")
    ws = pd.DataFrame(S_["window_stats"])
    tot = ws[["n", "confirmed", "contradicted", "unavailable"]].sum()
    byk = ws.groupby("kind")[["n", "confirmed", "contradicted", "unavailable", "still_min", "valid_h", "n_bouts_active_L1"]].sum()
    w(f"3. **Strict still windows (all four periods, 5 animals):** {int(tot['n']):,} windows (night {int(byk.loc['night', 'n']):,} in {byk.loc['night', 'valid_h']:.1f} valid h, {byk.loc['night', 'still_min']:.0f} min still; "
      f"day {int(byk.loc['day', 'n']):,} in {byk.loc['day', 'valid_h']:.1f} h, {byk.loc['day', 'still_min']:.0f} min still). WISER: confirmed {int(tot['confirmed']):,} ({tot['confirmed'] / tot['n'] * 100:.0f} %), "
      f"contradicted {int(tot['contradicted']):,} ({tot['contradicted'] / tot['n'] * 100:.0f} %, dropped), unavailable {int(tot['unavailable']):,} ({tot['unavailable'] / tot['n'] * 100:.0f} %, kept). "
      f"Active bouts between kept ≥ 1-s windows: night {int(byk.loc['night', 'n_bouts_active_L1']):,}, day {int(byk.loc['day', 'n_bouts_active_L1']):,}.")
    ff = fl.get(fkey, {})
    w(f"4. **Floor (test, windows ≥ 4 s, n {ff.get('n', 0)}):** $\\varphi_{{1.0}}$ median {_f(ff.get('phi_1_median'), 3)}° (p90 {_f(ff.get('phi_1_p90'), 3)}), $\\varphi_{{2.0}}$ {_f(ff.get('phi_2_median'), 3)}° (p90 {_f(ff.get('phi_2_p90'), 3)}), halves {_f(ff.get('phi_half_median'), 3)}°, "
      f"halves gyro-propagated centre-to-centre {_f(ff.get('phi_half_prop_median'), 3)}° (p90 {_f(ff.get('phi_half_prop_p90'), 3)}). Phase-0 floor (adjacent 0.5-s quiet windows) 0.048°.")
    pc = S_["pooled_cv"]
    w(f"5. **Model choice (tuning periods, 2-fold CV, pooled held-out median on 2–15 s bouts):** " + ", ".join(f"`{m}` {_f(pc[m], 3)}°" for m in pc) + f" → **`{sel}`** (frozen before the test periods were read).")
    ds = S_.get("drift_scaling", {})
    if ds:
        w(f"6. **Edge effect removed?** Rotation inside the two half-windows that the centre-to-centre test propagates: integrated |ω| median {_f(ds['inwin_rot_median'], 2)}° (p90 {_f(ds['inwin_rot_p90'], 2)}; this sum carries the gyro-noise floor of |ω|), net rotation median {_f(ds.get('inwin_net_median'), 2)}° (p90 {_f(ds.get('inwin_net_p90'), 2)}), vs 8.45° integrated |ω| in Phase 0's unpropagated 0.5-s edge windows; "
          f"edge-style minus centre-to-centre error on the same bouts: median {_f(ds['e_edge_minus_cc_median'], 3)}°. Residual error vs drivers (Spearman): rotation {_f(ds['spearman_e_rot'])}, active time {_f(ds['spearman_e_tact'])}, inner duration {_f(ds['spearman_e_Tin'])}, in-window rotation {_f(ds['spearman_e_inwin'])}; "
          f"{_f(ds['deg_per_100deg_median'])}° per 100° turned, {_f(ds['deg_per_s_act_median'])}° per active second (medians).")
    lp = lin.get("pooled", {})
    con = lp.get("contrasts", {})
    if lp.get("fits"):
        w(f"7. **Is the drift linear? {S_['verdicts']['pooled']}.** Held-out test log-likelihood per record (higher = better): " + ", ".join(f"`{m}` {lp['test_ll'][m]:.4f}" for m in lp["order_registered"])
          + f". Day records (still-dominated): {S_['verdicts'].get('day', 'n/a').split(';')[0]}; night records (active): {S_['verdicts'].get('night', 'n/a').split(';')[0]}."
          + (" Per animal (tuning fit, test LL among L_t / RW_t / L_a / R; no CIs): " + "; ".join(
              f"{a} best {max(v['test_ll'], key=v['test_ll'].get)} (L_t − RW_t {v['test_ll']['L_t'] - v['test_ll']['RW_t']:+.3f})" for a, v in S_.get("linearity_animal", {}).items())
             + " — the pooled verdict is not uniform across animals." if S_.get("linearity_animal") else ""))
    bp = S_.get("bias", {}).get("pooled")
    if bp:
        zr_ = S_.get("zaru", {})
        zt = ""
        if zr_.get("bins"):
            zb_ = pd.DataFrame(zr_["bins"])
            zp = zb_[zb_["kind"] == "pooled"].pivot_table(index="t_lo", columns="variant", values="e_median")
            if {"standard", "anchor_zaru"} <= set(zp.columns):
                zt = (" Exploratory anchor-ZARU (bias re-estimated from the anchor's own ≥ 10-s still window, same anchors): pooled median error "
                      + ", ".join(f"{int(k)}–{int(h)} s {_f(zp.loc[k, 'standard'])} → {_f(zp.loc[k, 'anchor_zaru'])}°" for k, h in ((10, 30), (30, 60), (60, 120), (300, 600)) if k in zp.index)
                      + " — a local bias update roughly halves the error for the first 1–2 min, then the bias has moved (§8).")
        w(f"8. **Gyro bias residual during still windows ≥ 10 s (test, n {bp['n']}):** leave-window-out tilt component median {_f(bp['r_loo_tilt_median'])} °/min (p90 {_f(bp['r_loo_tilt_p90'])}), yaw |median| {_f(bp['abs_r_loo_yaw_median'])} °/min; in-sample (A3 bias) tilt {_f(bp['r_in_tilt_median'])} °/min." + zt)
    if gl.get("tact"):
        A, P9 = gl["tact"]["A"], gl["tact"]["p90"]
        ct = gl.get("chain_t")
        w(f"9. **Corrected growth law (test bouts, t = active seconds):** $\\sigma_\\theta(t_{{act}})=\\sqrt{{{A['sigma0_deg']:.2f}^2+({A['k_deg_per_s']:.3f}\\,t_{{act}})^2}}$° (R² {A['r2']:.2f}); p90 envelope $\\sqrt{{{P9['p0_deg']:.2f}^2+({P9['k90_deg_per_s']:.3f}\\,t_{{act}})^2}}$° "
          f"— Phase 0: $\\sqrt{{0.82^2+(0.193\\,t)^2}}$, p90 $\\sqrt{{6.61^2+(0.477\\,t)^2}}$ (k about 5× smaller now)."
          + (f" **Over minutes the clock is t, not t_act** (the drift accumulates while the head is still): chain records give $\\sigma_\\theta(t)=\\sqrt{{{ct['A']['sigma0_deg']:.2f}^2+({ct['A']['k_deg_per_s']:.4f}\\,t)^2}}$° (R² {ct['A']['r2']:.2f}), p90 $\\sqrt{{{ct['p90']['p0_deg']:.2f}^2+({ct['p90']['k90_deg_per_s']:.4f}\\,t)^2}}$° for t up to 600 s since the last strict still window." if ct else ""))
    gq = S_.get("gate_by_rotation", [])
    if gq:
        gqd = {(r["dbin"], r["rot_bin"]): r for r in gq}
        hi_ = [r for r in gq if r["rot_bin"] == ">100"]
        w(f"10. **What the PASS does and does not mean.** The bouts between strict still windows are gentle: median total rotation {_f(pd.DataFrame(S_['tables']['gate']).query('animal == \"pooled\" and kind == \"pooled\" and dbin == \"2-5 s\"')['rot_deg_med'].iloc[0], 0)}° (2–5 s) and "
          f"{_f(pd.DataFrame(S_['tables']['gate']).query('animal == \"pooled\" and kind == \"pooled\" and dbin == \"5-15 s\"')['rot_deg_med'].iloc[0], 0)}° (5–15 s), and **no gate-eligible bout contains gyro clipping** (clipping happens in vigorous activity, which never lies between two strict windows ≤ 90 s apart). "
          f"Restricted to bouts with Θ > 100°, the gate bins give " + "; ".join(f"{r['dbin']} {_f(r['median'])}° (n {r['n']})" for r in hi_) + "; with Θ > 400° in 5–15 s " +
          (f"{_f(gqd[('5-15 s', '>400')]['median'])}° (n {gqd[('5-15 s', '>400')]['n']})" if ("5-15 s", ">400") in gqd else "n/a") +
          ". Rotation-matched against Phase 0 (§7), the error is 2–4× smaller for 50–400° of rotation and similar (2–4°) above 400°. The gate therefore says: across the activity that is bracketed by truly still windows, the calibrated gyro holds the vertical to well under the thresholds; it does not show that minutes of vigorous night activity are tracked — over minutes the bias drift (items 7–8, ≈ 2 °/min) dominates. Per the Phase-0 plan the gate decides whether inertial fusion with WISER is worth attempting; with this PASS it is, provided the filter re-estimates the gyro bias at every still window (zero-rate updates) and uses the clock-time growth law above as process noise.")
    w("")
    for f_ in figs:
        w(f"![{f_}](../figures/{f_})")
        w("")
    # ---------------------------------------------------------------- 2 definitions
    w("## 2. Definitions")
    w("")
    w("Head frame x nose, y left, z up (`make_imu.S`). 100-Hz samples k, $\\Delta t$ = 0.01 s; $\\mathbf a_k$ = calibrated accelerometer (A3 / A3-equivalent ellipsoid $D(\\mathbf a-\\mathbf o)$, m/s²); "
      "$\\mathbf w_k-\\mathbf b_k$ = Phase-0 gyro chain (Hampel → held-reading saturation reconstruction → 40-Hz Butterworth-4 zero-phase → `resample_poly(2,25)` → head frame) minus the A3 running-median bias (°/s); "
      "$\\boldsymbol\\omega_k=M(\\mathbf w_k-\\mathbf b_k)$ for a gyro model $M$ (rad/s in propagation); $\\boldsymbol\\omega^{A3}_k=1.03(\\mathbf w_k-\\mathbf b_k)$ without reconstruction (A3 `gyr`); $g$ = 9.81 m/s². Angles in degrees unless stated.")
    w("")
    defs = [
        ("Valid sample", "$v_k = [t_k\\in\\text{analysis window}]\\wedge\\neg\\text{frozen}_k\\wedge\\neg\\text{handling}_k\\wedge[t_k<t_{imu\\ valid}]$",
         "samples that may enter a still window, a bout or a chain. Analysis windows: nights 21:00 → 04:20, days 09-08 08:00 → 18:30 and 09-11 10:00 → 17:30 (field-PC local)."),
        ("Candidate block", "block $j$ = samples $[10j,10j+10)$; candidate iff all $v_k$, no `sat_acc`/`sat_gyr`, and $\\max_k|\\boldsymbol\\omega^{A3}_k|<3$ °/s",
         "a 0.1-s piece in which the head may be still; the gyro test is auxiliary (3 °/s ≈ 10× the still gyro noise)."),
        ("Strict still window $W=[s,e)$", "$\\max_{j\\in W}\\angle(\\hat{\\mathbf u}_j,\\bar{\\mathbf m}_W)<0.3^\\circ\\ \\wedge\\ \\big||\\bar{\\mathbf m}_W|-g\\big|<0.03g,\\ \\ \\bar{\\mathbf m}_W=\\tfrac1{|W|}\\sum_{j\\in W}\\mathbf m_j,\\ \\hat{\\mathbf u}_j=\\mathbf m_j/|\\mathbf m_j|$",
         "grown greedily left to right over consecutive candidate blocks; closed when the next block would break either condition (that block starts the next window); kept if ≥ 1.0 s (gate) or ≥ 2.0 s (variant). Bounds the in-window rotation to ≈ 0.6°; a slowly rotating head at constant |a| is rejected (self-test)."),
        ("Window gravity and centre", "$\\hat{\\mathbf g}_W=\\sum_{k\\in W}\\mathbf a_k/|\\sum_{k\\in W}\\mathbf a_k|$, $c_W=\\lfloor(s+e)/2\\rfloor$", "the measured vertical (head frame) attributed to the window centre."),
        ("WISER support", "span $[s-2\\,\\mathrm s, e+2\\,\\mathrm s]$; 1-s bin medians $\\mathbf p_k$ of valid unmasked fixes; $\\tilde{\\mathbf p}$ = coordinate-wise median; available iff ≥ 3 bins and ≥ 50 % of the span's seconds; confirmed iff $\\max_k|\\mathbf p_k-\\tilde{\\mathbf p}|\\le 6$ in, else contradicted",
         "the headstage tag did not move by more than 6 in (inches, WISER frame, unverified origin; IMU↔WISER lag 0.1–0.2 s ignored). Contradicted windows are dropped; unavailable ones kept. WISER cannot see head rotation."),
        ("Floor $\\varphi_L$, $\\varphi_{half}$, $\\varphi_{half,prop}$", "for kept windows with $e-s\\ge 4$ s and midpoint $m$: $\\varphi_L=\\angle(\\bar{\\mathbf a}_{[m-L,m)},\\bar{\\mathbf a}_{[m,m+L)})$, L = 1, 2 s; $\\varphi_{half}=\\angle(\\bar{\\mathbf a}_{[s,m)},\\bar{\\mathbf a}_{[m,e)})$; $\\varphi_{half,prop}$ = the same after propagating the first half's gravity from its centre to the second half's centre with $\\boldsymbol\\omega$",
         "the error the test reports with zero activity (acc noise + residual micro-motion, + still gyro drift for the propagated version). **Gate floor = pooled test median of $\\varphi_{1.0}$.** Cross-orientation acc-calibration residuals (≈ 0.1°) are not included → lower bound."),
        ("Bout, $T_{in}$, $T_{cc}$, active", "consecutive kept windows $W_i,W_{i+1}$ with all $v_k$ on $[c_i,c_{i+1})$; $T_{in}=(s_{i+1}-e_i)\\Delta t$, $T_{cc}=(c_{i+1}-c_i)\\Delta t$; active iff $\\exists k\\in[e_i,s_{i+1}):\\neg\\text{quiet}^{A3}_k$",
         "the activity between two strict still windows; binned by $T_{in}$ (2–5, 5–15, 15–40, 40–90 s; Phase-0 `pd.cut` convention); gaps without any A3 non-quiet sample are quasi-still gaps, not bouts."),
        ("Centre-to-centre tilt error $e$", "$\\mathbf g_{c_i}=\\hat{\\mathbf g}_{W_i}$, $\\mathbf g_{k+1}=\\mathrm{Exp}(-\\boldsymbol\\omega_k\\Delta t)\\mathbf g_k$ for $k=c_i..c_{i+1}-1$; $e=\\angle(\\mathbf g_{c_{i+1}},\\hat{\\mathbf g}_{W_{i+1}})$",
         "how far the gyro alone mis-tracks the vertical from one still window's centre to the next; no motion is left unpropagated at either edge. 0 = perfect; includes the floor."),
        ("Edge-style error $e_{edge}$", "as $e$ but $\\hat{\\mathbf g}_{W_i}$ placed at $e_i$ and propagated over $[e_i,s_{i+1})$ only", "Phase 0's construction applied to the same bouts: the difference $e_{edge}-e$ is the edge effect left with strict windows."),
        ("$t_{act}$, $\\Theta$, in-window rotation", "$t_{act}=\\Delta t\\,\\#\\{k\\in[c_i,c_{i+1}):\\neg\\text{quiet}^{A3}_k\\}$; $\\Theta=\\sum_k|\\boldsymbol\\omega_k|\\Delta t$; in-window rotation $=\\sum_{k\\in[c_i,e_i)\\cup[s_{i+1},c_{i+1})}|\\boldsymbol\\omega_k|\\Delta t$",
         "active seconds (s), total head rotation (°), and the rotation inside the two half-windows that Phase 0 left unpropagated (°)."),
        ("Saturated bout", "any raw gyro lane $|raw|\\ge 32700$ in raw frames $[12.5c_i,12.5c_{i+1})$", "kept out of the gate; reported with the clipped stream and with Phase-0 reconstruction (treatment ii)."),
        ("Gyro models and fit", "scalar $(1+s)I$, diag $\\mathrm{diag}(1+d_i)$, M $I+E$, M_rate $(1+c|\\mathbf w-\\mathbf b|^2/\\omega_0^2)(I+E)$, $\\omega_0$ = 1000 °/s; $\\min\\sum_i\\rho_H(\\boldsymbol\\varepsilon_i/f)$, $\\boldsymbol\\varepsilon_i=\\mathbf g_{c_{i+1}}-\\hat{\\mathbf g}_{W_{i+1}}$, $f$ = 3°",
         "Phase 0's models and Huber objective, fitted on tuning active no-sat bouts with 2 ≤ $T_{in}$ ≤ 15 s (night + day pooled per animal)."),
        ("Model selection", "2-fold CV, fold $=\\lfloor t_{0}/600\\rfloor \\bmod 2$ ($t_0$ = bout start, s since the period's window start); an animal contributes held-out errors only if both training folds have ≥ 20 bouts; lowest pooled held-out median wins, ties ≤ 0.05° → fewer parameters",
         "chosen on tuning data only and frozen (written to `selection.json`) before any test period was read; 200-draw bootstrap CIs of the selected parameters."),
        ("Gate", "PASS iff $\\mathrm{med}(e\\mid 2\\text{–}5\\,s)\\le 1.0^\\circ\\wedge \\mathrm{med}(e\\mid 5\\text{–}15\\,s)\\le 2.0^\\circ$ pooled and in ≥ 4/5 animals; floor clause: a failing bin with median − floor < 0.5° = test at its limit",
         "test night + test day, active strict no-saturation bouts, ≥ 1-s windows, WISER-filtered; 1000-draw bootstrap CIs for information. An animal with no bouts in a bin fails it."),
        ("Chain and record", "anchor = kept window, thinned to centres ≥ 30 s apart; $q_{c_A}$ = tilt from $\\hat{\\mathbf g}_A$ (yaw 0), $q_{k+1}=q_k\\otimes\\mathrm{Exp}(\\boldsymbol\\omega_k\\Delta t)$, no aiding; ends at $c_A$ + 600 s, an invalid sample, the period end or the first raw gyro saturation (primary); record at each later kept window $j$: $\\boldsymbol\\phi_j$ = rotation vector of the smallest rotation taking $\\mathbf e_z$ to $R(q_{c_j})\\hat{\\mathbf g}_{W_j}$, $e_j=|\\boldsymbol\\phi_j|$, with $t$, $t_{act}$, $\\Theta$ since the anchor",
         "accumulated tilt error without reset, as a horizontal vector in the anchor-initialised world frame (a fixed rotation of the anchor's head frame; its yaw drifts with the gyro)."),
        ("Chain models", "per-axis variance $\\sigma_\\theta^2$: `L_t` $\\sigma_0^2+(bt)^2$; `RW_t` $\\sigma_0^2+qt$; `R` $\\sigma_0^2+(c\\Theta)^2$; `LR_t` $\\sigma_0^2+(bt)^2+(c\\Theta)^2$; `L_a`, `RW_a`, `LR_a` with $t_{act}$; exploratory `RWR` $\\sigma_0^2+q_\\Theta\\Theta$, `RW_t+R`. $\\ell_i=\\ln(e_i/\\sigma_i^2)-e_i^2/(2\\sigma_i^2)$ (Rayleigh), $E[e^2]=2\\sigma_\\theta^2$",
         "constant bias → error ∝ time (linear); white rate noise → ∝ √t (random walk); scale/misalignment errors → ∝ rotation. Fitted by maximum likelihood on tuning records (animals pooled); compared by held-out test log-likelihood per record and tuning AIC $=2k-2\\ell$."),
        ("Block bootstrap of test ΔLL", "blocks = (animal, period, ⌊anchor time / 600 s⌋); 1000 multinomial resamples of blocks; $\\Delta\\ell=\\sum_{blocks}w_b(\\ell^A_b-\\ell^B_b)/\\sum_b w_b n_b$",
         "95 % CI of the per-record test-LL difference between two models, respecting the dependence of records within a chain and of overlapping chains."),
        ("Increment consistency $C_{inc}$", "records ≥ 30 s apart along a chain, origin $\\boldsymbol\\phi=0$ at the anchor; $C_{inc}=|\\sum_k\\Delta\\boldsymbol\\phi_k|/\\sum_k|\\Delta\\boldsymbol\\phi_k|$; null: increment directions uniform on the circle (200 draws, magnitudes kept)",
         "1 = every increment in the same direction (constant bias, steady heading); at the null (≈ 1/√n) = independent increments (random walk). Chains with ≥ 3 increments."),
        ("Gyro bias residual", "kept windows ≥ 10 s: $\\mathbf r=\\overline{\\boldsymbol\\omega}_W$ (in-sample, A3 bias) and $\\mathbf r_{LOO}=M(\\overline{\\mathbf w}_W-\\mathbf b_{LOO})$ with $\\mathbf b_{LOO}$ = median of the quiet-second gyro medians within ± 300 s excluding the window's seconds (widened ×3 if < 20); tilt $|\\mathbf r-(\\mathbf r\\cdot\\hat{\\mathbf g})\\hat{\\mathbf g}|$, yaw $\\mathbf r\\cdot\\hat{\\mathbf g}$; °/min",
         "the rate at which a still head's attitude estimate would drift; the leave-window-out version is the honest one (the in-sample bias contains the window itself)."),
        ("Growth law", "Phase-0 `fit_growth`: bins of $t$ (edges 0, 2, 3, 4, 5, 7, 10, 15, 22, 30, 45, 60, 90 s; ≥ 15 per bin), the floor at t = 0, $\\sigma_\\theta$ = median/1.1774; $\\sigma_\\theta(t)=\\sqrt{\\sigma_0^2+(kt)^2}$ and $p_{90}(t)=\\sqrt{p_0^2+(k_{90}t)^2}$, weights √n",
         "fitted on test active no-sat bouts with $t=t_{act}$ (corrected law) and $t=T_{in}$; the chain version uses chain records vs $t_{act}$ with edges extended to 600 s."),
        ("Spearman ρ", "rank correlation", "monotone association; used descriptively."),
    ]
    for name, formula, text in defs:
        w(f"**{name}.** {formula}. **Text:** {text}")
        w("")
    # ---------------------------------------------------------------- 3 data
    w("## 3. Data, day caches, regime context")
    w("")
    w("| period | role | analysis window (field-PC local) | source |")
    w("|---|---|---|---|")
    for pk, p in S_["periods"].items():
        w(f"| `{pk}` | {p['role']} | {p['start']} → {p['end']} | {'existing V4 caches' if p['kind'] == 'night' else 'new day caches; sessions ' + ', '.join(f'{a} `{s}`' for a, s in p['sessions'].items())} |")
    w("")
    if len(cs["imu_raw"]):
        w("| day A1 window | animal | session | frames | actual window | sat samples per lane | frozen | MB |")
        w("|---|---|---|---|---|---|---|---|")
        for _, r in cs["imu_raw"].sort_values(["night", "animal"]).iterrows():
            w(f"| {r['night']} | {r['animal']} | `{r['session']}` | {int(r['n']):,} | {' → '.join(json.loads(r['window_actual_local']))} | {r['sat_samples_per_lane']} | {r['frozen_samples']} | {r['bytes'] / 1e6:.0f} |")
        w("")
    w("Regime record checked (field2026-sync incident log 2026-09-21, recording repo, `cv/configs/cohort3_handling_windows.json`, `cohorts/2026c.yaml`): no handling round, ADC-lane window or implant loss inside any analysis window. "
      "Carried as context, not masked: **construction near the paddock from ~07:50 on 09-08 (end never logged) — the tuning day is a disturbed day**; BLE-only anchor passes 09-08 12:15–12:41 and 09-11 16:51–16:58 (no handling); SF09's day cell ran low from 16:41 on 09-11 (auto-stop after the window); SF12's 09-11 day session is field-flagged for its neural connector only (the IMU is used, as instructed); SF12 shanks 1/4 loosening contact from 09-10 (neural).")
    w("")
    # ---------------------------------------------------------------- 4 windows
    w("## 4. Strict still windows and WISER support")
    w("")
    w("| animal | period | valid h | windows | still min | median / p90 dur (s) | ≥ 2 s | ≥ 4 s | WISER confirmed / contradicted / unavailable | median WISER max dev (in) | active bouts | quasi-still gaps |")
    w("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for _, r in ws.sort_values(["role", "period", "animal"], ascending=[False, True, True]).iterrows():
        w(f"| {r['animal']} | {r['period']} | {r['valid_h']:.2f} | {r['n']} | {r['still_min']:.1f} | {r['dur_median_s']:.1f} / {r['dur_p90_s']:.1f} | {r['n_ge2s']} | {r['n_ge4s']} | {r['confirmed']} / {r['contradicted']} / {r['unavailable']} | {_f(r['maxdev_median_in'], 1)} | {r['n_bouts_active_L1']} | {r['n_gaps_quasi_still_L1']} |")
    w("")
    w(f"Bias identity check (Phase 0's b = w − gyr/1.03 against the stored 1-min nodes): max node interpolation error per period {_f(ws['bias_node_err_max'].min(), 3)}–{_f(ws['bias_node_err_max'].max(), 3)} °/s (the chain is A3's, so the exact bias is used).")
    w("")
    # ---------------------------------------------------------------- 5 floor
    w("## 5. Measurement floor")
    w("")
    w("| set | n windows ≥ 4 s | φ1.0 median / p90 | φ2.0 | halves | halves, propagated |")
    w("|---|---|---|---|---|---|")
    for k, v in fl.items():
        w(f"| {k} | {v['n']} | {_f(v['phi_1_median'], 3)} / {_f(v['phi_1_p90'], 3)} | {_f(v['phi_2_median'], 3)} / {_f(v['phi_2_p90'], 3)} | {_f(v['phi_half_median'], 3)} / {_f(v['phi_half_p90'], 3)} | {_f(v['phi_half_prop_median'], 3)} / {_f(v['phi_half_prop_p90'], 3)} |")
    w("")
    fbw = S_.get("floor_by_wiser", {})
    if fbw:
        w("**Is a WISER contradiction real motion? (descriptive; all strict windows ≥ 4 s of both roles, by WISER status):** if WISER-contradicted windows were truly moving, their accelerometer halves would disagree more.")
        w("")
        w("| kind | WISER | n | φ_half median / p90 | φ_half,prop median | φ1.0 median |")
        w("|---|---|---|---|---|---|")
        for k, v in fbw.items():
            kd, ws_ = k.split("|")
            w(f"| {kd} | {ws_} | {v['n']} | {_f(v['phi_half_median'], 3)} / {_f(v['phi_half_p90'], 3)} | {_f(v['phi_half_prop_median'], 3)} | {_f(v['phi_1_median'], 3)} |")
        w("")
    w("φ_half,prop exceeds φ_half: propagating the gyro across a still window adds error (still-gyro bias residual + angle random walk), i.e. the halves disagree less in the accelerometer than after gyro propagation — the head is still and the gyro is not perfect (see the bias residuals in §8).")
    w("")
    # ---------------------------------------------------------------- 6 model choice
    w("## 6. Model choice (tuning periods only)")
    w("")
    cvt = pd.DataFrame(S_["cv_table"])
    w("| animal | n fit bouts | CV | baseline 1.03 | " + " | ".join(cfg["gyro_fit"]["models"]) + " |")
    w("|---|---|---|---|" + "---|" * len(cfg["gyro_fit"]["models"]))
    for a in animals:
        ca = cvt[cvt["animal"] == a].set_index("model")
        if not len(ca):
            continue
        w(f"| {a} | {int(ca['n_fit_bouts'].iloc[0])} | {'yes' if bool(ca['cv'].iloc[0]) else 'no'} | {_f(ca.loc['baseline_1.03', 'cv_median_deg'])} | "
          + " | ".join(f"{_f(ca.loc[m, 'cv_median_deg'])} (train {_f(ca.loc[m, 'train_median_deg'])})" for m in cfg["gyro_fit"]["models"]) + " |")
    w(f"| pooled CV | | | | " + " | ".join(f"**{_f(pc[m], 3)}**" for m in cfg["gyro_fit"]["models"]) + " |")
    w("")
    names = P0.param_names(sel)
    w(f"Selected **`{sel}`**; parameters per animal (refit on all tuning bouts; 95 % bootstrap CI):")
    w("")
    w("| animal | " + " | ".join(names) + " |")
    w("|---|" + "---|" * len(names))
    for a in animals:
        fa = S_["fits"][a]
        th, lo, hi = fa[sel]["theta"], fa["bootstrap_selected"]["lo"], fa["bootstrap_selected"]["hi"]
        w(f"| {a} | " + " | ".join(f"{th[i]:+.4f} [{_f(lo[i], 4)}, {_f(hi[i], 4)}]" for i in range(len(names))) + " |")
    w("")
    # ---------------------------------------------------------------- 7 gate
    w("## 7. GATE (pre-registered, thresholds unchanged)")
    w("")
    w("| bin | threshold | pooled median (95 % CI) | p90 | n | excess over floor | pass |")
    w("|---|---|---|---|---|---|---|")
    for lab, b in G_["bins"].items():
        w(f"| {lab} | ≤ {b['threshold_deg']}° | {_ci(b)} | {_f(b['p90_deg'])} | {b['n']} | {_f(b['excess_over_floor_deg'])} | {'yes' if b['pooled_pass'] else 'no'} |")
    w("")
    w("| animal | 2–5 s median (n) | 5–15 s median (n) | passes both |")
    w("|---|---|---|---|")
    for a, r in G_["animals"].items():
        w(f"| {a} | {_f(r['2-5 s']['median_deg'])} ({r['2-5 s']['n']}) | {_f(r['5-15 s']['median_deg'])} ({r['5-15 s']['n']}) | {'yes' if r['pass_both'] else 'no'} |")
    w("")
    w(f"**Verdict: {G_['verdict']}** ({G_['n_animals_pass']}/{len(animals)} animals; floor {_f(S_['floor_gate_median'], 3)}°). The thresholds were not moved.")
    w("")
    w("**Information only (same rule, other sets):**")
    w("")
    w("| set | 2–5 s median (n) | 5–15 s median (n) | animals passing | verdict |")
    w("|---|---|---|---|---|")
    for nm, x in gi.items():
        w(f"| {nm} | {_f(x['bins']['2-5 s']['pooled_median_deg'])} ({x['bins']['2-5 s']['n']}) | {_f(x['bins']['5-15 s']['pooled_median_deg'])} ({x['bins']['5-15 s']['n']}) | {x['n_animals_pass']} | {x['verdict']} |")
    tg = S_["gate_tuning"]
    w(f"| tuning periods (selected model, in-sample for the fit) | {_f(tg['bins']['2-5 s']['pooled_median_deg'])} ({tg['bins']['2-5 s']['n']}) | {_f(tg['bins']['5-15 s']['pooled_median_deg'])} ({tg['bins']['5-15 s']['n']}) | {tg['n_animals_pass']} | {tg['verdict']} |")
    w("")
    gt = pd.DataFrame(S_["tables"]["gate"])
    w("**Per bin, animal and period type (test, gate set; medians in °):**")
    w("")
    w("| animal | kind | bin | n | e (centre-to-centre) | p90 | e_edge | baseline 1.03 | median T_in (s) | median t_act (s) | median Θ (°) | median in-window rotation (°) |")
    w("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for _, r in gt[gt["n"] > 0].iterrows():
        w(f"| {r['animal']} | {r['kind']} | {r['dbin']} | {int(r['n'])} | {_f(r['e_cc_med'])} | {_f(r['e_cc_p90'])} | {_f(r['e_edge_med'])} | {_f(r['e_baseline_med'])} | {_f(r['T_in_med'], 1)} | {_f(r['t_act_med'], 1)} | {_f(r['rot_deg_med'], 0)} | {_f(r['inwin_rot_deg_med'], 2)} |")
    w("")
    thm = pd.DataFrame(S_.get("theta_matched", []))
    if len(thm):
        w("**Rotation-matched comparison with Phase 0 (descriptive).** The bouts between strict still windows are much less vigorous than Phase 0's bouts, so the gate numbers are not a like-for-like comparison. Within the same bins of total rotation Θ (°), median error (n):")
        w("")
        bins_ = [b for b in thm["theta_bin"].unique() if b != "all"] + ["all"]
        sets_ = list(thm["set"].unique())
        w("| Θ bin (°) | " + " | ".join(sets_) + " |")
        w("|---|" + "---|" * len(sets_))
        for b in bins_:
            cells = []
            for st_ in sets_:
                x = thm[(thm["set"] == st_) & (thm["theta_bin"] == b)]
                cells.append(f"{_f(x['e_median'].iloc[0])} ({int(x['n'].iloc[0])})" if len(x) else "—")
            w(f"| {b} | " + " | ".join(cells) + " |")
        w("")
        w("Phase 0's test-night bouts (`e_cal`, its selected `diag` model, unpropagated 0.5-s edge windows) vs v2 night and day gate bouts (`e_cc`). Durations differ within a Θ bin (Phase 0's bins by bout duration, v2 by $T_{in}$).")
        w("")
    gq = pd.DataFrame(S_.get("gate_by_rotation", []))
    if len(gq):
        w("**Gate bins split by total rotation Θ (test, descriptive):**")
        w("")
        w("| bin | Θ (°) | n | median e (°) | p90 (°) | animals with bouts |")
        w("|---|---|---|---|---|---|")
        for _, r in gq.iterrows():
            w(f"| {r['dbin']} | {r['rot_bin']} | {int(r['n'])} | {_f(r['median'])} | {_f(r['p90'])} | {int(r['n_animals_with_bouts'])} |")
        w("")
    sbt = S_["sat_bouts"]
    if sbt["n"] == 0:
        w("**Saturated bouts:** none. Gyro clipping (Phase 0: 4,320 clipped runs over these nights, 80 % shake trains) happens in vigorous activity, and no such episode lies between two strict still windows ≤ 90 s apart; chains crossing clipping are compared in §8 (`through_saturation`). The Phase-0 reconstruction therefore never enters the gate.")
    else:
        w(f"**Saturated bouts (excluded from the gate):** {sbt['n']} active bouts with raw gyro clipping; median error clipped stream {_f(sbt['e_clipped_median'])}°, reconstructed {_f(sbt['e_recon_median'])}° "
          + "; ".join(f"{r}: n {v['n']}, {_f(v['e_clipped_median'])} → {_f(v['e_recon_median'])}°" for r, v in sbt.get("by_role", {}).items()) + ".")
    w("")
    # ---------------------------------------------------------------- 8 linearity
    w("## 8. Is the gyro drift linear? (chained anchors, no reset, ≤ 10 min)")
    w("")
    cn = S_["counts"]
    w(f"{cn['chains']:,} chains, {cn['chain_records']:,} records (chains stop at the first raw gyro saturation; {cn['chain_records_through_sat']:,} records when continuing through reconstructed saturation). Models fitted on tuning records, scored on test records.")
    w("")
    cvp = out / "chain_curves.csv"
    if cvp.exists():
        cvd = pd.read_csv(cvp)
        cvd = cvd[(cvd["role"] == role) & (cvd["x"] == "t")]
        w("**Plain answer to \"is the gyro drift linear?\"** — the empirical median tilt error of the test chains against the time since the anchor, and the ratio error / time (constant ratio = linear growth; for a random walk the ratio falls as $1/\\sqrt t$):")
        w("")
        w("| t bin (s) | " + " | ".join(f"{k}: n, median e (°), e/t (°/min), median t_act (s), median Θ (°)" for k in ("pooled", "day", "night")) + " |")
        w("|---|---|---|---|")
        for lo_ in sorted(cvd["lo"].unique()):
            cells = []
            for kd in ("pooled", "day", "night"):
                x = cvd[(cvd["kind"] == kd) & (cvd["lo"] == lo_)]
                if len(x):
                    r = x.iloc[0]
                    cells.append(f"{int(r['n'])}, {r['e_med']:.2f}, {r['e_med'] / max(r['t_med'], 1e-6) * 60:.2f}, {r['tact_med']:.0f}, {r['rot_med']:.0f}")
                else:
                    cells.append("—")
            hi_ = cvd[cvd["lo"] == lo_]["hi"].iloc[0]
            w(f"| {lo_:g}–{hi_:g} | " + " | ".join(cells) + " |")
        w("")
        w("Reading: from ≈ 5 s to 10 min the ratio stays at ≈ 1.6–2.1 °/min while the median error grows 60-fold (0.2° → 12°), in day records (head mostly still, median t_act a small fraction of t) and night records alike — linear growth in clock time, with a slight flattening at 5–10 min (a slowly wandering bias; heading changes also rotate a body-fixed bias in the world frame). Below ≈ 5 s the floor and the angle random walk add to it. "
          "The same ≈ 2 °/min accounts for most of the gate-bout errors (≈ 0.3° over the ≈ 6–8 s from window centre to window centre of a 2–5 s bout). "
          "Caveat: the per-record error distribution is heavier-tailed than the Rayleigh model (p90/median ≈ 3.4 vs 1.8 at 5–10 min: the residual bias differs between chains and periods), so the fitted b below describes the root-mean-square growth and over-predicts the median by about 2×; the likelihood comparison of shapes is affected alike for all models.")
        w("")
    for lab in ("pooled", "day", "night", "through_saturation"):
        x = lin.get(lab, {})
        if not x.get("fits"):
            w(f"- `{lab}`: too few records.")
            continue
        w(f"**{lab}** (tuning n {x['n_tuning']:,}, test n {x['n_test']:,}) — verdict: **{S_['verdicts'][lab]}**")
        w("")
        w("| model | parameters (tuning fit; s0 °, b °/s, q °²/s, c °/°, qth °) | tuning AIC | test LL / record |")
        w("|---|---|---|---|")
        for m, fit in x["fits"].items():
            tag = " (exploratory)" if m in cfg["chains"]["exploratory_models"] else ""
            w(f"| `{m}`{tag} | " + ", ".join(f"{k} {v:.4g}" for k, v in fit["params"].items()) + f" | {fit['aic']:.1f} | {x['test_ll'][m]:.4f} |")
        w("")
        w("| contrast (test ΔLL per record) | difference | 95 % block-bootstrap CI |")
        w("|---|---|---|")
        for k, v in x["contrasts"].items():
            w(f"| {k} | {v['diff']:+.4f} | [{v['ci95'][0]:+.4f}, {v['ci95'][1]:+.4f}] |")
        w("")
        w(f"Rotation share of the modelled variance at the median test record: LR_t {_f(x.get('rot_share_LR_t'))}, LR_a {_f(x.get('rot_share_LR_a'))}, RW_t+R {_f(x.get('rot_share_RW_t+R'))}.")
        w("")
    w(f"**Direction consistency of the error increments (test chains with ≥ 3 increments ≥ 30 s apart, n {inc.get('n_chains', 0)}):** median $C_{{inc}}$ {_f(inc.get('median_C'))} vs median null {_f(inc.get('median_null'))}; "
      f"fraction above the chain's null p95 {_f(inc.get('frac_above_null_p95'))}; day {_f(inc.get('day_median_C'))} vs {_f(inc.get('day_median_null'))} (n {inc.get('day_n', 0)}), night {_f(inc.get('night_median_C'))} vs {_f(inc.get('night_median_null'))} (n {inc.get('night_n', 0)}); "
      f"cumulative-direction resultant {_f(inc.get('median_C_cum'))} (persistent for a random walk too).")
    w("")
    la = S_.get("linearity_animal", {})
    if la:
        w("| animal | L_t b (°/s) | RW_t q (°²/s) | L_a b (°/s) | R c (°/°) | test LL L_t / RW_t / L_a / R |")
        w("|---|---|---|---|---|---|")
        for a, v in la.items():
            w(f"| {a} | {v['L_t']['b']:.4g} | {v['RW_t']['q']:.4g} | {v['L_a']['b']:.4g} | {v['R']['c']:.4g} | {v['test_ll']['L_t']:.4f} / {v['test_ll']['RW_t']:.4f} / {v['test_ll']['L_a']:.4f} / {v['test_ll']['R']:.4f} |")
        w("")
    zr = S_.get("zaru", {})
    if zr.get("bins"):
        w(f"**Exploratory (plan amendment 2): does a zero-rate bias update at the anchor remove the drift?** Same anchors (kept windows ≥ {zr['anchor_min_dur_s']:g} s, thinned to ≥ 30 s), chains with the standard A3 bias vs with the anchor window's own mean calibrated gyro subtracted for the whole chain "
          f"(median |anchor bias update| {_f(zr.get('anchor_bias_dpm_median'))} °/min). Verdicts: standard — {zr.get('verdict_standard', 'n/a')}; anchor-ZARU — {zr.get('verdict_anchor_zaru', 'n/a')}.")
        w("")
        zb = pd.DataFrame(zr["bins"])
        w("| kind | t bin (s) | standard median / p90 (n) | anchor-ZARU median / p90 (n) |")
        w("|---|---|---|---|")
        for (kd, lo_, hi_), x in zb.groupby(["kind", "t_lo", "t_hi"], sort=False):
            a_ = x[x["variant"] == "standard"]
            b_ = x[x["variant"] == "anchor_zaru"]
            fa = f"{_f(a_['e_median'].iloc[0])} / {_f(a_['e_p90'].iloc[0])} ({int(a_['n'].iloc[0])})" if len(a_) else "—"
            fb = f"{_f(b_['e_median'].iloc[0])} / {_f(b_['e_p90'].iloc[0])} ({int(b_['n'].iloc[0])})" if len(b_) else "—"
            w(f"| {kd} | {lo_:g}–{hi_:g} | {fa} | {fb} |")
        w("")
    bias = S_.get("bias", {})
    if bias:
        w("**Gyro bias residual during strict still windows ≥ 10 s (°/min):**")
        w("")
        w("| set | n | tilt, leave-window-out median / p90 | tilt, in-sample median / p90 | yaw, leave-window-out median / p90 | |yaw| median |")
        w("|---|---|---|---|---|---|")
        for k, v in bias.items():
            w(f"| {k} | {v['n']} | {_f(v['r_loo_tilt_median'])} / {_f(v['r_loo_tilt_p90'])} | {_f(v['r_in_tilt_median'])} / {_f(v['r_in_tilt_p90'])} | {_f(v['r_loo_yaw_median'])} / {_f(v['r_loo_yaw_p90'])} | {_f(v['abs_r_loo_yaw_median'])} |")
        w("")
    # ---------------------------------------------------------------- 9 growth
    w("## 9. Corrected attitude-error growth law")
    w("")
    for k, lab in (("tact", "test bouts vs t_act (corrected law)"), ("Tin", "test bouts vs T_in"), ("chain_tact", "chain records vs t_act"), ("chain_t", "chain records vs t")):
        x = gl.get(k)
        if not x:
            continue
        p9 = x.get("p90") or {}
        w(f"**{lab}:** A $\\sigma_\\theta=\\sqrt{{{x['A']['sigma0_deg']:.3f}^2+({x['A']['k_deg_per_s']:.4f}\\,t)^2}}$ (R² {x['A']['r2']:.2f}); B {x['B']['sigma0_deg']:.3f} + {x['B']['k_deg_per_s']:.4f} t (R² {x['B']['r2']:.2f}); "
          f"p90 $\\sqrt{{{_f(p9.get('p0_deg'), 2)}^2+({_f(p9.get('k90_deg_per_s'), 4)}\\,t)^2}}$.")
        w("")
        T = pd.DataFrame(x["table"])
        w("| t bin (s) | t mid | n | median e (°) | p90 e (°) |")
        w("|---|---|---|---|---|")
        for _, r in T.iterrows():
            w(f"| {r['t_lo']:g}–{r['t_hi']:g} | {r['t_mid']:.1f} | {int(r['n'])} | {_f(r['med'])} | {_f(r['p90'])} |")
        w("")
    w(f"Phase 0 (test night, unpropagated 0.5-s edge windows, t = bout duration): $\\sigma_\\theta=\\sqrt{{0.82^2+(0.193t)^2}}$, p90 $\\sqrt{{6.61^2+(0.477t)^2}}$.")
    w("")
    # ---------------------------------------------------------------- 10 human checks
    w("## 10. Suggested human video checks (not done; the agent never judges images)")
    w("")
    w("Times are field-PC local (the video file names are field-PC time; never use the burned-in OSD, which runs ≈ 59½ min behind). "
      "Each camera column gives the hourly segment under `F:\\3rd_rat\\<date>\\<CH>\\` and the offset from its file-name start. What a person would add: (a) still windows — the animal is visibly motionless for the whole window (validates the accelerometer rule and the WISER veto); "
      "(b) shake trains — a wet-dog shake / head twitch at that moment (validates the clipped-gyro class); (c) largest-error bouts — what the head did (fast turns, grooming, a collision, a headstage knock).")
    w("")
    hc = pd.DataFrame(S_["human_checks"])
    if len(hc):
        chs = cfg["human_checks"]["channels"]
        w("| type | animal | period | start | end | detail | " + " | ".join(chs) + " |")
        w("|---|---|---|---|---|---|" + "---|" * len(chs))
        for _, r in hc.iterrows():
            w(f"| {r['type']} | {r['animal']} | {r['period']} | {r['start_local']} | {r['end_local']} | {r['detail']} | " + " | ".join(str(r[c]) for c in chs) + " |")
        w("")
    # ---------------------------------------------------------------- 11 caveats / deviations / verification
    w("## 11. Caveats, deviations, verification")
    w("")
    w("- The tilt error is measured against accelerometer means in strict windows; the floor (§5) is part of every number; cross-orientation accelerometer-calibration residuals (≈ 0.1°) are not in the floor.")
    w("- Strict windows are rare during activity, so night bouts are the activity *between* the few strict windows of an active night, and day bouts are mostly posture shifts during sleep; the two regimes differ in what the gyro must track.")
    w("- WISER can veto only translation (tag on the headstage); the 6-in radius is close to the WISER jitter of 1-s medians, so contradictions include jitter (§4 reports the medians of the maximum deviation).")
    w("- The chained-anchor frame's yaw drifts with the gyro, which rotates the apparent direction of a constant world-frame tilt error; the increment consistency is computed over ≥ 30-s steps within ≤ 10 min.")
    w("- The tuning day (09-08) had construction near the paddock; the test day (09-11) did not. The day caches are A3-equivalent (same chain, per-window self-calibrated ellipsoid and bias).")
    w("- **Deviations from the plan:** (1) amendment 1 (two-part linearity verdict, from the synthetic self-test) before any real-data run; (2) amendment 2 after a tuning-only development pass "
      "(`D:\\Field2026_analysis_out\\2026c\\imu_attitude_gate_v2_20261001_0833`, kept; it showed tuning-period numbers only): descriptive additions (net in-window rotation, floor by WISER status, rotation-matched comparison with Phase 0) and the exploratory anchor-ZARU chains — no rule, threshold or model choice changed; "
      "(3) analysis windows 21:00 → 04:20 (not Phase 0's whole cached 20:50 → 05:30), as specified; (4) the Phase-0 exploratory g-sensitivity models were not refitted; (5) the gate-bins-by-rotation table and the error/time table were added at report time from the saved run outputs (descriptive).")
    w(f"- **Verification:** `--selftest` ALL PASS, 13 checks (strict detector rejects a 2 °/s rotation at constant |a| that the Phase-0 rule accepts; centre-to-centre removes a planted 7° edge bias to 0.003°; anchor-ZARU removes a planted constant bias; chained-anchor fits recover a planted bias (b within 25 %, LINEAR IN TIME) and a planted random walk (q within 35 %, RANDOM-WALK-LIKE); WISER classes); "
      "the selection was written to `selection.json` before the test periods were loaded (log); the day A3 files reproduce A3's chain: their stored 1-min bias nodes match the exact bias implied by the Phase-0 chain (b = w − gyr/1.03) to 0.02–0.20 °/s (per-period maximum; nights 0.007–0.50 °/s), and the exact bias is what is used; no raw file, existing cache file or existing script was modified; no commit.")
    p = rdir / f"{STEM}_{cohort}.md"
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    return p


# ====================================================================================================== self-test
def _synth_attitude(w_true_dps: np.ndarray, q0=None) -> np.ndarray:
    """True attitude after each sample (q_{k+1} = q_k (x) Exp(w_k dt)), via Phase 0's integrator with zero aiding."""
    n = len(w_true_dps)
    q0 = np.array([1.0, 0, 0, 0]) if q0 is None else np.asarray(q0, float)
    qo, ta = np.empty((n, 4)), np.empty(n)
    P0.integrate_attitude(np.deg2rad(np.asarray(w_true_dps, float)), np.zeros((n, 3)), np.zeros(n, bool), np.zeros(n, bool), DT, 0.0, q0, qo, ta)
    return qo


def _g_head_arr(qs: np.ndarray) -> np.ndarray:
    w, x, y, z = qs[:, 0], qs[:, 1], qs[:, 2], qs[:, 3]
    return np.column_stack([2.0 * (x * z - w * y), 2.0 * (y * z + w * x), 1.0 - 2.0 * (x * x + y * y)])


def selftest() -> int:
    cfg, p0cfg = load_cfg("2026c")
    cfg["_animals"] = ["SFX"]
    rng = np.random.default_rng(11)
    fails = []
    t0 = time.time()

    def check(name, ok, detail=""):
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {detail}")
        if not ok:
            fails.append(name)
    # ---------------------------------------------------------------- 1 strict detector
    print("self-test 1: strict still-window detector")
    n1, n2, n3 = 2000, 1000, 1000                       # 20 s still, 10 s slow rotation (2 deg/s about head x), 10 s still
    w_true = np.zeros((n1 + n2 + n3, 3))
    w_true[n1:n1 + n2, 0] = 2.0
    qs = _synth_attitude(w_true, P0.q_from_up(np.array([0.3, -0.2, 0.93])))
    acc = G * _g_head_arr(qs) + rng.normal(0, 0.02, (len(w_true), 3))
    om = np.linalg.norm(w_true + rng.normal(0, 0.3, w_true.shape), axis=1)
    win = detect_strict(acc, om, np.ones(len(acc), bool), cfg, 1.0)
    rot = np.zeros(len(acc), bool); rot[n1:n1 + n2] = True
    frac_in_rot = [rot[s:e].mean() for s, e in win]
    check("no window lives in the slowly rotating segment (constant |a|, gyro 2 deg/s < 3)", all(f < 0.5 for f in frac_in_rot) and sum(rot[s:e].sum() for s, e in win) < 60,
          f"windows {win.tolist()}, samples inside rotation {sum(int(rot[s:e].sum()) for s, e in win)}")
    qsr = quasi_static_phase0_rule(acc[n1:n1 + n2], om[n1:n1 + n2])
    check("the Phase-0 quasi-static rule accepts the rotating segment (contrast)", qsr.mean() > 0.9, f"accepted {qsr.mean():.2f} of its 0.5-s windows")
    first = [w for w in win if w[0] < n1]
    check("one window covers >= 95 % of the first still segment", len(first) == 1 and (min(first[0][1], n1) - first[0][0]) >= 0.95 * n1, f"{first}")
    # ---------------------------------------------------------------- 2 centre-to-centre
    print("self-test 2: centre-to-centre propagation removes a known edge bias")
    nA, nb_, nB = 200, 500, 200
    w2 = np.zeros((nA + nb_ + nB, 3))
    w2[:nA, 0] = 4.0                                    # 4 deg/s about x inside window A (4 deg over A, 2 deg centre->edge)
    w2[nA:nA + nb_] = P0._smooth_noise(rng, nb_, FS100, 1.5) * 150.0
    w2[nA + nb_:, 1] = 4.0                              # 4 deg/s about y inside window B
    qs2 = _synth_attitude(w2, P0.q_from_up(np.array([0.1, 0.2, 0.97])))
    acc2 = G * _g_head_arr(qs2) + rng.normal(0, 0.005, (len(w2), 3))
    Pm = {"wb": w2.astype(np.float32), "acc": acc2.astype(np.float32)}
    sA, eA, sB, eB = 0, nA, nA + nb_, nA + nb_ + nB
    gA = acc2[sA:eA].mean(axis=0); gA /= np.linalg.norm(gA)
    gB = acc2[sB:eB].mean(axis=0); gB /= np.linalg.norm(gB)
    arr = {"cc": np.array([[(sA + eA) // 2, (sB + eB) // 2]], np.int64), "edge": np.array([[eA, sB]], np.int64), "gs": gA[None, :], "ge": gB[None, :]}
    e_cc = P0.bout_errors(boutset(Pm, arr, "cc"), np.eye(3), 0.0, p0cfg)[0][0]
    e_ed = P0.bout_errors(boutset(Pm, arr, "edge"), np.eye(3), 0.0, p0cfg)[0][0]
    check("edge-style error carries the planted in-window rotation (> 2 deg)", e_ed > 2.0, f"e_edge {e_ed:.2f} deg")
    check("centre-to-centre error at the noise level (< 0.1 deg)", e_cc < 0.1, f"e_cc {e_cc:.3f} deg")
    # ---------------------------------------------------------------- 3 chained-anchor linearity
    print("self-test 3: chained-anchor fit separates a constant bias from a random walk")
    res = {}
    for case in ("linear", "rw"):
        recs = []
        beta_dps, q_true = 0.02, 0.06                   # linear: per-axis bias SD 0.02 deg/s; RW: per-axis angle variance 0.06 deg^2/s
        for seg in range(40):
            n = int(900 * FS100)
            wt = np.zeros((n, 3))
            still = np.ones(n, bool)
            for k0 in range(2000, n - 400, 2000):       # a 3-s there-and-back rotation in half of the 20-s slots, random amplitude
                if rng.random() < 0.5:                  # (decorrelates rotation and active time from clock time)
                    continue
                ax_ = rng.standard_normal(3); ax_ /= np.linalg.norm(ax_)
                prof = np.r_[np.full(150, 1.0), np.full(150, -1.0)] * rng.uniform(10.0, 60.0)
                wt[k0:k0 + 300] = prof[:, None] * ax_[None, :]
                still[k0 - 20:k0 + 320] = False
            qs3 = _synth_attitude(wt, P0.q_from_up(rng.standard_normal(3) * [0.2, 0.2, 0] + [0, 0, 1]))
            acc3 = G * _g_head_arr(qs3) + rng.normal(0, 0.01, (n, 3))
            if case == "linear":
                wm = wt + rng.normal(0, beta_dps, 3)[None, :]
            else:
                wm = wt + rng.normal(0, math.sqrt(q_true / DT), (n, 3))
            win3 = []
            for k in range(200, n - 300, 2000):         # 2-s still windows between the rotations
                win3.append((k - 200 + 350, k - 200 + 550))
            win3 = np.array([w for w in win3 if still[w[0]:w[1]].all()], np.int64)
            cs3 = np.vstack([np.zeros((1, 3)), np.cumsum(acc3, axis=0)])
            gw = cs3[win3[:, 1]] - cs3[win3[:, 0]]
            gw /= np.linalg.norm(gw, axis=1, keepdims=True)
            Wd = pd.DataFrame({"s": win3[:, 0], "e": win3[:, 1], "c": (win3[:, 0] + win3[:, 1]) // 2, "dur_s": (win3[:, 1] - win3[:, 0]) / FS100,
                               "wiser": "unavailable", "g_x": gw[:, 0], "g_y": gw[:, 1], "g_z": gw[:, 2]})
            Ps = {"animal": "SFX", "period": f"seg{seg}", "role": "tuning" if seg < 20 else "test", "kind": "day", "lo": 0.0,
                  "t100": np.arange(n) * 10.0, "wb": wm.astype(np.float32), "valid": np.ones(n, bool), "quiet": still, "satcnt": np.zeros(n, np.int32), "W": Wd}
            recs.append(chain_records(Ps, {"M": np.eye(3), "c": 0.0}, cfg, p0cfg))
            if case == "linear" and seg < 6:
                zz0 = chain_records(Ps, {"M": np.eye(3), "c": 0.0}, cfg, p0cfg, True, 1.5, False)
                zz1 = chain_records(Ps, {"M": np.eye(3), "c": 0.0}, cfg, p0cfg, True, 1.5, True)
                res.setdefault("zaru", []).append((zz0[zz0["t"] > 300]["e"].median(), zz1[zz1["t"] > 300]["e"].median()))
        Rr = pd.concat(recs, ignore_index=True)
        lin = linearity(Rr[Rr["role"] == "tuning"], Rr[Rr["role"] == "test"], cfg, case)
        _, inc = increment_consistency(Rr[Rr["role"] == "test"], cfg)
        res[case] = (lin, inc)
    z0, z1 = np.median([a for a, b in res["zaru"]]), np.median([b for a, b in res["zaru"]])
    check("anchor-ZARU removes a planted constant bias (median e at t > 300 s drops > 90 %)", z1 < 0.1 * z0, f"{z0:.2f} -> {z1:.3f} deg")
    lin, inc = res["linear"]
    b_hat = lin["fits"]["L_t"]["params"]["b"]
    check("planted constant bias: L_t beats RW_t (held-out), b recovered within 25 %",
          lin["test_ll"]["L_t"] > lin["test_ll"]["RW_t"] and abs(b_hat / 0.02 - 1) < 0.25, f"test LL L_t {lin['test_ll']['L_t']:.3f} vs RW_t {lin['test_ll']['RW_t']:.3f}; b {b_hat:.4f} (0.02)")
    check("planted constant bias: increments consistent (median C_inc > 0.8, above null)", inc["median_C"] > 0.8 and inc["median_C"] > inc["median_null"] + 0.2,
          f"C {inc['median_C']:.2f} vs null {inc['median_null']:.2f}")
    lin, inc = res["rw"]
    q_hat = lin["fits"]["RW_t"]["params"]["q"]
    check("planted random walk: RW_t beats L_t (held-out), q recovered within 35 %",
          lin["test_ll"]["RW_t"] > lin["test_ll"]["L_t"] and abs(q_hat / 0.06 - 1) < 0.35, f"test LL RW_t {lin['test_ll']['RW_t']:.3f} vs L_t {lin['test_ll']['L_t']:.3f}; q {q_hat:.4f} (0.06)")
    check("planted random walk: increments at the null (|C - null| < 0.15)", abs(inc["median_C"] - inc["median_null"]) < 0.15, f"C {inc['median_C']:.2f} vs null {inc['median_null']:.2f}")
    v_lin, v_rw = linearity_verdict(*res["linear"]), linearity_verdict(*res["rw"])
    check("verdict for the planted bias = LINEAR IN TIME", v_lin.startswith("LINEAR IN TIME"), v_lin)
    check("verdict for the planted random walk = RANDOM-WALK-LIKE", v_rw.startswith("RANDOM-WALK-LIKE"), v_rw)
    # ---------------------------------------------------------------- 4 WISER support
    print("self-test 4: WISER support classes")
    t100 = 1.7e12 + np.arange(6000) * 10.0
    winw = np.array([[500, 1000], [3000, 3500], [5200, 5700]], np.int64)
    ts = np.arange(t100[0], t100[-1], 280.0)
    x = rng.normal(0, 1.0, len(ts)); y = rng.normal(0, 1.0, len(ts))
    mv = (ts >= t100[3000] - 2000) & (ts < t100[3500] + 2000)
    x[mv] += np.linspace(0, 30, mv.sum())
    keep = ~((ts >= t100[5200] - 2000) & (ts < t100[5700] + 2000)) | (np.arange(len(ts)) % 9 == 0)
    fx = pd.DataFrame({"t_ms": ts[keep], "x": x[keep], "y": y[keep], "valid": True, "m_handling": False, "m_silence": False, "m_tag_validity": False, "m_adc_lane": False})
    st = wiser_support(t100, winw, fx, cfg)["wiser"].tolist()
    check("confirmed / contradicted / unavailable", st == ["confirmed", "contradicted", "unavailable"], f"{st}")
    print(f"self-test: {'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)} ({time.time() - t0:.0f} s)")
    return 0 if not fails else 1


# ====================================================================================================== main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", default="2026c")
    ap.add_argument("--config", default=None)
    ap.add_argument("--animals", nargs="*", default=None)
    ap.add_argument("--roles", nargs="*", default=["tuning", "test"], choices=["tuning", "test"])
    ap.add_argument("--build-day-caches", action="store_true")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--report-only", default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    cfg, p0cfg = load_cfg(args.cohort, args.config)
    cfg["_animals"] = args.animals or cfg["animals"]
    if args.build_day_caches:
        t0 = time.time()
        r = build_day_caches(cfg, args.workers)
        log(f"day caches done in {time.time() - t0:.0f} s: A1 {len(r['a1'])}, A3 {len(r['a3'])}, A2 {len(r['a2'])}")
        return 0
    if args.report_only:
        out = Path(args.report_only)
        S_ = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        fh = None
    else:
        out = output_paths.run_dir(NAME, args.cohort)
        fh = open(out / "log.txt", "a", encoding="utf-8")
        log(f"run dir {out}; animals {cfg['_animals']}; roles {args.roles}; config {cfg['_path']}; git {EC.git_commit()}", fh)
        S_ = run_analysis(cfg, p0cfg, out, args.roles, fh)
        log(f"analysis done in {S_['runtime_s'] / 60:.1f} min", fh)
    if "test" not in S_["roles"]:
        log("development run (tuning only): no figures/report written", fh)
        if fh:
            fh.close()
        return 0
    fig_dir = output_paths.figure_dir(args.cohort, DIRECTION)
    figs = make_figures(S_, out, fig_dir, args.cohort)
    (out / "figures").mkdir(exist_ok=True)
    for f in figs:
        shutil.copy2(fig_dir / f, out / "figures" / f)
    rdir = output_paths.report_dir(args.cohort, DIRECTION)
    rp = write_report(S_, figs, out, rdir, args.cohort, cfg)
    meta = {"cohort": args.cohort, "direction": DIRECTION, "analysis": NAME, "report": rp.name, "driver": "wiser/scripts/analyze_imu_attitude_gate_v2.py",
            "config": str(Path(cfg["_path"]).relative_to(REPO)).replace("\\", "/"), "git_commit": S_["git_commit"], "runtime_s": S_["runtime_s"],
            "caches": cfg["cache_roots"], "gate": S_["gate"]["verdict"], "selected_model": S_["selected_model"], "linearity": S_["verdicts"], "figures": figs}
    output_paths.write_run_manifest(out, out, **meta)
    (rdir / f"run_manifest_{NAME}_{args.cohort}.json").write_text(json.dumps({"run_dir": str(out), **meta}, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"report {rp}; figures {figs}", fh)
    if fh:
        fh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
