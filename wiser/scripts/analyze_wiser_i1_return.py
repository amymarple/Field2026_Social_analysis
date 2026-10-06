r"""I1 return test: does the raw WISER position come back after a V3 I1 event? (cohort 2026c)

Plan: implementation_plan/2026-10-05-wiser-i1-return-test-and-video-review.md, Part 1 (approved by the user 2026-10-05; committed
d722ec0 before any result; operational details in its "Amendment (Part 1)", written before any number of this step). Report
(full Definitions section): results/<cohort>/wiser_baseline/reports/wiser_baseline_i1_return_<cohort>.md. MEASUREMENT ONLY -
no correction is applied; the production tracks are not modified.

  Events     the IMU-WISER consistency audit's V3 I1 events (the V3 1-s median >= 12 in from its run reference for >= 2 s
             inside a no-locomotion run, trimmed 2 s at both ends) and their matched controls (audit run in the config).
  Positions  from RAW fixes (smoother-independent; unmasked, aligned time): P0 = coordinate-wise median of the fixes in the
             first 2 s of the trimmed run (the I1 reference window); P1 = median of the fixes in [t_end, t_end + 10 s) inside
             the trimmed run, t_end = the end of the event window; a window needs >= 5 s and >= 10 fixes.
  Classes    return |P1 - P0| < 6 in; relocate >= 12 in; ambiguous 6-12 in; censored = no valid post window inside the run.
             Structural note (Amendment (Part 1) 3): the I1 window holds every second >= 12 in, so a shift held until the run
             end is censored by construction; the declared sensitivity S3 (run-end window) classes it.
  Report     class shares (all / excluding censored) by zone, day-night, weather, size, duration, run length, animal; the
             <= 6-anchor share and dispersion ratios of each class's event windows vs the audit's matched controls (the audit's
             enrichment(), 10-min block bootstrap); raw excursion profiles per class; sensitivities S1 (10-s pre window),
             S2 (30-s post window), S3 (run-end window); reproduction of the audit's V3 I1 events from the production tracks.
  Reading    "WISER in-place wandering dominates I1" iff return >= 50 % of the non-censored events AND rho_S(return) >= 1.5
             AND its CI lower bound > 1 AND > rho_S(relocate) -> propose V8 as a new pre-registered test; otherwise V3 stays,
             no correction.
  Validation --with-verdicts <Part-2 export>: confusion table class x video verdict and Cohen's kappa (return <-> stayed,
             relocate <-> moved); the verdicts are the ground truth, nothing is re-tuned on them.

Inputs (read-only): the audit run's tables/events.csv.gz, controls.csv.gz, animals_info.csv, work/disp.npz; the production
default tracks (wiser/src/default_tracks.py). Existing scripts are imported, never modified.

Usage:
  python wiser/scripts/analyze_wiser_i1_return.py --cohort 2026c [--workers 6] [--animals SF07 ...]
  python wiser/scripts/analyze_wiser_i1_return.py --report-only <run_dir>          # re-aggregate + re-render from the run
  python wiser/scripts/analyze_wiser_i1_return.py --render-only <run_dir>          # re-render from the saved aggregate tables
  python wiser/scripts/analyze_wiser_i1_return.py --with-verdicts <export.json|.csv|folder> [--run <run_dir>]
  python wiser/scripts/analyze_wiser_i1_return.py --selftest                       # synthetic data, no field data
"""
from __future__ import annotations

import argparse
import json
import re
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
import default_tracks as DT  # noqa: E402  (reader of the production tracks)
import analyze_imu_wiser_calibration as C  # noqa: E402  (git_commit, true_runs, to_ms; unmodified)
import analyze_wiser_imu_consistency as AC  # noqa: E402  (the audit: load_cfg, per_second_medians, enrichment, analyze_arrays, track_days; unmodified)

DIRECTION = "wiser_baseline"
NAME = "wiser_i1_return"
STEM = f"{DIRECTION}_i1_return"
PLAN = "implementation_plan/2026-10-05-wiser-i1-return-test-and-video-review.md"
DRIVER = "wiser/scripts/analyze_wiser_i1_return.py"
CLASSES = ["return", "ambiguous", "relocate", "censored"]
VARIANTS = ["primary", "S1_pre10", "S2_post30", "S3_runend"]
VLABEL = {"primary": "primary (2-s run-start reference, 10-s post window)", "S1_pre10": "S1: 10-s pre window before the onset",
          "S2_post30": "S2: 30-s post window", "S3_runend": "S3: run-end window (declared, Amendment (Part 1) 3)"}
VERDICTS = ["stayed", "moved", "cannot_tell"]
# categorical slots of the dataviz reference palette (light), as in the audit's figures; text stays neutral
COL = {"return": "#2a78d6", "relocate": "#eb6834", "ambiguous": "#b38a2e", "censored": "#8a8986",
       "ink": "#0b0b0b", "ink2": "#52514e", "grid": "#d9d8d4"}


def log_to(fh, msg: str) -> None:
    print(msg, flush=True)
    if fh is not None:
        fh.write(msg + "\n")
        fh.flush()


# ====================================================================================================== config
def load_cfg(cohort: str, path: str | None = None) -> dict:
    cp = Path(path) if path else REPO / "wiser" / "configs" / f"wiser_i1_return_{cohort}.json"
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    cfg["_path"] = str(cp)
    cfg["_cohort"] = cohort
    return cfg


def load_acfg(cfg: dict) -> dict:
    """The audit's own config (enrichment / bootstrap / i1 keys) - read, never written."""
    return AC.load_cfg(cfg["_cohort"], str(REPO / cfg["audit_config"]))


# ====================================================================================================== core estimators
def window_medians(tf: np.ndarray, P: np.ndarray, a: np.ndarray, b: np.ndarray, min_fix: int) -> tuple[np.ndarray, np.ndarray]:
    """Coordinate-wise median of P at the fixes with time in [a_k, b_k) (NaN when fewer than min_fix fixes or b <= a) and the
    fix counts. tf sorted."""
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    i0 = np.searchsorted(tf, a, "left")
    i1 = np.searchsorted(tf, b, "left")
    n = np.where(b > a, i1 - i0, 0).astype(np.int64)
    out = np.full((len(a), 2), np.nan)
    for k in np.flatnonzero((n >= max(int(min_fix), 1))):
        out[k] = np.median(P[i0[k]:i1[k]], axis=0)
    return out, n


def classify(D: np.ndarray, valid: np.ndarray, ret: float, rel: float) -> np.ndarray:
    """return D < ret; relocate D >= rel; ambiguous otherwise; censored where the windows are not valid."""
    D = np.asarray(D, float)
    with np.errstate(invalid="ignore"):
        c = np.where(D < ret, "return", np.where(D >= rel, "relocate", "ambiguous"))
    return np.where(np.asarray(valid, bool) & np.isfinite(D), c, "censored").astype(object)


def classify_events(E: pd.DataFrame, tf: np.ndarray, P: np.ndarray, cfg: dict) -> pd.DataFrame:
    """Per event (columns run_t0, run_t1, t0, t1 in aligned s): P0, the primary post window and class, and S1-S3.
    Returns one row per event in the order of E."""
    w, cl = cfg["windows"], cfg["classes"]
    ret, rel = float(cl["return_lt_in"]), float(cl["relocate_ge_in"])
    mins, minf = float(w["min_window_s"]), int(w["min_window_fixes"])
    rt0, rt1 = E["run_t0"].to_numpy(float), E["run_t1"].to_numpy(float)
    t0, t1 = E["t0"].to_numpy(float), E["t1"].to_numpy(float)
    P0, n0 = window_medians(tf, P, rt0, rt0 + float(w["pre_ref_s"]), int(w["min_pre_ref_fixes"]))
    pre_ok = n0 >= int(w["min_pre_ref_fixes"])

    def post(a, b):
        b = np.maximum(b, a)
        M, n = window_medians(tf, P, a, b, minf)
        L = b - a
        ok = (L >= mins) & (n >= minf)
        reason = np.where(L < mins, "window<5s", np.where(n < minf, "fixes<10", ""))
        return M, n, L, ok, reason
    R = pd.DataFrame(index=E.index)
    R["p0_x"], R["p0_y"], R["n_pre"] = P0[:, 0], P0[:, 1], n0
    # primary
    M1, n1, L1, ok1, rs1 = post(t1, np.minimum(t1 + float(w["post_s"]), rt1))
    D1 = np.hypot(M1[:, 0] - P0[:, 0], M1[:, 1] - P0[:, 1])
    R["p1_x"], R["p1_y"], R["n_post"], R["post_len_s"], R["dist"] = M1[:, 0], M1[:, 1], n1, L1, D1
    R["cls"] = classify(D1, ok1 & pre_ok, ret, rel)
    R["censor_reason"] = np.where(R["cls"] == "censored", np.where(~pre_ok, "pre_ref", rs1), "")
    # S1: 10-s pre window before the onset (inside the run) as P0, the primary P1
    Ms, ns, Ls, oks, _ = post(np.maximum(t0 - float(w["sens_pre_s"]), rt0), t0)
    Ds1 = np.hypot(M1[:, 0] - Ms[:, 0], M1[:, 1] - Ms[:, 1])
    R["s1_n_pre"], R["s1_pre_len_s"], R["s1_dist"] = ns, Ls, Ds1
    R["s1_cls"] = classify(Ds1, ok1 & oks, ret, rel)
    R["s1_censor_reason"] = np.where(R["s1_cls"] == "censored", np.where(~ok1, "post:" + rs1.astype(object), "pre"), "")
    # S2: 30-s post window
    M2, n2, L2, ok2, rs2 = post(t1, np.minimum(t1 + float(w["sens_post_s"]), rt1))
    D2 = np.hypot(M2[:, 0] - P0[:, 0], M2[:, 1] - P0[:, 1])
    R["s2_n_post"], R["s2_post_len_s"], R["s2_dist"] = n2, L2, D2
    R["s2_cls"] = classify(D2, ok2 & pre_ok, ret, rel)
    R["s2_censor_reason"] = np.where(R["s2_cls"] == "censored", rs2, "")
    # S3: run-end window [max(t_onset, run_t1 - 10), run_t1)
    M3, n3, L3, ok3, rs3 = post(np.maximum(t0, rt1 - float(w["sens_runend_s"])), rt1)
    D3 = np.hypot(M3[:, 0] - P0[:, 0], M3[:, 1] - P0[:, 1])
    R["s3_n_post"], R["s3_post_len_s"], R["s3_dist"] = n3, L3, D3
    R["s3_cls"] = classify(D3, ok3 & pre_ok, ret, rel)
    R["s3_censor_reason"] = np.where(R["s3_cls"] == "censored", rs3, "")
    return R


def profiles(E: pd.DataFrame, P0: np.ndarray, ptil: np.ndarray, s0: int, pc: dict) -> tuple[np.ndarray, np.ndarray]:
    """Distance of the raw 1-s medians from P0 on seconds inside the trimmed run: onset-aligned (u = s - t_onset) and
    end-aligned (u = s - t_end). NaN outside the run or where the 1-s median is undefined."""
    out = []
    for col, lo, hi in (("t0", pc["onset_from_s"], pc["onset_to_s"]), ("t1", pc["end_from_s"], pc["end_to_s"])):
        u = np.arange(int(lo), int(hi) + 1, dtype=np.int64)
        base = np.round(E[col].to_numpy(float)).astype(np.int64)
        S = base[:, None] + u[None, :]
        inside = (S >= np.round(E["run_t0"].to_numpy(float)).astype(np.int64)[:, None]) & \
                 (S < np.round(E["run_t1"].to_numpy(float)).astype(np.int64)[:, None])
        j = np.clip(S - s0, 0, len(ptil) - 1)
        d = np.hypot(ptil[j, 0] - P0[:, 0][:, None], ptil[j, 1] - P0[:, 1][:, None])
        d[~inside] = np.nan
        out.append(d.astype(np.float32))
    return out[0], out[1]


def reproduce_i1(E: pd.DataFrame, ptil_v3: np.ndarray, s0: int, ic: dict) -> pd.DataFrame:
    """The audit's I1 quantities recomputed from the V3 1-s medians for each event's trimmed run [run_t0, run_t1): reference r
    (median of the first ref_s seconds), size (max displacement), duration (seconds >= disp_in), onset (first such second), window
    end (last such second + 1), max consecutive run; plus the V3 displacement maximum over the primary post window (the
    structural property of Amendment (Part 1) 3) and |P0 - r| is added by the caller."""
    ref_s, thr = int(ic["ref_s"]), float(ic["disp_in"])
    rows = []
    for e in E.itertuples():
        a, b = int(round(e.run_t0)) - s0, int(round(e.run_t1)) - s0
        Pm = ptil_v3[a:b]
        Rr = Pm[:ref_s]
        f = np.isfinite(Rr[:, 0]) & np.isfinite(Rr[:, 1])
        if not f.any():
            rows.append({"rep_ok": False})
            continue
        r = np.median(Rr[f], axis=0)
        d = np.hypot(Pm[:, 0] - r[0], Pm[:, 1] - r[1])
        with np.errstate(invalid="ignore"):
            ab = d >= thr
        idx = np.flatnonzero(ab)
        rs = C.true_runs(ab)
        t_end = int(round(e.t1)) - s0
        post = d[t_end - a: min(t_end - a + 10, b - a)] if t_end - a < b - a else np.zeros(0)
        rows.append({"rep_ok": True, "rep_ref_x": r[0], "rep_ref_y": r[1], "rep_size": float(np.nanmax(d)), "rep_dur_s": int(ab.sum()),
                     "rep_t0": float(s0 + a + idx[0]) if len(idx) else np.nan, "rep_t1": float(s0 + a + idx[-1] + 1) if len(idx) else np.nan,
                     "rep_max_consec": max((y - x for x, y in rs), default=0),
                     "v3_post_max_disp": float(np.nanmax(post)) if np.isfinite(post).any() else np.nan})
    return pd.DataFrame(rows, index=E.index)


