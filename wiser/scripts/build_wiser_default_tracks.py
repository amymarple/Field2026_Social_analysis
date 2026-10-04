r"""Production: the default WISER tracks for all of a cohort (V3 for the implanted animals, B2 for every other tag and time).

Plan: implementation_plan/2026-10-04-wiser-default-tracks-2026c.md (approved by the user 2026-10-04, "做"; committed 5281fc6
before any output). Report (coverage, reproduction, how to load, Definitions):
results/<cohort>/wiser_baseline/reports/wiser_baseline_default_tracks_<cohort>.md. Reader: wiser/src/default_tracks.py.
PRODUCTION ONLY - no new test, no tuning, no claim. Method-parameterised (--method), so a later default is a re-run from
the same caches.

  V3   (default, change_log/2026-10-03-wiser-v3.md) one B2 filter (smoothing pilot tuned.B2: q = 3 in^2/s^3, per-fix noise
       from anchors_used, chi2 gate + 2 Huber IRLS passes, forward KF + RTS) + q x 10 on IMU-QC-ok locomoting steps + Huber
       ZUPT (sigma 0.25 in/s) at fixes inside IMU-QC-ok still runs >= 3 s eroded by 1 s; no release; where the IMU QC fails
       (or no IMU session exists) B2 dynamics in the same filter. Kernel: analyze_wiser_v3.kf_v3 (imported, unmodified).
  B2   every tag of an animal without a head IMU, unknown tags (no identity claim).

Stages (each skips files that already exist - NOTHING IS EVER OVERWRITTEN; indexes are merged):
  fix     full-day WISER fixes  <OUT>/<c>/wiser_fix_cache/full_<YYYYMMDD>/<label>.csv.gz   (day +- 10 min; the A2 function
          build_imu_wiser_cache.wiser_frames: dedup per (tag, timestamp) max anchors_used, ties -> min reportid; library
          speed / validity flags; masks m_handling, m_silence, m_tag_validity, m_adc_lane) + index_full_<c>.csv
  imu     per field-PC second head-IMU QC / states (the failure audit's per_second_states, unmodified) + the head layer
          (turn_net_deg, turn_abs_deg, pitch_mean, roll_mean) for every animal-day with an IMU session
          <OUT>/<c>/imu_seconds_cache/<SFxx>/<YYYYMMDD>.csv.gz + index_<c>.csv + README.md
  tracks  <OUT>/<c>/wiser_default_tracks/<label>/<YYYYMMDD>.csv.gz (core day only, each day run with +- 10-min margins)
          + index_<c>.csv + README.md
  verify  IMU seconds vs the audit's imu_seconds; production V3 vs the V3 run's saved tracks; full-day fix caches vs the
          existing caches; coverage per label x day; no-IMU list  ->  <run_dir>/tables/
  report  results/<c>/wiser_baseline/reports/wiser_baseline_default_tracks_<c>.md + run_manifest_default_tracks_<c>.json

Inputs (read-only): the WISER SQLite copies <OUT>/<c>/wiser_working/3rdcohort_Spike_2026_3*.sqlite (wiser_io._connect_readonly:
mode=ro + query_only; sha256 recorded), make_imu 50-Hz npz (D:/3rd_rat_spikes/analysis/imu), the configs of the V3 step
(wiser_v3_<c>.json -> audit / smoothing configs), rat_identities_<c>.csv, cohorts/<c>.yaml. Existing drivers are imported,
never modified.

Usage:
  python wiser/scripts/build_wiser_default_tracks.py --cohort 2026c [--method V3] [--labels SF07 ...] [--dates 2026-09-08 ...]
         [--workers 12] [--stages fix imu tracks verify report] [--run-dir <existing run dir>] [--out-root <dir>]
  python wiser/scripts/build_wiser_default_tracks.py --selftest
"""
from __future__ import annotations

import argparse
import glob
import json
import math
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
import output_paths  # noqa: E402  (wiser shim -> common/output_paths.py)
import wiser_io  # noqa: E402  (read-only SQLite connection)
import default_tracks as DT  # noqa: E402  (the reader; layout constants)
import analyze_imu_wiser_calibration as C  # noqa: E402  (to_ms, in_any, sha256, git_commit; unmodified)
import analyze_wiser_imu_smoothing as P  # noqa: E402  (noise table -> r2, step states, IRLS constants; unmodified)
import build_imu_wiser_cache as B  # noqa: E402  (A2 fix function wiser_frames, WISER_COLS; unmodified)
import analyze_wiser_failure_audit as FA  # noqa: E402  (context, sessions_for, per_second_states; unmodified)
import analyze_wiser_v1b as V1B  # noqa: E402  (ZUPT runs / erosion / membership; unmodified)
import analyze_wiser_v3 as V3K  # noqa: E402  (V3 kernel kf_v3, kf_specs, loco_steps, qmult; unmodified)

DIRECTION = "wiser_baseline"
NAME = "wiser_default_tracks_run"
STEM = f"{DIRECTION}_default_tracks"
PLAN = "implementation_plan/2026-10-04-wiser-default-tracks-2026c.md"
DRIVER = "wiser/scripts/build_wiser_default_tracks.py"
READER = "wiser/src/default_tracks.py"
METHODS = ("V3", "B2")
DEFAULT_METHOD = "V3"
FS = 50.0                                   # make_imu npz rate
MIN_SAMPLES_PER_S = C.MIN_SAMPLES_PER_S     # 40 of 50 (the audit's m_nodata rule)
IMU_COLS = ["sec", "ok", "still", "state", "vedba_1s", "omega_1s", "sbf", "turn_net_deg", "turn_abs_deg", "pitch_mean", "roll_mean"]
TRACK_BOOL = list(DT.BOOL_COLS)
TRACK_COLS = ["t_ms", "t_al_ms", "shortid", "x_raw", "y_raw", "anchors_used", "valid", "m_handling", "m_silence", "m_tag_validity",
              "m_adc_lane", "m_off_animal", "x", "y", "vx", "vy", "method", "imu_ok", "imu_state", "zupt", "loco_boost"]
FIX_MARK = "<!-- full-day caches (build_wiser_default_tracks.py) -->"
WRITER = DRIVER


def log_to(fh, msg: str) -> None:
    V3K.log_to(fh, msg)


# ====================================================================================================== setup
def day_bounds(date: str, tz: str) -> tuple[int, int]:
    d = pd.Timestamp(date)
    return C.to_ms(d.strftime("%Y-%m-%d") + " 00:00:00", tz), C.to_ms((d + pd.Timedelta(days=1)).strftime("%Y-%m-%d") + " 00:00:00", tz)


def dkey(date: str) -> str:
    return pd.Timestamp(date).strftime("%Y%m%d")


def local(ms: float, tz: str = "America/New_York") -> str:
    return C.ms_to_local(ms, tz) if np.isfinite(ms) else ""


def db_inventory(db_glob: str, tz: str, hash_it: bool = True) -> tuple[list, pd.DataFrame]:
    """Every WISER DB copy matching the glob: path, sha256, rows, span; per-shortid counts / first / last fix."""
    dbs, rows = [], []
    for p in sorted(glob.glob(db_glob)):
        p = Path(p)
        con = wiser_io._connect_readonly(p)
        try:
            g = pd.read_sql('SELECT shortid, COUNT(*) AS n, MIN(timestamp) AS t0, MAX(timestamp) AS t1 FROM "reports" GROUP BY shortid', con)
        finally:
            con.close()
        info = C.file_info(p, hash_it=hash_it)
        dbs.append({"path": str(p), "name": p.name, "sha256": info["sha256"], "bytes": info["bytes"], "mtime": info["mtime"],
                    "rows": int(g.n.sum()), "t0": float(g.t0.min()), "t1": float(g.t1.max()),
                    "t0_local": local(g.t0.min(), tz), "t1_local": local(g.t1.max(), tz), "shortids": [int(s) for s in g.shortid]})
        for r in g.itertuples():
            rows.append({"db": p.name, "shortid": int(r.shortid), "rows": int(r.n), "t0": float(r.t0), "t1": float(r.t1),
                         "t0_local": local(r.t0, tz), "t1_local": local(r.t1, tz)})
    return dbs, pd.DataFrame(rows)


def build_labels(ids: pd.DataFrame, db_sids, scope_lo: float, scope_hi: float, implanted) -> pd.DataFrame:
    """One row per (label, shortid, validity window). The animal label inside a tag's validity window; a tag worn by an
    animal at the same time as a longer-valid tag of the same animal -> '<animal>_tag<shortid>'; any shortid outside the
    identity table -> 'tag_<shortid>' over the cohort scope (no identity claim)."""
    rows = []
    for animal, g in ids.groupby("animal", sort=True):
        g = g.reset_index(drop=True)
        dur = (g["until_ms"] - g["from_ms"]).to_numpy(float)
        for i, r in g.iterrows():
            secondary = False
            for j, o in g.iterrows():
                if j != i and o["from_ms"] < r["until_ms"] and o["until_ms"] > r["from_ms"]:
                    if dur[j] > dur[i] or (dur[j] == dur[i] and int(o["shortid"]) < int(r["shortid"])):
                        secondary = True
            rows.append({"label": f"{animal}_tag{int(r['shortid'])}" if secondary else animal, "shortid": int(r["shortid"]),
                         "animal": animal, "kind": "secondary" if secondary else "animal", "from_ms": float(r["from_ms"]),
                         "until_ms": float(r["until_ms"]), "implanted": animal in set(implanted)})
    known = set(int(s) for s in ids["shortid"])
    for sid in sorted(set(int(s) for s in db_sids) - known):
        rows.append({"label": f"tag_{sid}", "shortid": sid, "animal": "", "kind": "unknown", "from_ms": float(scope_lo),
                     "until_ms": float(scope_hi), "implanted": False})
    L = pd.DataFrame(rows).reset_index(drop=True)
    for lab, g in L.groupby("label"):
        w = g.sort_values("from_ms")[["from_ms", "until_ms"]].to_numpy(float)
        if len(w) > 1 and np.any(w[1:, 0] < w[:-1, 1]):
            raise SystemExit(f"label {lab}: validity windows overlap in time ({g.shortid.tolist()}) - one filter cannot carry two tags at once")
    return L


