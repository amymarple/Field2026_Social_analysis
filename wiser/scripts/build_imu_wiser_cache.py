r"""Phase A of the head-IMU inertial fusion (V4): build reusable caches so the raw data are read ONCE.

Plan: implementation_plan/2026-09-29-wiser-ins-fusion.md (approved by the user 2026-09-29).
Report (cache formats): results/<cohort>/wiser_baseline/reports/wiser_baseline_ins_fusion_<cohort>.md

A1  raw IMU cache   <imu_raw>/<SFxx>/<session>__<start>_<end>.npz   (+ <imu_raw>/index_<cohort>.csv)
      six      int16 (n, 6)   analogin.dat lanes 1-6 (acc x/y/z, gyro x/y/z), sensor frame, raw counts, 1250 Hz
      k0       int            first analogin frame of the window in the session (frame k <-> amplifier sample 16 k)
      amp0     int            16 * k0
      sat      bool (n, 6)    |raw| >= 32700 per lane (ephys/read_imu.py SAT)
      frozen   bool (n,)      all six lanes repeat >= 0.5 s (ephys/make_imu.py frozen_mask; hung chip)
      fit_json str            the session's pc_time_fit.json, verbatim
      meta_json str           animal, raw folder, MAC, session, start_local, night, windows (local + unix ms), sha256 of
                              the first 64 MiB of analogin.dat, size, mtime, n_frames_session, git commit, written time
    Field-PC Unix ms of frame j of the cache: unix_ms(j) = local_midnight(start_local) + make_imu.pc_time_ms(amp0 + 16 j,
    fit) (the pc_time_fit formula without the mod-24 h wrap) -> `cache_unix_ms()` below.
A2  WISER fix cache <wiser_fix>/night_<YYYYMMDD>/<SFxx>.csv.gz        (+ <wiser_fix>/index_<cohort>.csv)
      deduplicated fixes of the night +- 10 min (smoothing-pilot rule: per (tag, timestamp) keep max anchors_used, ties ->
      min reportid): reportid, shortid, t_ms (Unix ms UTC, field-PC clock), x, y (in, WISER frame), anchors_used,
      anchors_list, n_list, dup_n, valid, speed_inps_smooth (library add_speed / add_validity_flags) and the masks
      m_handling, m_silence (all-tag silence +- pad), m_tag_validity, m_adc_lane (this logger's ADC-lane on-windows).

Inputs (all read-only): raw analogin.dat on E: (np.fromfile with an offset: only the window is read), pc_time_fit.json on
Q:, the WISER SQLite copy (wiser_io._connect_readonly: mode=ro + query_only). Writes only under the cache roots.

Usage:
  python wiser/scripts/build_imu_wiser_cache.py --cohort 2026c [--workers 5] [--overwrite] [--only imu|wiser]
  python wiser/scripts/build_imu_wiser_cache.py --selftest
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
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
import wiser_io  # noqa: E402
import analyze_imu_wiser_calibration as C  # noqa: E402  (calibration pilot helpers: to_ms, in_any, tag_window, prepare_fixes)
import analyze_wiser_imu_smoothing as P  # noqa: E402  (smoothing pilot: dedup rule)
from cohorts import load_cohort  # noqa: E402
import read_imu as RI  # noqa: E402  (layout constants only)
import make_imu as MI  # noqa: E402  (frozen_mask, pc_time_ms; nothing runs on import)
import _common as EC  # noqa: E402  (ephys/_common: find_session_dir)

WISER_COLS = ["reportid", "shortid", "t_ms", "x", "y", "anchors_used", "anchors_list", "n_list", "dup_n", "valid",
              "speed_inps_smooth", "m_handling", "m_silence", "m_tag_validity", "m_adc_lane"]


# ================================================================ helpers
def raw_animal(animal: str) -> str:
    """Config 'SF07' -> raw folder 'SF7' (raw folders are unpadded)."""
    return f"SF{int(animal[2:])}"


def night_key(start_local: str) -> str:
    return "night_" + start_local[:10].replace("-", "")


def stamp(ms: float, tz: str = "America/New_York") -> str:
    return pd.Timestamp(int(round(ms)), unit="ms", tz="UTC").tz_convert(tz).strftime("%Y%m%dT%H%M%S")


def sha256_head(path: Path, n_bytes: int) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read(n_bytes))
    return h.hexdigest()


def local_midnight_ms(start_local: str, tz: str = "America/New_York") -> int:
    return C.to_ms(start_local[:10] + " 00:00:00", tz)


def frames_for_window(fit: dict, start_local: str, lo_ms: float, hi_ms: float, n_frames: int,
                      tz: str = "America/New_York") -> tuple[int, int]:
    """[k0, k1) analogin frames whose field-PC time lies in [lo_ms, hi_ms), clipped to the session."""
    base = local_midnight_ms(start_local, tz)
    step = 125                                              # 0.1 s grid, then refined exactly
    kg = np.arange(0, n_frames + step, step, dtype=np.int64)
    kg = kg[kg <= n_frames]
    ug = base + MI.pc_time_ms((16 * kg).astype(np.float64), fit)

    def locate(target: float) -> int:
        j = int(np.searchsorted(ug, target))
        a = max(0, (j - 1) * step)
        b = min(n_frames, (j + 1) * step)
        kk = np.arange(a, b + 1, dtype=np.int64)
        uu = base + MI.pc_time_ms((16 * kk).astype(np.float64), fit)
        return int(kk[min(int(np.searchsorted(uu, target)), len(kk) - 1)])

    k0 = 0 if lo_ms <= ug[0] else locate(lo_ms)
    k1 = n_frames if hi_ms >= ug[-1] else locate(hi_ms)
    return max(0, k0), min(n_frames, k1)


def cache_unix_ms(cache: dict, idx: np.ndarray | None = None) -> np.ndarray:
    """Field-PC Unix ms of cache frames `idx` (default all)."""
    meta = json.loads(str(cache["meta_json"]))
    fit = json.loads(str(cache["fit_json"]))
    n = cache["six"].shape[0]
    j = np.arange(n) if idx is None else np.asarray(idx)
    amp = int(cache["amp0"]) + 16 * j.astype(np.float64)
    return local_midnight_ms(meta["start_local"], meta.get("tz", "America/New_York")) + MI.pc_time_ms(amp, fit)


def load_imu_raw_cache(path: Path) -> dict:
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


# ================================================================ A1: raw IMU window
def cache_imu_window(session_dir: Path, fit: dict, start_local: str, lo_ms: float, hi_ms: float, out_dir: Path,
                     session: str, meta: dict, sha_bytes: int, tz: str = "America/New_York", overwrite: bool = False) -> dict:
    path_dat = Path(session_dir) / "analogin.dat"
    size = os.path.getsize(path_dat)
    n_frames = size // (2 * RI.LANES)
    k0, k1 = frames_for_window(fit, start_local, lo_ms, hi_ms, n_frames, tz)
    if k1 <= k0:
        raise ValueError(f"{session}: no frames inside the window")
    base = local_midnight_ms(start_local, tz)
    t0 = base + float(MI.pc_time_ms(np.array([16.0 * k0]), fit)[0])
    t1 = base + float(MI.pc_time_ms(np.array([16.0 * (k1 - 1)]), fit)[0])
    name = f"{session}__{stamp(t0, tz)}_{stamp(t1, tz)}.npz"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / name
    if out.exists() and not overwrite:
        with np.load(out) as z:
            old = json.loads(str(z["meta_json"]))
        return {**old, "path": str(out), "skipped": True, "bytes": out.stat().st_size}
    ti = time.time()
    raw = np.fromfile(path_dat, dtype=np.int16, count=(k1 - k0) * RI.LANES, offset=k0 * RI.LANES * 2).reshape(-1, RI.LANES)
    six = np.ascontiguousarray(raw[:, list(RI.ACC_LANES) + list(RI.GYR_LANES)])
    del raw
    t_read = time.time() - ti
    sat = np.abs(six.astype(np.int32)) >= RI.SAT
    frz = MI.frozen_mask(six)
    st = path_dat.stat()
    m = {**meta, "session": session, "session_dir": str(session_dir), "start_local": start_local, "tz": tz,
         "fs_hz": RI.FS_IMU, "lanes": "analogin lanes 1-6 = acc x/y/z, gyro x/y/z (sensor frame, raw counts)",
         "scale": {"acc_ms2_per_count": RI.ACC_FS_G * RI.G / 32768, "gyr_dps_per_count": RI.GYR_FS_DPS / 32768,
                   "sat_abs_counts": RI.SAT},
         "window_requested_unix_ms": [lo_ms, hi_ms], "window_requested_local": [C.ms_to_local(lo_ms, tz), C.ms_to_local(hi_ms, tz)],
         "window_actual_unix_ms": [t0, t1], "window_actual_local": [C.ms_to_local(t0, tz), C.ms_to_local(t1, tz)],
         "k0": int(k0), "k1": int(k1), "n": int(k1 - k0), "n_frames_session": int(n_frames),
         "source_bytes": int(size), "source_mtime": pd.Timestamp(st.st_mtime, unit="s", tz="UTC").tz_convert(tz).isoformat(),
         "source_sha256_head": sha256_head(path_dat, sha_bytes), "sha_head_bytes": int(sha_bytes),
         "sat_samples_per_lane": sat.sum(axis=0).tolist(), "frozen_samples": int(frz.sum()),
         "git_commit": C.git_commit(), "written_local": pd.Timestamp.now(tz=tz).isoformat(timespec="seconds"),
         "writer": "wiser/scripts/build_imu_wiser_cache.py", "read_s": round(t_read, 1)}
    tmp = out.with_name(out.stem + ".partial.npz")
    np.savez_compressed(tmp, six=six, k0=np.int64(k0), amp0=np.int64(16 * k0), sat=sat, frozen=frz,
                        fit_json=np.array(json.dumps(fit)), meta_json=np.array(json.dumps(m)))
    os.replace(tmp, out)
    m["path"] = str(out)
    m["bytes"] = out.stat().st_size
    m["elapsed_s"] = round(time.time() - ti, 1)
    return m


def _imu_job(args: tuple) -> dict:
    try:
        return cache_imu_window(*args[:-1], overwrite=args[-1])
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}", "session": args[6]}


# ================================================================ A2: WISER fixes
def wiser_night(db: Path, table: str, tags: dict, lo: float, hi: float, handling, silences, adc, ids: pd.DataFrame,
                tz: str) -> tuple[dict, dict]:
    """Deduplicated fixes per animal with masks. tags: animal -> shortid."""
    con = wiser_io._connect_readonly(Path(db))
    try:
        ph = ",".join("?" * len(tags))
        df = pd.read_sql(f'SELECT reportid, shortid, timestamp, location_x, location_y, anchors_used, anchors_list FROM "{table}" '
                         f'WHERE timestamp >= ? AND timestamp < ? AND shortid IN ({ph})', con,
                         params=[int(lo), int(hi), *[int(t) for t in tags.values()]])
    finally:
        con.close()
    return wiser_frames(df, tags, handling, silences, adc, ids)


def wiser_frames(df: pd.DataFrame, tags: dict, handling, silences, adc, ids: pd.DataFrame) -> tuple[dict, dict]:
    dup_n = df.groupby(["shortid", "timestamp"])["reportid"].transform("size")
    df = df.assign(dup_n=dup_n.astype(int))
    d, st = P.dedup_fixes(df)
    d = d.rename(columns={"timestamp": "ts_raw", "location_x": "x", "location_y": "y"})
    d = C.prepare_fixes(d) if len(d) else d
    out = {}
    for a, sid in tags.items():
        f = d[d.shortid == sid].copy()
        t = f["t_ms"].to_numpy(float)
        f["anchors_list"] = f["anchors_list"].fillna("").astype(str)
        f["n_list"] = f["anchors_list"].map(lambda s: len([x for x in s.split(",") if x.strip()]))
        f["m_handling"] = C.in_any(t, handling)
        f["m_silence"] = C.in_any(t, silences)
        vf, vu = C.tag_window(ids, sid, a, float(np.median(t))) if len(t) else (np.inf, -np.inf)
        f["m_tag_validity"] = (t < vf) | (t >= vu)
        f["m_adc_lane"] = C.in_any(t, [w_ for w_ in adc if w_[2] == a])
        out[a] = f[WISER_COLS].reset_index(drop=True)
    return out, st


# ================================================================ driver
def run(cohort: str, workers: int, overwrite: bool, only: str | None) -> None:
    t_start = time.time()
    coh = load_cohort(cohort)
    cfg = json.loads((REPO / "wiser" / "configs" / f"wiser_ins_fusion_{cohort}.json").read_text(encoding="utf-8"))
    scfg = json.loads((REPO / cfg["smoothing_config"]).read_text(encoding="utf-8"))
    tz = cfg.get("tz", "America/New_York")
    cw = cfg["cache_window"]
    roots = {k: Path(v) for k, v in cfg["cache_roots"].items()}
    raw_root = Path((coh.get("raw_data_roots") or {}).get("analysis_pc", {}).get("ephys"))
    pct = Path(cfg["pc_time_root"])
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
    macs = {k: v.get("mac") for k, v in ((coh.get("ephys") or {}).get("loggers") or {}).items()}

    if only in (None, "imu"):
        jobs = []
        for key, night in scfg["nights"].items():
            lo, hi = C.to_ms(night["start"], tz), C.to_ms(night["end"], tz)
            for a, s in night["sessions"].items():
                session_dir = EC.find_session_dir(raw_root, raw_animal(a), s)
                fit = json.loads((pct / a / s / "pc_time_fit.json").read_text(encoding="utf-8"))
                side = json.loads((Path(cfg["imu_npz_root"]) / a / f"{s}.imu.json").read_text(encoding="utf-8"))
                meta = {"cohort": cohort, "animal": a, "raw_animal": raw_animal(a), "night": night_key(night["start"]),
                        "night_role": key, "night_window_local": [night["start"], night["end"]],
                        "mac": macs.get(raw_animal(a)) or macs.get(a) or session_dir.parent.name,
                        "pc_time_fit_path": str(pct / a / s / "pc_time_fit.json")}
                jobs.append((session_dir, fit, side["start_local"], lo - cw["pre_margin_s"] * 1000, hi + cw["post_margin_s"] * 1000,
                             roots["imu_raw"] / a, s, meta, int(cw["sha_head_bytes"]), tz, overwrite))
        rows = []
        with ProcessPoolExecutor(max_workers=max(1, workers)) as ex:
            for r in ex.map(_imu_job, jobs):
                if "error" in r:
                    print(f"ERROR {r['session']}: {r['error']}", flush=True)
                    continue
                print(f"A1 {r['animal']} {r['night']} {r['session']}: {r['n']:,} frames "
                      f"{r['window_actual_local'][0]} -> {r['window_actual_local'][1]}, sat/lane {r['sat_samples_per_lane']}, "
                      f"frozen {r['frozen_samples']}, {r.get('bytes', 0) / 1e6:.0f} MB"
                      f"{' (existing)' if r.get('skipped') else f' in {r.get('elapsed_s')} s'}", flush=True)
                rows.append({k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in r.items()
                             if k in ("animal", "night", "night_role", "session", "session_dir", "mac", "start_local", "k0", "k1", "n",
                                      "window_actual_local", "window_requested_local", "source_bytes", "source_sha256_head",
                                      "sat_samples_per_lane", "frozen_samples", "path", "bytes", "git_commit", "written_local")})
        if rows:
            idx = roots["imu_raw"] / f"index_{cohort}.csv"
            new = pd.DataFrame(rows)
            if idx.exists():
                old = pd.read_csv(idx)
                new = pd.concat([old[~old.path.isin(new.path)], new], ignore_index=True)
            new.sort_values(["night", "animal"]).to_csv(idx, index=False)
            print(f"A1 index: {idx}", flush=True)

    if only in (None, "wiser"):
        db = Path(scfg["wiser_db"])
        dbi = C.file_info(db)
        if not dbi["sha256"].startswith(scfg["wiser_db_sha256_prefix_expected"]):
            raise SystemExit(f"WISER DB sha256 {dbi['sha256'][:12]} != expected {scfg['wiser_db_sha256_prefix_expected']}")
        rows = []
        for key, night in scfg["nights"].items():
            lo, hi = C.to_ms(night["start"], tz), C.to_ms(night["end"], tz)
            animals = list(night["sessions"])
            tags = {a: C.resolve_tag(ids, a, lo, hi) for a in animals}
            m = cw["wiser_margin_s"] * 1000
            fr, st = wiser_night(db, scfg["wiser_table"], tags, lo - m, hi + m, handling, silences, adc, ids, tz)
            od = roots["wiser_fix"] / night_key(night["start"])
            od.mkdir(parents=True, exist_ok=True)
            for a, f in fr.items():
                p = od / f"{a}.csv.gz"
                if p.exists() and not overwrite:
                    print(f"A2 {a} {night_key(night['start'])}: exists", flush=True)
                else:
                    f.to_csv(p, index=False)
                inw = (f.t_ms >= lo) & (f.t_ms < hi)
                rows.append({"night": night_key(night["start"]), "night_role": key, "animal": a, "shortid": tags[a], "path": str(p),
                             "rows": len(f), "rows_in_night": int(inw.sum()), "dup_groups_all_tags": st["dup_groups"],
                             "rows_dropped_all_tags": st["rows_dropped"], "db": str(db), "db_sha256": dbi["sha256"],
                             "window_local": json.dumps([C.ms_to_local(lo - m, tz), C.ms_to_local(hi + m, tz)]),
                             "m_handling": int(f.m_handling[inw].sum()), "m_silence": int(f.m_silence[inw].sum()),
                             "m_tag_validity": int(f.m_tag_validity[inw].sum()), "m_adc_lane": int(f.m_adc_lane[inw].sum()),
                             "git_commit": C.git_commit()})
                print(f"A2 {a} {night_key(night['start'])}: {len(f):,} fixes ({int(inw.sum()):,} in the night), "
                      f"adc-lane {int(f.m_adc_lane[inw].sum())}", flush=True)
        pd.DataFrame(rows).to_csv(roots["wiser_fix"] / f"index_{cohort}.csv", index=False)
    print(f"done in {time.time() - t_start:.0f} s", flush=True)


# ================================================================ selftest
def selftest() -> int:
    import tempfile
    ok_all = True

    def check(name, cond, info=""):
        nonlocal ok_all
        ok_all &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {info}", flush=True)

    rng = np.random.default_rng(1)
    dur_s = 1800.0
    n = int(dur_s * RI.FS_IMU)
    raw = rng.integers(-200, 200, size=(n, RI.LANES)).astype(np.int16)
    raw[:, 3] = 4000                                            # acc z ~ +1 g
    raw[5000:5010, 4] = 32767                                   # gyro x saturated 10 frames
    f0, f1 = 800_000, 800_000 + int(2 * RI.FS_IMU)
    raw[f0:f1, 1:7] = raw[f0, 1:7]                              # 2-s freeze of lanes 1-6
    start_local = "2026-09-08 19:37:33.435"
    fit = {"fs": 20000.0, "rtc_start_ms_of_day": 70653435.0, "offset_ms": 263.0, "drift_ppm": -22.4,
           "field_pc_clock_steps_inside": []}
    tz = "America/New_York"
    base = local_midnight_ms(start_local, tz)
    lo = base + 70653435.0 + 263.0 + 600_000.0                  # 10 min into the session
    hi = lo + 300_000.0                                         # 5 min
    with tempfile.TemporaryDirectory() as td:
        sd = Path(td) / "sess"
        sd.mkdir()
        raw.tofile(sd / "analogin.dat")
        m = cache_imu_window(sd, fit, start_local, lo, hi, Path(td) / "cache", "sess", {"animal": "SF07"}, 1 << 20, tz)
        cache = load_imu_raw_cache(Path(m["path"]))
        k_exp = int(round(600.0 / (1 - 22.4e-6) * RI.FS_IMU))
        check("window start frame matches the fit inversion (+-2 frames)", abs(int(cache["k0"]) - k_exp) <= 2,
              f"{int(cache['k0'])} vs {k_exp}")
        n_exp = 300 * RI.FS_IMU / (1 - 22.4e-6)                  # 5 min of PC time in logger frames (clock drift)
        check("window length = 5 min of PC time (+-2 frames)", abs(cache["six"].shape[0] - n_exp) <= 2,
              f"{cache['six'].shape[0]} vs {n_exp:.1f}")
        u = cache_unix_ms(cache)
        check("time map: first sample inside [lo, lo + 1 frame)", lo - 1e-6 <= u[0] < lo + 1000 / RI.FS_IMU + 1e-6,
              f"{u[0] - lo:.3f} ms")
        check("lanes 1-6 copied verbatim", np.array_equal(cache["six"], raw[int(cache["k0"]):int(cache["k0"]) + cache["six"].shape[0], 1:7]))
        check("frozen block flagged (2 s)", abs(int(cache["frozen"].sum()) - int(2 * RI.FS_IMU)) <= 2, str(int(cache["frozen"].sum())))
        meta = json.loads(str(cache["meta_json"]))
        check("sha256 of the file head recorded", meta["source_sha256_head"] == sha256_head(sd / "analogin.dat", 1 << 20))
        m2 = cache_imu_window(sd, fit, start_local, base, base + 30_000.0 + 70653435.0 + 263.0, Path(td) / "cache2", "sess",
                              {"animal": "SF07"}, 1 << 20, tz)
        c2 = load_imu_raw_cache(Path(m2["path"]))
        check("window before the session start is clipped to frame 0", int(c2["k0"]) == 0)
        check("saturation flagged per lane", bool(c2["sat"][5000:5010, 3].all()) and int(c2["sat"][:, [0, 1, 2, 4, 5]].sum()) == 0)
    # WISER dedup + masks
    df = pd.DataFrame({"reportid": [5, 3, 7, 8, 9, 10], "shortid": [1, 1, 1, 1, 2, 1], "timestamp": [10, 10, 10, 11, 10, 5000],
                       "location_x": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0], "location_y": [0.0] * 6, "anchors_used": [8, 9, 9, 7, 6, 9],
                       "anchors_list": [",1,2,", ",1,2,3,", ",1,", "", ",4,", ",1,2,3,4,5,6,7,8,9,"]})
    ids = pd.DataFrame({"shortid": [1, 2], "animal": ["SF07", "SF08"], "from_ms": [0, 0], "until_ms": [10**12, 10**12]})
    fr, st = wiser_frames(df, {"SF07": 1, "SF08": 2}, [(4000, 6000, "h")], [], [(0, 20, "SF08")], ids)
    a = fr["SF07"]
    check("dedup keeps max anchors then min reportid; dup_n recorded",
          int(a.loc[a.t_ms == 10, "reportid"].iloc[0]) == 3 and int(a.loc[a.t_ms == 10, "dup_n"].iloc[0]) == 3)
    check("anchor list counted", int(a.loc[a.t_ms == 5000, "n_list"].iloc[0]) == 9)
    check("handling mask", bool(a.loc[a.t_ms == 5000, "m_handling"].iloc[0]) and not bool(a.loc[a.t_ms == 10, "m_handling"].iloc[0]))
    check("ADC-lane mask only for its own logger", bool(fr["SF08"].m_adc_lane.all()) and not bool(a.m_adc_lane.any()))
    print("PASS - build_imu_wiser_cache self-test" if ok_all else "FAIL - build_imu_wiser_cache self-test")
    return 0 if ok_all else 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cohort", default="2026c")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--only", choices=["imu", "wiser"], default=None)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    run(a.cohort, a.workers, a.overwrite, a.only)


if __name__ == "__main__":
    main()