def analyze_animal_arrays(E: pd.DataFrame, tf: np.ndarray, Praw: np.ndarray, Pv3: np.ndarray | None, cfg: dict, acfg: dict) -> dict:
    """Everything that depends only on arrays (shared by the field run and the selftest). E: one animal's V3 I1 event rows
    (aligned-s columns run_t0, run_t1, t0, t1, and the audit's ref_x, ref_y, size, dur_s); tf sorted aligned s of the unmasked
    fixes; Praw / Pv3 (N, 2) raw fixes / V3 track at those fixes."""
    E = E.reset_index(drop=True)
    lo = min(float(tf.min()), float(E["run_t0"].min()) if len(E) else np.inf)
    hi = max(float(tf.max()), float(E["run_t1"].max()) if len(E) else -np.inf)
    s0 = int(np.floor(lo)) - 2
    n = int(np.ceil(hi)) - s0 + 3
    mf = int(cfg["profile"]["median_min_fix"])
    ptil_raw, _ = AC.per_second_medians(tf, Praw, s0, n, mf)
    R = classify_events(E, tf, Praw, cfg)
    P0 = R[["p0_x", "p0_y"]].to_numpy(float)
    pon, pend = profiles(E, P0, ptil_raw, s0, cfg["profile"])
    if Pv3 is not None:
        ptil_v3, _ = AC.per_second_medians(tf, Pv3, s0, n, int(acfg["i1"]["median_min_fix"]))
        RP = reproduce_i1(E, ptil_v3, s0, acfg["i1"])
        R = pd.concat([R, RP], axis=1)
        R["p0_ref_dist"] = np.hypot(R["p0_x"] - E["ref_x"].to_numpy(float), R["p0_y"] - E["ref_y"].to_numpy(float))
    return {"R": R, "prof_onset": pon, "prof_end": pend}


# ====================================================================================================== field run (one animal)
def process_animal(job: dict) -> dict:
    t_job = time.time()
    cfg, acfg, animal = job["cfg"], job["acfg"], job["animal"]
    E = pd.DataFrame(job["events"])
    days = AC.track_days(cfg["tracks_root"], animal)
    cols = ["t_ms", "t_al_ms", "x_raw", "y_raw", "anchors_used"] + cfg["masks"] + ["x", "y"]
    frames = [DT.load_default_track(animal, d, root=cfg["tracks_root"], columns=cols) for d in days]
    F = pd.concat(frames, ignore_index=True)
    t_al = F["t_al_ms"].astype("float64").to_numpy()
    if not np.isfinite(t_al).all():
        raise ValueError(f"{animal}: t_al_ms missing")
    mask = np.zeros(len(F), bool)
    for m in cfg["masks"]:
        mask |= F[m].to_numpy(bool)
    um = ~mask
    tf = t_al[um] / 1000.0
    Praw = F.loc[um, ["x_raw", "y_raw"]].to_numpy(np.float64)
    Pv3 = F.loc[um, ["x", "y"]].to_numpy(np.float64)
    if np.any(np.diff(tf) < 0):
        o = np.argsort(tf, kind="stable")
        tf, Praw, Pv3 = tf[o], Praw[o], Pv3[o]
    tau = float(np.median(F["t_ms"].to_numpy(np.int64) - F["t_al_ms"].astype("int64").to_numpy()))
    res = analyze_animal_arrays(E, tf, Praw, Pv3, cfg, acfg)
    res["info"] = {"animal": animal, "days": len(days), "fixes_total": int(len(F)), "fixes_unmasked": int(um.sum()),
                   "masked_fixes": int(mask.sum()), "events": int(len(E)), "tau_ms": tau, "runtime_s": round(time.time() - t_job, 1)}
    res["keys"] = E[["animal", "event_id"]].to_dict("list")
    return res


def _process_safe(job: dict) -> dict:
    try:
        return process_animal(job)
    except Exception as e:  # noqa: BLE001
        import traceback
        return {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc(), "animal": job["animal"]}


EVENT_COLS = ["animal", "track", "type", "event_id", "win", "run", "subtype", "run_t0", "run_t1", "run_len_s", "t0", "t1", "peak_t",
              "size", "dur_s", "n_segments", "max_consec_s", "ref_x", "ref_y", "n", "n_le6", "dur", "disp_med", "anchors_med",
              "n_controls", "zone", "zone_detail", "dn", "wx", "hour_ms", "bio", "block"]


def load_audit(cfg: dict) -> dict:
    ar = Path(cfg["audit_run"])
    E = pd.read_csv(ar / "tables" / "events.csv.gz")
    E = E[(E.track == cfg["track"]) & (E.type == cfg["type"])].reset_index(drop=True)
    Ct = pd.read_csv(ar / "tables" / "controls.csv.gz")
    Ct = Ct[(Ct.track == cfg["track"]) & (Ct.type == cfg["type"])].reset_index(drop=True)
    info = pd.read_csv(ar / "tables" / "animals_info.csv")
    return {"E": E[[c for c in EVENT_COLS if c in E.columns]], "Ct": Ct, "info": info, "run": ar}


def run_compute(cfg: dict, workers: int, animals: list | None, fh_holder: dict) -> Path:
    t0 = time.time()
    acfg = load_acfg(cfg)
    out = output_paths.run_dir(NAME, cfg["_cohort"])
    for sub in ("tables", "work", "figures"):
        (out / sub).mkdir(exist_ok=True)
    fh = open(out / "log.txt", "w", encoding="utf-8")
    fh_holder["fh"] = fh
    log_to(fh, f"run dir {out}; git {C.git_commit()}; config {cfg['_path']}; plan {PLAN}; audit run {cfg['audit_run']}")
    AU = load_audit(cfg)
    E = AU["E"]
    animals = animals or cfg["animals"]
    log_to(fh, f"audit V3 I1 events: {len(E):,}; matched controls: {len(AU['Ct']):,}")
    jobs = [{"cfg": cfg, "acfg": acfg, "animal": a, "events": E[E.animal == a].to_dict("list")} for a in animals if (E.animal == a).any()]
    parts, pon, pend, infos = [], [], [], []
    with ProcessPoolExecutor(max_workers=max(1, min(int(workers), 8, len(jobs)))) as ex:
        for r in ex.map(_process_safe, jobs):
            if "error" in r:
                log_to(fh, f"ERROR {r['animal']}: {r['error']}\n{r['trace']}")
                raise RuntimeError(f"animal {r['animal']} failed")
            i = r["info"]
            log_to(fh, f"{i['animal']}: {i['days']} days, {i['fixes_unmasked']:,} unmasked fixes, {i['events']:,} events, {i['runtime_s']} s")
            R = r["R"].copy()
            R.insert(0, "event_id", r["keys"]["event_id"])
            R.insert(0, "animal", r["keys"]["animal"])
            parts.append(R)
            pon.append(r["prof_onset"])
            pend.append(r["prof_end"])
            infos.append(i)
    R = pd.concat(parts, ignore_index=True)
    EC = E.merge(R, on=["animal", "event_id"], how="inner", validate="one_to_one")
    if len(EC) != len(E):
        raise RuntimeError(f"event merge lost rows: {len(EC)} of {len(E)}")
    # integer-ms times (exact; Amendment (Part 1) 1: event times are integer aligned seconds)
    taus = dict(zip(AU["info"].animal, AU["info"].tau_ms))
    for c in ("run_t0", "run_t1", "t0", "t1", "peak_t"):
        EC[c + "_al_ms"] = np.round(EC[c].to_numpy(float) * 1000.0).astype(np.int64)
    EC["onset_pc_ms"] = (EC["t0_al_ms"] + EC["animal"].map(taus).round().astype(np.int64)).astype(np.int64)
    EC["end_pc_ms"] = (EC["t1_al_ms"] + EC["animal"].map(taus).round().astype(np.int64)).astype(np.int64)
    EC["onset_pc"] = [pd.Timestamp(int(v), unit="ms", tz="UTC").tz_convert(cfg["tz"]).strftime("%Y-%m-%d %H:%M:%S") for v in EC["onset_pc_ms"]]
    EC = EC.drop(columns=["run_t0", "run_t1", "t0", "t1", "peak_t"])
    EC.to_csv(out / "tables" / "event_classes.csv.gz", index=False)
    order = pd.concat(parts, ignore_index=True)[["animal", "event_id"]]
    np.savez_compressed(out / "work" / "profiles.npz", onset=np.concatenate(pon), end=np.concatenate(pend),
                        animal=order["animal"].to_numpy(str), event_id=order["event_id"].to_numpy(np.int64))
    pd.DataFrame(infos).to_csv(out / "tables" / "animals_info.csv", index=False)
    prov = {"config": Path(cfg["_path"]).relative_to(REPO).as_posix(), "plan": PLAN, "driver": DRIVER, "git_commit": C.git_commit(),
            "audit_run": cfg["audit_run"], "audit_config": cfg["audit_config"], "tracks_root": cfg["tracks_root"],
            "audit_tables": ["tables/events.csv.gz", "tables/controls.csv.gz", "tables/animals_info.csv", "work/disp.npz"],
            "track_files": int(sum(i["days"] for i in infos)), "animals": animals, "events": int(len(EC)),
            "controls": int(len(AU["Ct"])), "runtime_compute_s": round(time.time() - t0, 1)}
    (out / "input_provenance.json").write_text(json.dumps(prov, indent=2, default=str), encoding="utf-8")
    log_to(fh, f"compute done ({time.time() - t0:.0f} s)")
    return out