def assign_rows(sid: np.ndarray, t: np.ndarray, L: pd.DataFrame, lo: float | None = None, hi: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Per fix: the row of L (label window of its shortid) containing t (inside = True); otherwise, when lo/hi are given,
    the nearest window of that shortid among those overlapping [lo, hi) (inside = False, flagged m_tag_validity); else -1."""
    lab = np.full(len(t), -1, np.int64)
    inside = np.zeros(len(t), bool)
    for s in np.unique(sid):
        m = sid == s
        W = L[L.shortid == int(s)]
        if not len(W):
            continue
        tt = t[m]
        li = np.full(len(tt), -1, np.int64)
        ins = np.zeros(len(tt), bool)
        for k, w in W.iterrows():
            ii = (tt >= w.from_ms) & (tt < w.until_ms)
            li[ii] = k
            ins |= ii
        if lo is not None:
            ov = W[(W.from_ms < hi) & (W.until_ms > lo)]
            rest = ~ins
            if len(ov) and rest.any():
                d = np.stack([np.maximum(np.maximum(w.from_ms - tt[rest], tt[rest] - w.until_ms), 0.0) for _, w in ov.iterrows()])
                li[np.flatnonzero(rest)] = ov.index.to_numpy()[np.argmin(d, axis=0)]
        lab[m] = li
        inside[m] = ins
    return lab, inside


def setup(cohort: str, method: str, out_root: Path | None, hash_dbs: bool = True) -> dict:
    v3cfg = V3K.load_cfg(cohort)
    acfg = V3K.load_acfg(v3cfg)
    ctx = FA.context(acfg)
    tz = ctx["tz"]
    hj = json.loads((REPO / acfg["handling_json"]).read_text(encoding="utf-8"))
    scope = {"release": hj["release"], "end": hj["end"], "popchange": hj["popchange"]}
    s_lo, s_hi = C.to_ms(scope["release"] + ":00", tz), C.to_ms(scope["end"] + ":00", tz)
    dates = [d.strftime("%Y-%m-%d") for d in pd.date_range(scope["release"][:10], scope["end"][:10], freq="D")]
    coh = ctx["coh"]
    loggers = (coh.get("ephys") or {}).get("loggers") or {}
    implanted = sorted(loggers)
    taus_meas = {k: float(v) for k, v in ctx["taus"].items() if not k.startswith("_")}
    tau_med = float(np.median(list(taus_meas.values())))
    taus, tau_assumed = {}, {}
    for a in implanted:
        if a in taus_meas:
            taus[a] = taus_meas[a]
        else:
            taus[a] = tau_med
            tau_assumed[a] = f"not measured; median of the measured tau* ({', '.join(f'{k} {v:g}' for k, v in sorted(taus_meas.items()))}) = {tau_med:g} s (plan [op])"
    implant_lost = {a: C.to_ms(str(v["implant_lost"])[:19], tz) for a, v in loggers.items() if v.get("implant_lost")}
    root = Path(out_root) if out_root else Path(output_paths.out_root())
    croot = root / cohort
    db_glob = str(Path(acfg["wiser_db"]).parent / "3rdcohort_Spike_2026_3*.sqlite")
    dbs, dbsid = db_inventory(db_glob, tz, hash_it=hash_dbs)
    for d in dbs:
        if Path(d["path"]).resolve() == Path(acfg["wiser_db"]).resolve() and hash_dbs and not d["sha256"].startswith(acfg["wiser_db_sha256_prefix_expected"]):
            raise SystemExit(f"{d['name']}: sha256 {d['sha256'][:12]} != expected {acfg['wiser_db_sha256_prefix_expected']}")
    labels = build_labels(ctx["ids"], dbsid["shortid"].unique(), s_lo, s_hi, implanted)
    tu = ctx["tuned"]
    specs = V3K.kf_specs(tu, v3cfg)
    if method not in METHODS:
        raise SystemExit(f"--method {method}: not one of {METHODS}")
    track_dir = croot / DT.TRACK_DIRNAME if method == DEFAULT_METHOD else croot / f"wiser_tracks_{method}"
    return {"cohort": cohort, "method": method, "v3cfg": v3cfg, "acfg": acfg, "tz": tz, "scope": scope, "scope_ms": (s_lo, s_hi),
            "dates": dates, "implanted": implanted, "taus": taus, "tau_assumed": tau_assumed, "implant_lost": implant_lost,
            "root": root, "croot": croot, "fix_root": croot / "wiser_fix_cache", "imu_root": croot / "imu_seconds_cache",
            "track_root": track_dir, "dbs": dbs, "dbsid": dbsid, "labels": labels, "specs": specs, "tuned": tu,
            "margin_ms": float(acfg["fix_cache"]["margin_s"]) * 1000.0, "imu_ext_ms": float(acfg["fix_cache"]["margin_s"]) * 1000.0,
            "v3": v3cfg["v3"], "v3_run": v3cfg["decision"]["run_dir"], "audit_run": v3cfg["audit_run"]}


def label_info(S: dict, label: str) -> dict:
    g = S["labels"][S["labels"].label == label]
    animal = str(g.animal.iloc[0])
    implanted = bool(g.implanted.iloc[0])
    use_imu = implanted and S["method"] == "V3"
    return {"label": label, "animal": animal, "kind": str(g.kind.iloc[0]), "implanted": implanted, "use_imu": use_imu,
            "shortids": sorted(set(int(s) for s in g.shortid)), "windows": g[["from_ms", "until_ms"]].to_numpy(float).tolist(),
            "tau_ms": int(round(1000.0 * S["taus"][animal])) if implanted else 0,
            "tau_assumed": S["tau_assumed"].get(animal, "") if implanted else "",
            "implant_lost_ms": S["implant_lost"].get(animal, np.inf) if animal else np.inf,
            "method_default": "V3" if use_imu else "B2"}


def animal_windows(S: dict, animal: str) -> list:
    g = S["labels"][(S["labels"].animal == animal)]
    return [(float(a), float(b), "tag") for a, b in g[["from_ms", "until_ms"]].to_numpy(float)]


# ====================================================================================================== stage: fix caches
def _query(db: str, lo: float, hi: float) -> pd.DataFrame:
    con = wiser_io._connect_readonly(Path(db))
    try:
        return pd.read_sql('SELECT reportid, shortid, timestamp, location_x, location_y, anchors_used, anchors_list FROM "reports" '
                           'WHERE timestamp >= ? AND timestamp < ?', con, params=[int(lo), int(hi)])
    finally:
        con.close()


def fix_job(job: dict) -> dict:
    t_job = time.time()
    S, date = job["S"], job["date"]
    tz, m = S["tz"], S["margin_ms"]
    ctx = FA._ctx(S["acfg"])
    L = S["labels"]
    d0, d1 = day_bounds(date, tz)
    lo, hi = d0 - m, d1 + m
    parts, used = [], []
    for db in S["dbs"]:
        if db["t1"] >= lo and db["t0"] < hi:
            q = _query(db["path"], lo, hi)
            if len(q):
                parts.append(q)
                used.append({"name": db["name"], "sha256": db["sha256"], "rows": int(len(q))})
    out = {"date": date, "dbs": used, "rows": [], "outside": [], "tv_mismatch": 0}
    if not parts:
        out["runtime_s"] = round(time.time() - t_job, 1)
        return out
    df = pd.concat(parts, ignore_index=True)
    sid = df["shortid"].to_numpy(np.int64)
    ts = df["timestamp"].to_numpy(np.float64)
    lab, inside = assign_rows(sid, ts, L, lo, hi)
    # fixes outside every validity window (core day, deduplicated): counted, never tracked
    core = (ts >= d0) & (ts < d1)
    ud = df.loc[core & ~inside, ["shortid", "timestamp"]].drop_duplicates()
    for s, g in ud.groupby("shortid"):
        cached = int(((sid == s) & core & ~inside & (lab >= 0)).sum())
        out["outside"].append({"date": date, "shortid": int(s), "n_outside_dedup": int(len(g)), "n_outside_rows_cached_flagged": cached,
                               "first_local": local(g.timestamp.min(), tz), "last_local": local(g.timestamp.max(), tz)})
    for label in sorted(L.loc[np.unique(lab[lab >= 0]), "label"].unique()):
        if job.get("labels") and label not in job["labels"]:
            continue
        frames = []
        stats = {"dup_groups": 0, "rows_dropped": 0}
        for k in sorted(set(L.index[L.label == label]) & set(np.unique(lab[lab >= 0]))):
            r = L.loc[k]
            sel = lab == k
            sub = df[sel]
            key = r.animal if r.animal else label
            fr, st = B.wiser_frames(sub, {key: int(r.shortid)}, ctx["handling_raw"], ctx["silences"], ctx["adc"], ctx["ids"])
            f = fr[key]
            ww = L[(L.label == label) & (L.shortid == int(r.shortid))][["from_ms", "until_ms"]].to_numpy(float)
            tq = f["t_ms"].to_numpy(float)
            ins = np.zeros(len(f), bool)
            for a_, b_ in ww:
                ins |= (tq >= a_) & (tq < b_)
            out["tv_mismatch"] += int((f["m_tag_validity"].to_numpy(bool) != ~ins).sum())
            f["m_tag_validity"] = ~ins
            frames.append(f)
            stats["dup_groups"] += int(st["dup_groups"])
            stats["rows_dropped"] += int(st["rows_dropped"])
        F = pd.concat(frames, ignore_index=True).sort_values("t_ms", kind="stable").reset_index(drop=True)[B.WISER_COLS]
        od = S["fix_root"] / f"full_{dkey(date)}"
        od.mkdir(parents=True, exist_ok=True)
        p = od / f"{label}.csv.gz"
        existing = p.exists()
        if not existing:
            tmp = od / f"{label}.partial.csv.gz"
            F.to_csv(tmp, index=False)
            os.replace(tmp, p)
        else:
            F = pd.read_csv(p)
        inday = (F.t_ms >= d0) & (F.t_ms < d1)
        out["rows"].append({"date": date, "label": label, "shortids": ";".join(str(s) for s in sorted(F.shortid.unique())), "path": str(p),
                            "rows": int(len(F)), "rows_in_day": int(inday.sum()), "rows_tracked_in_day": int((inday & ~F.m_tag_validity).sum()),
                            "dup_groups": stats["dup_groups"], "rows_dropped": stats["rows_dropped"],
                            "dbs": ";".join(u["name"] for u in used), "db_sha256": ";".join((u["sha256"] or "")[:16] for u in used),
                            "window_local": json.dumps([local(lo, tz), local(hi, tz)]),
                            "m_handling": int(F.m_handling[inday].sum()), "m_silence": int(F.m_silence[inday].sum()),
                            "m_tag_validity": int(F.m_tag_validity[inday].sum()), "m_adc_lane": int(F.m_adc_lane[inday].sum()),
                            "bytes": p.stat().st_size, "existing": existing, "git_commit": C.git_commit(), "writer": WRITER})
    out["runtime_s"] = round(time.time() - t_job, 1)
    return out


def _safe(fn, job):
    try:
        return fn(job)
    except Exception as e:  # noqa: BLE001
        import traceback
        return {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc(), "job": {k: v for k, v in job.items() if k != "S"}}


def _fix_safe(job):
    return _safe(fix_job, job)


def merge_index(path: Path, new: pd.DataFrame, keys: list) -> pd.DataFrame:
    if path.exists() and len(new):
        old = pd.read_csv(path, dtype={k: str for k in keys})
        new = new.astype({k: str for k in keys})
        k_new = set(map(tuple, new[keys].to_numpy()))
        old = old[[tuple(r) not in k_new for r in old[keys].to_numpy()]]
        new = pd.concat([old, new], ignore_index=True)
    if len(new):
        new = new.sort_values(keys).reset_index(drop=True)
        new.to_csv(path, index=False)
    return new


def run_fix(S: dict, out: Path, workers: int, fh, dates: list, labels: list | None) -> None:
    t0 = time.time()
    S["fix_root"].mkdir(parents=True, exist_ok=True)
    jobs = [{"S": S, "date": d, "labels": labels} for d in dates]
    rows, outside, dbu = [], [], []
    with ProcessPoolExecutor(max_workers=max(1, min(workers, 8))) as ex:
        for r in ex.map(_fix_safe, jobs):
            if "error" in r:
                log_to(fh, f"ERROR fix {r['job']}: {r['error']}\n{r['trace']}")
                continue
            rows += r["rows"]
            outside += r["outside"]
            dbu += [{"date": r["date"], **u} for u in r["dbs"]]
            log_to(fh, f"fix {r['date']}: {len(r['rows'])} label files ({sum(x['rows_in_day'] for x in r['rows']):,} fixes in the day, "
                       f"{sum(1 for x in r['rows'] if x['existing'])} existing), DBs {[u['name'] for u in r['dbs']]}, "
                       f"m_tag_validity recomputed != wiser_frames {r['tv_mismatch']}, {r['runtime_s']} s")
    idx = merge_index(S["fix_root"] / f"index_full_{S['cohort']}.csv", pd.DataFrame(rows), ["date", "label"])
    tb = out / "tables"
    pd.DataFrame(outside).to_csv(tb / "fixes_outside_validity_by_day.csv", index=False)
    pd.DataFrame(dbu).to_csv(tb / "db_rows_by_day.csv", index=False)
    write_fix_readme(S, idx)
    log_to(fh, f"stage fix done ({time.time() - t0:.0f} s): {len(rows)} label-day files")


def write_fix_readme(S: dict, idx: pd.DataFrame) -> None:
    readme = S["fix_root"] / "README.md"
    txt = readme.read_text(encoding="utf-8") if readme.exists() else ""
    if FIX_MARK in txt or not len(idx):
        return
    full = idx[idx.path.astype(str).str.contains("full_")]
    mb = full["bytes"].sum() / 1e6
    dbn = sorted(set(";".join(full.dbs.astype(str)).split(";")))
    with open(readme, "a", encoding="utf-8") as f:
        f.write(f"\n\n{FIX_MARK}\n**Full-day caches** (`{DRIVER}`, plan `{PLAN}`, {pd.Timestamp.now(tz=S['tz']).strftime('%Y-%m-%d')}): "
                f"`full_<YYYYMMDD>/<label>.csv.gz`, one file per WISER label and field-PC calendar day (00:00-24:00), window "
                f"day +- 10 min, same function (`build_imu_wiser_cache.wiser_frames`, i.e. the SQL rows of `wiser_night` from every "
                f"DB copy that overlaps the window) and the same columns as the files above, never overwriting. Labels: the animal "
                f"(`SF07` ... `SF12`) inside a tag's validity window of `wiser/configs/rat_identities_{S['cohort']}.csv`; a tag worn at "
                f"the same time as the animal's primary tag -> `<animal>_tag<shortid>`; any other shortid -> `tag_<shortid>`. A file "
                f"holds every fix of its tag(s) in the window; fixes outside the label's validity window(s) are kept with "
                f"`m_tag_validity` = True (recomputed per fix from the label's own window(s)); a tag's fixes outside every window "
                f"that overlaps the day are not cached. `shortid` tells the tags of one label apart (SF11 wears 12378 then 12376). "
                f"DB copies (opened mode=ro, sha256 in the index and the run's `input_provenance.json`): {', '.join(dbn)}. "
                f"{len(full)} files, {mb:.0f} MB. Index: `index_full_{S['cohort']}.csv`.\n")


# ====================================================================================================== stage: IMU seconds
IMU_KEYS_HEAD = FA.IMU_KEYS + ("pitch_deg", "roll_deg")


def load_imu_head(sessions: list, lo: float, hi: float, tz: str) -> dict:
    """FA.load_imu with pitch_deg / roll_deg added (same session selection, concatenation, ordering and dtypes)."""
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
            for k in IMU_KEYS_HEAD:
                d[k] = z[k][m] if k in z.files else np.zeros(int(m.sum()), bool)
            parts.append(d)
    if not parts:
        return {"unix_ms": np.zeros(0), **{k: np.zeros(0) for k in IMU_KEYS_HEAD}, "n_sessions": 0}
    parts.sort(key=lambda d: d["unix_ms"][0])
    out = {k: np.concatenate([d[k] for d in parts]) for k in parts[0]}
    o = np.argsort(out["unix_ms"], kind="stable")
    out = {k: v[o] for k, v in out.items()}
    for k in ("omega_dps", "vedba_ms2", "turn_dps", "pitch_deg", "roll_deg"):
        out[k] = out[k].astype(np.float64)
    for k in ("saturated", "unreliable", "frozen", "invalid"):
        out[k] = out[k].astype(bool)
    out["n_sessions"] = len(parts)
    return out


def head_layer(imu: dict, secs: np.ndarray) -> dict:
    """Per field-PC second (make_imu's per-second definitions on the PC-second grid): turn_net_deg = sum(turn_dps)/50,
    turn_abs_deg = sum(|turn_dps|)/50, pitch_mean = mean pitch, roll_mean = circular mean roll; NaN with < 40 samples
    (turn also NaN when any sample in the second is blanked)."""
    n = len(secs)
    nan = np.full(n, np.nan)
    if not n or not len(imu["unix_ms"]):
        return {"turn_net_deg": nan, "turn_abs_deg": nan.copy(), "pitch_mean": nan.copy(), "roll_mean": nan.copy()}
    s0 = int(secs[0])
    idx = np.floor(imu["unix_ms"] / 1000.0).astype(np.int64) - s0
    inb = (idx >= 0) & (idx < n)
    ix = idx[inb]
    bc = lambda w: np.bincount(ix, weights=np.asarray(w, float), minlength=n)  # noqa: E731
    cnt = np.bincount(ix, minlength=n)
    tr, pi, ro = imu["turn_dps"][inb], imu["pitch_deg"][inb], imu["roll_deg"][inb]
    ftr = np.isfinite(tr)
    with np.errstate(invalid="ignore", divide="ignore"):
        tn = bc(np.where(ftr, tr, 0.0)) / FS
        ta = bc(np.where(ftr, np.abs(tr), 0.0)) / FS
        bad_t = (cnt < MIN_SAMPLES_PER_S) | (bc(~ftr) > 0)
        tn[bad_t] = np.nan
        ta[bad_t] = np.nan
        fp = np.isfinite(pi) & np.isfinite(ro)
        nf = bc(fp)
        pm = bc(np.where(fp, pi, 0.0)) / nf
        rr = np.radians(np.where(fp, ro, 0.0))
        rm = np.degrees(np.arctan2(bc(np.where(fp, np.sin(rr), 0.0)) / nf, bc(np.where(fp, np.cos(rr), 0.0)) / nf))
        pm[nf < MIN_SAMPLES_PER_S] = np.nan
        rm[nf < MIN_SAMPLES_PER_S] = np.nan
    return {"turn_net_deg": tn, "turn_abs_deg": ta, "pitch_mean": pm, "roll_mean": rm}


def imu_seconds_window(imu: dict, ctx: dict, animal: str, lo: float, hi: float, windows: list) -> pd.DataFrame:
    """The failure audit's per-second table on [lo, hi) (its own rule, tag limits = the union of the animal's validity
    windows) + the head layer."""
    ps = FA.per_second_states(imu, ctx, animal, lo, hi, -np.inf, np.inf)
    mid = (ps["sec"].to_numpy(np.float64) + 0.5) * 1000.0
    tv = C.in_any(mid, windows)
    ps["ok"] = ps["ok"].to_numpy(bool) & tv
    ps["still"] = ps["still"].to_numpy(bool) & tv
    ps["state"] = np.where(tv, ps["state"].to_numpy(np.int8), 0).astype(np.int8)
    hl = head_layer(imu, ps["sec"].to_numpy(np.int64))
    for k, v in hl.items():
        ps[k] = v
    return ps[IMU_COLS]


def imu_job(job: dict) -> dict:
    t_job = time.time()
    if P.HAVE_NUMBA:
        P.set_num_threads(1)
    S, animal, date = job["S"], job["animal"], job["date"]
    tz, ext = S["tz"], S["imu_ext_ms"]
    ctx = FA._ctx(S["acfg"])
    d0, d1 = day_bounds(date, tz)
    sess = FA.sessions_for(S["acfg"], ctx, animal, d0 - ext, d1 + ext)
    imu = load_imu_head(sess, d0 - ext, d1 + ext, tz)
    u = imu["unix_ms"]
    n_core = int(((u >= d0) & (u < d1)).sum())
    res = {"animal": animal, "date": date, "sessions": ";".join(s["session"] for s in sess), "n_samples_core": n_core, "written": False}
    if n_core == 0:
        res["runtime_s"] = round(time.time() - t_job, 1)
        return res
    ps = imu_seconds_window(imu, ctx, animal, d0 - ext, d1 + ext, animal_windows(S, animal))
    ps = ps[(ps.sec >= d0 // 1000) & (ps.sec < d1 // 1000)].reset_index(drop=True)
    od = S["imu_root"] / animal
    od.mkdir(parents=True, exist_ok=True)
    p = od / f"{dkey(date)}.csv.gz"
    existing = p.exists()
    if not existing:
        tmp = od / f"{dkey(date)}.partial.csv.gz"
        ps.to_csv(tmp, index=False, float_format="%.6g")
        os.replace(tmp, p)
    else:
        ps = pd.read_csv(p)
    st = ps["state"].to_numpy(int)
    res.update({"written": True, "existing": existing, "path": str(p), "bytes": p.stat().st_size, "n_sec": int(len(ps)),
                "ok_s": int(ps.ok.sum()), "still_s": int((st == 1).sum()), "active_s": int((st == 2).sum()), "loco_s": int((st == 3).sum()),
                "git_commit": C.git_commit(), "writer": WRITER, "runtime_s": round(time.time() - t_job, 1)})
    return res


def _imu_safe(job):
    return _safe(imu_job, job)


def run_imu(S: dict, out: Path, workers: int, fh, dates: list, animals: list) -> None:
    t0 = time.time()
    S["imu_root"].mkdir(parents=True, exist_ok=True)
    jobs = [{"S": S, "animal": a, "date": d} for a in animals for d in dates]
    rows = []
    with ProcessPoolExecutor(max_workers=max(1, min(workers, 14))) as ex:
        for r in ex.map(_imu_safe, jobs):
            if "error" in r:
                log_to(fh, f"ERROR imu {r['job']}: {r['error']}\n{r['trace']}")
                continue
            rows.append(r)
            if r["written"]:
                log_to(fh, f"imu {r['animal']} {r['date']}: ok {r['ok_s'] / 3600:.2f} h (still {r['still_s'] / 3600:.2f} / active "
                           f"{r['active_s'] / 3600:.2f} / loco {r['loco_s'] / 3600:.2f} h), sessions {r['sessions']}"
                           f"{' (existing)' if r['existing'] else ''}, {r['runtime_s']} s")
    R = pd.DataFrame(rows)
    R.to_csv(out / "tables" / "imu_days_all.csv", index=False)
    idx = merge_index(S["imu_root"] / f"index_{S['cohort']}.csv", R[R.written].drop(columns=["written"]), ["animal", "date"])
    write_imu_readme(S, idx)
    log_to(fh, f"stage imu done ({time.time() - t0:.0f} s): {int(R.written.sum())} animal-day files")


def write_imu_readme(S: dict, idx: pd.DataFrame) -> None:
    p = S["imu_root"] / "README.md"
    if p.exists() or not len(idx):
        return
    loco = S["tuned"]["loco"]
    p.write_text(f"""# IMU seconds cache - per field-PC second head-IMU QC, states and head layer (cohort {S['cohort']})

Written by `{DRIVER}` (plan `{PLAN}`), never overwriting. One file per animal and field-PC calendar day with at least one
make_imu session: `<SFxx>/<YYYYMMDD>.csv.gz`, one row per field-PC second `sec` (Unix s; the second [sec, sec + 1) of the
field-PC clock, America/New_York day 00:00-24:00). Index: `index_{S['cohort']}.csv` (sessions, ok / still / active / locomoting
seconds, bytes). Source: the make_imu 50-Hz npz (`D:/3rd_rat_spikes/analysis/imu/<SFxx>/<session>.imu.npz`, field-PC time from
`t_pc_ms`), sessions selected and concatenated as the failure audit does (`analyze_wiser_failure_audit.sessions_for` /
`load_imu`; field-flagged sessions skipped); each day computed with +- 10 min of samples, only the core day written.

Columns (the failure audit's `per_second_states`, unmodified):
- `ok` - IMU QC passed: >= 40 of 50 samples, no saturated / frozen (flag or the audit's derived-signal rule, padded 2 s) /
  invalid / NaN sample, Fusion recovery ('unreliable') in < half the samples, not inside a handling window +- 5 min
  (`cv/configs/cohort3_handling_windows.json`), not inside an all-tag WISER silence +- 120 s, not inside this logger's ADC-lane
  on-window (`cohorts/{S['cohort']}.yaml ephys.adc_lane`), inside one of the animal's tag validity windows
  (`wiser/configs/rat_identities_{S['cohort']}.csv`; union over its tags).
- `still` - ok and VeDBA_1s < theta_a (per-animal `IMU_STILL_THR`, `ephys/imu_lfp_state_check.py`) and omega_1s < 10 deg/s.
- `state` - 0 unusable (not ok), 1 still, 2 active, 3 locomoting (ok, not still, VeDBA_1s >= theta_l = {loco['theta_l']:.4f} m/s^2
  and stride-band fraction sbf >= rho_l = {loco['rho_l']:g}; smoothing-pilot tuned values).
- `vedba_1s` (m/s^2), `omega_1s` (deg/s) - means over the second's finite samples; `sbf` - P[4-7 Hz] / P[1-20 Hz] of the vertical
  earth-frame linear acceleration over the 2-s Hann window [sec - 0.5, sec + 1.5) (NaN when incomplete). `sbf` is meaningful
  only where `ok`: in a second without samples the pilot function (kept unmodified) can return the value of the next 2 s
  of data after the gap.

Head layer (make_imu's per-second definitions recomputed on the field-PC-second grid; use together with `ok`):
- `turn_net_deg` = sum of turn_dps / 50 over the second (deg; turn_dps = head angular velocity about the gravity axis):
  **turn left = positive, counter-clockwise seen from above**; `turn_abs_deg` = sum |turn_dps| / 50 (deg). NaN when the
  second has < 40 samples or any blanked sample.
- `pitch_mean` (deg, mean), `roll_mean` (deg, circular mean) of the Fusion gravity-derived head pitch / roll; NaN with < 40
  finite samples.

This layer is the head-behaviour layer: it is **not** merged into WISER coordinates (head yaw is not observable; the
magnetometer is unusable - `docs/methods/wild_ce64_imu.md`). Floats are written with 6 significant digits. The audit periods'
`imu_seconds` (failure-audit run) are reproduced by these files: see the default-tracks report.
""", encoding="utf-8")


# ====================================================================================================== stage: tracks
def imu_table(imu_root: Path, animal: str, dates: list) -> pd.DataFrame | None:
    parts = []
    for d in dates:
        p = imu_root / animal / f"{dkey(d)}.csv.gz"
        if p.exists():
            parts.append(pd.read_csv(p, usecols=["sec", "ok", "still", "state"]))
    if not parts:
        return None
    T = pd.concat(parts, ignore_index=True).drop_duplicates("sec").sort_values("sec").reset_index(drop=True)
    return T


def track_window(fx: pd.DataFrame, imu: pd.DataFrame | None, d0: float, d1: float, margin_ms: float, spec: dict, tuned: dict,
                 table: dict, tau_ms: int, vc: dict) -> pd.DataFrame:
    """One filter run over the fixes in [d0 - margin, d1 + margin) (t_ms), returning the core rows d0 <= t_ms < d1.
    imu: per-second table (sec, ok, still, state) or None (no IMU: q x 1, no ZUPT = B2 dynamics)."""
    lo, hi = d0 - margin_ms, d1 + margin_ms
    f = fx[(fx["t_ms"] >= lo) & (fx["t_ms"] < hi)].sort_values("t_ms", kind="stable").reset_index(drop=True)
    n = len(f)
    t_ms = f["t_ms"].to_numpy(np.int64)
    t_al = t_ms.astype(np.float64) - float(tau_ms)
    z = f[["x", "y"]].to_numpy(np.float64)
    A = f["anchors_used"].to_numpy(np.float64)
    t = (t_al - float(d0)) / 1000.0
    none = np.zeros(n, bool)
    if imu is not None and len(imu) and n:
        s_lo, s_hi = int(math.floor(lo / 1000.0)), int(math.ceil(hi / 1000.0))
        secs = np.arange(s_lo, s_hi, dtype=np.int64)
        ok_s, still_s, state = np.zeros(len(secs), bool), np.zeros(len(secs), bool), np.zeros(len(secs), np.int8)
        j = imu["sec"].to_numpy(np.int64) - s_lo
        mj = (j >= 0) & (j < len(secs))
        ok_s[j[mj]] = imu["ok"].to_numpy(bool)[mj]
        still_s[j[mj]] = imu["still"].to_numpy(bool)[mj]
        state[j[mj]] = imu["state"].to_numpy(np.int8)[mj]
        still_s &= ok_s
        state = np.where(ok_s, state, 0).astype(np.int8)
        fsec = np.floor(t_al / 1000.0).astype(np.int64)
        ok_f = V3K.DS.lookup(secs, ok_s, fsec, False)
        st_f = V3K.DS.lookup(secs, state, fsec, np.int8(0))
        st_mid, _ = P.step_states(t_al, secs, state)
        loco = V3K.loco_steps(st_mid, int(vc["loco_state"])) if spec.get("mloco", 1.0) != 1.0 else none.copy()
        iv = (V1B.eroded(V1B.still_runs(still_s, secs), float(vc["min_run_s"]), float(vc["erode_s"])) * 1000.0 - float(d0)) / 1000.0
        zupt = V1B.membership(t, iv)[1] if spec.get("zupt") else none.copy()
    else:
        ok_f, st_f, loco, zupt = none.copy(), np.zeros(n, np.int8), none.copy(), none.copy()
    if n:
        r2 = P.r2_from_anchors(A, table)
        Pk, Vk, _, _ = V3K.kf_v3(t, z, r2, np.ones(n, bool), zupt, V3K.qmult(loco, spec.get("mloco", 1.0)), spec, tuned)
    else:
        Pk = Vk = np.zeros((0, 2))
    core = (t_ms >= d0) & (t_ms < d1)
    res = f.loc[core, ["t_ms", "shortid", "x", "y", "anchors_used", "valid", "m_handling", "m_silence", "m_tag_validity", "m_adc_lane"]].copy()
    res = res.rename(columns={"x": "x_raw", "y": "y_raw"}).reset_index(drop=True)
    res.insert(1, "t_al_ms", t_al[core].astype(np.int64))
    res["x"], res["y"] = Pk[core, 0], Pk[core, 1]
    res["vx"], res["vy"] = Vk[core, 0], Vk[core, 1]
    res["imu_ok"] = ok_f[core]
    res["imu_state"] = st_f[core].astype(np.int8)
    res["zupt"] = zupt[core]
    res["loco_boost"] = loco[core]
    return res


def track_job(job: dict) -> dict:
    t_job = time.time()
    if P.HAVE_NUMBA:
        P.set_num_threads(1)
    S, label, date = job["S"], job["label"], job["date"]
    tz, m = S["tz"], S["margin_ms"]
    li = label_info(S, label)
    d0, d1 = day_bounds(date, tz)
    fp = S["fix_root"] / f"full_{dkey(date)}" / f"{label}.csv.gz"
    res = {"label": label, "date": date, "written": False}
    if not fp.exists():
        return res
    fx = pd.read_csv(fp)
    fx = fx[~fx["m_tag_validity"].astype(bool)]
    if not ((fx.t_ms >= d0) & (fx.t_ms < d1)).any():
        return res
    ctx = FA._ctx(S["acfg"])
    imu_files = []
    imu = None
    if li["use_imu"]:
        nb = [(pd.Timestamp(date) + pd.Timedelta(days=k)).strftime("%Y-%m-%d") for k in (-1, 0, 1)]
        imu_files = [d for d in nb if (S["imu_root"] / li["animal"] / f"{dkey(d)}.csv.gz").exists()]
        imu = imu_table(S["imu_root"], li["animal"], nb)
        spec = S["specs"]["V3"]
    else:
        spec = S["specs"]["B2"]
    T = track_window(fx, imu, d0, d1, m, spec, S["tuned"], ctx["table"], li["tau_ms"], S["v3"])
    if not li["implanted"]:
        T["t_al_ms"] = pd.array([pd.NA] * len(T), dtype="Int64")
    T["m_off_animal"] = T["t_ms"].to_numpy(float) >= li["implant_lost_ms"]
    T["method"] = np.where(T["imu_ok"].to_numpy(bool) & li["use_imu"], "V3", "B2")
    for c in ("x", "y", "vx", "vy"):
        T[c] = T[c].round(6)
    T = T[TRACK_COLS]
    od = S["track_root"] / label
    od.mkdir(parents=True, exist_ok=True)
    p = od / f"{dkey(date)}.csv.gz"
    existing = p.exists()
    if not existing:
        W = T.copy()
        for c in TRACK_BOOL:
            W[c] = W[c].astype(np.int8)
        tmp = od / f"{dkey(date)}.partial.csv.gz"
        W.to_csv(tmp, index=False)
        os.replace(tmp, p)
    else:
        T = DT.load_default_track(label, date, root=S["track_root"])
    nsec = len(np.unique(T["t_ms"].to_numpy(np.int64) // 1000))
    n = len(T)
    res.update({"written": True, "existing": existing, "animal": li["animal"], "kind": li["kind"], "shortids": ";".join(str(s) for s in sorted(T.shortid.unique())),
                "n_by_shortid": json.dumps({str(k): int(v) for k, v in T.shortid.value_counts().sort_index().items()}),
                "method_default": li["method_default"], "n_fix": n, "hours": nsec / 3600.0,
                "first_fix_local": local(T.t_ms.min(), tz), "last_fix_local": local(T.t_ms.max(), tz),
                "n_V3": int((T.method == "V3").sum()), "share_V3": float((T.method == "V3").mean()), "share_imu_ok": float(T.imu_ok.mean()),
                "share_zupt": float(T.zupt.mean()), "share_loco_boost": float(T.loco_boost.mean()),
                "n_m_handling": int(T.m_handling.sum()), "n_m_silence": int(T.m_silence.sum()), "n_m_adc_lane": int(T.m_adc_lane.sum()),
                "n_m_off_animal": int(T.m_off_animal.sum()), "anchors_le6_share": float((T.anchors_used <= 6).mean()),
                "tau_s": li["tau_ms"] / 1000.0 if li["implanted"] else np.nan, "tau_assumed": li["tau_assumed"],
                "imu_cache_days": ";".join(imu_files), "path": str(p), "bytes": p.stat().st_size, "git_commit": C.git_commit(),
                "runtime_s": round(time.time() - t_job, 1)})
    return res


def _track_safe(job):
    return _safe(track_job, job)


def _warm() -> None:
    V3K._warm()


def run_tracks(S: dict, out: Path, workers: int, fh, dates: list, labels: list) -> None:
    t0 = time.time()
    S["track_root"].mkdir(parents=True, exist_ok=True)
    _warm()
    jobs = [{"S": S, "label": lab, "date": d} for lab in labels for d in dates]
    rows = []
    with ProcessPoolExecutor(max_workers=max(1, min(workers, 14))) as ex:
        for r in ex.map(_track_safe, jobs):
            if "error" in r:
                log_to(fh, f"ERROR tracks {r['job']}: {r['error']}\n{r['trace']}")
                continue
            if r["written"]:
                rows.append(r)
                log_to(fh, f"track {r['label']} {r['date']}: {r['n_fix']:,} fixes, {r['hours']:.2f} h, V3 {100 * r['share_V3']:.1f} %, "
                           f"ZUPT {100 * r['share_zupt']:.1f} %, loco x10 {100 * r['share_loco_boost']:.1f} %"
                           f"{' (existing)' if r['existing'] else ''}, {r['runtime_s']} s")
    R = pd.DataFrame(rows)
    if len(R):
        R = R.drop(columns=["written"])
    idx = merge_index(S["track_root"] / f"index_{S['cohort']}.csv", R, ["label", "date"])
    write_track_readme(S, idx)
    log_to(fh, f"stage tracks done ({time.time() - t0:.0f} s): {len(rows)} label-day files")


def write_track_readme(S: dict, idx: pd.DataFrame) -> None:
    p = S["track_root"] / "README.md"
    if p.exists() or not len(idx):
        return
    v = S["v3"]
    b2 = S["tuned"]["B2"]
    ta = "; ".join(f"{k}: {v_}" for k, v_ in S["tau_assumed"].items()) or "none"
    taus = ", ".join(f"{k} {v_:g}" for k, v_ in S["taus"].items())
    p.write_text(f"""# Default WISER tracks - cohort {S['cohort']} (method {S['method']}: V3 for the implanted animals, B2 otherwise)

Written by `{DRIVER}` (plan `{PLAN}`), never overwriting; read with `{READER}`
(`load_default_track(label, date)`, `list_default_tracks()`). Report (coverage, reproduction, definitions):
`results/{S['cohort']}/wiser_baseline/reports/{STEM}_{S['cohort']}.md`.

**Positions are in the UNVERIFIED WISER inch frame** (offset origin; no georeference to the paddock until the anchor <-> pole
fit exists). **Do not read V3's 1-s speed or summed path during in-place activity that the head IMU labels 'locomoting' as
translation**: there V3's 1-s speed is +62-69 % above B2's (V3 report, jitter check (ii)) because q x 10 lets fix scatter
through. The default's validation covers only the audit periods (09-03 ... 09-10 nights/days); other days (e.g. 08-30 - 09-02,
rain days) are produced with the same rule but were never audited.

Layout: `<label>/<YYYYMMDD>.csv.gz` = one row per deduplicated WISER fix whose WISER time `t_ms` lies in the field-PC calendar
day [00:00, 24:00) (America/New_York) and inside the label's validity window; each day was filtered with +- 10 min of fixes
(and IMU seconds) on both sides and only the core written, so consecutive days join without a seam. `index_{S['cohort']}.csv` =
one row per label and day (fixes, hours, method share, IMU-ok share, ZUPT / loco shares, mask counts, tau*, IMU cache days).
Inputs: the full-day fix caches `wiser_fix_cache/full_<YYYYMMDD>/<label>.csv.gz` and `imu_seconds_cache/<SFxx>/<YYYYMMDD>.csv.gz`.

Labels: `SF07` ... `SF12` = the animal inside a tag's validity window (`wiser/configs/rat_identities_{S['cohort']}.csv`); a tag
worn at the same time as the animal's longer-valid primary tag -> `<animal>_tag<shortid>` (SF12's second tag 3058 = 12376,
08-30 19:00 -> 08-31 19:24); any shortid outside the identity table -> `tag_<shortid>` (none occur in the four DB copies;
the five females released 09-11 19:40 have no tag in them). Fixes outside every validity window (e.g. 3058 on no animal
08-31 19:24 -> 09-02 08:00, after 09-07 08:20, anything after 09-12 10:10 or before the 08-30 19:00 release) are not tracked.

Method: V3 = one B2 filter (q = {b2['q']:g} in^2/s^3 constant-velocity Kalman + RTS, per-fix noise from `anchors_used`,
chi2 gate {S['tuned']['gate2']:g} + {S['tuned']['n_irls']} Huber IRLS passes, k_H = {S['tuned']['huber_k']:g}) with q x {v['loco_mult']:g} on every
step whose midpoint second is IMU-QC-ok and locomoting, and Huber zero-velocity pseudo-measurements (sigma {v['sigma_zupt_inps']:g} in/s) at
fixes inside runs of >= {v['min_run_s']} IMU-QC-ok still seconds eroded by {v['erode_s']} s at each end (no release); where the IMU QC fails
or no IMU session exists, the same filter runs with B2 dynamics (no splice). B2 = the same kernel without IMU input, for
every label without a head IMU. IMU time alignment: the per-second IMU table is read at t_al = t_ms - tau* (tau* = {taus} s;
assumed: {ta}).

Columns:
- `t_ms` WISER time (Unix ms UTC = field-PC clock); `t_al_ms` = t_ms - tau* (implanted animals only, else empty); `shortid`.
- `x_raw`, `y_raw` (in) the fix; `anchors_used`; `valid` (library flag: >= min anchors, no gap, no raw jump; informational).
- masks (flags, the fix is still used by the filter): `m_handling` (operator round, unpadded), `m_silence` (all-tag WISER
  silence +- 120 s), `m_tag_validity` (always 0 here: such fixes are not tracked), `m_adc_lane` (this logger's ADC-lane
  window), `m_off_animal` (the tag rode on a lost implant: SF11 from {local(S['implant_lost'].get('SF11', np.nan), S['tz'])} -
  `cohorts/{S['cohort']}.yaml ephys.loggers.SF11.implant_lost`, video-confirmed - to the identity table's 09-07 08:20; the
  track there is the tag on the dropped implant - left in the house, retrieved 07:24-08:09 - not the rat).
- `x`, `y` (in), `vx`, `vy` (in/s): the default track (RTS-smoothed position / velocity) at the fix, 6 decimals.
- `method`: V3 where the label has a head IMU and the fix's aligned second is IMU-QC-ok, else B2 (the dynamics in force).
- `imu_ok`, `imu_state` (0 unusable / 1 still / 2 active / 3 locomoting) at the fix's aligned second; `zupt` (the fix carries the
  zero-velocity pseudo-measurement); `loco_boost` (the step ending at this fix had q x {v['loco_mult']:g}).
Booleans are stored as 0/1 (the reader returns bool).
""", encoding="utf-8")


# ====================================================================================================== stage: verify
def periods(acfg: dict, tz: str) -> list:
    return [(pk, C.to_ms(p["start"], tz), C.to_ms(p["end"], tz), p) for pk, p in acfg["periods"].items()]


def dates_covering(lo: float, hi: float, tz: str) -> list:
    a = pd.Timestamp(C.ms_to_local(lo, tz)[:10])
    b = pd.Timestamp(C.ms_to_local(hi - 1, tz)[:10])
    return [d.strftime("%Y-%m-%d") for d in pd.date_range(a, b, freq="D")]


def _eqf(a: np.ndarray, b: np.ndarray) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    both = np.isnan(a) & np.isnan(b)
    d = np.where(both, 0.0, np.abs(a - b))
    d = np.where(np.isnan(d), np.inf, d)
    return float(d.max()) if len(d) else np.nan


def repro_imu_job(job: dict) -> dict:
    S, animal, pk, lo, hi = job["S"], job["animal"], job["pk"], job["lo"], job["hi"]
    aud = pd.read_csv(Path(S["audit_run"]) / "imu_seconds" / f"{animal}_{pk}.csv.gz")
    parts = [pd.read_csv(S["imu_root"] / animal / f"{dkey(d)}.csv.gz") for d in dates_covering(lo, hi, S["tz"])
             if (S["imu_root"] / animal / f"{dkey(d)}.csv.gz").exists()]
    row = {"animal": animal, "period": pk, "n_sec": int(len(aud))}
    if not parts:
        row["missing"] = True
        return row
    T = pd.concat(parts, ignore_index=True).set_index("sec").reindex(aud["sec"].to_numpy())
    okc = T["ok"].astype("boolean").fillna(False).to_numpy(bool)
    stc = T["still"].astype("boolean").fillna(False).to_numpy(bool)
    row.update({"missing": False, "n_cache_missing": int(T["ok"].isna().sum()),
                "ok_agree": float((okc == aud["ok"].to_numpy(bool)).mean()),
                "still_agree": float((stc == aud["still"].to_numpy(bool)).mean()),
                "state_agree": float((T["state"].fillna(-1).astype(int).to_numpy() == aud["state"].to_numpy(int)).mean()),
                "vedba_maxdiff": _eqf(T["vedba_1s"].to_numpy(), aud["vedba_1s"].to_numpy()),
                "omega_maxdiff": _eqf(T["omega_1s"].to_numpy(), aud["omega_1s"].to_numpy()),
                "sbf_maxdiff": _eqf(T["sbf"].to_numpy(), aud["sbf"].to_numpy()),
                "sbf_maxdiff_ok": _eqf(T["sbf"].to_numpy()[aud.ok.to_numpy(bool)], aud["sbf"].to_numpy()[aud.ok.to_numpy(bool)]),
                "sbf_nan_mismatch": int((np.isnan(T["sbf"].to_numpy(float)) != np.isnan(aud["sbf"].to_numpy(float))).sum()),
                "sbf_nan_mismatch_ok": int(((np.isnan(T["sbf"].to_numpy(float)) != np.isnan(aud["sbf"].to_numpy(float))) & aud.ok.to_numpy(bool)).sum()),
                "vedba_maxrel": float(np.nanmax(np.abs(T["vedba_1s"].to_numpy() - aud["vedba_1s"].to_numpy()) / np.maximum(np.abs(aud["vedba_1s"].to_numpy()), 1e-9))),
                "ok_s_audit": int(aud.ok.sum()), "ok_s_cache": int(okc.sum())})
    return row


def repro_v3_job(job: dict) -> dict:
    """Production V3 vs the V3 run's saved V3 (float32) at the same fixes; B2 rebuilt from the full-day caches vs the saved B2."""
    if P.HAVE_NUMBA:
        P.set_num_threads(1)
    S, animal, pk, lo, hi = job["S"], job["animal"], job["pk"], job["lo"], job["hi"]
    tz, m = S["tz"], S["margin_ms"]
    ctx = FA._ctx(S["acfg"])
    with np.load(Path(S["v3_run"]) / "tracks" / f"{animal}_{pk}.npz") as z:
        t_ms = z["t_ms"].astype(np.int64)
        t_al = z["t_al_ms"].astype(np.float64)
        v3s = z["V3"].astype(np.float64)
        b2s = z["B2"].astype(np.float64)
        zs, ls = z["zupt"].astype(bool), z["loco_step"].astype(bool)
    days = dates_covering(lo - m, hi + m, tz)
    pparts = [DT.load_default_track(animal, d, root=S["track_root"]) for d in days if DT.track_path(animal, d, root=S["track_root"]).exists()]
    if not pparts:
        return {"animal": animal, "period": pk, "n_saved": int(len(t_ms)), "missing": True}
    prod = pd.concat(pparts, ignore_index=True)
    li = label_info(S, animal)
    b2parts = []
    for d in days:
        fp = S["fix_root"] / f"full_{dkey(d)}" / f"{animal}.csv.gz"
        if fp.exists():
            fx = pd.read_csv(fp)
            fx = fx[~fx["m_tag_validity"].astype(bool)]
            d0, d1 = day_bounds(d, tz)
            b2parts.append(track_window(fx, None, d0, d1, m, S["specs"]["B2"], S["tuned"], ctx["table"], li["tau_ms"], S["v3"])[["t_ms", "x", "y"]])
    B2p = pd.concat(b2parts, ignore_index=True).set_index("t_ms")
    Pp = prod.set_index("t_ms")
    have = np.isin(t_ms, Pp.index.to_numpy())
    row = {"animal": animal, "period": pk, "n_saved": int(len(t_ms)), "n_missing_in_production": int((~have).sum())}
    tq = t_ms[have]
    pv = Pp.loc[tq, ["x", "y"]].to_numpy(float)
    pb = B2p.reindex(tq)[["x", "y"]].to_numpy(float)
    ta = t_al[have]
    dv = np.hypot(*(pv - v3s[have]).T)
    db = np.hypot(*(pb - b2s[have]).T)
    inwin = (ta >= lo) & (ta < hi)
    core10 = (ta >= lo + 600_000) & (ta < hi - 600_000)
    # effective run edges of the V3 run: >= 10 min of fix coverage (inter-fix intervals capped at 5 s) from its first and
    # last fix - an all-tag silence (operator round) at a window edge leaves the run without data in its margin
    cc = np.r_[0.0, np.cumsum(np.minimum(np.diff(t_al) / 1000.0, 5.0))]
    cov_ok = ((cc >= 600.0) & (cc[-1] - cc >= 600.0))[have]
    core10e = core10 & cov_ok
    edge = np.minimum(ta - lo, hi - ta) / 60000.0
    row.update({"n_win": int(inwin.sum()), "n_core10": int(core10.sum()), "n_core10e": int(core10e.sum()),
                "v3run_first_fix_local": local(float(t_al[0]), tz), "v3run_last_fix_local": local(float(t_al[-1]), tz),
                "V3_maxdiff_core10e_in": float(dv[core10e].max()) if core10e.any() else np.nan,
                "B2_maxdiff_core10e_in": float(np.nanmax(db[core10e])) if core10e.any() else np.nan,
                "V3_n_gt_1e-3_core10": int((dv[core10] > 1e-3).sum()),
                "V3_first_gt_1e-3_core10_local": local(float(t_ms[have][core10][dv[core10] > 1e-3].min()), tz) if (dv[core10] > 1e-3).any() else "",
                "V3_last_gt_1e-3_core10_local": local(float(t_ms[have][core10][dv[core10] > 1e-3].max()), tz) if (dv[core10] > 1e-3).any() else "",
                "V3_maxdiff_core10_in": float(dv[core10].max()) if core10.any() else np.nan,
                "V3_p99diff_core10_in": float(np.percentile(dv[core10], 99)) if core10.any() else np.nan,
                "V3_maxdiff_win_in": float(dv[inwin].max()) if inwin.any() else np.nan,
                "V3_maxdiff_edge_lt1min_in": float(dv[inwin & (edge < 1)].max()) if (inwin & (edge < 1)).any() else np.nan,
                "V3_maxdiff_edge_1_5min_in": float(dv[inwin & (edge >= 1) & (edge < 5)].max()) if (inwin & (edge >= 1) & (edge < 5)).any() else np.nan,
                "V3_maxdiff_edge_5_10min_in": float(dv[inwin & (edge >= 5) & (edge < 10)].max()) if (inwin & (edge >= 5) & (edge < 10)).any() else np.nan,
                "V3_share_gt_1e-3_win": float((dv[inwin] > 1e-3).mean()) if inwin.any() else np.nan,
                "B2_maxdiff_win_in": float(np.nanmax(db[inwin])) if inwin.any() else np.nan,
                "B2_maxdiff_all_in": float(np.nanmax(db)) if len(db) else np.nan,
                "zupt_agree_core10": float((Pp.loc[tq, "zupt"].to_numpy(bool)[core10] == zs[have][core10]).mean()) if core10.any() else np.nan,
                "loco_agree_core10": float((Pp.loc[tq, "loco_boost"].to_numpy(bool)[core10] == ls[have][core10]).mean()) if core10.any() else np.nan})
    return row


def repro_fix_job(job: dict) -> dict:
    S, r = job["S"], job["row"]
    tz = S["tz"]
    ex = pd.read_csv(r["path"])
    wl = json.loads(r["window_local"])
    lo, hi = C.to_ms(wl[0], tz), C.to_ms(wl[1], tz)
    label = r["animal"]
    parts = []
    for d in dates_covering(lo, hi, tz):
        fp = S["fix_root"] / f"full_{dkey(d)}" / f"{label}.csv.gz"
        if fp.exists():
            d0, d1 = day_bounds(d, tz)
            Fd = pd.read_csv(fp)
            parts.append(Fd[(Fd.t_ms >= d0) & (Fd.t_ms < d1)])          # each row from the file whose core day holds it
    out = {"cache": r["key"], "animal": label, "window_local": r["window_local"], "rows_existing": int(len(ex))}
    if not parts:
        out["missing"] = True
        return out
    F = pd.concat(parts, ignore_index=True)
    F = F[(F.t_ms >= lo) & (F.t_ms < hi)].sort_values("t_ms", kind="stable").reset_index(drop=True)
    ex = ex.sort_values("t_ms", kind="stable").reset_index(drop=True)
    j = ex.merge(F, on=["shortid", "t_ms"], how="outer", suffixes=("_e", "_p"), indicator=True)
    both = j[j["_merge"] == "both"]
    out.update({"missing": False, "rows_production": int(len(F)), "only_existing": int((j["_merge"] == "left_only").sum()),
                "only_production": int((j["_merge"] == "right_only").sum())})
    exact = ["reportid", "x", "y", "anchors_used", "anchors_list", "n_list", "dup_n", "m_handling", "m_silence", "m_tag_validity", "m_adc_lane"]
    ne = 0
    for c in exact:
        a, b = both[f"{c}_e"], both[f"{c}_p"]
        if c == "anchors_list":
            k = int((a.fillna("").astype(str) != b.fillna("").astype(str)).sum())
        else:
            k = int((a.to_numpy() != b.to_numpy()).sum())
        out[f"neq_{c}"] = k
        ne += k
    out["neq_exact_total"] = ne
    both = both.sort_values("t_ms", kind="stable")
    tt = both["t_ms"].to_numpy(float)
    rk = np.arange(len(both))
    # >= 60 s AND >= 10 rows from both ends of the window (the rolling median is over rows: after an all-tag silence that
    # touches a window edge, the first fixes are row-neighbours of the edge although minutes away in time)
    far = (tt >= lo + 60_000) & (tt < hi - 60_000) & (rk >= 10) & (rk < len(both) - 10)
    va, vb = both["valid_e"].to_numpy(bool), both["valid_p"].to_numpy(bool)
    out["valid_agree_all"] = float((va == vb).mean()) if len(va) else np.nan
    out["valid_agree_far60s"] = float((va[far] == vb[far]).mean()) if far.any() else np.nan
    sa, sb = both["speed_inps_smooth_e"].to_numpy(float), both["speed_inps_smooth_p"].to_numpy(float)
    out["speed_maxdiff_all"] = _eqf(sa, sb)
    out["speed_maxdiff_far60s"] = _eqf(sa[far], sb[far])
    return out


def _rimu(job):
    return _safe(repro_imu_job, job)


def _rv3(job):
    return _safe(repro_v3_job, job)


def _rfix(job):
    return _safe(repro_fix_job, job)


def existing_fix_caches(S: dict) -> list:
    rows = []
    for f, kcol in (("index_2026c.csv", "night"), ("index_day_2026c.csv", "night"), (f"index_failure_audit_{S['cohort']}.csv", "period")):
        p = S["fix_root"] / f.replace("2026c", S["cohort"])
        if not p.exists():
            continue
        d = pd.read_csv(p)
        for r in d.itertuples():
            rows.append({"key": f"{getattr(r, kcol)}/{r.animal}", "path": r.path, "window_local": r.window_local, "animal": r.animal})
    return rows


def run_verify(S: dict, out: Path, workers: int, fh) -> dict:
    t0 = time.time()
    tb = out / "tables"
    acfg, tz = S["acfg"], S["tz"]
    pers = periods(acfg, tz)
    _warm()
    jobs = [{"S": S, "animal": a, "pk": pk, "lo": lo, "hi": hi} for pk, lo, hi, _ in pers for a in acfg["animals"]]
    res = {}
    with ProcessPoolExecutor(max_workers=max(1, min(workers, 14))) as ex:
        for name, fn, jj in (("repro_imu_seconds", _rimu, jobs), ("repro_v3", _rv3, jobs),
                             ("repro_fix_cache", _rfix, [{"S": S, "row": r} for r in existing_fix_caches(S)])):
            rows = []
            for r in ex.map(fn, jj):
                if "error" in r:
                    log_to(fh, f"ERROR {name} {r['job'].get('animal', r['job'].get('row'))} {r['job'].get('pk', '')}: {r['error']}\n{r['trace']}")
                    continue
                rows.append(r)
            D = pd.DataFrame(rows)
            D.to_csv(tb / f"{name}.csv", index=False)
            res[name] = D
            log_to(fh, f"{name}: {len(D)} rows")
    # coverage
    cov = pd.read_csv(S["track_root"] / f"index_{S['cohort']}.csv", dtype={"date": str})
    cov.to_csv(tb / "coverage_label_day.csv", index=False)
    imu_all = pd.read_csv(tb / "imu_days_all.csv") if (tb / "imu_days_all.csv").exists() else pd.DataFrame()
    noimu = cov[(cov.method_default == "V3") & (cov.share_imu_ok == 0)][["label", "date", "n_fix", "hours", "imu_cache_days"]]
    noimu.to_csv(tb / "no_imu_label_days.csv", index=False)
    res["coverage"], res["no_imu"] = cov, noimu
    log_to(fh, f"stage verify done ({time.time() - t0:.0f} s)")
    return res


# ====================================================================================================== stage: report
def _f(x, nd=2):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x:,.{nd}f}"