# ====================================================================================================== aggregation
def add_bands(EC: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    b = cfg["bands"]
    EC = EC.copy()
    EC["size_band"] = pd.cut(EC["size"], list(b["size_in"]) + [np.inf], right=False, labels=b["size_labels"]).astype(str)
    EC["dur_band"] = pd.cut(EC["dur_s"], list(b["dur_s"]) + [np.inf], right=False, labels=b["dur_labels"]).astype(str)
    EC["runlen_band"] = pd.cut(EC["run_len_s"], list(b["run_len_s"]) + [np.inf], right=True, labels=b["run_len_labels"]).astype(str)
    return EC


STRATA = [("all", None), ("zone", "zone"), ("zone detail", "zone_detail"), ("day/night", "dn"), ("weather", "wx"),
          ("size", "size_band"), ("duration", "dur_band"), ("run length", "runlen_band"), ("run subtype", "subtype"), ("animal", "animal")]
LEVEL_ORDER = {"zone": ["house", "field"], "zone_detail": ["house_1", "house_2", "field"], "dn": ["night", "day", "twilight"],
               "wx": ["rain", "wet", "dry", "unknown"], "subtype": ["all_still", "any_active"]}
VCOL = {"primary": "cls", "S1_pre10": "s1_cls", "S2_post30": "s2_cls", "S3_runend": "s3_cls"}


def share_table(EC: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    rows = []
    b = cfg["bands"]
    order = {**LEVEL_ORDER, "size_band": b["size_labels"], "dur_band": b["dur_labels"], "runlen_band": b["run_len_labels"],
             "animal": sorted(EC["animal"].unique())}
    for v in VARIANTS:
        cc = VCOL[v]
        for sn, col in STRATA:
            levels = ["all"] if col is None else [lv for lv in order[col] if (EC[col] == lv).any()] + \
                sorted(set(EC[col].unique()) - set(order[col]))
            for lv in levels:
                e = EC if col is None else EC[EC[col] == lv]
                k = e[cc].value_counts()
                n = int(len(e))
                ncl = int(sum(k.get(c, 0) for c in ("return", "ambiguous", "relocate")))
                row = {"variant": v, "stratum": sn, "level": lv, "n_events": n, "n_classifiable": ncl}
                for c in CLASSES:
                    row[f"n_{c}"] = int(k.get(c, 0))
                    row[f"share_{c}"] = k.get(c, 0) / n if n else np.nan
                for c in ("return", "ambiguous", "relocate"):
                    row[f"share_{c}_cl"] = k.get(c, 0) / ncl if ncl else np.nan
                rows.append(row)
    return pd.DataFrame(rows)


def enrichment_tables(EC: pd.DataFrame, Ct: pd.DataFrame, dv: np.ndarray, dw: np.ndarray, cfg: dict, acfg: dict, fh=None) -> pd.DataFrame:
    """The audit's enrichment() per class (and variant / zone): event windows of the class's events vs their matched controls."""
    seed0 = int(acfg["bootstrap"]["seed"]) + int(cfg["enrichment_seed_offset"])
    rel = np.union1d(EC["win"].to_numpy(np.int64), Ct["win"].to_numpy(np.int64))
    keep = np.isin(dw, rel)                      # pure efficiency: enrichment() only uses windows with weight > 0
    dvf, dwf = dv[keep], dw[keep]
    combos = [("primary", c, z) for c in CLASSES for z in ("all", "house", "field")] + \
             [(v, c, "all") for v in ("S1_pre10", "S2_post30", "S3_runend") for c in CLASSES]
    rows = []
    for k, (v, c, z) in enumerate(combos):
        t_ = time.time()
        e = EC[EC[VCOL[v]] == c]
        if z != "all":
            e = e[e.zone == z]
        cc = Ct[Ct.zone == z] if z != "all" else Ct
        r = AC.enrichment(e, cc, dvf, dwf, acfg, seed0 + k) if len(e) else {"n_events": 0, "n_controls": 0}
        rows.append({"variant": v, "cls": c, "zone": z, "events_total": int(len(e)), **r})
        log_to(fh, f"  enrichment {v} {c} {z}: events {r.get('n_events', 0):,}, rho_S {r.get('share_ratio', np.nan):.3f} "
                   f"[{r.get('share_ratio_lo', np.nan):.3f}, {r.get('share_ratio_hi', np.nan):.3f}] ({time.time() - t_:.0f} s)")
    return pd.DataFrame(rows)


def reading(SH: pd.DataFrame, EN: pd.DataFrame, cfg: dict) -> dict:
    """The pre-registered reading (Amendment (Part 1) 6) on the primary classes."""
    rr = cfg["reading_rule"]
    a = SH[(SH.variant == "primary") & (SH.stratum == "all")].iloc[0]
    share = float(a["share_return_cl"]) if a["n_classifiable"] else np.nan
    er = EN[(EN.variant == "primary") & (EN.cls == "return") & (EN.zone == "all")]
    el = EN[(EN.variant == "primary") & (EN.cls == "relocate") & (EN.zone == "all")]
    g = lambda d, k: float(d.iloc[0][k]) if len(d) and k in d and pd.notna(d.iloc[0][k]) else np.nan  # noqa: E731
    rho, lo, hi = g(er, "share_ratio"), g(er, "share_ratio_lo"), g(er, "share_ratio_hi")
    rho_rel, rel_lo, rel_hi = g(el, "share_ratio"), g(el, "share_ratio_lo"), g(el, "share_ratio_hi")
    c1 = bool(np.isfinite(share) and share >= float(rr["min_return_share_of_classifiable"]))
    c2 = bool(np.isfinite(rho) and rho >= float(rr["min_return_le6_ratio"]))
    c3 = bool(np.isfinite(lo) and lo > float(rr["return_ci_lower_gt"]))
    c4 = bool(np.isfinite(lo) and np.isfinite(rho_rel) and lo > rho_rel)
    c4_loose = bool(np.isfinite(rho) and np.isfinite(rho_rel) and rho > rho_rel)
    dom = c1 and c2 and c3 and c4
    return {"verdict": "WISER IN-PLACE WANDERING DOMINATES I1" if dom else "NOT ESTABLISHED (otherwise branch)",
            "action": "propose V8 (piecewise-constant position during non-locomoting runs; a relocation accepted only when WISER settles "
                      "at a new stable position) as a new pre-registered test" if dom else "V3 stays, no correction",
            "plan_label": "WISER in-place wandering dominates I1" if dom else "I1 is mainly real movement the IMU missed",
            "n_events": int(a["n_events"]), "n_classifiable": int(a["n_classifiable"]), "n_return": int(a["n_return"]),
            "n_ambiguous": int(a["n_ambiguous"]), "n_relocate": int(a["n_relocate"]), "n_censored": int(a["n_censored"]),
            "return_share_classifiable": share, "c1_return_share_ge_0p5": c1,
            "rho_S_return": rho, "rho_S_return_ci": [lo, hi], "c2_rho_ge_1p5": c2, "c3_ci_lower_gt_1": c3,
            "rho_S_relocate": rho_rel, "rho_S_relocate_ci": [rel_lo, rel_hi], "n_relocate_with_controls": int(g(el, "n_events")) if np.isfinite(g(el, "n_events")) else 0,
            "c4_ci_lower_gt_relocate_point": c4, "c4_loose_point_gt_point": c4_loose, "c4_evaluable": bool(np.isfinite(rho_rel))}


def profile_table(EC: pd.DataFrame, PR: dict, cfg: dict) -> pd.DataFrame:
    """Per class (primary and S3) and alignment: median / quartiles / n of the distance from P0 at each u."""
    key = pd.DataFrame({"animal": PR["animal"], "event_id": PR["event_id"]})
    key["row"] = np.arange(len(key))
    m = EC[["animal", "event_id", "cls", "s3_cls"]].merge(key, on=["animal", "event_id"], how="left")
    rows = []
    pc = cfg["profile"]
    for align, M, lo, hi in (("onset", PR["onset"], pc["onset_from_s"], pc["onset_to_s"]), ("end", PR["end"], pc["end_from_s"], pc["end_to_s"])):
        u = np.arange(int(lo), int(hi) + 1)
        for v, col in (("primary", "cls"), ("S3_runend", "s3_cls")):
            for c in CLASSES:
                rr = m.loc[m[col] == c, "row"].to_numpy(np.int64)
                X = M[rr].astype(np.float64) if len(rr) else np.full((0, len(u)), np.nan)
                with np.errstate(all="ignore"):
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", category=RuntimeWarning)
                        q = np.nanpercentile(X, [25, 50, 75], axis=0) if len(rr) else np.full((3, len(u)), np.nan)
                nn = np.isfinite(X).sum(axis=0) if len(rr) else np.zeros(len(u), int)
                for j, uu in enumerate(u):
                    rows.append({"align": align, "variant": v, "cls": c, "u_s": int(uu), "n": int(nn[j]), "q25": q[0, j], "median": q[1, j], "q75": q[2, j]})
    return pd.DataFrame(rows)


def repro_summary(EC: pd.DataFrame) -> dict:
    if "rep_ok" not in EC:
        return {}
    ok = EC["rep_ok"].astype(bool)
    d_ref = np.hypot(EC["rep_ref_x"] - EC["ref_x"], EC["rep_ref_y"] - EC["ref_y"])[ok]
    d_size = (EC["rep_size"] - EC["size"]).abs()[ok]
    t0m = (np.round(EC["rep_t0"] * 1000).astype("Int64") - EC["t0_al_ms"])[ok]
    t1m = (np.round(EC["rep_t1"] * 1000).astype("Int64") - EC["t1_al_ms"])[ok]
    dd = (EC["rep_dur_s"] - EC["dur_s"])[ok]
    ncl = EC["cls"] != "censored"
    vp = EC.loc[ncl, "v3_post_max_disp"]
    res = {"events": int(len(EC)), "evaluable": int(ok.sum()), "ref_max_in": float(d_ref.max()), "size_max_in": float(d_size.max()),
           "onset_mismatch": int((t0m != 0).sum()), "end_mismatch": int((t1m != 0).sum()), "dur_mismatch": int((dd != 0).sum()),
           "max_consec_lt2": int((EC.loc[ok, "rep_max_consec"] < 2).sum()),
           "v3_post_max_disp_max": float(vp.max()) if len(vp) else np.nan, "v3_post_ge_thr": int((vp >= 12.0).sum()),
           "classifiable": int(ncl.sum())}
    res["pass"] = bool(res["evaluable"] == res["events"] and res["ref_max_in"] <= 1e-6 and res["size_max_in"] <= 1e-6 and res["onset_mismatch"] == 0
                       and res["end_mismatch"] == 0 and res["dur_mismatch"] == 0 and res["max_consec_lt2"] == 0)
    q = EC["p0_ref_dist"].quantile([0.5, 0.9, 0.99]).to_list() if "p0_ref_dist" in EC else [np.nan] * 3
    res["p0_ref_dist_p50_p90_p99"] = q
    return res


def dist_quantiles(EC: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for v, dcol, ccol in (("primary", "dist", "cls"), ("S1_pre10", "s1_dist", "s1_cls"), ("S2_post30", "s2_dist", "s2_cls"), ("S3_runend", "s3_dist", "s3_cls")):
        for sub in ("classifiable", "return", "ambiguous", "relocate"):
            m = EC[ccol] != "censored" if sub == "classifiable" else EC[ccol] == sub
            x = EC.loc[m, dcol].to_numpy(float)
            x = x[np.isfinite(x)]
            q = np.percentile(x, [10, 25, 50, 75, 90]) if len(x) else [np.nan] * 5
            rows.append({"variant": v, "subset": sub, "n": int(len(x)), "p10": q[0], "p25": q[1], "p50": q[2], "p75": q[3], "p90": q[4]})
    return pd.DataFrame(rows)


def aggregate(out: Path, cfg: dict, fh=None) -> dict:
    t0 = time.time()
    acfg = load_acfg(cfg)
    tb = out / "tables"
    EC = add_bands(pd.read_csv(tb / "event_classes.csv.gz"), cfg)
    AU = load_audit(cfg)
    z = np.load(Path(cfg["audit_run"]) / "work" / "disp.npz")
    dv, dw = z["disp"].astype(np.float64), z["win"].astype(np.int64)
    SH = share_table(EC, cfg)
    SH.to_csv(tb / "class_shares.csv", index=False)
    EN = enrichment_tables(EC, AU["Ct"], dv, dw, cfg, acfg, fh)
    EN.to_csv(tb / "enrichment_by_class.csv", index=False)
    pz = np.load(out / "work" / "profiles.npz")
    PR = {k: pz[k] for k in pz.files}
    PT = profile_table(EC, PR, cfg)
    PT.to_csv(tb / "profiles.csv", index=False)
    X = pd.crosstab(EC["cls"], EC["s3_cls"]).reindex(index=CLASSES, columns=CLASSES, fill_value=0)
    X.to_csv(tb / "cross_primary_s3.csv")
    DQ = dist_quantiles(EC)
    DQ.to_csv(tb / "distance_quantiles.csv", index=False)
    CR = pd.concat([EC.groupby(f"{p}censor_reason").size().rename("n").reset_index().rename(columns={f"{p}censor_reason": "reason"}).assign(variant=v)
                    for v, p in (("primary", ""), ("S1_pre10", "s1_"), ("S2_post30", "s2_"), ("S3_runend", "s3_"))], ignore_index=True)
    CR = CR[CR.reason.fillna("") != ""]
    CR.to_csv(tb / "censor_reasons.csv", index=False)
    rd = reading(SH, EN, cfg)
    rp = repro_summary(EC)
    summ = {"reading": rd, "repro": rp, "n_events": int(len(EC)), "audit_run": cfg["audit_run"], "run_dir": str(out),
            "runtime_aggregate_s": round(time.time() - t0, 1)}
    (out / "summary.json").write_text(json.dumps(summ, indent=2, default=str), encoding="utf-8")
    log_to(fh, f"aggregate done ({summ['runtime_aggregate_s']} s): reading {rd['verdict']}; repro pass {rp.get('pass')}")
    return load_aggregate(out, cfg)


def load_aggregate(out: Path, cfg: dict) -> dict:
    tb = out / "tables"
    A = {"EC": add_bands(pd.read_csv(tb / "event_classes.csv.gz"), cfg), "SH": pd.read_csv(tb / "class_shares.csv"),
         "EN": pd.read_csv(tb / "enrichment_by_class.csv"), "PT": pd.read_csv(tb / "profiles.csv"),
         "X": pd.read_csv(tb / "cross_primary_s3.csv", index_col=0), "DQ": pd.read_csv(tb / "distance_quantiles.csv"),
         "CR": pd.read_csv(tb / "censor_reasons.csv"), "INFO": pd.read_csv(tb / "animals_info.csv"),
         "summary": json.loads((out / "summary.json").read_text(encoding="utf-8")), "out": out}
    A["summary"]["reading"]["plan_label"] = str(A["summary"]["reading"]["plan_label"]).replace(" (the plan's label of the otherwise branch)", "")
    vp = tb / "verdict_agreement.json"
    A["VA"] = json.loads(vp.read_text(encoding="utf-8")) if vp.exists() else None
    return A


def reading_by_variant(SH: pd.DataFrame, EN: pd.DataFrame, cfg: dict) -> dict:
    """(Information only; no rule uses it.) The reading rule evaluated on each sensitivity's classes."""
    out = {}
    for v in VARIANTS:
        out[v] = reading(SH[SH.variant == v].assign(variant="primary"), EN[EN.variant == v].assign(variant="primary"), cfg)
    return out


# ====================================================================================================== video verdicts (Part 2)
def _norm_verdict(v, cfg: dict):
    vc = cfg["verdicts"]
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return np.nan
    if isinstance(v, (bool, np.bool_)):
        return "moved" if v else "stayed"
    s = str(v).strip().lower().replace("-", "_")
    if not s or s in ("nan", "none", "todo", ""):
        return np.nan
    if s in [x.lower() for x in vc["moved_values"]]:
        return "moved"
    if s in [x.lower() for x in vc["stayed_values"]]:
        return "stayed"
    if s in [x.lower() for x in vc["cannot_values"]]:
        return "cannot_tell"
    if any(k in s for k in ("cannot", "cant", "can't", "not visible", "not_visible", "unsure", "identity")):
        return "cannot_tell"
    if any(k in s for k in ("stay", "in place", "in_place", "did not", "didn't", "not move", "not_move")):
        return "stayed"
    if "move" in s or "changed" in s:
        return "moved"
    return np.nan                                 # e.g. an I2 answer (turned / ran straight)


def _read_export(p: Path) -> tuple[pd.DataFrame, str, str]:
    """One export file -> rows, reviewer, exported time (string)."""
    if p.suffix.lower() == ".json":
        o = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(o, list):
            return pd.DataFrame(o), "", ""
        rows = o.get("rows")
        if isinstance(rows, list) and rows:
            D = pd.DataFrame(rows)
        elif isinstance(o.get("judgements"), dict):
            D = pd.DataFrame([{"id": k, **(v if isinstance(v, dict) else {"verdict": v})} for k, v in o["judgements"].items()])
        else:
            D = pd.DataFrame()
        return D, str(o.get("reviewer") or ""), str(o.get("exported_local") or o.get("exported") or "")
    D = pd.read_csv(p)
    rv = str(D["reviewer"].dropna().iloc[0]) if "reviewer" in D and D["reviewer"].notna().any() else ""
    return D, rv, ""


def load_verdicts(path: Path, cfg: dict) -> pd.DataFrame:
    """The Part-2 export(s) -> one row per judged I1 event: animal, event_id (or NaN), onset_pc_ms (or NaN), verdict, reviewer,
    source. A folder = the newest export per reviewer (JSON preferred over a CSV of the same name)."""
    path = Path(path)
    if path.is_dir():
        fs = sorted([f for f in path.iterdir() if f.suffix.lower() in (".json", ".csv")], key=lambda f: f.stat().st_mtime)
        stems_json = {f.stem for f in fs if f.suffix.lower() == ".json"}
        fs = [f for f in fs if f.suffix.lower() == ".json" or f.stem not in stems_json]
        by_rev = {}
        for f in fs:                               # later (newer) files overwrite earlier ones of the same reviewer
            D, rv, _ = _read_export(f)
            by_rev[rv or f.stem] = (f, D, rv)
        items = list(by_rev.values())
    else:
        D, rv, _ = _read_export(path)
        items = [(path, D, rv)]
    out = []
    for f, D, rv in items:
        if not len(D):
            continue
        D = D.rename(columns={c: str(c).strip().lower() for c in D.columns})
        vcol = next((c for c in cfg["verdicts"]["verdict_columns"] if c in D.columns and D[c].notna().any()
                     and D[c].astype(str).str.strip().ne("").any()), None)
        if vcol is None:                           # no saved verdict in this export (e.g. the placeholder) -> skipped
            print(f"verdicts: {f} has no saved verdict (looked for {cfg['verdicts']['verdict_columns']}); skipped", flush=True)
            continue
        typ = D["type"].astype(str).str.upper() if "type" in D else pd.Series("", index=D.index)
        if "id" in D:
            typ = typ.where(typ.isin(["I1", "I2"]), D["id"].astype(str).str.extract(r"(I[12])", expand=False).fillna(""))
        # Part 2's join key `event_key` = <animal>|<track>|<type>|<event_id> (Amendment (Part 2) 1 item 7)
        ek = D["event_key"].astype(str).str.split("|", expand=True) if "event_key" in D else None
        if ek is not None and ek.shape[1] >= 4:
            D = D[ek[1].isin(["V3", "None", "nan", ""])] if (ek[1] != "V3").any() else D
            ek = ek.loc[D.index]
            typ = typ.loc[D.index]
            typ = typ.where(typ.isin(["I1", "I2"]), ek[2].str.upper())
            if "animal" not in D:
                D = D.assign(animal=ek[0])
            if not any(c in D.columns for c in ("event_id", "audit_event_id", "eid")):
                D = D.assign(event_id=pd.to_numeric(ek[3], errors="coerce"))
        eid = next((c for c in ("event_id", "audit_event_id", "eid") if c in D.columns), None)
        on = next((c for c in ("onset_pc_ms",) if c in D.columns), None)
        ons = next((c for c in ("onset_pc", "onset_local", "start_local", "event_start_local", "t_onset_pc") if c in D.columns), None)
        R = pd.DataFrame({"animal": D["animal"].astype(str) if "animal" in D else np.nan,
                          "type": typ, "event_id": pd.to_numeric(D[eid], errors="coerce") if eid else np.nan,
                          "verdict_raw": D[vcol], "reviewer": rv or (D["reviewer"].astype(str) if "reviewer" in D else ""),
                          "source": str(f)})
        R["onset_al_ms"] = pd.to_numeric(D["onset_al_ms"], errors="coerce") if "onset_al_ms" in D else np.nan
        R["changed_after_reveal"] = (D["changed_after_reveal"].astype(str).str.lower().isin(["true", "1", "yes"])
                                     if "changed_after_reveal" in D else False)
        if on:
            R["onset_pc_ms"] = pd.to_numeric(D[on], errors="coerce")
        elif ons:
            ts = pd.to_datetime(D[ons].astype(str).str.slice(0, 23), errors="coerce")
            R["onset_pc_ms"] = [int(pd.Timestamp(x).tz_localize(cfg["tz"]).value // 10**6) if pd.notna(x) else np.nan for x in ts]
        else:
            R["onset_pc_ms"] = np.nan
        R["verdict"] = [_norm_verdict(v, cfg) for v in R["verdict_raw"]]
        R = R[(R["type"].isin(["I1", ""])) & R["verdict"].notna()]
        out.append(R)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["animal", "type", "event_id", "verdict", "onset_pc_ms",
                                                                                 "onset_al_ms", "changed_after_reveal", "reviewer"])


def match_verdicts(V: pd.DataFrame, EC: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Join verdict rows to this run's events: (animal, event_id), else (animal, nearest field-PC onset within the tolerance)."""
    tol = float(cfg["verdicts"]["onset_tolerance_s"]) * 1000.0
    keys = EC[["animal", "event_id", "onset_pc_ms", "t0_al_ms", "cls", "s3_cls", "size", "zone", "dn"]]
    rows = []
    for r in V.itertuples():
        hit = None
        if pd.notna(r.event_id):
            h = keys[(keys.animal == r.animal) & (keys.event_id == int(r.event_id))]
            if len(h):
                hit, how = h.iloc[0], "event_id"
        for col, val in (("t0_al_ms", getattr(r, "onset_al_ms", np.nan)), ("onset_pc_ms", r.onset_pc_ms)):
            if hit is not None or not pd.notna(val):
                continue
            h = keys[keys.animal == r.animal]
            if len(h):
                j = int(np.argmin(np.abs(h[col].to_numpy(float) - float(val))))
                if abs(float(h[col].iloc[j]) - float(val)) <= tol:
                    hit, how = h.iloc[j], "onset"
        car = bool(getattr(r, "changed_after_reveal", False))
        if hit is None:
            rows.append({"animal": r.animal, "event_id": r.event_id, "verdict": r.verdict, "matched": False, "how": "", "reviewer": r.reviewer,
                         "changed_after_reveal": car})
            continue
        rows.append({"animal": r.animal, "event_id": int(hit.event_id), "verdict": r.verdict, "matched": True, "how": how, "cls": hit.cls,
                     "s3_cls": hit.s3_cls, "size": hit["size"], "zone": hit.zone, "dn": hit.dn, "reviewer": r.reviewer, "changed_after_reveal": car})
    return pd.DataFrame(rows)


def kappa_2x2(cls: np.ndarray, ver: np.ndarray) -> tuple[float, float, int]:
    """Cohen's kappa of return<->stayed / relocate<->moved on the pairs with cls in {return, relocate} and verdict in {stayed, moved}.
    Returns (kappa, observed agreement, N)."""
    m = np.isin(cls, ["return", "relocate"]) & np.isin(ver, ["stayed", "moved"])
    a = (cls[m] == "return").astype(int)
    b = (ver[m] == "stayed").astype(int)
    N = int(m.sum())
    if N == 0:
        return np.nan, np.nan, 0
    po = float(np.mean(a == b))
    pe = float(a.mean() * b.mean() + (1 - a.mean()) * (1 - b.mean()))
    k = (po - pe) / (1 - pe) if pe < 1 else np.nan
    return k, po, N


def verdict_agreement(M: pd.DataFrame, cfg: dict) -> dict:
    vc = cfg["verdicts"]
    Mm = M[M.matched.astype(bool)] if len(M) else M
    res = {"n_rows": int(len(M)), "n_matched": int(len(Mm)), "n_unmatched": int(len(M) - len(Mm)),
           "n_changed_after_reveal": int(Mm["changed_after_reveal"].astype(bool).sum()) if len(Mm) and "changed_after_reveal" in Mm else 0}
    rng = np.random.default_rng(int(vc["seed"]))
    for v, col in (("primary", "cls"), ("S3_runend", "s3_cls")):
        if not len(Mm):
            res[v] = {}
            continue
        T = pd.crosstab(Mm[col], Mm["verdict"]).reindex(index=CLASSES, columns=VERDICTS, fill_value=0)
        cl, ve = Mm[col].to_numpy(str), Mm["verdict"].to_numpy(str)
        k, po, N = kappa_2x2(cl, ve)
        boots = []
        if N:
            for _ in range(int(vc["n_boot"])):
                j = rng.integers(0, len(cl), len(cl))
                kb, _, nb = kappa_2x2(cl[j], ve[j])
                if nb and np.isfinite(kb):
                    boots.append(kb)
        lo, hi = (float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))) if len(boots) > 20 else (np.nan, np.nan)
        res[v] = {"confusion": T.to_dict(orient="index"), "kappa": k, "kappa_ci": [lo, hi], "observed_agreement": po, "n_kappa": N}
    return res


def run_with_verdicts(path: Path, run: Path, cfg: dict, fh=None) -> dict:
    A = load_aggregate(run, cfg)
    V = load_verdicts(path, cfg)
    if not len(V):
        raise SystemExit(f"no saved I1 verdict found in {path} - nothing written (the report keeps its 'pending' section)")
    M = match_verdicts(V, A["EC"], cfg)
    M.to_csv(run / "tables" / "verdict_matches.csv", index=False)
    VA = verdict_agreement(M, cfg)
    VA["source"] = str(path)
    VA["written"] = pd.Timestamp.now(tz=cfg["tz"]).strftime("%Y-%m-%d %H:%M")
    (run / "tables" / "verdict_agreement.json").write_text(json.dumps(VA, indent=2, default=str), encoding="utf-8")
    log_to(fh, f"verdicts: {VA['n_rows']} rows, {VA['n_matched']} matched; primary kappa {VA.get('primary', {}).get('kappa')}")
    return VA


# ====================================================================================================== figures
def make_figures(A: dict, cfg: dict, fdir: Path, cohort: str) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 8, "axes.edgecolor": COL["ink2"], "axes.labelcolor": COL["ink"], "xtick.color": COL["ink2"],
                         "ytick.color": COL["ink2"], "axes.spines.top": False, "axes.spines.right": False})
    figs = {}
    SH, EN, PT = A["SH"], A["EN"], A["PT"]
    # 1) class shares by stratum, primary and S3
    rows = SH[SH.variant == "primary"][["stratum", "level"]].drop_duplicates().values.tolist()
    rows = [r for r in rows if r[0] != "run subtype"]
    fig, axs = plt.subplots(1, 2, figsize=(11, 0.17 * len(rows) + 1.3), sharey=True)
    for ax, v in zip(axs, ("primary", "S3_runend")):
        S = SH[SH.variant == v].set_index(["stratum", "level"])
        left = np.zeros(len(rows))
        for c in CLASSES:
            vals = np.array([float(S.loc[(s, lv), f"share_{c}"]) if (s, lv) in S.index else np.nan for s, lv in rows])
            ax.barh(np.arange(len(rows)), np.nan_to_num(vals), left=left, color=COL[c], height=0.75, label=c, edgecolor="white", linewidth=0.3)
            left += np.nan_to_num(vals)
        ax.set_xlim(0, 1)
        ax.axvline(0.5, color=COL["ink2"], lw=0.5, ls=":")
        ax.set_title(VLABEL[v] + " — share of events", color=COL["ink"], fontsize=8)
        ax.set_xlabel("share of all events")
    lab = [f"{s}: {lv}" + (f"  (n {int(SH[(SH.variant == 'primary') & (SH.stratum == s) & (SH.level == lv)].n_events.iloc[0]):,})") for s, lv in rows]
    axs[0].set_yticks(np.arange(len(rows)))
    axs[0].set_yticklabels(lab, fontsize=6)
    axs[0].invert_yaxis()
    axs[1].legend(frameon=False, loc="lower right", fontsize=7, ncol=4, bbox_to_anchor=(1.0, 1.04))
    fig.tight_layout()
    p = fdir / f"{STEM}_shares_{cohort}.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    figs["shares"] = p.name
    # 2) enrichment by class
    combos = [("primary", c, z) for c in CLASSES for z in ("all", "house", "field")] + \
             [(v, c, "all") for v in ("S1_pre10", "S2_post30", "S3_runend") for c in CLASSES]
    fig, axs = plt.subplots(1, 2, figsize=(10, 0.2 * len(combos) + 1.2), sharey=True)
    for ax, (q, lab_) in zip(axs, (("share_ratio", "≤ 6-anchor share ratio (event / matched control)"), ("disp_ratio", "dispersion ratio"))):
        for i, (v, c, z) in enumerate(combos):
            r = EN[(EN.variant == v) & (EN.cls == c) & (EN.zone == z)]
            if not len(r) or q not in r or not np.isfinite(r[q].iloc[0]):
                continue
            val, lo, hi = r[q].iloc[0], r[q + "_lo"].iloc[0], r[q + "_hi"].iloc[0]
            ax.plot([lo, hi], [i, i], color=COL[c], lw=1.2)
            ax.plot([val], [i], "o", color=COL[c], ms=3.5)
        ax.axvline(1.0, color=COL["ink2"], lw=0.7)
        if q == "share_ratio":
            ax.axvline(1.5, color=COL["ink2"], lw=0.7, ls="--")
            ax.set_xscale("log")
            ax.set_xlim(0.3, 6.0)
            ax.set_xticks([0.5, 1, 1.5, 2, 4])
            ax.set_xticklabels(["0.5", "1", "1.5", "2", "4"])
        ax.set_title(lab_, color=COL["ink"], fontsize=8)
        ax.grid(axis="x", color=COL["grid"], lw=0.5)
    axs[0].set_yticks(np.arange(len(combos)))
    axs[0].set_yticklabels([f"{v.split('_')[0]} · {c} · {z}" for v, c, z in combos], fontsize=6)
    axs[0].invert_yaxis()
    fig.tight_layout()
    p = fdir / f"{STEM}_enrichment_{cohort}.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    figs["enrichment"] = p.name
    # 3) excursion profiles (primary classes; S3 relocate dashed)
    fig, axs = plt.subplots(1, 2, figsize=(11, 3.4), gridspec_kw={"width_ratios": [1.6, 1]})
    for ax, align, xl in ((axs[0], "onset", "time from the event onset (s)"), (axs[1], "end", "time from the event-window end (s)")):
        for c in CLASSES:
            d = PT[(PT["align"] == align) & (PT.variant == "primary") & (PT.cls == c)].sort_values("u_s")
            ok = d.n >= 10
            if not ok.any():
                continue
            nmax = int(d.n.max())
            ax.plot(d.u_s[ok], d["median"][ok], color=COL[c], lw=1.3, label=f"{c} (n ≤ {nmax:,})")
            ax.fill_between(d.u_s[ok], d.q25[ok], d.q75[ok], color=COL[c], alpha=0.15, lw=0)
        d = PT[(PT["align"] == align) & (PT.variant == "S3_runend") & (PT.cls == "relocate")].sort_values("u_s")
        ok = d.n >= 10
        if ok.any():
            ax.plot(d.u_s[ok], d["median"][ok], color=COL["relocate"], lw=1.0, ls="--", label=f"S3 relocate (n ≤ {int(d.n.max()):,})")
        for yv in (6, 12):
            ax.axhline(yv, color=COL["ink2"], lw=0.5, ls=":")
        ax.axvline(0, color=COL["ink2"], lw=0.5)
        ax.set_xlabel(xl)
        ax.set_ylabel("median raw distance from P0 (in)")
        ax.grid(color=COL["grid"], lw=0.4)
        ax.set_axisbelow(True)
    axs[0].legend(frameon=False, fontsize=7)
    axs[0].set_title("Raw-WISER excursion profile (1-s raw medians inside the trimmed run; band = quartiles)", color=COL["ink"], fontsize=8)
    fig.tight_layout()
    p = fdir / f"{STEM}_profiles_{cohort}.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    figs["profiles"] = p.name
    return figs


# ====================================================================================================== report
def _f(x, nd: int = 2) -> str:
    try:
        if x is None or not np.isfinite(float(x)):
            return "–"
    except (TypeError, ValueError):
        return str(x)
    return f"{float(x):,.{nd}f}"


def _pc(x, nd: int = 1) -> str:
    try:
        return "–" if x is None or not np.isfinite(float(x)) else f"{100 * float(x):.{nd}f} %"
    except (TypeError, ValueError):
        return "–"


def _ci(r, q: str, nd: int = 2) -> str:
    try:
        v = float(r[q])
    except (KeyError, TypeError, ValueError):
        return "–"
    return f"{_f(v, nd)} [{_f(r[q + '_lo'], nd)}, {_f(r[q + '_hi'], nd)}]" if np.isfinite(v) else "–"


DEFINITIONS = r"""
## Definitions

All positions in the WISER native **inch** frame (UNVERIFIED offset origin; only distances are used). Times are aligned
seconds $t^{\rm al} = t_{\rm WISER} - \tau^*_a$ (the field-PC / IMU clock; $\tau^*$ per animal from the production tracks);
lists give field-PC time. Symbols: an event $e$ of the audit (V3, I1) with trimmed run $[t^{e}_{r0}, t^{e}_{r1})$, onset
$t^{e}_{\rm on}$ and window end $t^{e}_{\rm end}$ (integer seconds); $k$ a raw fix with aligned time $t_k$, position
$\mathbf z_k = (x^{\rm raw}_k, y^{\rm raw}_k)$ and anchors $A_k$; only fixes with none of the masks `m_handling`, `m_silence`,
`m_tag_validity`, `m_adc_lane`, `m_off_animal` (the audit's fix set). $\operatorname{med}_{\rm c}$ = coordinate-wise median.

### The audit's I1 event (input, not redefined)
Run = maximal stretch of included seconds with IMU state still / active, ≥ 5 s, trimmed 2 s at both ends; $\tilde{\mathbf p}(s)$ =
$\operatorname{med}_{\rm c}$ of the V3 track at the fixes in $[s, s+1)$ (≥ 2 fixes); reference $\mathbf r$ = $\operatorname{med}_{\rm c}$ of
$\tilde{\mathbf p}$ over the first 2 s of the trimmed run; $d(s) = \lVert\tilde{\mathbf p}(s) - \mathbf r\rVert$; event iff $d \ge 12$ in for
≥ 2 consecutive seconds; window $W_e = \{s : d(s) \ge 12\}$ (inside the trimmed run); $t_{\rm on} = \min W_e$, $t_{\rm end} = \max W_e + 1$;
size $= \max_s d(s)$; duration $= |W_e|$ (s). **Text:** the V3 track moves ≥ 12 in from where the run started while the head IMU
never reports locomotion (consistency audit, `change_log/2026-10-05-wiser-imu-consistency.md`).

### Window median and validity
$$ \mathbf M[a, b) = \operatorname{med}_{\rm c}\{\mathbf z_k : t_k \in [a, b)\}, \qquad n[a,b) = \#\{k : t_k \in [a, b)\} $$
A post (or S1 pre) window is **valid** iff $b - a \ge 5$ s and $n[a, b) \ge 10$ fixes. **Text:** a robust position estimate from the
raw fixes alone (no smoother), required to rest on ≥ 5 s and ≥ 10 fixes. Thresholds 5 s / 10 fixes fixed in the plan **[op]**.

### Start and end positions ($\mathbf P_0$, $\mathbf P_1$)
$$ \mathbf P_0 = \mathbf M[t_{r0}, t_{r0} + 2), \qquad \mathbf P_1 = \mathbf M[t_{\rm end}, \min(t_{\rm end} + 10, t_{r1})) $$
**Text:** $\mathbf P_0$ = where WISER put the animal at the start of the run (the I1 reference window, raw fixes; ≥ 2 fixes);
$\mathbf P_1$ = where WISER puts it in the 10 s after the excursion's last ≥ 12-in second, inside the same no-locomotion run. Units in.

### Return distance and classes
$$ D = \lVert \mathbf P_1 - \mathbf P_0 \rVert, \qquad \text{class} = \begin{cases} \text{censored} & \text{post window not valid} \\ \text{return} & D < 6 \\ \text{ambiguous} & 6 \le D < 12 \\ \text{relocate} & D \ge 12 \end{cases} $$
**Text:** return = WISER came back to within 6 in of where it was (WISER error under the mean-reversion premise); relocate = it
settled ≥ 12 in away (a real relocation); ambiguous between; censored = no valid post window inside the run (the event runs into
the run end / next locomotion). Thresholds 6 / 12 in fixed in advance (≈ the 7-in jitter floor / the I1 threshold).
**Structural property (Amendment (Part 1) 3):** since $W_e$ holds every second with $d \ge 12$, $d(s) < 12$ on every second of the
primary post window; a shift held until the run end is therefore censored, and *relocate* arises only where the raw median
differs from V3 (or $\mathbf P_0$ from $\mathbf r$) by several inches.

### Sensitivities
S1: $\mathbf P_0^{(1)} = \mathbf M[\max(t_{\rm on} - 10, t_{r0}), t_{\rm on})$ (valid as above), with the primary $\mathbf P_1$. S2:
$\mathbf P_1^{(2)} = \mathbf M[t_{\rm end}, \min(t_{\rm end} + 30, t_{r1}))$ (same censored set as the primary). S3 (declared, no rule uses it):
$\mathbf P_1^{(3)} = \mathbf M[\max(t_{\rm on}, t_{r1} - 10), t_{r1})$ — where WISER is in the last 10 s before the IMU next reports
locomotion. Same classes and minimums. **Text:** S1 tests the start reference, S2 the post-window length, S3 classes the shifts
that persist to the end of the run (which the primary censors).

### Class shares
$$ s_c = \frac{n_c}{n_{\rm events}}, \qquad s^{\rm cl}_c = \frac{n_c}{n_{\rm return} + n_{\rm ambiguous} + n_{\rm relocate}} \quad (c \ne \text{censored}) $$
**Text:** share of all events, and share of the classifiable (non-censored) events, per stratum (the event's onset second for
zone / day-night / weather, as in the audit; bands of size, duration and trimmed run length; animal).

### Enrichment of a class (the audit's estimator, imported unmodified)
For the events $e$ of class $c$ that have matched controls (the audit's: same animal and bio-day, event-free evaluable runs of
trimmed length within $[0.5, 2]\times$, up to 5, weight $\omega = 1/k_e$), with window fix counts $n_w$, ≤ 6-anchor counts $n^{\le 6}_w$:
$$ \rho_S(c) = \frac{\sum_{e \in c} n^{\le 6}_{W_e} / \sum_{e \in c} n_{W_e}}{\sum_{w \in {\rm ctrl}(c)} \omega_w n^{\le 6}_w / \sum_{w \in {\rm ctrl}(c)} \omega_w n_w}, \qquad
   \rho_D(c) = \frac{\operatorname{wmed}\{\delta_k\}_{W_e,\, e \in c}}{\operatorname{wmed}\{\delta_k\}_{{\rm ctrl}(c)}} $$
$\delta_k = \lVert \mathbf z_k - \tilde{\mathbf p}_{\rm raw}(\lfloor t_k \rfloor)\rVert$ = raw-fix dispersion about its 1-s raw median (in). The fix-rate ratio
$\rho_F$ (fixes per second) is shown for information (it carries the audit's Amendment-2 window-construction asymmetry). CI: 2.5–97.5
percentiles of a block bootstrap (block = animal × 10-min field-PC bin of the window onset; events and controls resampled together;
1000 replicates). **Text:** $\rho_S > 1$ = the class's event windows hold more bad-geometry (≤ 6-anchor) fixes than matched windows —
circumstantial evidence that the class is WISER error.

### Pre-registered reading
$$ \text{dominates} \iff s^{\rm cl}_{\rm return} \ge 0.5 \ \wedge\ \rho_S({\rm return}) \ge 1.5 \ \wedge\ \mathrm{CI}_{\rm lo}(\rho_S({\rm return})) > 1 \ \wedge\ \mathrm{CI}_{\rm lo}(\rho_S({\rm return})) > \rho_S({\rm relocate}) $$
(primary classes, pooled; an undefined $\rho_S({\rm relocate})$ = the last condition not met; Amendment (Part 1) 6). **Text:** if
true, WISER in-place wandering dominates I1 → propose V8 as a new pre-registered test; otherwise V3 stays, no correction.

### Excursion profile
$$ \pi_c(u) = \operatorname{med}_{e \in c}\ \lVert \tilde{\mathbf p}_{\rm raw}(t^e_{\rm on} + u) - \mathbf P^e_0 \rVert, \qquad t^e_{\rm on} + u \in [t^e_{r0}, t^e_{r1}) $$
$\tilde{\mathbf p}_{\rm raw}(s)$ = $\operatorname{med}_{\rm c}$ of the raw fixes in $[s, s+1)$ (≥ 2 fixes); quartiles likewise; events without a value at
$u$ drop out ($n$ shown). End-aligned version with $t^e_{\rm end}$. **Text:** how far raw WISER is from the run-start position, second
by second, around the event. Units in.

### Reproduction
For every event, $\mathbf r$, size, duration, $t_{\rm on}$, $t_{\rm end}$ recomputed from the production V3 track with the definition
above and compared with the audit's event table (exact seconds; ≤ 1e-6 in). Also $\max_{s \in {\rm post}} d(s)$ (must be < 12 in on
classifiable events, the structural property) and $\lVert \mathbf P_0 - \mathbf r\rVert$ (raw vs V3 start position).

### Video-verdict agreement (`--with-verdicts`)
With $a_e = [{\rm class}_e = {\rm return}]$, $b_e = [{\rm verdict}_e = {\rm stayed}]$ on the $N$ events with class ∈ {return, relocate} and
verdict ∈ {stayed, moved}: $p_o = \frac1N\sum_e [a_e = b_e]$, $p_e = \bar a \bar b + (1 - \bar a)(1 - \bar b)$,
$$ \kappa = \frac{p_o - p_e}{1 - p_e} $$
CI: 2.5–97.5 percentiles of 1000 event bootstrap replicates. **Text:** agreement of the return / relocate classes with the
user's "stayed in place" / "moved" beyond chance (1 = perfect, 0 = chance). Nothing is re-tuned on the verdicts.
"""


def render_report(A: dict, cfg: dict, figs: dict, meta: dict) -> str:
    SH, EN, PT, X, DQ, CR, INFO, EC = A["SH"], A["EN"], A["PT"], A["X"], A["DQ"], A["CR"], A["INFO"], A["EC"]
    S = A["summary"]
    rd, rp = S["reading"], S["repro"]
    VA = A.get("VA")
    out = A["out"]
    c = cfg["_cohort"]
    L = []
    w = L.append

    def sh(v, s="all", lv="all"):
        r = SH[(SH.variant == v) & (SH.stratum == s) & (SH.level == lv)]
        return r.iloc[0] if len(r) else None

    def en(v, cl, z="all"):
        r = EN[(EN.variant == v) & (EN.cls == cl) & (EN.zone == z)]
        return r.iloc[0] if len(r) else None
    w(f"# WISER baseline {c} — I1 return test: does WISER come back after an I1 event?\n")
    w(f"- **Status:** measurement report, {pd.Timestamp.now(tz=cfg['tz']).strftime('%Y-%m-%d')}. Plan `{PLAN}` Part 1 (approved by the user "
      f"2026-10-05; committed d722ec0 before any result; operational details, one ambiguity and one structural property of the classifier in "
      f"its *Amendment (Part 1) 1*, written before any number of this step; *Amendment (Part 1) 2*, written after the pooled numbers, fixes a "
      f"profile-rendering bug, adds declared descriptive lines and aligns the verdict reader with Part 2 — no class, threshold or rule changed). Driver `{DRIVER}`, config `wiser/configs/wiser_i1_return_{c}.json` "
      f"(reading in `reading`), run `{out}`, git `{meta['git_commit']}`. Input: the consistency audit's V3 I1 events and matched controls "
      f"(`{cfg['audit_run']}`).")
    w("- **What this is:** for each of the audit's V3 I1 events (the V3 track moves ≥ 12 in during a stretch the head IMU never calls "
      "locomotion), the raw-fix position after the excursion is compared with the raw-fix position at the start of the run. A **return** "
      "(< 6 in) is read as WISER error, a **relocate** (≥ 12 in) as a real relocation, 6–12 in as ambiguous; **censored** = no valid post "
      "window inside the run. **No correction is applied and no behavioural claim is made.** Frame: WISER native inches, unverified offset "
      "origin (distances only).")
    w("- **Regime context (regime-aware-wiser-tracking):** the premise is that WISER's error is bounded and mean-reverting (certified "
      "stillness: per-fix RMS 5.6 in, worst 10-s median a median 1.5 in, ≥ 12 in for ≥ 10 s 3 times in 75 still-hours — measured mostly "
      "in the houses). A rat can also walk away and come back inside one run (a *return* that was real movement), and the head IMU's "
      "locomotion class has TPR 0.75 / FPR 0.15. The video verdicts of Part 2 are the ground truth for this classifier (§6).\n")
    # ---- reading
    w("## Pre-registered reading\n")
    a = sh("primary")
    w("| Quantity (primary classes, pooled) | value | rule | met |\n|---|---|---|---|")
    w(f"| events: return / ambiguous / relocate / censored | {rd['n_return']:,} / {rd['n_ambiguous']:,} / {rd['n_relocate']:,} / {rd['n_censored']:,} "
      f"(of {rd['n_events']:,}) | | |")
    w(f"| return share of the classifiable (non-censored) events | {_pc(rd['return_share_classifiable'])} (n {rd['n_classifiable']:,}) | ≥ 50 % | "
      f"{'yes' if rd['c1_return_share_ge_0p5'] else 'no'} |")
    w(f"| ≤ 6-anchor share ratio of the return class, ρ_S [95 % CI] | {_f(rd['rho_S_return'])} [{_f(rd['rho_S_return_ci'][0])}, {_f(rd['rho_S_return_ci'][1])}] | ≥ 1.5 | "
      f"{'yes' if rd['c2_rho_ge_1p5'] else 'no'} |")
    w(f"| its CI lower bound | {_f(rd['rho_S_return_ci'][0])} | > 1 | {'yes' if rd['c3_ci_lower_gt_1'] else 'no'} |")
    w(f"| … and above the relocate class's ρ_S | relocate {_f(rd['rho_S_relocate'])} [{_f(rd['rho_S_relocate_ci'][0])}, {_f(rd['rho_S_relocate_ci'][1])}] "
      f"(n {rd['n_relocate_with_controls']:,} with controls) | CI_lo(return) > ρ_S(relocate) | "
      f"{'yes' if rd['c4_ci_lower_gt_relocate_point'] else ('no' if rd['c4_evaluable'] else 'not evaluable → no')} |")
    w(f"| (information) looser reading: ρ_S(return) > ρ_S(relocate) | | | {'yes' if rd['c4_loose_point_gt_point'] else 'no'} |\n")
    w(f"**Reading: {rd['verdict']}** → {rd['action']}. (Plan's label for this branch: *{rd['plan_label']}*.)\n")
    w("**Structural caveat — read with the reading (Amendment (Part 1) 3).** The audit's I1 window contains every second of the run "
      "whose V3 1-s median is ≥ 12 in from the run reference, so after $t_{\\rm end}$ the V3 track is by construction back within 12 in. "
      f"Verified: on all {rp.get('classifiable', 0):,} classifiable events the V3 displacement over the post window stays below 12 in "
      f"(max {_f(rp.get('v3_post_max_disp_max'), 4)} in). Hence a shift held until the IMU next reports locomotion is **censored**, never "
      "*relocate*, and the primary *relocate* class only collects events whose raw median sits ≥ 12 in from the raw start while the V3 "
      "track is < 12 in from its own reference (raw-vs-V3 differences; raw $\\mathbf P_0$ vs V3 reference: median "
      f"{_f(rp.get('p0_ref_dist_p50_p90_p99', [np.nan])[0], 2)} in, p90 {_f(rp.get('p0_ref_dist_p50_p90_p99', [np.nan] * 2)[1], 2)} in). "
      f"The primary relocate events are borderline (D median {_f(DQ[(DQ.variant == 'primary') & (DQ.subset == 'relocate')].p50.iloc[0], 1)} in). "
      "The post window also starts at the first second below 12 in, i.e. on the excursion's tail. The ≥ 50 %-of-classifiable condition "
      "therefore compares a full return with a partial (6–12 in) one, not with a persistent relocation, and the relocate comparison "
      "rests on a class made of raw-vs-V3 differences. The declared run-end sensitivity S3 (§5) classes the persistent shifts; no "
      "rule uses it.\n")
    # ---- headline bullets
    w("## Reading\n")
    s3 = sh("S3_runend")
    w(f"- **Primary, all {a['n_events']:,} events:** return {_pc(a['share_return'])}, ambiguous {_pc(a['share_ambiguous'])}, relocate "
      f"{_pc(a['share_relocate'])}, censored {_pc(a['share_censored'])}. **Excluding censored** ({a['n_classifiable']:,}): return "
      f"{_pc(a['share_return_cl'])}, ambiguous {_pc(a['share_ambiguous_cl'])}, relocate {_pc(a['share_relocate_cl'])}.")
    if s3 is not None:
        w(f"- **S3 (run-end window; declared):** return {_pc(s3['share_return'])}, ambiguous {_pc(s3['share_ambiguous'])}, relocate "
          f"{_pc(s3['share_relocate'])}, censored {_pc(s3['share_censored'])}; excluding censored ({s3['n_classifiable']:,}): return "
          f"{_pc(s3['share_return_cl'])}, ambiguous {_pc(s3['share_ambiguous_cl'])}, relocate {_pc(s3['share_relocate_cl'])}. "
          f"Of the {int(X.loc['censored'].sum()):,} primary-censored events, S3 classes {int(X.loc['censored', 'relocate']):,} relocate, "
          f"{int(X.loc['censored', 'ambiguous']):,} ambiguous, {int(X.loc['censored', 'return']):,} return and leaves "
          f"{int(X.loc['censored', 'censored']):,} censored (§5).")
    cells = []
    for cl in CLASSES:
        r = en("primary", cl)
        if r is not None and r.get("n_events", 0):
            cells.append(f"{cl} {_ci(r, 'share_ratio')} (n {int(r['n_events']):,})")
    w("- **≤ 6-anchor enrichment by primary class** (ρ_S [95 % CI]): " + "; ".join(cells) + ". S3: " + "; ".join(
        f"{cl} {_ci(en('S3_runend', cl), 'share_ratio')}" for cl in CLASSES if en("S3_runend", cl) is not None and en("S3_runend", cl).get("n_events", 0)) + ".")
    cells = [f"{cl} {_ci(en('primary', cl), 'disp_ratio')}" for cl in CLASSES if en("primary", cl) is not None and en("primary", cl).get("n_events", 0)]
    w("- **Dispersion ratio by primary class** (ρ_D [CI]): " + "; ".join(cells) + ". No class stands out as bad geometry: every "
      "class's ≤ 6-anchor ratio is of the order of the audit's pooled I1 value (1.43), and the return class is the least enriched.")
    RV = reading_by_variant(SH, EN, cfg)
    s1, s2 = sh("S1_pre10"), sh("S2_post30")

    def pm(al, v, cl, u):
        r = PT[(PT["align"] == al) & (PT.variant == v) & (PT.cls == cl) & (PT.u_s == u)]
        return r["median"].iloc[0] if len(r) else np.nan
    w(f"- **Sensitivities (§5):** S1 (10-s pre-onset reference) return {_pc(s1['share_return_cl'])} of the classifiable "
      f"({int(s1['n_classifiable']):,}), ρ_S(return) {_ci(en('S1_pre10', 'return'), 'share_ratio')}, ρ_S(relocate) "
      f"{_ci(en('S1_pre10', 'relocate'), 'share_ratio')}; S2 (30-s post window) return {_pc(s2['share_return_cl'])}; S3 return "
      f"{_pc(s3['share_return_cl'])}. Evaluated on each variant's classes (information only), the reading rule is "
      + ", ".join(f"{v.split('_')[0]} {'met' if 'DOMINATES' in RV[v]['verdict'] else 'not met'}" for v in VARIANTS)
      + f". S1 differs from the primary because 10 s before the onset the raw position is already a median "
      f"{_f(pm('onset', 'primary', 'return', -10), 1)}–{_f(pm('onset', 'primary', 'ambiguous', -10), 1)} in from the run-start position "
      "(return / ambiguous classes): after the excursion WISER comes back near where it was just before the onset, which is itself "
      "away from where the run started.")
    szl = cfg["bands"]["size_labels"]
    rll = cfg["bands"]["run_len_labels"]
    big = [sh("primary", "size", lv) for lv in szl[1:]]
    big3 = [sh("S3_runend", "size", lv) for lv in szl[1:]]
    w(f"- **The larger events persist:** {big[0]['share_censored'] * 100:.1f} % of the {szl[1]} and {big[1]['share_censored'] * 100:.1f} % of the "
      f"{szl[2]} events are censored (they run to the end of the run); under S3, {_pc(big3[0]['share_relocate_cl'])} and "
      f"{_pc(big3[1]['share_relocate_cl'])} of their classifiable events end ≥ 12 in from the start. Runs ≤ 10 s are "
      f"{_pc(sh('primary', 'run length', rll[0])['share_censored'])} censored; in runs > 30 min S3 return is "
      f"{_pc(sh('S3_runend', 'run length', rll[-1])['share_return_cl'])} of the classifiable.")
    w(f"- **Excursion profiles (§4):** the median raw distance from P0 is {_f(pm('onset', 'primary', 'censored', -10), 1)}–"
      f"{_f(pm('onset', 'primary', 'ambiguous', -10), 1)} in 10 s before the onset (1-s raw medians are noisy and the position has wandered "
      f"since the run start) and peaks at {_f(pm('onset', 'primary', 'ambiguous', 1), 1)}–{_f(pm('onset', 'primary', 'censored', 2), 1)} in "
      f"1–2 s after it; the return class falls back to {_f(pm('onset', 'primary', 'return', 15), 1)} in by +15 s "
      f"({_f(pm('onset', 'primary', 'return', 60), 1)} in at +60 s), while the S3-relocate events stay at "
      f"{_f(pm('onset', 'S3_runend', 'relocate', 30), 1)} in at +30 s and {_f(pm('onset', 'S3_runend', 'relocate', 90), 1)} in at +90 s "
      "(events still inside their run).")
    w("- Class shares by stratum: §2; enrichment within zone: §3; excursion profiles: §4; sensitivities: §5; video validation: §6.\n")
    w("Classification (regime-aware-wiser-tracking): a **measurement** result about WISER and the head IMU (no behavioural content). "
      "Classes are candidate explanations of I1 events, not confirmed errors or movements.\n")
    # ---- 1 coverage + reproduction
    w("## 1. Coverage and reproduction\n")
    w("| animal | track days | fixes (unmasked) | masked fixes | V3 I1 events | τ* (ms) |\n|---|---|---|---|---|---|")
    for r in INFO.itertuples():
        w(f"| {r.animal} | {r.days} | {r.fixes_unmasked:,} | {r.masked_fixes:,} | {r.events:,} | {r.tau_ms:.0f} |")
    w(f"| **all** | {INFO.days.sum()} | {INFO.fixes_unmasked.sum():,} | {INFO.masked_fixes.sum():,} | **{INFO.events.sum():,}** | |\n")
    if rp:
        w(f"**Reproduction of the audit's events from the production V3 track** ({rp['events']:,} events, {rp['evaluable']:,} evaluable): max "
          f"|Δ reference| {rp['ref_max_in']:.2e} in, max |Δ size| {rp['size_max_in']:.2e} in, onset mismatches {rp['onset_mismatch']}, window-end "
          f"mismatches {rp['end_mismatch']}, duration mismatches {rp['dur_mismatch']}, runs without 2 consecutive ≥ 12-in seconds "
          f"{rp['max_consec_lt2']} → **{'PASS' if rp['pass'] else 'FAIL'}** (time base and fix set as in the audit).\n")
    nret = CR[CR.variant == "primary"]
    if len(nret):
        w("Censoring reasons (primary): " + ", ".join(f"{r.reason} {int(r.n):,}" for r in nret.itertuples()) +
          f" (`window<5s` = the event window ends < 5 s before the end of the trimmed run — exactly at its end for "
          f"{int((EC['post_len_s'] <= 0).sum()):,} events; `fixes<10` = a ≥ 5-s window with < 10 raw fixes).\n")
    # ---- 2 shares
    w("## 2. Class shares (primary)\n")
    w(f"![shares](../figures/{figs['shares']})\n")
    w("Left: primary; right: S3 (run-end window, declared). Bars = share of all events; dotted line = 50 %.\n")
    w("| stratum | level | events | return | ambiguous | relocate | censored | classifiable | return (excl. censored) | ambiguous (excl.) | relocate (excl.) |\n"
      "|---|---|---|---|---|---|---|---|---|---|---|")
    for r in SH[SH.variant == "primary"].itertuples():
        w(f"| {r.stratum} | {r.level} | {r.n_events:,} | {_pc(r.share_return)} | {_pc(r.share_ambiguous)} | {_pc(r.share_relocate)} | {_pc(r.share_censored)} | "
          f"{r.n_classifiable:,} | {_pc(r.share_return_cl)} | {_pc(r.share_ambiguous_cl)} | {_pc(r.share_relocate_cl)} |")
    dq = DQ[(DQ.variant == "primary")]
    w("\n**Return distance D (primary, in):** " + "; ".join(f"{r.subset} (n {r.n:,}) p10 {_f(r.p10, 1)}, p50 {_f(r.p50, 1)}, p90 {_f(r.p90, 1)}"
                                                            for r in dq.itertuples() if r.n) + ".\n")
    # ---- 3 enrichment
    w("## 3. Enrichment of each class's event windows vs the audit's matched controls\n")
    w(f"![enrichment](../figures/{figs['enrichment']})\n")
    w("Dots = ratio event / control, bars = 95 % block-bootstrap CI; ≤ 6-anchor panel on a log scale, the reading's 1.5 dashed. Event "
      "window = the audit's I1 window (its ≥ 12-in seconds); controls = the audit's matched controls of those events.\n")
    w("| variant | class | zone | events (with controls / all) | controls | ≤ 6 share event | ≤ 6 share control | ρ_S [CI] | dispersion event / control (in) | ρ_D [CI] | ρ_F [CI] |\n"
      "|---|---|---|---|---|---|---|---|---|---|---|")
    for r in EN.itertuples():
        d = r._asdict()
        if not d.get("n_events") or not np.isfinite(d.get("n_events", np.nan)):
            w(f"| {r.variant} | {r.cls} | {r.zone} | 0 / {r.events_total:,} | – | – | – | – | – | – | – |")
            continue
        w(f"| {r.variant} | {r.cls} | {r.zone} | {int(d['n_events']):,} / {r.events_total:,} | {int(d['n_controls']):,} | {_pc(d.get('share_e'))} | "
          f"{_pc(d.get('share_c'))} | {_ci(d, 'share_ratio')} | {_f(d.get('disp_e'), 2)} / {_f(d.get('disp_c'), 2)} | {_ci(d, 'disp_ratio')} | {_ci(d, 'rate_ratio')} |")
    # ---- 4 profiles
    w("\n## 4. Raw-WISER excursion profiles\n")
    w(f"![profiles](../figures/{figs['profiles']})\n")

    def prof_at(align, v, cl, u):
        r = PT[(PT["align"] == align) & (PT.variant == v) & (PT.cls == cl) & (PT.u_s == u)]
        return (r["median"].iloc[0], int(r.n.iloc[0])) if len(r) else (np.nan, 0)
    w("| class (primary) | onset −5 s | onset +5 s | onset +15 s | onset +30 s | onset +60 s | end −5 s | end +5 s | end +20 s |\n|---|---|---|---|---|---|---|---|---|")
    for cl in CLASSES:
        cells = [prof_at("onset", "primary", cl, u) for u in (-5, 5, 15, 30, 60)] + [prof_at("end", "primary", cl, u) for u in (-5, 5, 20)]
        w(f"| {cl} | " + " | ".join(f"{_f(m_, 1)} (n {n_:,})" for m_, n_ in cells) + " |")
    cells = [prof_at("onset", "S3_runend", "relocate", u) for u in (-5, 5, 15, 30, 60)] + [prof_at("end", "S3_runend", "relocate", u) for u in (-5, 5, 20)]
    w("| S3 relocate | " + " | ".join(f"{_f(m_, 1)} (n {n_:,})" for m_, n_ in cells) + " |")
    w("\nMedian raw distance from $\\mathbf P_0$ (in) over the events with a 1-s raw median at that second inside the trimmed run "
      "(n in brackets; full table `tables/profiles.csv`).\n")
    # ---- 5 sensitivities
    w("## 5. Sensitivities\n")
    w("| variant | return | ambiguous | relocate | censored | return (excl. censored) | relocate (excl.) | ρ_S return [CI] | ρ_S relocate [CI] |\n|---|---|---|---|---|---|---|---|---|")
    for v in VARIANTS:
        r = sh(v)
        er, el = en(v, "return"), en(v, "relocate")
        w(f"| {VLABEL[v]} | {_pc(r['share_return'])} | {_pc(r['share_ambiguous'])} | {_pc(r['share_relocate'])} | {_pc(r['share_censored'])} | "
          f"{_pc(r['share_return_cl'])} | {_pc(r['share_relocate_cl'])} | {_ci(er, 'share_ratio') if er is not None else '–'} | "
          f"{_ci(el, 'share_ratio') if el is not None else '–'} |")
    w("\n**Primary class (rows) × S3 class (columns):**\n")
    w("| primary \\ S3 | " + " | ".join(CLASSES) + " |\n|---|" + "---|" * len(CLASSES))
    for cl in CLASSES:
        w(f"| {cl} | " + " | ".join(f"{int(X.loc[cl, c2]):,}" for c2 in CLASSES) + " |")
    s3cr = CR[CR.variant == "S3_runend"]
    if len(s3cr):
        w("\nS3 censoring reasons: " + ", ".join(f"{r.reason} {int(r.n):,}" for r in s3cr.itertuples()) + " (an onset < 5 s before the run end, or < 10 fixes).")
    w("\n**S3 shares by stratum** (share of all events; excl. censored in brackets):\n")
    w("| stratum | level | events | return | ambiguous | relocate | censored |\n|---|---|---|---|---|---|---|")
    for r in SH[(SH.variant == "S3_runend") & SH.stratum.isin(["all", "zone", "day/night", "size", "duration", "run length"])].itertuples():
        w(f"| {r.stratum} | {r.level} | {r.n_events:,} | {_pc(r.share_return)} ({_pc(r.share_return_cl)}) | {_pc(r.share_ambiguous)} ({_pc(r.share_ambiguous_cl)}) | "
          f"{_pc(r.share_relocate)} ({_pc(r.share_relocate_cl)}) | {_pc(r.share_censored)} |")
    # ---- 6 validation
    w("\n## 6. Validation against the user's video verdicts (Part 2)\n")
    if VA:
        w(f"Source `{VA.get('source')}` ({VA.get('written')}): {VA['n_rows']} judged I1 rows, {VA['n_matched']} matched to this run's events "
          f"({VA['n_unmatched']} unmatched). Agreement: return ↔ *stayed (in place)*, relocate ↔ *moved*; *cannot tell* and the ambiguous / "
          f"censored classes are shown but not in κ. The blind verdict (`verdict_blind`, given before the panel was revealed) is used; "
          f"{VA.get('n_changed_after_reveal', 0)} of the matched answers were changed after the reveal (not used). Nothing was re-tuned "
          "on the verdicts.\n")
        for v in ("primary", "S3_runend"):
            d = VA.get(v) or {}
            if not d:
                continue
            w(f"**{VLABEL[v]}:** Cohen's κ {_f(d['kappa'], 2)} [{_f(d['kappa_ci'][0], 2)}, {_f(d['kappa_ci'][1], 2)}], observed agreement "
              f"{_pc(d['observed_agreement'])} (N {d['n_kappa']}).\n")
            w("| class \\ verdict | " + " | ".join(VERDICTS) + " |\n|---|" + "---|" * len(VERDICTS))
            for cl in CLASSES:
                row = d["confusion"].get(cl, {})
                w(f"| {cl} | " + " | ".join(str(int(row.get(vv, 0))) for vv in VERDICTS) + " |")
            w("")
    else:
        w("**Pending.** The video verdicts do not exist yet. When the Part-2 export is in `wiser/configs/wiser_event_review_2026c/`, run "
          f"`python {DRIVER} --with-verdicts wiser/configs/wiser_event_review_2026c/ --run {Path(out).as_posix()}`: it matches the verdicts to "
          "these events, writes the confusion table (class × moved / stayed / cannot tell) and Cohen's κ (return ↔ stayed, relocate ↔ moved), "
          "and re-renders this report. Part 2 chose its events without these classes.\n")
    # ---- 7 caveats
    w("## 7. Caveats\n")
    w("- The structural property above: persistent shifts are censored in the primary; S3 classes them but no rule uses it, and S3 "
      "cannot tell a persistent shift from a WISER excursion that is still out when the run ends (both end ≥ 12 in away).\n"
      "- Mean-reversion was measured mostly in the houses during certified stillness; outside it a WISER bias may persist longer, and a rat "
      "can walk away and return within one run (a *return* that was movement) — the video verdicts check both.\n"
      "- Enrichment is circumstantial evidence; the ≤ 6-anchor fixes are also more common in the houses (within-zone rows in §3).\n"
      "- The 6 / 12-in thresholds and the 5-s / 10-fix minimums were fixed in advance and are not tuned; positions are in the unverified WISER "
      "inch frame.\n")
    w(DEFINITIONS)
    return "\n".join(L) + "\n"


def publish(A: dict, cfg: dict, fh=None) -> None:
    c = cfg["_cohort"]
    out = Path(A["out"])
    fdir = output_paths.figure_dir(c, DIRECTION)
    figs = make_figures(A, cfg, fdir, c)
    (out / "figures").mkdir(exist_ok=True)
    import shutil
    for f in figs.values():
        shutil.copy2(fdir / f, out / "figures" / f)
    rd = A["summary"]["reading"]
    meta = {"cohort": c, "direction": DIRECTION, "analysis": NAME, "report": f"{STEM}_{c}.md", "driver": DRIVER,
            "config": f"wiser/configs/wiser_i1_return_{c}.json", "plan": PLAN, "git_commit": C.git_commit(), "figures": sorted(figs.values()),
            "audit_run": cfg["audit_run"], "reading": rd["verdict"], "return_share_classifiable": rd["return_share_classifiable"],
            "rho_S_return": rd["rho_S_return"], "rho_S_return_ci": rd["rho_S_return_ci"], "rho_S_relocate": rd["rho_S_relocate"],
            "validation": bool(A.get("VA"))}
    rdir = output_paths.report_dir(c, DIRECTION)
    rep = rdir / f"{STEM}_{c}.md"
    rep.write_text(render_report(A, cfg, figs, meta), encoding="utf-8")
    output_paths.write_run_manifest(out, out, **meta)
    mp = rdir / f"run_manifest_i1_return_{c}.json"
    mp.write_text(json.dumps({"run_dir": str(out.resolve()), **meta}, indent=2, default=str) + "\n", encoding="utf-8")
    cp = Path(cfg["_path"])
    raw = json.loads(cp.read_text(encoding="utf-8"))
    raw["reading"] = {**rd, "repro_pass": A["summary"]["repro"].get("pass"), "run_dir": str(out),
                      "written": pd.Timestamp.now(tz=cfg["tz"]).strftime("%Y-%m-%d %H:%M")}
    if A.get("VA"):
        VA = A["VA"]
        raw["validation"] = {"source": VA.get("source"), "written": VA.get("written"), "n_matched": VA.get("n_matched"),
                             **{v: {k: VA[v].get(k) for k in ("kappa", "kappa_ci", "observed_agreement", "n_kappa")} for v in ("primary", "S3_runend") if VA.get(v)}}
    cp.write_text(json.dumps(raw, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    log_to(fh, f"report {rep}; pointer {mp}; figures {sorted(figs.values())}; config reading written")


# ====================================================================================================== selftest
def _synth(seed: int = 11) -> dict:
    """A synthetic animal for the end-to-end test through the audit's own I1 detector: walking bouts separating 120-s
    no-locomotion runs of five kinds - 'return' (a 20-in WISER excursion of ~10 s built from <= 6-anchor fixes, back to the start),
    'relocate' (a real 25-in shift the IMU misses, held to the run end, background anchors), 'partial' (a 20-in excursion that
    settles 9 in away), 'late' (an excursion ending < 5 s before the run end) and 'quiet' (no event)."""
    rng = np.random.default_rng(seed)
    fsg = 50.0
    s0 = int(C.to_ms("2026-09-05 22:00:00") // 1000)
    kinds = ["return", "relocate", "partial", "quiet", "late", "quiet"] * 12
    T = len(kinds) * 140
    t = np.arange(0.0, T, 1.0 / fsg)
    x, y = np.zeros(len(t)), np.zeros(len(t))
    state = np.zeros(T, np.int8)
    off = []                                      # (t_start, t_end, dx(u) function id) WISER-only offsets
    truth = []                                    # per run: (run_start, run_end, kind)
    cx, cy, dirn = 300.0, 300.0, 1.0
    t0 = 0
    for k in kinds:
        # walking bout 20 s at 15 in/s (alternating direction)
        i0, i1 = int(t0 * fsg), int((t0 + 20) * fsg)
        tt = t[i0:i1] - t0
        x[i0:i1] = cx + dirn * 15.0 * tt
        y[i0:i1] = cy
        state[t0:t0 + 20] = 3
        cx = x[i1 - 1]
        dirn = -dirn
        t0 += 20
        # no-locomotion run 120 s (still / active alternating 10-s blocks)
        i0, i1 = int(t0 * fsg), int((t0 + 120) * fsg)
        tt = t[i0:i1] - t0
        x[i0:i1], y[i0:i1] = cx, cy
        state[t0:t0 + 120] = np.where((np.arange(120) // 10) % 2 == 0, 1, 2)
        if k == "relocate":                       # real shift (missed loco) at u = 40 s, +25 in in y over 2 s, held
            y[i0:i1] = cy + 25.0 * np.clip((tt - 40.0) / 2.0, 0, 1)
        elif k in ("return", "partial"):
            off.append((t0 + 40.0, k))
        elif k == "late":
            off.append((t0 + 109.0, k))
        truth.append((t0, t0 + 120, k))
        if k == "relocate":
            cy = cy + 25.0
        t0 += 120
    tfx = np.sort(np.arange(0.0, T, 0.125) + rng.uniform(0, 0.02, int(T / 0.125)))
    tfx = tfx[tfx < T - 0.05]
    X = np.interp(tfx, t, x) + rng.normal(0, 1.5, len(tfx))
    Y = np.interp(tfx, t, y) + rng.normal(0, 1.5, len(tfx))
    anch = np.where(rng.uniform(size=len(tfx)) < 0.9, 9, rng.choice([5, 6], size=len(tfx))).astype(np.int64)
    for ts, k in off:                             # WISER-only x offsets: ramp 2 s to 20 in, hold 6 s, ramp 2 s back (to 9 in for partial)
        u = tfx - ts
        end_level = 9.0 if k == "partial" else 0.0
        dx = np.where(u < 2, 10.0 * u, np.where(u < 8, 20.0, np.maximum(20.0 - (20.0 - end_level) * (u - 8) / 2.0, end_level)))
        m = (u >= 0) & ((u < 10) | (k == "partial"))
        if k == "partial":                        # settle at 9 in until the run end
            m &= u < 80.0 - (ts % 1)              # stays inside the run (run end = ts + 80)
        X[m] += dx[m]
        anch[(u >= 0) & (u < 10)] = 5
    planted = np.zeros(len(tfx), bool)
    for ts, k in off:
        planted |= (tfx >= ts) & (tfx < ts + 10)
    P = np.column_stack([X, Y])
    v3 = pd.DataFrame(P).rolling(5, center=True, min_periods=1).median().to_numpy()
    return {"s0": s0, "T": T, "tf": s0 + tfx, "raw": P, "V3": v3, "anch": anch, "state": state, "truth": truth, "planted": planted}


def _synth_audit(S: dict, acfg: dict) -> dict:
    """Run the audit's analyze_arrays (unmodified) on the synthetic animal -> its V3 I1 events and matched controls."""
    s0, T = S["s0"], S["T"]
    n = T + 2
    s0g = s0 - 1
    incl = np.zeros(n, bool)
    incl[1:T + 1] = True
    state = np.zeros(n, np.int8)
    state[1:T + 1] = S["state"]
    g = float(s0g) + 0.5 * np.arange(2 * n)
    A = {"animal": "SF00", "tau_ms": 0.0, "s0": s0g, "n": n, "incl": incl, "ok": incl, "state": state, "tf": S["tf"], "anch": S["anch"],
         "pos": {"V3": S["V3"], "raw": S["raw"]}, "dpsi": np.full(len(g), np.nan), "gok": np.zeros(len(g), bool),
         "dn": np.zeros(n, np.int8), "wx": np.full(n, 3, np.int8), "bio": np.zeros(n, np.int64), "hour_ms": np.full(n, s0g * 1000, np.int64)}
    return AC.analyze_arrays(A, acfg, [])


def selftest() -> int:
    t_start = time.time()
    cfg = load_cfg("2026c")
    acfg = load_acfg(cfg)
    acfg = json.loads(json.dumps(acfg))
    acfg["bootstrap"]["block_s"] = 140            # one synthetic run cycle per block (more blocks than the field's 10 min)
    ok_all = True

    def check(name, cond, detail=""):
        nonlocal ok_all
        ok_all &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}", flush=True)
    # ---- 1) classifier arithmetic on hand-made events (windows set explicitly)
    rng = np.random.default_rng(3)
    tf = np.arange(0.0, 400.0, 0.125)
    P = np.column_stack([np.full(len(tf), 100.0), np.full(len(tf), 100.0)]) + rng.normal(0, 1.0, (len(tf), 2))
    # event a: return (excursion 20-30 s), b: relocate (shift +20 at 120 s, window declared to end at 130), c: ambiguous (+9 after 230),
    # d: censored (window ends 2 s before the run end), e: censored (fix dropout after the window)
    P[(tf >= 20) & (tf < 30), 0] += 20.0
    P[(tf >= 120) & (tf < 200), 1] += 20.0
    P[(tf >= 220) & (tf < 230), 0] += 20.0
    P[(tf >= 230) & (tf < 270), 0] += 9.0
    keep = ~((tf >= 340) & (tf < 352))
    tf2, P2 = tf[keep], P[keep]
    E = pd.DataFrame({"run_t0": [0.0, 100.0, 200.0, 280.0, 320.0], "run_t1": [60.0, 200.0, 270.0, 318.0, 360.0],
                      "t0": [20.0, 120.0, 220.0, 300.0, 330.0], "t1": [30.0, 130.0, 230.0, 316.0, 340.0]})
    R = classify_events(E, tf2, P2, cfg)
    exp = ["return", "relocate", "ambiguous", "censored", "censored"]
    check("classifier: return / relocate / ambiguous / censored (window < 5 s) / censored (< 10 fixes) on hand-made windows",
          list(R["cls"]) == exp and list(R["censor_reason"])[3:] == ["window<5s", "fixes<10"],
          f"({list(R['cls'])}, D {np.round(R['dist'].to_numpy(), 1).tolist()}, reasons {list(R['censor_reason'])})")
    check("S2 (30-s post): censored set a subset of the primary's (window < 5 s kept, < 10 fixes can become valid); S1 pre window inside the run",
          list(R["s2_cls"]) == ["return", "relocate", "ambiguous", "censored", "return"] and R["s1_pre_len_s"].iloc[0] == 10.0
          and not ((R["s2_cls"] == "censored") & (R["cls"] != "censored")).any(),
          f"(S2 {list(R['s2_cls'])}, S1 {list(R['s1_cls'])})")
    # ---- 2) end to end through the audit's own I1 detector and matched controls
    S = _synth()
    RA = _synth_audit(S, acfg)
    E, Ct = RA["events"], RA["controls"]
    E = E[(E.track == "V3") & (E.type == "I1")].reset_index(drop=True)
    Ct = Ct[(Ct.track == "V3") & (Ct.type == "I1")].reset_index(drop=True)
    E["ref_x"], E["ref_y"] = E["ref_x"].astype(float), E["ref_y"].astype(float)
    out = analyze_animal_arrays(E, S["tf"], S["raw"], S["V3"], cfg, acfg)
    Rr = out["R"]
    EC = pd.concat([E.reset_index(drop=True), Rr.reset_index(drop=True)], axis=1)
    kind = []
    for e in EC.itertuples():
        k = [kk for a, b, kk in S["truth"] if a + S["s0"] <= e.t0 < b + S["s0"]]
        kind.append(k[0] if k else "none")
    EC["kind"] = kind
    tab = pd.crosstab(EC["kind"], EC["cls"])
    tab3 = pd.crosstab(EC["kind"], EC["s3_cls"])
    nkind = {k: sum(1 for *_, kk in S["truth"] if kk == k) for k in ("return", "relocate", "partial", "late", "quiet")}
    got = EC.groupby("kind").size().to_dict()
    check("audit detector finds one I1 event per planted excursion / shift and none in the quiet runs",
          all(got.get(k, 0) == nkind[k] for k in ("return", "relocate", "partial", "late")) and got.get("quiet", 0) == 0 and got.get("none", 0) == 0,
          f"(events by kind {got}, planted {nkind})")
    pr = lambda tb, k, c_: int(tb.loc[k, c_]) if (k in tb.index and c_ in tb.columns) else 0  # noqa: E731
    check("primary: planted WISER excursions -> return, partial returns -> ambiguous, late ones -> censored",
          pr(tab, "return", "return") == nkind["return"] and pr(tab, "partial", "ambiguous") == nkind["partial"] and pr(tab, "late", "censored") == nkind["late"],
          f"({tab.to_dict(orient='index')})")
    check("primary: planted persistent relocations are CENSORED by construction (Amendment (Part 1) 3), S3 classes them relocate "
          "(and, by its definition, also the WISER excursions still out at the run end - the 'late' runs)",
          pr(tab, "relocate", "censored") == nkind["relocate"] and pr(tab3, "relocate", "relocate") == nkind["relocate"]
          and pr(tab3, "return", "return") == nkind["return"] and pr(tab3, "late", "relocate") == nkind["late"],
          f"(S3 {tab3.to_dict(orient='index')})")
    check("structural property: V3 displacement over every classifiable post window < 12 in",
          bool((EC.loc[EC.cls != "censored", "v3_post_max_disp"] < 12.0).all()), f"(max {EC.loc[EC.cls != 'censored', 'v3_post_max_disp'].max():.2f} in)")
    EC["t0_al_ms"] = np.round(EC["t0"] * 1000).astype(np.int64)
    EC["t1_al_ms"] = np.round(EC["t1"] * 1000).astype(np.int64)
    rp = repro_summary(EC)
    check("reproduction recomputes the audit's reference, size, onset, window end and duration exactly", rp["pass"],
          f"(ref {rp['ref_max_in']:.1e} in, size {rp['size_max_in']:.1e} in, onset/end/dur mismatches {rp['onset_mismatch']}/{rp['end_mismatch']}/{rp['dur_mismatch']})")
    # enrichment through the audit's enrichment(): return windows are all <= 6 anchors (background ~10 %), relocations at background
    z = RA["disp"].astype(float)
    dw = RA["disp_win"].astype(np.int64)
    bg = float((S["anch"][~S["planted"]] <= 6).mean())
    er = AC.enrichment(EC[EC.cls == "return"], Ct, z, dw, acfg, 1)
    e3 = AC.enrichment(EC[(EC.s3_cls == "relocate") & (EC.kind == "relocate")], Ct, z, dw, acfg, 2)
    exp_r = 1.0 / bg
    check("enrichment: return class rho_S ≈ planted ratio (1 / background share) with CI > 1; S3 relocate (planted shifts) rho_S ≈ 1",
          abs(er["share_ratio"] / exp_r - 1) < 0.35 and er["share_ratio_lo"] > 1 and abs(e3["share_ratio"] - 1) < 0.35,
          f"(return {er['share_ratio']:.2f} [{er['share_ratio_lo']:.2f}, {er['share_ratio_hi']:.2f}] vs planted ≈ {exp_r:.2f}; "
          f"S3 relocate {e3['share_ratio']:.2f} [{e3['share_ratio_lo']:.2f}, {e3['share_ratio_hi']:.2f}])")
    # profiles: return events come back below 6 in after the window end; S3 relocations stay >= 12 in
    pe = out["prof_end"]
    u_end = np.arange(int(cfg["profile"]["end_from_s"]), int(cfg["profile"]["end_to_s"]) + 1)
    j5 = int(np.flatnonzero(u_end == 5)[0])
    mret = float(np.nanmedian(pe[(EC.cls == "return").to_numpy(), j5]))
    po = out["prof_onset"]
    u_on = np.arange(int(cfg["profile"]["onset_from_s"]), int(cfg["profile"]["onset_to_s"]) + 1)
    j30 = int(np.flatnonzero(u_on == 30)[0])
    mrel = float(np.nanmedian(po[(EC.s3_cls == "relocate").to_numpy(), j30]))
    check("excursion profiles: return class < 6 in 5 s after the window end; relocations ≈ 25 in 30 s after the onset",
          mret < 6 and abs(mrel - 25) < 4, f"(return end+5 s {mret:.1f} in; relocate onset+30 s {mrel:.1f} in)")
    # ---- 3) aggregation helpers + the reading rule
    EC["zone"], EC["zone_detail"], EC["dn"], EC["wx"] = "field", "field", "night", "dry"
    ECb = add_bands(EC, cfg)
    SH = share_table(ECb, cfg)
    ok_sh = abs(SH[(SH.variant == "primary") & (SH.stratum == "all")][[f"share_{c_}" for c_ in CLASSES]].sum(axis=1).iloc[0] - 1) < 1e-9
    check("share table: shares of the four classes sum to 1; size / duration / run-length bands assigned", ok_sh and ECb["size_band"].ne("nan").all(),
          f"(strata {SH.stratum.nunique()}, rows {len(SH)})")

    def mk(share_ret, rho, lo, hi, rho_rel):
        sh_ = pd.DataFrame([{"variant": "primary", "stratum": "all", "level": "all", "n_events": 100, "n_classifiable": 80, "n_return": int(80 * share_ret),
                             "n_ambiguous": 80 - int(80 * share_ret), "n_relocate": 0, "n_censored": 20, "share_return_cl": share_ret}])
        en_ = pd.DataFrame([{"variant": "primary", "cls": "return", "zone": "all", "share_ratio": rho, "share_ratio_lo": lo, "share_ratio_hi": hi, "n_events": 50},
                            {"variant": "primary", "cls": "relocate", "zone": "all", "share_ratio": rho_rel, "share_ratio_lo": np.nan, "share_ratio_hi": np.nan,
                             "n_events": 5 if np.isfinite(rho_rel) else 0}])
        return reading(sh_, en_, cfg)
    cases = [(mk(0.6, 1.8, 1.3, 2.4, 1.1), True), (mk(0.6, 1.8, 1.3, 2.4, 1.4), False), (mk(0.4, 1.8, 1.3, 2.4, 1.1), False),
             (mk(0.6, 1.4, 1.2, 1.7, 1.0), False), (mk(0.6, 1.8, 0.9, 2.4, 0.5), False), (mk(0.6, 1.8, 1.3, 2.4, np.nan), False)]
    check("reading rule: dominates only when share ≥ 0.5, ρ ≥ 1.5, CI_lo > 1 and CI_lo > ρ(relocate); undefined relocate = not met",
          all(("DOMINATES" in r_["verdict"]) == exp_ for r_, exp_ in cases), f"({[r_['verdict'][:12] for r_, _ in cases]})")
    # ---- 4) video-verdict pass: CSV + JSON, matching by event_id and by onset, kappa
    import tempfile
    EC["onset_pc_ms"] = EC["t0_al_ms"]
    EC["event_id"] = EC["event_id"].astype(int)
    EC["animal"] = "SF00"
    rows = []
    for e in EC.itertuples():
        vv = "stayed" if e.cls == "return" else ("moved" if e.cls in ("censored",) else "cannot_tell")
        rows.append({"animal": e.animal, "type": "I1", "event_id": int(e.event_id), "verdict": vv, "reviewer": "test"})
    rows[0]["verdict"] = "moved"                  # one disagreement
    with tempfile.TemporaryDirectory() as td:
        pcsv = Path(td) / "wiser_event_review_2026c_test_20261006_1200.csv"
        pd.DataFrame(rows).to_csv(pcsv, index=False)
        V = load_verdicts(pcsv, cfg)
        M = match_verdicts(V, EC, cfg)
        # JSON with onset strings and no event_id (matching by onset)
        jrows = [{"animal": r_["animal"], "type": "I1", "onset_pc": pd.Timestamp(int(EC.onset_pc_ms.iloc[i]), unit="ms", tz="UTC").tz_convert(cfg["tz"]).strftime("%Y-%m-%d %H:%M:%S"),
                  "answer": {"stayed": "stayed (in place)", "moved": "moved", "cannot_tell": "cannot tell"}[r_["verdict"]]} for i, r_ in enumerate(rows)]
        pj = Path(td) / "export.json"
        pj.write_text(json.dumps({"reviewer": "test", "rows": jrows}), encoding="utf-8")
        Vj = load_verdicts(pj, cfg)
        Mj = match_verdicts(Vj, EC, cfg)
        # Part-2 export format: event_key + audit_event_id, verdict = verdict_blind, verdict_final may differ, I2 rows ignored
        prow = []
        for i, r_ in enumerate(rows):
            prow.append({"review_id": f"W{i + 1:02d}", "event_key": f"{r_['animal']}|V3|I1|{r_['event_id']}", "audit_event_id": r_["event_id"],
                         "animal": r_["animal"], "type": "I1", "verdict_blind": r_["verdict"], "verdict": r_["verdict"],
                         "verdict_final": "moved", "changed_after_reveal": r_["verdict"] != "moved"})
        prow.append({"review_id": "W99", "event_key": "SF00|V3|I2|3", "audit_event_id": 3, "animal": "SF00", "type": "I2",
                     "verdict_blind": "turned", "verdict": "turned", "verdict_final": "turned", "changed_after_reveal": False})
        pj2 = Path(td) / "wiser_event_review_2026c_test_20261006_1300.json"
        pj2.write_text(json.dumps({"schema": "wiser_event_review_labels/1", "reviewer": "test", "rows": prow}), encoding="utf-8")
        (Path(td) / "wiser_event_review_2026c_placeholder.json").write_text(json.dumps({"schema": "wiser_event_review_labels/1", "reviewer": "",
                                                                                     "rows": [], "judgements": {}}), encoding="utf-8")
        for f_ in (pcsv, pj):
            f_.unlink()
        Vp = load_verdicts(Path(td), cfg)          # folder: the placeholder is skipped, the Part-2 export read
        Mp = match_verdicts(Vp, EC, cfg)
    VA = verdict_agreement(M, cfg)
    VAj = verdict_agreement(Mj, cfg)
    VAp = verdict_agreement(Mp, cfg)
    check("verdict pass, Part-2 format (folder with the placeholder): event_key / audit_event_id matched, the BLIND verdict used, I2 rows dropped, changes after the reveal counted",
          len(Vp) == len(rows) and Mp.matched.all() and abs(VAp["S3_runend"]["kappa"] - VA["S3_runend"]["kappa"]) < 1e-12
          and VAp["n_changed_after_reveal"] == sum(r_["verdict"] != "moved" for r_ in rows),
          f"(rows {len(Vp)} of {len(prow)}, matched {int(Mp.matched.sum())}, κ S3 {VAp['S3_runend']['kappa']:.3f})")
    # hand computation on the S3 classes: return<->stayed, relocate<->moved
    cl3 = EC["s3_cls"].to_numpy(str)
    ve = np.array([r_["verdict"] for r_ in rows])
    m = np.isin(cl3, ["return", "relocate"]) & np.isin(ve, ["stayed", "moved"])
    a_ = (cl3[m] == "return").astype(int)
    b_ = (ve[m] == "stayed").astype(int)
    po = np.mean(a_ == b_)
    pe_ = a_.mean() * b_.mean() + (1 - a_.mean()) * (1 - b_.mean())
    k_hand = (po - pe_) / (1 - pe_)
    check("verdict pass: CSV matched by event_id, JSON by onset; normalisation; κ equals the hand computation",
          M.matched.all() and Mj.matched.all() and (Mj.how == "onset").all() and abs(VA["S3_runend"]["kappa"] - k_hand) < 1e-12
          and abs(VAj["S3_runend"]["kappa"] - k_hand) < 1e-12 and VA["S3_runend"]["n_kappa"] == int(m.sum()),
          f"(matched {int(M.matched.sum())}/{len(M)} + {int(Mj.matched.sum())}/{len(Mj)}; κ S3 {VA['S3_runend']['kappa']:.3f} vs hand {k_hand:.3f}; "
          f"primary κ {VA['primary']['kappa'] if VA['primary'] else float('nan')})")
    check("verdict normalisation", [_norm_verdict(x, cfg) for x in ("Moved", "stayed (in place)", "cannot tell", "turned", True, "")] ==
          ["moved", "stayed", "cannot_tell", np.nan, "moved", np.nan] or
          [str(_norm_verdict(x, cfg)) for x in ("Moved", "stayed (in place)", "cannot tell", "turned", True, "")] == ["moved", "stayed", "cannot_tell", "nan", "moved", "nan"])
    # ---- 5) exact integer-ms times survive the CSV round trip
    with tempfile.TemporaryDirectory() as td:
        pth = Path(td) / "ec.csv.gz"
        EC[["t0_al_ms", "t1_al_ms"]].to_csv(pth, index=False)
        back = pd.read_csv(pth)
        dt = int(np.max(np.abs(back.to_numpy(np.int64) - EC[["t0_al_ms", "t1_al_ms"]].to_numpy(np.int64))))
    check("integer-ms times round-trip exactly through CSV", dt == 0, f"(max |Δ| {dt} ms)")
    print(f"selftest {time.time() - t_start:.1f} s -> {'ALL PASS' if ok_all else 'FAILED'}", flush=True)
    return 0 if ok_all else 1


# ====================================================================================================== main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cohort", default="2026c")
    ap.add_argument("--config", default=None)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--animals", nargs="*", default=None)
    ap.add_argument("--report-only", default=None, help="re-aggregate (incl. the bootstrap, ~15 min) and re-render from an existing run dir")
    ap.add_argument("--render-only", default=None, help="re-render the report / figures from a run dir's saved aggregate tables (no recompute)")
    ap.add_argument("--with-verdicts", default=None, help="Part-2 video-verdict export (JSON / CSV / folder)")
    ap.add_argument("--run", default=None, help="with --with-verdicts: the run dir (default: the pointer's run_dir)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    if a.selftest:
        sys.exit(selftest())
    cfg = load_cfg(a.cohort, a.config)
    if a.with_verdicts:
        run = Path(a.run) if a.run else Path(json.loads((output_paths.report_dir(cfg["_cohort"], DIRECTION) / f"run_manifest_i1_return_{cfg['_cohort']}.json")
                                                        .read_text(encoding="utf-8"))["run_dir"])
        with open(run / "log_verdicts.txt", "a", encoding="utf-8") as fh:
            run_with_verdicts(Path(a.with_verdicts), run, cfg, fh)
            publish(load_aggregate(run, cfg), cfg, fh)
        return
    if a.render_only:
        run = Path(a.render_only)
        with open(run / "log_report.txt", "a", encoding="utf-8") as fh:
            publish(load_aggregate(run, cfg), cfg, fh)
        return
    holder = {}
    if a.report_only:
        out = Path(a.report_only)
        fh = open(out / "log_report.txt", "a", encoding="utf-8")
    else:
        out = run_compute(cfg, a.workers or int(cfg["workers"]), a.animals, holder)
        fh = holder["fh"]
    A = aggregate(out, cfg, fh)
    publish(A, cfg, fh)
    fh.close()


if __name__ == "__main__":
    main()