def _pc(x, nd=1):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{100 * x:.{nd}f} %"


def shortid_summary(S: dict, out: Path) -> pd.DataFrame:
    tb = out / "tables"
    L, dbsid, tz = S["labels"], S["dbsid"], S["tz"]
    cov = pd.read_csv(S["track_root"] / f"index_{S['cohort']}.csv", dtype={"date": str})
    outside = pd.read_csv(tb / "fixes_outside_validity_by_day.csv") if (tb / "fixes_outside_validity_by_day.csv").exists() else pd.DataFrame(columns=["shortid", "n_outside_dedup"])
    rows = []
    for sid, g in dbsid.groupby("shortid"):
        labs = L[L.shortid == sid]
        lab_txt = "; ".join(f"{r.label} [{local(r.from_ms, tz)[5:16]} → {local(r.until_ms, tz)[5:16]})" for r in labs.itertuples())
        tracked = 0
        for lab in sorted(set(labs.label)):
            for js in cov.loc[cov.label == lab, "n_by_shortid"]:
                tracked += int(json.loads(js).get(str(sid), 0))
        o = outside[outside.shortid == sid]
        rows.append({"shortid": int(sid), "labels": lab_txt or "—", "kind": ";".join(sorted(set(labs.kind))) or "unknown",
                     "dbs": ";".join(g.db), "rows_db": int(g.rows.sum()), "first_local": local(g.t0.min(), tz), "last_local": local(g.t1.max(), tz),
                     "fixes_tracked": tracked, "fixes_outside_validity_dedup": int(o.n_outside_dedup.sum()) if len(o) else 0,
                     "outside_first": o.first_local.min() if len(o) else "", "outside_last": o.last_local.max() if len(o) else "",
                     "appears_only_after_popchange": bool(g.t0.min() >= C.to_ms(S["scope"]["popchange"] + ":00", tz))})
    D = pd.DataFrame(rows)
    D.to_csv(tb / "shortid_summary.csv", index=False)
    return D


def render_report(S: dict, out: Path, meta: dict) -> str:
    tb = out / "tables"
    tz = S["tz"]
    cov = pd.read_csv(tb / "coverage_label_day.csv", dtype={"date": str})
    ri = pd.read_csv(tb / "repro_imu_seconds.csv")
    rv = pd.read_csv(tb / "repro_v3.csv")
    rf = pd.read_csv(tb / "repro_fix_cache.csv")
    sids = pd.read_csv(tb / "shortid_summary.csv")
    noimu = pd.read_csv(tb / "no_imu_label_days.csv", dtype={"date": str})
    fidx = pd.read_csv(S["fix_root"] / f"index_full_{S['cohort']}.csv", dtype={"date": str})
    iidx = pd.read_csv(S["imu_root"] / f"index_{S['cohort']}.csv", dtype={"date": str})
    c = S["cohort"]
    L = []
    w = L.append
    w(f"# Default WISER tracks for all of cohort {c} — production (V3 for the implanted animals, B2 otherwise)\n")
    gits = sorted(set(cov.git_commit.astype(str)) | set(fidx.git_commit.astype(str)) | set(iidx.git_commit.astype(str)))
    w(f"**Status:** production run {meta['run_ts']} (caches written at git `{', '.join(gits)}`; report rendered at "
      f"`{meta['git_commit']}`). **Production only — no new test, no tuning, no "
      f"behavioural or spatial claim.** Plan: [`{PLAN}`](../../../../{PLAN}) (approved 2026-10-04, committed 5281fc6 before any output; "
      f"amendments at its end). Driver `{DRIVER}` (`--selftest` passes); reader `{READER}`. Bulk run: `{out}`; pointer "
      f"`run_manifest_default_tracks_{c}.json`.\n")
    w("The default itself was decided earlier ([V3 report](wiser_baseline_v3_" + c + ".md), "
      "[change_log 2026-10-03](../../../../change_log/2026-10-03-wiser-v3.md)): **V3** for SF07–SF12 wherever the head-IMU QC passes "
      "(the same filter runs with B2 dynamics where it fails or no IMU session exists), **B2** for every other tag. This step only "
      "applies it to every label and day and checks that the production code reproduces the audited numbers.\n")
    w("> **Carry these caveats into every use.** Positions are in the **unverified WISER inch frame** (offset origin; no paddock "
      "georeference until the anchor ↔ pole fit exists). **V3's 1-s speed / summed path during in-place activity that the head IMU "
      "labels 'locomoting' is +62–69 % above B2's — not translation.** The default's validation covers only the audit periods "
      "(09-03 … 09-11); 08-30 – 09-02 (regime A), the other rain days and every other hour are produced with the same rule but "
      "were never audited.\n")
    # ---- outputs
    trk_mb = cov["bytes"].sum() / 1e6
    w("## 1. What was written\n")
    w("| cache / output | path | files | size |\n|---|---|---|---|")
    full = fidx[fidx.path.astype(str).str.contains("full_")]
    w(f"| full-day WISER fixes (day ± 10 min) | `{S['fix_root']}\\full_<YYYYMMDD>\\<label>.csv.gz` + `index_full_{c}.csv` | {len(full)} | {full['bytes'].sum() / 1e6:.0f} MB |")
    w(f"| IMU seconds (QC, states, head layer) | `{S['imu_root']}\\<SFxx>\\<YYYYMMDD>.csv.gz` + `index_{c}.csv` + README | {len(iidx)} | {iidx['bytes'].sum() / 1e6:.0f} MB |")
    w(f"| default tracks | `{S['track_root']}\\<label>\\<YYYYMMDD>.csv.gz` + `index_{c}.csv` + README | {len(cov)} | {trk_mb:.0f} MB |")
    w(f"| run (logs, provenance, tables) | `{out}` | | |\n")
    # ---- inputs
    w("## 2. Inputs\n")
    w("WISER DB copies (one per WISER restart; opened `mode=ro` + `query_only`; spans are the first / last fix of any tag, field-PC local):\n")
    w("| file | first fix | last fix | rows | shortids | sha256 (first 16) |\n|---|---|---|---|---|---|")
    for d in S["dbs"]:
        w(f"| `{d['name']}` | {d['t0_local']} | {d['t1_local']} | {d['rows']:,} | {', '.join(str(s) for s in d['shortids'])} | `{(d['sha256'] or '')[:16]}` |")
    dbs_sorted = sorted(S["dbs"], key=lambda d: d["t0"])
    overlap = any(b["t0"] < a["t1"] for a, b in zip(dbs_sorted[:-1], dbs_sorted[1:]))
    gaps = ", ".join(f"{a['t1_local'][5:16]} → {b['t0_local'][5:16]}" for a, b in zip(dbs_sorted[:-1], dbs_sorted[1:]))
    w(f"\nThe {len(dbs_sorted)} copies {'overlap' if overlap else 'do not overlap'} in time; between consecutive copies there is no "
      f"fix at all ({gaps}). The identity table is `wiser/configs/rat_identities_" + c + ".csv`; the IMU is the make_imu "
      "50-Hz npz under `D:/3rd_rat_spikes/analysis/imu/`; method parameters come unchanged from `wiser/configs/wiser_v3_" + c + ".json` "
      "→ `wiser_imu_smoothing_" + c + ".json` (`tuned`) and the exclusions from `wiser_failure_audit_" + c + ".json`.\n")
    # ---- labels
    w("## 3. Labels\n")
    w("| shortid | label(s) [validity, local) | DBs | first fix | last fix | fixes tracked | fixes outside every window (dedup.) | outside first → last |\n|---|---|---|---|---|---|---|---|")
    for r in sids.itertuples():
        w(f"| {r.shortid} | {r.labels} | {r.dbs.replace('3rdcohort_Spike_2026_', '').replace('.sqlite', '')} | {r.first_local[5:]} | {r.last_local[5:]} | "
          f"{r.fixes_tracked:,} | {r.fixes_outside_validity_dedup:,} | {str(r.outside_first)[5:] if isinstance(r.outside_first, str) else ''} → "
          f"{str(r.outside_last)[5:] if isinstance(r.outside_last, str) else ''} |")
    unk = sids[sids.kind == "unknown"]
    w(f"\n**Unknown shortids: {len(unk)}.** " + ("No shortid outside the identity table appears in any of the four DB copies, so no "
      "`tag_<shortid>` label exists; the five non-implanted females released 09-11 19:40 left no tag in the WISER record (their "
      "tags were never stated)." if not len(unk) else
      "They are tracked with B2 as `tag_<shortid>` (no identity claim); those first seen after 09-11 19:40: " +
      ", ".join(str(s) for s in unk[unk.appears_only_after_popchange].shortid) + "."))
    w(" SF12 wore two tags at once from the release to 08-31 19:24 (3059 = 12377, the primary, first fix 08-31 06:36, and 3058 = "
      "12376): the second gets its own label `SF12_tag12376` (amendment 1). Tag 3058 then carried no animal until SF11's remount "
      "(09-02 08:15) and again after 09-07 08:20 — those fixes are not tracked. SF11's track from the implant loss "
      f"({local(S['implant_lost'].get('SF11', np.nan), tz)}, video-confirmed) to 08:20 is the tag riding on the dropped implant "
      "(left in the house, retrieved 07:24–08:09 per `cohorts/" + c + ".yaml`), not the rat: flagged `m_off_animal` (amendment 3).")
    fix_only = fidx.merge(cov[["label", "date"]], on=["label", "date"], how="left", indicator=True)
    fix_only = fix_only[fix_only["_merge"] == "left_only"]
    first_by = cov.groupby("label").first_fix_local.min()
    w(" First tracked fix per label: " + ", ".join(f"{lab} {v[5:16]}" for lab, v in first_by.items()) + " (release 08-30 19:00)." +
      (" Label-days with a fix-cache file but no tracked fix (all their fixes outside the validity window): " +
       ", ".join(f"{r.label} {r.date}" for r in fix_only.itertuples()) + "." if len(fix_only) else "") + "\n")
    # ---- coverage
    w("## 4. Coverage per label × day\n")
    w("Hours = field-PC seconds holding ≥ 1 tracked fix ÷ 3600; V3 = share of the day's fixes whose aligned second is IMU-QC-ok "
      "(the rest run with B2 dynamics = the IMU fallback).\n")
    labs = sorted(cov.label.unique())
    dates = sorted(cov.date.unique())
    w("| date | " + " | ".join(labs) + " |\n|---|" + "---|" * len(labs))
    for d in dates:
        cells = []
        for lab in labs:
            r = cov[(cov.label == lab) & (cov.date == d)]
            if not len(r):
                cells.append("—")
            else:
                r = r.iloc[0]
                cells.append(f"{r.hours:.1f} h" + (f" · V3 {100 * r.share_V3:.0f} %" if r.method_default == "V3" else ""))
        w(f"| {d} | " + " | ".join(cells) + " |")
    w("\n**Totals per label:**\n")
    w("| label | method | days | fixes | hours | V3 share (fixes) | IMU fallback share | ZUPT share | loco ×10 share | m_handling | m_silence | m_adc_lane | m_off_animal | τ* (s) |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for lab, g in cov.groupby("label"):
        nf = g.n_fix.sum()
        v3 = (g.share_V3 * g.n_fix).sum() / nf
        md = g.method_default.iloc[0]
        tau = g.tau_s.iloc[0]
        w(f"| {lab} | {md} | {len(g)} | {nf:,} | {g.hours.sum():.1f} | {_pc(v3) if md == 'V3' else '—'} | {_pc(1 - v3) if md == 'V3' else '100 % (no IMU)'} | "
          f"{_pc((g.share_zupt * g.n_fix).sum() / nf)} | {_pc((g.share_loco_boost * g.n_fix).sum() / nf)} | {g.n_m_handling.sum():,} | "
          f"{g.n_m_silence.sum():,} | {g.n_m_adc_lane.sum():,} | {g.n_m_off_animal.sum():,} | "
          f"{'' if not np.isfinite(tau) else f'{tau:g}'}{' (assumed)' if isinstance(g.tau_assumed.iloc[0], str) and g.tau_assumed.iloc[0] else ''} |")
    w(f"\n**Label-days of implanted animals with no IMU-QC-ok fix** (B2 dynamics all day; {len(noimu)}): " +
      (", ".join(f"{r.label} {r.date} ({r.hours:.1f} h)" for r in noimu.itertuples()) if len(noimu) else "none") + ".")
    iall = pd.read_csv(tb / "imu_days_all.csv", dtype={"date": str}) if (tb / "imu_days_all.csv").exists() else pd.DataFrame()
    if len(iall):
        nos = iall[~iall.written.astype(bool)]
        w(f" Animal-days in the scope without any make_imu sample: " + (", ".join(f"{r.animal} {r.date}" for r in nos.itertuples()) or "none") + ".\n")
    # ---- reproduction
    w("## 5. Reproduction\n")
    ok_all = ri[["ok_agree", "still_agree", "state_agree"]].min()
    w(f"**(a) IMU seconds vs the failure audit's `imu_seconds`** ({len(ri)} animal-periods, {int(ri.n_sec.sum()):,} seconds; the audit computed "
      f"each period with ± 10 min of samples, the cache each calendar day with ± 10 min and night periods are joined across midnight): "
      f"agreement ok ≥ {_pc(ok_all['ok_agree'], 3)}, still ≥ {_pc(ok_all['still_agree'], 3)}, state ≥ {_pc(ok_all['state_agree'], 3)}; "
      f"seconds missing from the cache {int(ri.n_cache_missing.sum())}; max |Δ| VeDBA_1s {ri.vedba_maxdiff.max():.2g} m/s² (max relative "
      f"{ri.vedba_maxrel.max():.1g}; the cache stores 6 significant digits), omega_1s {ri.omega_maxdiff.max():.2g} °/s, sbf on the "
      f"audit's ok seconds {ri.sbf_maxdiff_ok.max():.2g}. sbf NaN / value mismatches: {int(ri.sbf_nan_mismatch.sum()):,} seconds, "
      f"{int(ri.sbf_nan_mismatch_ok.sum())} of them in an ok second" +
      (" — they sit in QC-failed seconds (e.g. SF10's IMU data gap from 09-06 04:02:08), where the pilot's SBF function reads the "
       "2 s after a data gap when those lie inside the loaded window (the audit's window ended earlier); sbf enters the state "
       "only in ok seconds, so no state differs.\n" if int(ri.sbf_nan_mismatch_ok.sum()) == 0 else ".\n"))
    bigp = rv[rv["V3_n_gt_1e-3_core10"] > 0]
    big_txt = ("; ".join(f"{r.animal} {r.period} {r['V3_n_gt_1e-3_core10']} fixes {str(r['V3_first_gt_1e-3_core10_local'])[11:]}–"
                         f"{str(r['V3_last_gt_1e-3_core10_local'])[11:]} (V3 run's first fix {str(r['v3run_first_fix_local'])[11:]})"
                         for _, r in bigp.iterrows()) if len(bigp) else "none")
    w(f"**(b) Production V3 vs the V3 run's saved V3** (`{S['v3_run']}`, float32; {len(rv)} animal-periods): fixes missing from "
      f"production {int(rv.n_missing_in_production.sum())}; at the {int(rv.n_core10.sum()):,} fixes ≥ 10 min inside the audit "
      f"windows max |Δ| = {rv.V3_maxdiff_core10_in.max():.2g} in (p99 ≤ {rv.V3_p99diff_core10_in.max():.2g} in). Fixes among them "
      f"with |Δ| > 0.001 in: {big_txt}. They are the first fixes after an all-tag silence (operator round) that reaches into "
      f"the audit window's start: the V3 run had no fix — or only an isolated one before the gap — in its margin, so its track "
      f"effectively *starts* at these fixes (a run edge in data terms although minutes inside the window), while production "
      f"carries the earlier fixes. Measured ≥ 10 min from the audit-window edges **and** ≥ 10 min of "
      f"fix coverage (inter-fix intervals capped at 5 s) from the V3 run's first / last fix ({int(rv.n_core10e.sum()):,} fixes): "
      f"max |Δ| = **{rv.V3_maxdiff_core10e_in.max():.2g} in** "
      f"(float32 storage of the saved track); ZUPT / loco masks agree on {_pc(rv.zupt_agree_core10.min(), 3)} / "
      f"{_pc(rv.loco_agree_core10.min(), 3)} of the ≥ 10-min fixes. Closer to the window "
      f"edges production differs by design (the V3 run had no IMU seconds in its ± 10-min margins, production runs continuous days): "
      f"max |Δ| {rv['V3_maxdiff_edge_5_10min_in'].max():.2g} in at 5–10 min, {rv['V3_maxdiff_edge_1_5min_in'].max():.2g} in at "
      f"1–5 min, {rv['V3_maxdiff_edge_lt1min_in'].max():.2g} in within 1 min of an edge. **B2 rebuilt from the full-day caches** "
      f"(same day stitching, no IMU) vs the saved B2: max |Δ| {rv.B2_maxdiff_win_in.max():.2g} in over every window fix (the same "
      f"silence-edge fixes), {rv.B2_maxdiff_core10e_in.max():.2g} in ≥ 10 min from the effective edges — the day stitching and "
      f"the fix caches reproduce B2 to float32 resolution.\n")
    rfm = rf[~rf.missing.astype(bool)] if "missing" in rf else rf
    w(f"**(c) Full-day fix caches vs the existing caches** ({len(rf)} files: nights, days and failure-audit periods, all from "
      f"`3rdcohort_Spike_2026_3_4.sqlite`): rows only in the existing caches {int(rfm.only_existing.sum())}, only in the full-day "
      f"caches {int(rfm.only_production.sum())}; unequal values in reportid / x / y / anchors_used / anchors_list / n_list / dup_n / "
      f"the four masks: {int(rfm.neq_exact_total.sum())} (of {int(rfm.rows_existing.sum()):,} rows). Window-dependent library "
      f"columns: `valid` agrees on ≥ {_pc(rfm.valid_agree_far60s.min(), 4)} of the rows ≥ 60 s and ≥ 10 rows from a window edge "
      f"(≥ {_pc(rfm.valid_agree_all.min(), 4)} overall; its gap flag compares each interval with the window's median interval, "
      f"so a few rows flip anywhere), `speed_inps_smooth` max |Δ| {rfm.speed_maxdiff_far60s.max():.2g} in/s there (floating-point "
      f"noise of the window-relative time origin; {rfm.speed_maxdiff_all.max():.2g} in/s overall: the 7-row rolling median and the "
      f"1-s window are truncated at a window's ends). The filter uses neither column.\n")
    # ---- how to load
    w("## 6. How to load\n")
    w("```python\nimport sys; sys.path.insert(0, r\"<repo>/wiser/src\")\nfrom default_tracks import load_default_track, list_default_tracks\n"
      f"idx = list_default_tracks(\"{c}\")              # label, date, n_fix, hours, share_V3, share_imu_ok, ...\n"
      f"df = load_default_track(\"SF09\", \"2026-09-08\")  # one row per fix: t_ms, t_al_ms, x_raw, y_raw, masks, x, y, vx, vy, method, imu_ok, imu_state, zupt, loco_boost\n"
      "```\n")
    w("A day file holds the fixes with WISER time in [00:00, 24:00) local; concatenating consecutive days gives the continuous "
      "track (each day was filtered with ± 10 min on both sides). Masks are flags — the filter used every tracked fix — so "
      "an analysis drops `m_handling` / `m_silence` / `m_adc_lane` / `m_off_animal` rows itself. The head-IMU per-second layer "
      f"(`{S['imu_root']}`) is joined on `floor(t_al_ms / 1000)`.\n")
    # ---- caveats
    w("## 7. Caveats\n")
    w(f"- SF11's τ*: {S['tau_assumed'].get('SF11', 'n/a')} — flagged in the index (`tau_assumed`).")
    w("- The females' tags are unidentified and absent from the DB copies; after 09-11 19:40 the paddock holds 10 rats, 5 tracked.")
    w("- `SF12_tag12376` uses SF12's IMU and τ* (the tag's own lag was never measured).")
    w("- Production days include periods never audited (08-30 – 09-02 regime A, rain days, every non-audit hour); the default's "
      "validation covers only the audit periods.")
    w("- In-place activity: see the boxed caveat above. Positions: unverified WISER frame; no distance below 14 in is resolvable.\n")
    # ---- definitions
    w("## Definitions\n")
    w("Units: inches (WISER frame, unverified origin), seconds; $t^{\\rm W}_k$ = WISER time of fix $k$ (ms, field-PC clock); "
      "$\\mathcal{D} = [d_0, d_1)$ = a field-PC calendar day (local 00:00–24:00); $m$ = 600 s margin.\n")
    w("### Label and validity\n$$ \\ell(k) = \\begin{cases} a & t^{\\rm W}_k \\in [v^{\\rm from}_{s,a}, v^{\\rm until}_{s,a}) \\text{ for the tag } s \\text{ of fix } k \\text{ and animal } a \\\\ \\varnothing & \\text{otherwise (not tracked)} \\end{cases} $$\n"
      "**Text:** a fix belongs to the animal whose identity-table window for its tag contains its time; a second tag worn at the same "
      "time as the animal's longer-valid tag is labelled `<animal>_tag<shortid>`, an unlisted shortid `tag_<shortid>` (window = "
      "release → end).\n")
    w("### Aligned time\n$$ t^{\\rm al}_k = t^{\\rm W}_k - \\tau^*_a $$\n**Text:** the WISER fix time moved onto the IMU clock by the "
      "animal's measured WISER-behind-IMU lag $\\tau^*_a$ (s; SF11 assumed); IMU per-second values are read at second "
      "$\\lfloor t^{\\rm al}_k / 1000 \\rfloor$.\n")
    w("### Day stitching\n$$ \\hat{\\mathbf p}_k = \\mathrm{V3}\\big(\\{ \\mathbf z_j : t^{\\rm W}_j \\in [d_0 - m, d_1 + m) \\}\\big)_k, \\quad k : t^{\\rm W}_k \\in \\mathcal D $$\n"
      "**Text:** each day is filtered once with 10 min of fixes and IMU seconds on both sides and only the core is written; the "
      "selftest shows the stitched days equal one continuous run.\n")
    w("### V3 / B2 (unchanged; full definitions in the V3 report)\nConstant-velocity Kalman filter + RTS per axis with "
      "$Q_k = q\\,\\mu_k \\begin{pmatrix} \\Delta t^3/3 & \\Delta t^2/2 \\\\ \\Delta t^2/2 & \\Delta t \\end{pmatrix}$, $q = 3$ in²/s³, "
      "$\\mu_k = 10$ if the step's midpoint second is IMU-QC-ok and locomoting else 1; fix noise $R_k = \\mathrm{diag}(\\sigma_x^2, \\sigma_y^2)(A_k)$ "
      "from the anchors-used table; pseudo-measurement $0 = v$ with $\\sigma_Z = 0.25$ in/s at fixes in eroded still runs; χ² gate "
      "13.8155 then 2 Huber IRLS passes ($k_H = 2.5$). B2 = $\\mu_k \\equiv 1$, no pseudo-measurement. **Text:** V3 is B2 wherever "
      "the IMU is unusable.\n")
    w("### Per-fix method\n$$ \\mathrm{method}_k = \\mathrm{V3} \\iff a \\text{ has a head IMU} \\wedge \\mathrm{ok}(\\lfloor t^{\\rm al}_k/1000 \\rfloor) $$\n"
      "**Text:** which dynamics were in force at the fix; the IMU fallback share of a label-day is $1 - $ its V3 share.\n")
    w("### Coverage hours\n$$ H = \\frac{1}{3600} \\big|\\{ \\lfloor t^{\\rm W}_k / 1000 \\rfloor : k \\in \\mathcal D,\\ \\ell(k) = \\text{label} \\}\\big| $$\n"
      "**Text:** hours of the day with at least one tracked fix in the second (h, 0–24).\n")
    w("### Shares\nV3 share $= \\frac{1}{N}\\sum_k \\mathbb 1[\\mathrm{method}_k = \\mathrm{V3}]$; ZUPT share $= \\frac{1}{N}\\sum_k \\mathbb 1[\\text{ZUPT at } k]$; "
      "loco ×10 share $= \\frac{1}{N}\\sum_k \\mathbb 1[\\mu_k = 10]$, $N$ = tracked fixes of the label-day (or label, pooled by fixes).\n")
    w("### Reproduction statistics\nAgreement $= \\frac{1}{|\\mathcal S|}\\sum_{s \\in \\mathcal S} \\mathbb 1[x^{\\rm cache}_s = x^{\\rm audit}_s]$ over the audit "
      "period's seconds $\\mathcal S$ (missing = disagreement); $\\max|\\Delta| = \\max_k \\lVert \\hat{\\mathbf p}^{\\rm prod}_k - \\hat{\\mathbf p}^{\\rm saved}_k \\rVert_2$ "
      "(in) over the fixes common to both, restricted where stated to $t^{\\rm al}_k \\in [\\mathrm{lo} + 10\\,\\mathrm{min}, \\mathrm{hi} - 10\\,\\mathrm{min})$ "
      "of the audit window; the saved tracks are float32 (≈ 3e-5 in resolution at 500 in). Fix-cache comparison: rows matched on "
      "(shortid, t_ms); 'unequal' counts matched rows whose value differs.\n")
    return "\n".join(L) + "\n"


def run_report(S: dict, out: Path, fh, run_ts: str) -> None:
    shortid_summary(S, out)
    c = S["cohort"]
    rdir = output_paths.report_dir(c, DIRECTION)
    rep = rdir / f"{STEM}_{c}.md"
    meta = {"cohort": c, "direction": DIRECTION, "analysis": "wiser_default_tracks", "report": rep.name, "driver": DRIVER, "reader": READER,
            "plan": PLAN, "method": S["method"], "git_commit": C.git_commit(), "run_ts": run_ts,
            "caches": {"fix_full": str(S["fix_root"]), "imu_seconds": str(S["imu_root"]), "tracks": str(S["track_root"])},
            "v3_run": S["v3_run"], "audit_run": S["audit_run"], "dbs": [{k: d[k] for k in ("name", "sha256", "rows", "t0_local", "t1_local")} for d in S["dbs"]]}
    rep.write_text(render_report(S, out, meta), encoding="utf-8")
    output_paths.write_run_manifest(out, out, **meta)
    mp = rdir / f"run_manifest_default_tracks_{c}.json"
    mp.write_text(json.dumps({"run_dir": str(out.resolve()), **meta}, indent=2, default=str) + "\n", encoding="utf-8")
    log_to(fh, f"report {rep}\nmanifest {mp}")


# ====================================================================================================== provenance
def write_provenance(S: dict, out: Path, args) -> None:
    prov = {"plan": PLAN, "driver": DRIVER, "reader": READER, "git_commit": C.git_commit(), "method": S["method"], "cohort": S["cohort"],
            "scope": S["scope"], "dates": S["dates"], "margin_s": S["margin_ms"] / 1000.0, "imu_ext_s": S["imu_ext_ms"] / 1000.0,
            "dbs": [{k: v for k, v in d.items() if k != "shortids"} | {"shortids": d["shortids"]} for d in S["dbs"]],
            "configs": {"v3": S["v3cfg"]["_path"], "audit": S["acfg"]["_path"], "smoothing": S["acfg"]["smoothing_config"],
                        "identities": "wiser/configs/rat_identities_" + S["cohort"] + ".csv", "cohort_yaml": f"cohorts/{S['cohort']}.yaml",
                        "handling": S["acfg"]["handling_json"], "silences": S["acfg"]["silences_csv"], "imu_root": S["acfg"]["imu_root"]},
            "tuned_B2": S["tuned"]["B2"], "irls": {k: S["tuned"][k] for k in ("huber_k", "gate2", "n_irls")}, "loco": S["tuned"]["loco"],
            "v3": S["v3"], "specs": S["specs"], "tau_star_s": S["taus"], "tau_assumed": S["tau_assumed"],
            "implant_lost_local": {k: local(v, S["tz"]) for k, v in S["implant_lost"].items()},
            "labels": S["labels"].assign(from_local=S["labels"].from_ms.map(lambda x: local(x, S["tz"])),
                                         until_local=S["labels"].until_ms.map(lambda x: local(x, S["tz"]))).to_dict("records"),
            "roots": {"fix": str(S["fix_root"]), "imu": str(S["imu_root"]), "tracks": str(S["track_root"])},
            "v3_run": S["v3_run"], "audit_run": S["audit_run"], "numba": P.HAVE_NUMBA, "argv": sys.argv}
    p = out / "input_provenance.json"
    if p.exists():
        old = json.loads(p.read_text(encoding="utf-8"))
        prov["previous_invocations"] = old.get("previous_invocations", []) + [old.get("argv")]
    p.write_text(json.dumps(prov, indent=2, default=str), encoding="utf-8")


# ====================================================================================================== selftest
def selftest() -> int:
    import tempfile
    ok_all = True

    def check(name, cond, info=""):
        nonlocal ok_all
        ok_all &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {info}", flush=True)

    t0 = time.time()
    tuned = {"B2": {"q": 3.0, "mrej": 1e9}, "huber_k": P.HUBER_K, "gate2": P.GATE2, "n_irls": P.N_IRLS}
    vcfg = {"v3": {"sigma_zupt_inps": 0.25, "huber_zupt": True, "loco_mult": 10.0, "loco_state": 3, "min_run_s": 3, "erode_s": 1}, "variants": {}}
    specs = V3K.kf_specs(tuned, vcfg)
    vc = vcfg["v3"]
    table = {k: {"rsd_x": s, "rsd_y": 1.3 * s} for k, s in zip(range(3, 10), (6.5, 4.2, 5.0, 3.5, 2.3, 1.7, 1.4))}
    # 1) day stitching with margins = one continuous run
    syn = V3K._synth(seed=11, dur_s=5400.0)
    base_ms = 1_788_000_000_000
    tau_ms = 150
    fx = pd.DataFrame({"t_ms": np.round(syn["t"] * 1000.0).astype(np.int64) + base_ms + tau_ms, "shortid": 1, "x": syn["z"][:, 0],
                       "y": syn["z"][:, 1], "anchors_used": syn["A"].astype(int), "valid": True, "m_handling": False, "m_silence": False,
                       "m_tag_validity": False, "m_adc_lane": False})
    st = syn["state"].copy()
    okk = np.ones(len(st), bool)
    okk[1000:1300] = False                       # an IMU-QC gap -> B2 dynamics there
    st[~okk] = 0
    imu = pd.DataFrame({"sec": syn["secs"] + base_ms // 1000, "ok": okk, "still": (st == 1) & okk, "state": st})
    day_s = 1800.0
    edges = [base_ms + int(k * day_s * 1000) for k in range(4)]
    stitched = pd.concat([track_window(fx, imu, edges[k], edges[k + 1], 600_000.0, specs["V3"], tuned, table, tau_ms, vc) for k in range(3)],
                         ignore_index=True)
    cont = track_window(fx, imu, edges[0], edges[3], 600_000.0, specs["V3"], tuned, table, tau_ms, vc)
    same_rows = len(stitched) == len(cont) and np.array_equal(stitched.t_ms.to_numpy(), cont.t_ms.to_numpy())
    dd = np.hypot(stitched.x.to_numpy() - cont.x.to_numpy(), stitched.y.to_numpy() - cont.y.to_numpy()) if same_rows else np.array([np.inf])
    dseam = np.min(np.abs(stitched.t_ms.to_numpy()[:, None] - np.array(edges[1:3])[None, :]), axis=1) / 1000.0 if same_rows else np.array([0.0])
    far = dseam >= 1.0
    check("day stitching (+-10-min margins) = one continuous run away from the seams (<= 1e-6 in)", same_rows and float(dd[far].max()) <= 1e-6,
          f"max {float(dd[far].max()):.2e} in at >= 1 s from a seam; {float(dd.max()):.2e} in over all {len(dd)} fixes")
    check("stitched ZUPT / loco masks = the continuous run's", same_rows and np.array_equal(stitched.zupt.to_numpy(), cont.zupt.to_numpy())
          and np.array_equal(stitched.loco_boost.to_numpy(), cont.loco_boost.to_numpy()),
          f"(ZUPT {100 * cont.zupt.mean():.1f} %, loco {100 * cont.loco_boost.mean():.1f} % of fixes)")
    # 2) V3 with no IMU = B2 (same kernel, multiplier 1, no ZUPT), and V3 != B2 with the IMU
    nb = track_window(fx, None, edges[0], edges[3], 600_000.0, specs["V3"], tuned, table, tau_ms, vc)
    b2 = track_window(fx, None, edges[0], edges[3], 600_000.0, specs["B2"], tuned, table, tau_ms, vc)
    imu_bad = imu.assign(ok=False, still=False, state=0)
    nq = track_window(fx, imu_bad, edges[0], edges[3], 600_000.0, specs["V3"], tuned, table, tau_ms, vc)
    d_nb = float(np.max(np.hypot(nb.x - b2.x, nb.y - b2.y)))
    d_nq = float(np.max(np.hypot(nq.x - b2.x, nq.y - b2.y)))
    d_v3 = float(np.max(np.hypot(cont.x - b2.x, cont.y - b2.y)))
    check("V3 with no IMU session = B2, and with every IMU second QC-failed = B2 (exactly)", d_nb == 0.0 and d_nq == 0.0 and not nq.zupt.any(),
          f"(max {d_nb:.1e} / {d_nq:.1e} in; V3 with IMU differs from B2 by up to {d_v3:.2f} in)")
    Pref, _, _ = P.kf_run((b2.t_al_ms.to_numpy(float) - edges[0]) / 1000.0, b2[["x_raw", "y_raw"]].to_numpy(float),
                          P.r2_from_anchors(b2.anchors_used.to_numpy(float), table), [np.ones(len(b2), bool)], [np.zeros(len(b2), np.int8)],
                          [np.zeros(len(b2), np.int8)], [{"q": 3.0, "mrej": 1e9}])
    d_p = float(np.max(np.hypot(*(b2[["x", "y"]].to_numpy(float) - Pref[0]).T)))
    check("B2 through the production path = the smoothing pilot's B2 kernel (<= 1e-6 in)", d_p <= 1e-6, f"max {d_p:.2e} in")
    # 3) label assignment across a tag swap, a second tag, an unknown tag
    ids = pd.DataFrame({"shortid": [12378, 12376, 12377, 12376, 12409], "animal": ["SF11", "SF11", "SF12", "SF12", "SF07"],
                        "from_ms": [0, 120, 0, 0, 0], "until_ms": [100, 250, 300, 60, 300]})
    Lb = build_labels(ids, [12378, 12376, 12377, 12409, 999], 0, 300, ["SF07", "SF11", "SF12"])
    lab_of = {(r.shortid, r.from_ms): r.label for r in Lb.itertuples()}
    check("labels: SF11 keeps one label across its tag swap; SF12's shorter concurrent tag -> SF12_tag12376; unknown -> tag_999",
          lab_of[(12378, 0)] == "SF11" and lab_of[(12376, 120)] == "SF11" and lab_of[(12377, 0)] == "SF12"
          and lab_of[(12376, 0)] == "SF12_tag12376" and lab_of[(999, 0)] == "tag_999" and bool(Lb[Lb.label == "tag_999"].implanted.iloc[0]) is False)
    sid = np.array([12376, 12376, 12376, 12378, 12378, 999, 12377, 12409])
    tt = np.array([30.0, 90.0, 200.0, 50.0, 110.0, 10.0, 30.0, 299.0])
    li, ins = assign_rows(sid, tt, Lb)
    got = [Lb.label[i] if i >= 0 else None for i in li]
    check("fix assignment by time: 3058 at 30 -> SF12_tag12376, at 90 (on no animal) -> not tracked, at 200 -> SF11; 305a after its "
          "window -> not tracked", got == ["SF12_tag12376", None, "SF11", "SF11", None, "tag_999", "SF12", "SF07"]
          and ins.tolist() == [True, False, True, True, False, True, True, True], f"{got}")
    li2, ins2 = assign_rows(sid, tt, Lb, lo=150.0, hi=400.0)
    check("fix-cache assignment of an outside-window fix: nearest window overlapping the day (flagged), else dropped",
          [Lb.label[i] if i >= 0 else None for i in li2][1] == "SF11" and not ins2[1] and [Lb.label[i] if i >= 0 else None for i in li2][4] is None)
    try:
        build_labels(pd.DataFrame({"shortid": [1, 2], "animal": ["SF07", "SF07"], "from_ms": [0, 50], "until_ms": [100, 100]}), [], 0, 1, [])
        bad = False
    except SystemExit:
        bad = True
    check("two concurrent tags of equal span on one animal -> the larger shortid becomes <animal>_tag<sid> (no label carries two tags at once)",
          not bad and set(build_labels(pd.DataFrame({"shortid": [1, 2], "animal": ["SF07", "SF07"], "from_ms": [0, 0], "until_ms": [100, 100]}),
                                       [], 0, 1, []).label) == {"SF07", "SF07_tag2"})
    # 4) head layer on the PC-second grid
    u = 1_788_000_000_000.0 + np.arange(0, 3 * 50) * 20.0
    imu_h = {"unix_ms": u, "turn_dps": np.r_[np.full(50, 10.0), np.full(50, -20.0), np.full(50, 5.0)],
             "pitch_deg": np.full(150, 12.0), "roll_deg": np.r_[np.full(25, 179.0), np.full(25, -179.0), np.full(100, 0.0)]}
    imu_h["turn_dps"][120] = np.nan
    hl = head_layer(imu_h, np.arange(1_788_000_000, 1_788_000_003))
    check("head layer: turn_net = sum/50 (left = +), |turn|, circular roll mean across +-180, blanked sample -> NaN turn",
          np.allclose(hl["turn_net_deg"][:2], [10.0, -20.0]) and np.isnan(hl["turn_net_deg"][2]) and np.allclose(hl["turn_abs_deg"][1], 20.0)
          and abs(abs(hl["roll_mean"][0]) - 180.0) < 1e-6 and np.allclose(hl["pitch_mean"], 12.0), f"{hl['turn_net_deg']}, roll {hl['roll_mean']}")
    # 5) reader round trip
    with tempfile.TemporaryDirectory() as td:
        T = cont.copy()
        T["m_off_animal"] = False
        T["method"] = np.where(T.imu_ok, "V3", "B2")
        T = T[TRACK_COLS]
        W = T.copy()
        for cc in TRACK_BOOL:
            W[cc] = W[cc].astype(np.int8)
        (Path(td) / "SF07").mkdir()
        W.to_csv(Path(td) / "SF07" / "20260908.csv.gz", index=False)
        R = DT.load_default_track("SF07", "2026-09-08", root=td)
        lst = DT.list_default_tracks(root=td)
        try:
            DT.load_default_track("SF07", "2026-09-09", root=td)
            nf = False
        except FileNotFoundError:
            nf = True
        check("reader: round trip (bool / Int64 dtypes, values), listing without an index, FileNotFoundError for a missing day",
              len(R) == len(T) and R.zupt.dtype == bool and str(R.t_al_ms.dtype) == "Int64" and np.allclose(R.x.to_numpy(), T.x.to_numpy())
              and list(lst.label) == ["SF07"] and nf)
    print(f"numba: {P.HAVE_NUMBA}; selftest {time.time() - t0:.1f} s -> {'ALL PASS' if ok_all else 'FAILED'}", flush=True)
    return 0 if ok_all else 1


# ====================================================================================================== main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cohort", default="2026c")
    ap.add_argument("--method", default=DEFAULT_METHOD, choices=list(METHODS))
    ap.add_argument("--labels", nargs="*", default=None)
    ap.add_argument("--dates", nargs="*", default=None, help="YYYY-MM-DD (default: every day of the cohort scope)")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--stages", nargs="*", default=["fix", "imu", "tracks", "verify", "report"],
                    choices=["fix", "imu", "tracks", "verify", "report"])
    ap.add_argument("--run-dir", default=None, help="continue in an existing run dir (logs / tables append there)")
    ap.add_argument("--out-root", default=None, help="override FIELD2026_ANALYSIS_OUT_ROOT for the caches and the run dir (tests)")
    ap.add_argument("--no-hash", action="store_true", help="skip the DB sha256 (tests only)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    t0 = time.time()
    S = setup(a.cohort, a.method, Path(a.out_root) if a.out_root else None, hash_dbs=not a.no_hash)
    if a.run_dir:
        out = Path(a.run_dir)
    else:
        out = output_paths.run_dir(NAME, a.cohort, make_figures=False, root=Path(a.out_root) if a.out_root else None)
    (out / "tables").mkdir(parents=True, exist_ok=True)
    fh = open(out / "log.txt", "a", encoding="utf-8")
    run_ts = out.name.replace(NAME + "_", "")
    log_to(fh, f"=== {pd.Timestamp.now(tz=S['tz']).strftime('%Y-%m-%d %H:%M:%S')} {' '.join(sys.argv)}\nrun dir {out}; git {C.git_commit()}; "
               f"method {S['method']}; numba {P.HAVE_NUMBA}; DBs {[d['name'] for d in S['dbs']]}")
    write_provenance(S, out, a)
    S["labels"].assign(from_local=S["labels"].from_ms.map(lambda x: local(x, S["tz"])),
                       until_local=S["labels"].until_ms.map(lambda x: local(x, S["tz"]))).to_csv(out / "tables" / "labels.csv", index=False)
    pd.DataFrame([{k: v for k, v in d.items() if k != "shortids"} for d in S["dbs"]]).to_csv(out / "tables" / "db_inventory.csv", index=False)
    S["dbsid"].to_csv(out / "tables" / "db_shortids.csv", index=False)
    dates = a.dates or S["dates"]
    labels = a.labels or sorted(S["labels"].label.unique())
    animals = sorted({label_info(S, lab)["animal"] for lab in labels if label_info(S, lab)["implanted"]})
    if "fix" in a.stages:
        run_fix(S, out, a.workers, fh, dates, a.labels)
    if "imu" in a.stages and S["method"] == "V3":
        run_imu(S, out, a.workers, fh, dates, animals)
    if "tracks" in a.stages:
        run_tracks(S, out, a.workers, fh, dates, labels)
    if "verify" in a.stages:
        run_verify(S, out, a.workers, fh)
    if "report" in a.stages:
        run_report(S, out, fh, run_ts)
    log_to(fh, f"done ({time.time() - t0:.0f} s)")
    fh.close()


if __name__ == "__main__":
    main()
