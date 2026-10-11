r"""Where do the rats make awake ripples at night? (cohort 2026c; plan implementation_plan/2026-10-10-awake-ripple-map.md,
Amendment 1 after the Codex audit; written before any map). This driver implements Phase 0 (counts, no maps); later
phases are added after their gates.

Usage:  python ephys/awake_ripple_map.py phase0 [--workers 6]
        python ephys/awake_ripple_map.py --selftest

Per-second night table per animal (field-PC local time; night = sunset -> sunrise; nothing from 09-11 19:40):
  state      final 1-s sleep state (records as sleep_model.records_for)
  quiet      WAKE & head IMU ok & still (imu_seconds_cache) & not handling (lid events +-5 min, operator windows +-30 min,
             the 09-01 ~00:34 midnight round +-30 min) & SWR-covered (tier validated / good, use_until, settle windows) &
             detectable (theta ratio `th` and the fast LFP-EMG below the session's NREM 95th percentile) & a position
  position   V3 default track on t_al_ms, masks m_handling / m_silence / m_tag_validity / m_off_animal dropped, 1-s median
  zone       hysteretic house membership of the night-sleep analysis (1 house_1, 2 house_2, 3 field, 0 unknown)
  qSWR       a detected SWR event in a quiet second with x_theta, x_emg_lfp and x_moving all False
  trial      the night window split at every home nap (a sleep stretch >= 5 min with >= 3 min NREM, >= 80 % of its known
             zone seconds in a house) and at record gaps; excursion = a maximal field run >= 120 s
  bins       24-in squares of the WISER frame anchored at the P0 paddock origin (Map.inv of pole A0); reference only
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "wiser" / "src"))
from _common import git_commit, report_dir, write_json  # noqa: E402

COHORT = "2026c"
W, N, R = 1, 3, 5
BIN_IN = 24.0
MIN_OCC_S = 120
FEMALES = pd.Timestamp("2026-09-11 19:40")
MIDNIGHT_ROUND = (pd.Timestamp("2026-09-01 00:04"), pd.Timestamp("2026-09-01 01:04"))     # ~00:34 +- 30 min
BLE_PASSES = [("2026-09-03 00:16", "2026-09-03 00:25"), ("2026-09-06 00:21", "2026-09-06 00:36"), ("2026-09-06 23:43", "2026-09-06 23:57"),
              ("2026-09-07 23:14", "2026-09-07 23:33"), ("2026-09-09 03:17", "2026-09-09 03:27"), ("2026-09-07 06:41", "2026-09-07 06:49"),
              ("2026-09-10 06:04", "2026-09-10 06:12")]
SWR_ROOT = "Q:/hc997/SocialFieldRat2026/3rd_rat/analysis/swr"
EMG_ROOT = "Q:/hc997/SocialFieldRat2026/3rd_rat/analysis/emg_from_lfp"
OUT_ROOT = Path("D:/Field2026_analysis_out") / COHORT
EPOCH = pd.Timestamp("1970-01-01")


def sec_of(t) -> np.ndarray:
    """Local-naive timestamps -> integer seconds (floor)."""
    return np.floor((pd.to_datetime(pd.Series(t)) - EPOCH).dt.total_seconds().to_numpy()).astype(np.int64)


# ------------------------------------------------------------------ geometry (P0 map)
def p0_params() -> dict:
    f = sorted(OUT_ROOT.glob("cv_field_wiser_assist_p0_*/mapping.json"))[-1]
    m = json.loads(f.read_text())["accepted_map"]
    return {"d": np.array([m["dx_in"], m["dy_in"]]), "th": np.deg2rad(m["theta_deg"]), "s": m["scale"], "c": np.array(m["centre_wiser_in"]), "file": str(f)}


def to_paddock(Wxy: np.ndarray, p: dict) -> np.ndarray:
    c, s, th = p["c"], p["s"], p["th"]
    Rm = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    return (s * (Rm @ (np.atleast_2d(Wxy) - c).T)).T + c + p["d"]


def to_wiser(Pxy: np.ndarray, p: dict) -> np.ndarray:
    c, s, th = p["c"], p["s"], p["th"]
    Ri = np.array([[np.cos(-th), -np.sin(-th)], [np.sin(-th), np.cos(-th)]])
    return (Ri @ ((np.atleast_2d(Pxy) - c - p["d"]) / s).T).T + c


# ------------------------------------------------------------------ pure pieces (selftested)
def segments_between(n: int, cuts: list[tuple[int, int]], min_len: int = 1) -> list[tuple[int, int]]:
    """[0, n) minus the cut intervals, as (a, b) runs of length >= min_len."""
    m = np.ones(n, bool)
    for a, b in cuts:
        m[max(a, 0):min(b, n)] = False
    out, i = [], 0
    while i < n:
        if m[i]:
            j = i
            while j < n and m[j]:
                j += 1
            if j - i >= min_len:
                out.append((i, j))
            i = j
        else:
            i += 1
    return out


def home_naps(state: np.ndarray, zone: np.ndarray) -> list[tuple[int, int]]:
    from night_sleep_wiser import sleep_stretches
    out = []
    for a, b in sleep_stretches(state):
        z = zone[a:b]
        k = z[z > 0]
        if len(k) and float(np.isin(k, (1, 2)).mean()) >= 0.8:
            out.append((a, b))
    return out


def field_runs(zone: np.ndarray, min_s: int = 120) -> list[tuple[int, int]]:
    from night_sleep_wiser import runs
    return [(a, b) for v, a, b in runs((zone == 3).astype(int)) if v == 1 and b - a >= min_s]


# ------------------------------------------------------------------ inputs
def night_windows() -> list[tuple[str, pd.Timestamp, pd.Timestamp]]:
    from sleep_quant import sun_times
    out = []
    for d in pd.date_range("2026-08-30", "2026-09-11"):
        ss = pd.Timestamp(sun_times(d.date())[1])
        sr = pd.Timestamp(sun_times((d + pd.Timedelta(days=1)).date())[0])
        out.append((f"{d:%m-%d}", ss, min(sr, FEMALES)))
    return [w for w in out if w[1] < w[2]]


def track_seconds(an: str) -> pd.DataFrame:
    from default_tracks import list_default_tracks, load_default_track
    idx = list_default_tracks(COHORT)
    parts = []
    for d in idx[idx.label == an].date:
        df = load_default_track(an, d)
        df = df[~(df.m_handling | df.m_silence | df.m_off_animal | df.m_tag_validity)]
        qf = OUT_ROOT / "wiser_default_tracks_qc" / an / f"{pd.Timestamp(d):%Y%m%d}.csv.gz"
        q = pd.read_csv(qf, usecols=["t_ms", "qc_i1"]) if qf.exists() else pd.DataFrame({"t_ms": [], "qc_i1": []})
        df = df.merge(q, on="t_ms", how="left")
        t = pd.to_datetime(df.t_al_ms, unit="ms", utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
        parts.append(pd.DataFrame({"sec": sec_of(t), "x": df.x.to_numpy(), "y": df.y.to_numpy(), "anchors": df.anchors_used.to_numpy(),
                                   "qc_i1": df.qc_i1.fillna(0).astype(bool).to_numpy()}))
    T = pd.concat(parts, ignore_index=True)
    return T.groupby("sec").agg(x=("x", "median"), y=("y", "median"), anchors=("anchors", "median"), qc_i1=("qc_i1", "max"))


def imu_seconds(an: str) -> pd.DataFrame:
    parts = []
    for f in sorted((OUT_ROOT / "imu_seconds_cache" / an).glob("*.csv.gz")):
        d = pd.read_csv(f, usecols=["sec", "ok", "still", "state"])
        d["sec"] = d.sec.astype(np.int64) - 4 * 3600                    # Unix UTC -> EDT-naive seconds
        parts.append(d)
    return pd.concat(parts, ignore_index=True).drop_duplicates("sec").set_index("sec")


def operator_windows() -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    e = json.loads((REPO / "cv/configs/cohort3_handling_windows.json").read_text(encoding="utf-8"))
    out = []
    for w in e["windows"]:
        a = pd.Timestamp(w.get("start") or w.get("t0") or w[0]) if not isinstance(w, list) else pd.Timestamp(w[0])
        b = pd.Timestamp(w.get("end") or w.get("t1") or w[1]) if not isinstance(w, list) else pd.Timestamp(w[1])
        out.append((a - pd.Timedelta(minutes=30), b + pd.Timedelta(minutes=30)))
    out.append(MIDNIGHT_ROUND)
    return out


def session_detectability(an: str, ses: str, states_root: Path, n: int) -> tuple[np.ndarray, np.ndarray]:
    """Per session second: (theta ok, LFP-EMG ok) = `th` / the fast LFP-EMG below the session's NREM 95th percentile."""
    with np.load(states_root / an / f"{ses}.states.npz") as z:
        ts, st, th = z["ts"].astype(int), z["state"], z["th"].astype(float)
    ok = np.ones(n, bool)
    ok_e = np.ones(n, bool)
    sec = np.clip(ts - 1, 0, n - 1)                                     # ts is 1-based
    thr_th = np.nanpercentile(th[st == N], 95) if (st == N).any() else np.inf
    ok[sec[th > thr_th]] = False
    ef = Path(EMG_ROOT) / an / f"{ses}.EMGFromLFP50Hz.npz"
    if ef.exists():
        with np.load(ef) as z:
            s_ = np.floor(z["j"] * 0.02).astype(int)
            c = z["corr"].astype(float)
        e = pd.Series(c).groupby(s_).mean()
        nrem_sec = set(sec[st == N])
        en = e[e.index.isin(nrem_sec)]
        thr_e = np.nanpercentile(en, 95) if len(en) else np.inf
        bad = e.index[(e > thr_e).to_numpy()].to_numpy()
        ok_e[bad[(bad >= 0) & (bad < n)]] = False
    return ok, ok_e


def build_animal(an: str, a) -> pd.DataFrame:
    import rem_ripple_model as rrm
    from sleep_model import records_for
    from sleep_schedule import REVIEW, STATES, included_sessions
    ctx = rrm.prepare(a)
    recs = [r for r in records_for(STATES) if r["animal"] == an]
    starts = {(r.animal, r.session): r.start for r in included_sessions(REVIEW, STATES).itertuples() if r.animal == an}
    wins = night_windows()
    T = track_seconds(an)
    I = imu_seconds(an)
    import yaml
    from swr_auto import channels_for
    cfg = yaml.safe_load(open(HERE / "configs/swr_channels_2026c.yaml"))
    Z = pd.read_csv(Path(a.night_run) / f"zones_smoothed_{an}.csv.gz", parse_dates=["t"])
    Z["sec"] = sec_of(Z.t)
    Z = Z.drop_duplicates("sec").set_index("sec")
    ops = operator_windows()
    parts = []
    for rc in recs:
        st = rc["state"]
        n = len(st)
        t0 = rc["start"]
        secs = sec_of([t0])[0] + np.arange(n)
        tt = pd.to_datetime(secs, unit="s")
        night = np.zeros(n, bool)
        nlab = np.full(n, "", object)
        for lab, a0, a1 in wins:
            m = (tt >= a0) & (tt < a1)
            night |= m
            nlab[m] = lab
        if not night.any():
            continue
        A = rrm.record_arrays(rc, starts, ctx["Q"], ctx["settle"], ctx["cache"], ctx["codes"])
        det_th, det_em, rip_only = np.ones(n, bool), np.ones(n, bool), np.zeros(n, bool)
        qsw, kept, allw = np.zeros(n, np.int16), np.zeros(n, np.int16), np.zeros(n, np.int16)
        offs = [int(round((starts[(an, s)] - t0).total_seconds())) for s in rc["sessions"]]
        for s, o, e in zip(rc["sessions"], offs, offs[1:] + [n]):
            lo, hi = max(o, 0), min(e, n)
            if hi <= lo:
                continue
            dth, dem = session_detectability(an, s, Path(a.states_root), hi - o)
            det_th[lo:hi], det_em[lo:hi] = dth[lo - o:hi - o], dem[lo - o:hi - o]
            rip_only[lo:hi] = channels_for(cfg, an, s).get("boundary_features") == "ripple"
            f = Path(a.swr_root) / an / s / f"{s}.swr_events.npz"
            if not f.exists():
                continue
            with np.load(f, allow_pickle=True) as z:
                pk = o + np.floor(z["peak_s"]).astype(np.int64)
                good = ~(z["x_theta"] | z["x_emg_lfp"] | z["x_moving"])
                keep = ~z["excluded"].astype(bool)
            k = (pk >= lo) & (pk < hi)
            np.add.at(kept, pk[k & keep & (st[np.clip(pk, 0, n - 1)] == W)], 1)
            np.add.at(allw, pk[k & (st[np.clip(pk, 0, n - 1)] == W)], 1)
            np.add.at(qsw, pk[k & good & (st[np.clip(pk, 0, n - 1)] == W)], 1)
        hand = np.zeros(n, bool)
        for a0, a1 in ops:
            hand |= (tt >= a0) & (tt < a1)
        zi = Z.reindex(secs)
        hand |= zi.handling.fillna(False).astype(bool).to_numpy()
        ble = np.zeros(n, bool)
        for a0, a1 in BLE_PASSES:
            ble |= (tt >= pd.Timestamp(a0) - pd.Timedelta(minutes=15)) & (tt < pd.Timestamp(a1) + pd.Timedelta(minutes=15))
        ii = I.reindex(secs)
        istate = ii.state.fillna(0).astype(np.int8).to_numpy()
        ti = T.reindex(secs)
        zone = zi.zone.fillna(0).astype(np.int8).to_numpy()
        df = pd.DataFrame({"sec": secs, "night": nlab, "rec": rc["record_id"], "state": st, "zone": zone,
                           "imu_ok": ii.ok.fillna(False).astype(bool).to_numpy(), "still": ii.still.fillna(False).astype(bool).to_numpy(),
                           "x": ti.x.to_numpy(), "y": ti.y.to_numpy(), "anchors": ti.anchors.to_numpy(), "qc_i1": ti.qc_i1.fillna(False).astype(bool).to_numpy(),
                           "imu_state": istate, "cov": A["cov"], "blk": A["blk"], "det_theta": det_th, "det_emg": det_em,
                           "ripple_only_block": rip_only, "handling": hand, "ble_pass": ble, "qswr_raw": qsw, "kept_raw": kept,
                           "wake_events": allw})
        # trials: the record's night stretch split at home naps (computed on the whole record, then restricted)
        naps = home_naps(st, zone)
        df["home_nap"] = False
        for a_, b_ in naps:
            df.loc[a_:b_ - 1, "home_nap"] = True
        df = df[night].copy()
        parts.append(df)
    S = pd.concat(parts, ignore_index=True).sort_values("sec").reset_index(drop=True)
    S["has_pos"] = S.x.notna()
    S["detectable"] = S.det_theta & S.det_emg
    S["quiet"] = (S.state == W) & S.imu_ok & S.still & ~S.handling & S["cov"] & S.detectable & S.has_pos
    S["qswr"] = np.where(S.quiet, S.qswr_raw, 0)
    # Amendment 2 (primary): the production's kept-event rule in non-locomotor wake that is theta-detectable (and
    # EMG-detectable on ripple-only blocks, where EMG-flagged events are excluded)
    S["det2"] = S.det_theta & (S.det_emg | ~S.ripple_only_block)
    S["nonloco"] = (S.state == W) & S.imu_ok & S.imu_state.isin([1, 2]) & ~S.handling & S["cov"] & S.det2 & S.has_pos
    S["aswr"] = np.where(S.nonloco, S.kept_raw, 0)
    # trial and excursion ids: contiguous runs within (night, record) outside home naps
    S["trial"] = -1
    S["excursion"] = -1
    tid = eid = 0
    for (nt, rec), g in S.groupby(["night", "rec"], sort=False):
        idx = g.index.to_numpy()
        gap = np.r_[True, np.diff(g.sec.to_numpy()) != 1]
        for a_, b_ in segments_between(len(g), [(i, i + 1) for i in np.flatnonzero(g.home_nap.to_numpy())]):
            sub = idx[a_:b_]
            cut = np.flatnonzero(gap[a_:b_])[1:]
            for piece in np.split(sub, cut):
                S.loc[piece, "trial"] = tid
                tid += 1
        for a_, b_ in field_runs(g.zone.to_numpy()):
            S.loc[idx[a_:b_], "excursion"] = eid
            eid += 1
    S["animal"] = an
    return S


# ------------------------------------------------------------------ phase 0
def phase0(a):
    from joblib import Parallel, delayed
    from output_paths import run_dir
    t0 = time.time()
    out = Path(a.run) if a.run else run_dir("awake_ripple_map", COHORT)
    p = p0_params()
    origin = to_wiser(np.array([[0.0, 0.0]]), p)[0]
    animals = ["SF07", "SF08", "SF09", "SF10", "SF11", "SF12"]
    tabs = Parallel(n_jobs=min(a.workers, 6), backend="loky")(delayed(build_animal)(an, a) for an in animals)
    rows, trows = [], []
    for S in tabs:
        an = S.animal.iloc[0]
        S["bx"] = np.floor((S.x - origin[0]) / BIN_IN)
        S["by"] = np.floor((S.y - origin[1]) / BIN_IN)
        S.to_csv(out / f"seconds_{an}.csv.gz", index=False)
        for nt, g in S.groupby("night"):
            q = g[g.quiet]
            fq = q[q.zone == 3]
            occ = fq.groupby(["bx", "by"]).size()
            tr = g[(g.trial >= 0)].groupby("trial").size()
            rows.append(dict(animal=an, night=nt, recorded_min=len(g) / 60, wake_min=float((g.state == W).sum() / 60),
                             quiet_min=len(q) / 60, quiet_field_min=len(fq) / 60, quiet_h1_min=float((q.zone == 1).sum() / 60),
                             quiet_h2_min=float((q.zone == 2).sum() / 60), quiet_unknown_zone_min=float((q.zone == 0).sum() / 60),
                             qswr=int(q.qswr.sum()), qswr_field=int(fq.qswr.sum()), qswr_house=int(q[q.zone.isin([1, 2])].qswr.sum()),
                             wake_events_all=int(g.wake_events.sum()), bins_field_120s=int((occ >= MIN_OCC_S).sum()),
                             trials=int((tr >= 600).sum()), trials_all=len(tr), excursions=int(g[g.excursion >= 0].excursion.nunique()),
                             nonloco_min=float(g.nonloco.sum() / 60), nonloco_field_min=float((g.nonloco & (g.zone == 3)).sum() / 60),
                             aswr=int(g.aswr.sum()), aswr_field=int(g.aswr[g.zone == 3].sum()), aswr_house=int(g.aswr[g.zone.isin([1, 2])].sum()),
                             share_wake_handling=float(g.handling[g.state == W].mean()) if (g.state == W).any() else np.nan,
                             share_wake_theta_undet=float((~g.det_theta)[g.state == W].mean()) if (g.state == W).any() else np.nan,
                             share_wake_locomoting=float((g.imu_state == 3)[(g.state == W) & g.imu_ok].mean()) if ((g.state == W) & g.imu_ok).any() else np.nan,
                             share_wake_not_covered=float((~g["cov"])[g.state == W].mean()) if (g.state == W).any() else np.nan,
                             share_wake_undetectable=float((~g.detectable)[g.state == W].mean()) if (g.state == W).any() else np.nan,
                             share_wake_no_pos=float((~g.has_pos)[g.state == W].mean()) if (g.state == W).any() else np.nan,
                             share_wake_imu_not_ok=float((~g.imu_ok)[g.state == W].mean()) if (g.state == W).any() else np.nan,
                             share_wake_still=float(g.still[(g.state == W) & g.imu_ok].mean()) if ((g.state == W) & g.imu_ok).any() else np.nan))
        for tr_, g in S[S.trial >= 0].groupby("trial"):
            q = g[g.quiet]
            trows.append(dict(animal=an, night=g.night.iloc[0], trial=int(tr_), start=str(pd.to_datetime(g.sec.iloc[0], unit="s")),
                              minutes=len(g) / 60, quiet_min=len(q) / 60, quiet_field_min=float((q.zone == 3).sum() / 60), qswr=int(q.qswr.sum())))
    C = pd.DataFrame(rows)
    TR = pd.DataFrame(trows)
    C.to_csv(out / "phase0_nights.csv", index=False)
    TR.to_csv(out / "phase0_trials.csv", index=False)
    A = C.groupby("animal").agg(nights=("night", "nunique"), quiet_h=("quiet_min", lambda x: x.sum() / 60), quiet_field_h=("quiet_field_min", lambda x: x.sum() / 60),
                                qswr=("qswr", "sum"), qswr_field=("qswr_field", "sum"), qswr_house=("qswr_house", "sum"),
                                trials_10min=("trials", "sum"), excursions=("excursions", "sum"),
                                nonloco_h=("nonloco_min", lambda x: x.sum() / 60), nonloco_field_h=("nonloco_field_min", lambda x: x.sum() / 60),
                                aswr=("aswr", "sum"), aswr_field=("aswr_field", "sum"), aswr_house=("aswr_house", "sum")).reset_index()
    bins, bins2 = {}, {}
    for S in tabs:
        an = S.animal.iloc[0]
        q = S[S.quiet & (S.zone == 3)]
        bins[an] = int((q.groupby(["bx", "by"]).size() >= MIN_OCC_S).sum())
        q2 = S[S.nonloco & (S.zone == 3)]
        bins2[an] = int((q2.groupby(["bx", "by"]).size() >= MIN_OCC_S).sum())
    A["bins_field_120s_pooled"] = A.animal.map(bins)
    A["bins2_field_120s_pooled"] = A.animal.map(bins2)
    A["enters_inference"] = (A.qswr_field >= 300) & (A.bins_field_120s_pooled >= 20)
    A["enters_inference_A2"] = (A.aswr_field >= 300) & (A.bins2_field_120s_pooled >= 20)
    A.to_csv(out / "phase0_animals.csv", index=False)
    print(A.round(2).to_string(index=False))
    write_json(out / "meta.json", dict(git=git_commit(), p0_map=p["file"], origin_wiser=origin.tolist(), bin_in=BIN_IN,
                                      minutes=(time.time() - t0) / 60))
    report0(out, A, C, TR)


def report0(out: Path, A: pd.DataFrame, C: pd.DataFrame, TR: pd.DataFrame) -> Path:
    rd = report_dir(COHORT)
    A.to_csv(rd / f"ephys_spikes_awake_ripple_map_phase0_animals_{COHORT}.csv", index=False)
    C.to_csv(rd / f"ephys_spikes_awake_ripple_map_phase0_nights_{COHORT}.csv", index=False)
    L = [f"# Awake ripples at night across the paddock (cohort {COHORT}) — Phase 0: counts, no maps", "",
         "Plan: [2026-10-10-awake-ripple-map.md](../../../../implementation_plan/2026-10-10-awake-ripple-map.md) (Amendment 1 "
         f"after the Codex audit). Driver `ephys/awake_ripple_map.py phase0`; run `{out}`.", "",
         "## Per animal", "",
         "| animal | nights | quiet wake h | in the field h | qSWR | in the field | in the houses | trials ≥ 10 min | excursions | field bins ≥ 120 s | enters inference |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|"]
    for r in A.itertuples():
        L.append(f"| {r.animal} | {r.nights} | {r.quiet_h:.1f} | {r.quiet_field_h:.1f} | {r.qswr} | {r.qswr_field} | {r.qswr_house} | "
                 f"{r.trials_10min} | {r.excursions} | {r.bins_field_120s_pooled} | {'yes' if r.enters_inference else 'no'} |")
    L += ["", "Amendment 2 definition (the production's kept rule in non-locomotor, theta-detectable wake):", "",
          "| animal | non-locomotor wake h | in the field h | awake ripples | in the field | in the houses | field bins >= 120 s | enters inference |",
          "|---|---:|---:|---:|---:|---:|---:|:---:|"]
    for r in A.itertuples():
        L.append(f"| {r.animal} | {r.nonloco_h:.1f} | {r.nonloco_field_h:.1f} | {r.aswr} | {r.aswr_field} | {r.aswr_house} | "
                 f"{r.bins2_field_120s_pooled} | {'yes' if r.enters_inference_A2 else 'no'} |")
    L += ["", "## Where the night's wake seconds are lost (median over animal-nights)", "",
          f"- in handling windows: {C.share_wake_handling.median():.3f}",
          f"- theta above the session's NREM 95th pct.: {C.share_wake_theta_undet.median():.3f}",
          f"- head IMU locomoting (of IMU-ok wake): {C.share_wake_locomoting.median():.3f}",
          f"- not SWR-covered: {C.share_wake_not_covered.median():.3f}",
          f"- undetectable (theta / LFP-EMG above the session's NREM 95th pct.): {C.share_wake_undetectable.median():.3f}",
          f"- no position: {C.share_wake_no_pos.median():.3f}",
          f"- head IMU not ok: {C.share_wake_imu_not_ok.median():.3f}",
          f"- IMU-still share of IMU-ok wake: {C.share_wake_still.median():.3f}", "",
          "Definitions in the driver's docstring and the plan. No rate, map or place statistic is computed in Phase 0.", ""]
    p = rd / f"ephys_spikes_awake_ripple_map_phase0_{COHORT}.md"
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    write_json(rd / f"run_manifest_awake_ripple_map_{COHORT}.json", dict(name="awake_ripple_map", run_dir=str(out), git=git_commit(), report=str(p)))
    print(f"report {p}")
    return p


# ------------------------------------------------------------------ Phase 1: the blind validity page (Amendment 3)
REVIEW_PLAN = {"aswr_field": 40, "aswr_house": 40, "nrem": 30, "neg": 30}


def event_catalogue(an: str, a) -> pd.DataFrame:
    """Every kept event of the animal's covered sessions with its session, peak, local second, state and strength."""
    import rem_ripple_model as rrm
    q = pd.read_csv(a.quality)
    q = q[(q.animal == an) & q.tier.isin(["validated", "good"])]
    rv = pd.read_csv(a.review)[["animal", "session", "start_local"]]
    q = q.merge(rv, on=["animal", "session"], how="left")
    rows = []
    for r in q.itertuples():
        f = Path(a.swr_root) / an / r.session / f"{r.session}.swr_events.npz"
        if not f.exists():
            continue
        with np.load(f, allow_pickle=True) as z:
            k = ~z["excluded"].astype(bool)
            t = pd.to_datetime(r.start_local) + pd.to_timedelta(z["peak_s"][k], unit="s")
            rows.append(pd.DataFrame({"animal": an, "session": r.session, "block": r.block, "peak_s": z["peak_s"][k], "sec": sec_of(t),
                                      "state": z["state"][k], "amplitude": z["amplitude"][k], "RipMax_z": z["RipMax_z"][k]}))
    return pd.concat(rows, ignore_index=True)


def pick_items(run: Path, a, rng: np.random.Generator) -> pd.DataFrame:
    items = []
    animals = ["SF07", "SF08", "SF09", "SF10", "SF11", "SF12"]
    pools = {}
    for an in animals:
        S = pd.read_csv(run / f"seconds_{an}.csv.gz", usecols=["sec", "zone", "nonloco", "aswr", "night"])
        E = event_catalogue(an, a)
        E["tert"] = E.groupby("block").amplitude.transform(lambda x: pd.qcut(x, 3, labels=False, duplicates="drop"))
        W_ = E[E.state == "WAKE"].merge(S[S.nonloco & (S.aswr > 0)][["sec", "zone", "night"]], on="sec")
        pools[an] = {"field": W_[W_.zone == 3], "house": W_[W_.zone.isin([1, 2])], "nrem": E[E.state == "NREM"]}
        quiet = S[S.nonloco].sec.to_numpy()
        ev = np.sort(E.sec.to_numpy())
        near = (np.searchsorted(ev, quiet + 3) - np.searchsorted(ev, quiet - 2)) > 0
        cand = quiet[~near]
        sess = E.groupby("session").sec.agg(["min", "max"]).reset_index()
        pools[an]["neg"] = pd.DataFrame({"sec": cand})
        pools[an]["sessions"] = sess

    def round_robin(kind, n, by_tert=True):
        take, k = [], 0
        order = [an for an in animals if len(pools[an][kind])]
        while len(take) < n and order:
            an = order[k % len(order)]
            P = pools[an][kind]
            if by_tert and "tert" in P:
                t = k // len(order) % 3
                P2 = P[P.tert == t]
                P = P2 if len(P2) else P
            if len(P):
                r = P.iloc[int(rng.integers(len(P)))]
                take.append(dict(animal=an, kind=kind, session=r.session, peak_s=float(r.peak_s), zone=int(r.get("zone", 0)),
                                 amplitude=float(r.amplitude), RipMax_z=float(r.RipMax_z), tert=int(r.tert) if pd.notna(r.tert) else -1))
                pools[an][kind] = pools[an][kind].drop(r.name)
            else:
                order.remove(an)
                continue
            k += 1
        return take

    items += [dict(x, set="aSWR field") for x in round_robin("field", REVIEW_PLAN["aswr_field"])]
    items += [dict(x, set="aSWR house") for x in round_robin("house", REVIEW_PLAN["aswr_house"])]
    items += [dict(x, set="NREM SWR") for x in round_robin("nrem", REVIEW_PLAN["nrem"])]
    # negatives: a random non-locomotor detectable second, mapped back to its session
    neg = []
    k = 0
    while len(neg) < REVIEW_PLAN["neg"]:
        an = animals[k % len(animals)]
        k += 1
        P = pools[an]["neg"]
        if not len(P):
            continue
        s_ = int(P.sec.iloc[int(rng.integers(len(P)))])
        ss = pools[an]["sessions"]
        hit = ss[(ss["min"] <= s_) & (ss["max"] >= s_)]
        if not len(hit):
            continue
        ses = hit.session.iloc[0]
        rv = pd.read_csv(a.review)
        st0 = pd.to_datetime(rv[(rv.animal == an) & (rv.session == ses)].start_local.iloc[0])
        neg.append(dict(animal=an, kind="neg", session=ses, peak_s=float(s_ + 0.5 - (st0 - EPOCH).total_seconds()), zone=-1,
                        amplitude=np.nan, RipMax_z=np.nan, tert=-1, set="random quiet moment"))
    items += neg
    P = pd.DataFrame(items)
    P = P.iloc[rng.permutation(len(P))].reset_index(drop=True)
    P["rid"] = [f"R{i + 1:03d}" for i in range(len(P))]
    return P


def regress_out(x: np.ndarray, ref: np.ndarray, fit_mask: np.ndarray, fs: float = 1250.0, hp: float = 80.0) -> tuple[np.ndarray, float]:
    """x minus beta * ref, both high-passed at `hp` Hz, beta fitted by least squares on fit_mask (the candidate's own
    +-0.25 s are left out, so a local ripple does not enter the fit). Removes the common-mode (EMG) part above hp only,
    so the sharp wave and theta are untouched."""
    from scipy import signal
    sos = signal.butter(3, hp, btype="highpass", fs=fs, output="sos")
    xh, rh = signal.sosfiltfilt(sos, x), signal.sosfiltfilt(sos, ref)
    den = float(np.dot(rh[fit_mask], rh[fit_mask]))
    beta = float(np.dot(xh[fit_mask], rh[fit_mask]) / den) if den > 0 else 0.0
    return x - beta * rh, beta


def emgica_item(it, a, cfg: dict, out: Path) -> dict:
    """EMG removal by ICA (ephys/emg_ica.py = Chen 2023's EMG_removing, 'hw' path) on the chunk of +-ica_half_s around one
    validity item, every shank separately; keeps the cleaned +-6 s window (all live sites) and the raw-vs-cleaned numbers
    of the denoiser comparison (Addendum 4a)."""
    from scipy import signal
    import emg_ica
    from swr_auto import channels_for
    from swr_channel_scan import XML, shanks_from_xml
    FS = 1250
    ch = channels_for(cfg, it.animal, it.session)
    rc, nc = int(ch["ripple_col"]), int(ch["noise_col"])
    excl = set(ch.get("exclude_cols", []))
    sh = shanks_from_xml(HERE / "configs/xml" / XML[it.animal])
    shanks = [[c for c, sk in g if not sk and c not in excl] for _, g in sh]
    lfp = Path(a.lfp_root) / it.animal / f"{it.session}.lfp"
    nch = int(json.loads(Path(str(lfp) + ".json").read_text())["n_channels"])
    mm = np.memmap(lfp, dtype=np.int16, mode="r")
    mm = mm[: mm.size // nch * nch].reshape(-1, nch)
    c0 = max(int((it.peak_s - a.ica_half_s) * FS), 0)
    c1 = min(int((it.peak_s + a.ica_half_s) * FS), len(mm))
    X = np.asarray(mm[c0:c1], np.float64)
    own = next(si for si, s in enumerate(shanks) if rc in s)
    seeds = list(a.ica_seeds)
    if a.ica_own_shank_only:
        # only the ripple's shank is shown cleaned (noise site raw, LFP-EMG panel raw, theta < 30 Hz untouched); the toolbox's
        # acceptance is seed-dependent near its thresholds (also in the MATLAB original, 2026-10-10) -> accept only when it
        # holds for a majority of the seeds, and keep the output of the first accepting seed
        runs = []
        for s in seeds:
            Xs, inf = emg_ica.clean_chunk(X, [shanks[own]], fs=FS, lower=a.ica_lower_hz, seed=s, always_rm=False)
            runs.append((s, Xs, inf[0]))
        met = [s for s, _, inf in runs if inf.get("criteria_met")]
        accepted = len(met) >= len(seeds) // 2 + 1
        s_use, Xc, inf_own = next(r for r in runs if r[0] == met[0]) if accepted else (seeds[0], X.copy(), runs[0][2])
        inf_own = dict(inf_own, shank=own, removed=accepted, removed_by="criteria_majority" if accepted else None,
                       seeds=seeds, seeds_met=met, seed_used=s_use if accepted else None)
        infos = [dict(shank=si, skipped="not processed (own shank only)") for si in range(len(shanks))]
        infos[own] = inf_own
    else:
        Xc, infos = emg_ica.clean_chunk(X, shanks, fs=FS, lower=a.ica_lower_hz, seed=seeds[0], always_rm=a.ica_always_rm)
    w0, w1 = max(int((it.peak_s - 6.0) * FS), 0), int((it.peak_s + 6.0) * FS)
    cols = sorted(c for s in shanks for c in s)
    win = Xc[w0 - c0:w1 - c0][:, cols]
    np.savez_compressed(out / f"{it.rid}.npz", w0=w0, cols=np.array(cols), X=win.astype(np.float32), chunk=np.array([c0, c1]))
    (out / f"{it.rid}.json").write_text(json.dumps(dict(rid=it.rid, chunk_s=[c0 / FS, c1 / FS], shanks=infos)))
    # numbers at the ripple site (as review_denoise_compare.csv): 100-250 Hz RMS after / before
    t = (np.arange(w1 - w0) + w0) / FS - it.peak_s
    raw, cln = X[w0 - c0:w1 - c0, rc], win[:, cols.index(rc)]
    sos = signal.butter(3, (100, 250), btype="bandpass", fs=FS, output="sos")
    esos = signal.butter(3, (300, 450), btype="bandpass", fs=FS, output="sos")
    rr, cr = signal.sosfiltfilt(sos, raw), signal.sosfiltfilt(sos, cln)
    bg, pk = (np.abs(t) >= 0.25) & (np.abs(t) <= 2), np.abs(t) <= 0.025
    en = signal.sosfiltfilt(esos, X[w0 - c0:w1 - c0, nc])
    inf = infos[own]
    return dict(rid=it.rid, bg=float(np.sqrt(np.mean(cr[bg] ** 2) / np.mean(rr[bg] ** 2))),
                pk=float(np.sqrt(np.mean(cr[pk] ** 2) / np.mean(rr[pk] ** 2))),
                con=float(np.sqrt(np.mean(cr[pk] ** 2) / np.mean(cr[bg] ** 2))),
                con_raw=float(np.sqrt(np.mean(rr[pk] ** 2) / np.mean(rr[bg] ** 2))),
                emg_r=float(np.corrcoef(signal.sosfiltfilt(esos, cln)[bg], en[bg])[0, 1]),
                own_removed=bool(inf.get("removed", False)), own_removed_by=inf.get("removed_by"),
                own_criteria_met=inf.get("criteria_met"), own_flat_max=inf.get("flat_max"),
                own_n_flat_gt10=inf.get("n_flat_gt10"), own_thrd_frac=inf.get("thrd_frac"),
                own_seeds_met=" ".join(map(str, inf.get("seeds_met", []))) if "seeds_met" in inf else None,
                n_shanks_removed=int(sum(bool(i.get("removed", False)) for i in infos)), n_shanks=len(shanks),
                chunk_s=round((c1 - c0) / FS, 1))


def emgica(a):
    """Run emgica_item on every validity item (GPU FastICA when the env's torch can run on this card)."""
    import yaml
    from joblib import Parallel, delayed
    man = json.loads((report_dir(COHORT) / f"run_manifest_awake_ripple_map_{COHORT}.json").read_text())
    run = Path(a.run or man["run_dir"])
    P = pd.read_csv(run / "review_key_SEALED.csv")
    out = Path(a.ica_dir) if a.ica_dir else run / "emg_ica"
    out.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(open(HERE / "configs/swr_channels_2026c.yaml"))
    done = pd.read_csv(out / "emg_ica_items.csv") if (out / "emg_ica_items.csv").exists() else pd.DataFrame(columns=["rid", "own_removed"])
    redo = set(done.rid[~done.own_removed.astype(bool)]) if a.ica_always_rm else set()   # only items the criteria left uncleaned
    todo = [it for it in P.itertuples() if not (out / f"{it.rid}.npz").exists() or it.rid in redo]
    rows = Parallel(n_jobs=a.workers, backend="loky")(delayed(emgica_item)(it, a, cfg, out) for it in todo)
    old = pd.read_csv(out / "emg_ica_items.csv") if (out / "emg_ica_items.csv").exists() else pd.DataFrame()
    D = pd.concat([old, pd.DataFrame(rows)]).drop_duplicates("rid", keep="last")
    D.to_csv(out / "emg_ica_items.csv", index=False)
    print(f"EMG-ICA: {len(rows)} new items, {len(D)} in {out}")


def render_ripple(it, a, png: Path, cfg: dict, denoise: str = "none") -> None:
    """One blind panel: +-2 s raw stack, +-0.5 s raw and 100-250 Hz, +-2 s spectrogram, theta (the detector's
    theta/delta with its x_theta threshold, + the radiatum 6-10 Hz trace) and the LFP-EMG with its x_emg_lfp threshold
    (the user, 2026-10-10: awake false positives are EMG noise and gamma riding on theta)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy import signal
    import swr_emg
    from swr_auto import channels_for
    from swr_channel_scan import XML, shanks_from_xml
    ch = channels_for(cfg, it.animal, it.session)
    xml = HERE / "configs/xml" / XML[it.animal]
    sh = shanks_from_xml(xml)
    rc, swc, nc = int(ch["ripple_col"]), int(ch["sharpwave_col"]), int(ch["noise_col"])
    col_list = next(g for _, g in sh if any(c == rc for c, _ in g))
    cols = [c for c, sk in col_list]
    i = cols.index(rc)
    show = cols[max(0, i - 2):i + 3] + [nc]
    emg_cols = swr_emg.emg_channels(xml, skip=set(ch.get("exclude_cols", [])))
    summ = Path(a.swr_root) / it.animal / it.session / f"{it.session}.swr_summary.json"
    thr = json.loads(summ.read_text()).get("thresholds", {}) if summ.exists() else {}
    lfp = Path(a.lfp_root) / it.animal / f"{it.session}.lfp"
    nch = int(json.loads(Path(str(lfp) + ".json").read_text())["n_channels"])
    mm = np.memmap(lfp, dtype=np.int16, mode="r")
    mm = mm[: mm.size // nch * nch].reshape(-1, nch)
    FS = 1250
    PAD = 6.0                                                          # context for the filters
    c0 = int((it.peak_s - PAD) * FS)
    c0c = max(c0, 0)
    allc = sorted(set(show) | set(emg_cols) | {swc})
    X = np.asarray(mm[c0c:int((it.peak_s + PAD) * FS), allc], np.float64)
    t_all = (np.arange(X.shape[0]) + c0c) / FS - it.peak_s
    col = {c: X[:, k] for k, c in enumerate(allc)}
    rawcol = dict(col)
    raw_rc = col[rc].copy()
    if denoise == "regress":                                           # the user, 2026-10-10: EMG makes awake panels unreadable
        fit = np.abs(t_all) >= 0.25
        for c in show[:-1]:
            col[c], _ = regress_out(col[c], col[nc], fit)
    ica_note = ""
    cleaned = denoise == "regress"
    if denoise == "ica":                                               # Chen 2023 EMG_removing (ephys/emg_ica.py)
        z = np.load(Path(a.ica_dir) / f"{it.rid}.npz")
        assert int(z["w0"]) == c0c and z["X"].shape[0] == X.shape[0], f"{it.rid}: ICA window mismatch"
        info = json.loads((Path(a.ica_dir) / f"{it.rid}.json").read_text())["shanks"]
        own = next(si for si, (_, g) in enumerate(sh) if any(c == rc for c, _ in g))
        cleaned = bool(info[own].get("removed", False))
        zc = list(z["cols"])
        for c in allc:
            if c in zc and c != nc:                                    # the noise site stays raw: the reference (the user, 10-10)
                col[c] = z["X"][:, zc.index(c)].astype(np.float64)
        ica_note = ("EMG-ICA: the flattest (muscle) component removed above 30 Hz on this shank; "
                    "noise site RAW (grey) = the reference, ± 2 s" if cleaned else
                    "EMG-ICA: NOT CLEANED on this shank (no single flat component found, toolbox criteria not met) - "
                    "all traces RAW, ± 2 s")
    w2 = (t_all >= -2.0) & (t_all <= 2.0)
    w05 = (t_all >= -0.5) & (t_all <= 0.5)
    uv = 0.195
    fig = plt.figure(figsize=(12, 13.5))
    gs = fig.add_gridspec(6, 1, height_ratios=[3.0, 1.1, 1.1, 1.7, 1.4, 1.0], hspace=0.55)
    # (1) raw stack
    ax = fig.add_subplot(gs[0])
    Y = np.column_stack([col[c][w2] * uv for c in show])
    sc = np.percentile(np.abs(Y - np.median(Y, 0)), 99) or 1
    for k, c in enumerate(show):
        y = Y[:, k] - np.median(Y[:, k])
        lab = "ripple site" if c == rc else ("noise site (cortex, top)" if k == len(show) - 1 else f"neighbour col {c}")
        ax.plot(t_all[w2], y / sc / 1.8 - 1.2 * k, lw=0.55, color="tab:red" if c == rc else ("tab:gray" if k == len(show) - 1 else "k"))
        ax.text(-2.0, -1.2 * k + 0.35, lab, fontsize=8)
    ax.axvline(0, color="tab:blue", lw=0.8, ls="--")
    if getattr(a, "mark_ms", 0):
        ax.axvspan(-a.mark_ms / 1000, a.mark_ms / 1000, color="tab:blue", alpha=0.10, lw=0)
    ax.set_yticks([])
    ax.set_xlim(-2, 2)
    ax.set_title({"regress": "DENOISED (the noise site's > 80 Hz part regressed out of each CA1 site; noise site itself raw, grey), ± 2 s",
                  "ica": ica_note}
                 .get(denoise, "raw LFP, ± 2 s (same-shank sites top -> bottom, then the noise site)"), fontsize=9,
                 color="tab:red" if (denoise == "ica" and not cleaned) else "k")
    # (2) raw zoom, (3) ripple band zoom
    xr = col[rc] * uv
    ax = fig.add_subplot(gs[1])
    ax.plot(t_all[w05], xr[w05] - np.median(xr[w05]), lw=0.7, color="tab:red")
    ax.axvline(0, color="tab:blue", lw=0.8, ls="--")
    if getattr(a, "mark_ms", 0):
        ax.axvspan(-a.mark_ms / 1000, a.mark_ms / 1000, color="tab:blue", alpha=0.10, lw=0)
    ax.set_xlim(-0.5, 0.5)
    ax.set_ylabel("uV")
    ax.set_title("ripple site, denoised, ± 0.5 s" if cleaned else "ripple site, raw, ± 0.5 s", fontsize=9)
    sos = signal.butter(3, (100, 250), btype="bandpass", fs=FS, output="sos")
    ax = fig.add_subplot(gs[2])
    if cleaned:
        ax.plot(t_all[w05], signal.sosfiltfilt(sos, raw_rc * uv)[w05], lw=0.6, color="0.75", label="raw")
    ax.plot(t_all[w05], signal.sosfiltfilt(sos, xr)[w05], lw=0.7, color="tab:purple", label="denoised" if cleaned else None)
    ax.axvline(0, color="tab:blue", lw=0.8, ls="--")
    if getattr(a, "mark_ms", 0):
        ax.axvspan(-a.mark_ms / 1000, a.mark_ms / 1000, color="tab:blue", alpha=0.10, lw=0)
    ax.set_xlim(-0.5, 0.5)
    ax.set_ylabel("uV")
    if cleaned:
        ax.legend(fontsize=7, loc="upper left", ncol=2)
    ax.set_title("ripple site, 100-250 Hz, ± 0.5 s" + (" (grey = before denoising)" if cleaned else ""), fontsize=9)
    # (4) spectrogram 20-250 Hz, +-2 s, each frequency relative to its median over the +-6 s context
    ax = fig.add_subplot(gs[3])
    f, t, Sx = signal.spectrogram(xr, fs=FS, window="hann", nperseg=125, noverlap=113, scaling="density")
    t = t + t_all[0]
    m = (f >= 20) & (f <= 250)
    Z = np.log(Sx[m] + 1e-12)
    Z = Z - np.median(Z, axis=1, keepdims=True)
    k = (t >= -2) & (t <= 2)
    ax.pcolormesh(t[k], f[m], Z[:, k], shading="auto", cmap="magma", vmin=-1.0, vmax=3.0)
    ax.axvline(0, color="c", lw=0.8, ls="--")
    ax.set_ylabel("Hz")
    ax.set_xlim(-2, 2)
    ax.set_title("ripple site, 20-250 Hz power relative to its own ± 6 s median (a ripple = a brief bright blob above ~100 Hz; "
                 "gamma on theta = bands repeating every ~0.12 s)", fontsize=8.5)
    # (5) theta
    ax = fig.add_subplot(gs[4])
    td = swr_emg.theta_delta_log(col[rc])
    ax.plot(t_all[w2], td[w2], color="tab:orange", lw=1.2, label="theta/delta (ripple site, the detector's measure)")
    if thr.get("theta_delta_log") is not None:
        ax.axhline(thr["theta_delta_log"], color="tab:orange", lw=0.8, ls=":", label="x_theta threshold (session NREM 95th pct)")
    ax.set_ylabel("log ratio")
    ax2 = ax.twinx()
    sth = signal.butter(3, (6, 10), btype="bandpass", fs=FS, output="sos")
    ax2.plot(t_all[w2], signal.sosfiltfilt(sth, col[swc] * uv)[w2], color="tab:green", lw=0.6, alpha=0.7, label="radiatum 6-10 Hz (uV)")
    ax2.set_yticks([])
    ax.axvline(0, color="tab:blue", lw=0.8, ls="--")
    ax.set_xlim(-2, 2)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=7, loc="upper left", ncol=3)
    ax.set_title("theta", fontsize=9)
    # (6) LFP-EMG
    ax = fig.add_subplot(gs[5])
    src = rawcol if denoise == "ica" else col                         # after ICA the cross-shank measure is ~0 by design
    E = swr_emg.LfpEmg(np.column_stack([src[c] for c in emg_cols]))
    idx = np.flatnonzero(w2)[::25]
    ax.plot(t_all[idx], E.at(idx), color="k", lw=1.0,
            label="LFP-EMG (300-450 Hz cross-shank correlation)" + (", BEFORE cleaning = what the detector saw" if denoise == "ica" else ""))
    if thr.get("emg_lfp") is not None:
        ax.axhline(thr["emg_lfp"], color="k", lw=0.8, ls=":", label="x_emg_lfp threshold (session NREM 95th pct)")
    ax.axvline(0, color="tab:blue", lw=0.8, ls="--")
    ax.set_xlim(-2, 2)
    ax.legend(fontsize=7, loc="upper left", ncol=2)
    ax.set_xlabel("s from the candidate", fontsize=9)
    fig.suptitle(f"{it.rid}", fontsize=13)
    fig.savefig(png, dpi=85, bbox_inches="tight")
    plt.close(fig)


def rerender(a):
    """Re-draw the same blind items (same key, same ids) with the current panel layout (--denoise / --denoise regress: the
    noise site regressed out; --denoise ica: the EMG-ICA windows written by `emgica`)."""
    import yaml
    from joblib import Parallel, delayed
    man = json.loads((report_dir(COHORT) / f"run_manifest_awake_ripple_map_{COHORT}.json").read_text())
    run = Path(a.run or man["run_dir"])
    P = pd.read_csv(a.key if getattr(a, "key", None) else run / "review_key_SEALED.csv")
    out = Path(a.review_out) if a.review_out else run / "review"
    (out / "img").mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(open(HERE / "configs/swr_channels_2026c.yaml"))
    if a.denoise == "ica" and not a.ica_dir:
        a.ica_dir = str(run / "emg_ica")
    Parallel(n_jobs=a.workers, backend="loky")(delayed(render_ripple)(it, a, out / "img" / f"{it.rid}.png", cfg, a.denoise)
                                                for it in P.itertuples())
    print(f"re-rendered {len(P)} items -> {out / 'img'} (denoise={a.denoise})")


def review(a):
    import yaml
    from joblib import Parallel, delayed
    man = json.loads((report_dir(COHORT) / f"run_manifest_awake_ripple_map_{COHORT}.json").read_text())
    run = Path(a.run or man["run_dir"])
    P = pick_items(run, a, np.random.default_rng(11))
    out = Path(a.review_out) if a.review_out else run / "review"
    (out / "img").mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(open(HERE / "configs/swr_channels_2026c.yaml"))
    Parallel(n_jobs=a.workers, backend="loky")(delayed(render_ripple)(it, a, out / "img" / f"{it.rid}.png", cfg) for it in P.itertuples())
    P.to_csv(run / "review_key_SEALED.csv", index=False)
    print(P.groupby(["set", "animal"]).size().unstack(fill_value=0).to_string())
    print(f"{len(P)} items -> {out / 'img'}; key {run / 'review_key_SEALED.csv'}")


def selftest():
    ok = True
    s = segments_between(10, [(3, 5), (8, 9)])
    a = s == [(0, 3), (5, 8), (9, 10)]
    print(f"{'PASS' if a else 'FAIL'} segments_between {s}")
    ok &= a
    st = np.array([W] * 100 + [N] * 400 + [W] * 200 + [N] * 300 + [W] * 200, np.int8)
    zone = np.array([3] * 100 + [2] * 400 + [3] * 200 + [3] * 300 + [3] * 200, np.int8)
    hn = home_naps(st, zone)
    b = hn == [(100, 500)]
    print(f"{'PASS' if b else 'FAIL'} home naps (only the in-house sleep) {hn}")
    ok &= b
    fr = field_runs(np.array([3] * 150 + [1] * 10 + [3] * 50 + [0] * 5 + [3] * 130, np.int8))
    c = fr == [(0, 150), (215, 345)]
    print(f"{'PASS' if c else 'FAIL'} field runs {fr}")
    ok &= c
    p = {"d": np.array([-272.85, -605.8]), "th": np.deg2rad(0.114), "s": 0.963, "c": np.array([501.7, 761.1])}
    P = np.array([[0.0, 0.0], [480.0, 240.0]])
    rt = to_paddock(to_wiser(P, p), p)
    d = np.allclose(rt, P, atol=1e-9)
    print(f"{'PASS' if d else 'FAIL'} P0 round trip; paddock (0, 0) -> WISER {to_wiser(P, p)[0].round(1)}")
    ok &= d
    print("SELFTEST " + ("PASS" if ok else "FAIL"))
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["phase0", "review", "rerender", "emgica", "phase2", "night", "nights"])
    ap.add_argument("--first", type=int, default=7, help="nights: how many of the animal's first nights")
    ap.add_argument("--animal", default="SF10", help="night: the animal")
    ap.add_argument("--night", default="09-07", help="night: the night label (the evening's date, MM-DD)")
    ap.add_argument("--min-trial-min", type=float, default=2.0, help="night: shortest trial drawn (min)")
    ap.add_argument("--perms", type=int, default=1000, help="phase2: bout swaps for the primary tests")
    ap.add_argument("--sens-perms", type=int, default=500, help="phase2: bout swaps per sensitivity")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--run", default=None)
    ap.add_argument("--review-out", default=None, help="review: folder for the panels (default <run>/review)")
    ap.add_argument("--denoise", nargs="?", const="regress", default="none", choices=["none", "regress", "ica"],
                    help="rerender: 'regress' (= bare --denoise) regresses the noise site's > 80 Hz part out of the CA1 sites; "
                         "'ica' uses the EMG-ICA windows of `emgica`")
    ap.add_argument("--ica-dir", default=None, help="emgica / rerender --denoise ica: folder of the cleaned windows (default <run>/emg_ica)")
    ap.add_argument("--ica-half-s", type=float, default=450.0, help="emgica: half length of the chunk cleaned around each item (s)")
    ap.add_argument("--ica-lower-hz", type=float, default=30.0, help="emgica: EMG removed above this frequency (Chen 2023: 20-30 Hz)")
    ap.add_argument("--key", default=None, help="rerender: the item key (default <run>/review_key_SEALED.csv)")
    ap.add_argument("--mark-ms", type=float, default=0.0, help="rerender: shade +-this many ms around the line in panels 1-3")
    ap.add_argument("--ica-seeds", type=int, nargs="+", default=[0],
                    help="emgica: FastICA seeds; with --ica-own-shank-only an item counts as cleaned when the toolbox's rule holds "
                         "for a majority of them")
    ap.add_argument("--ica-own-shank-only", action="store_true", help="emgica: clean only the ripple's own shank")
    ap.add_argument("--ica-always-rm", action="store_true",
                    help="emgica: the toolbox's always_rm switch - where its acceptance rule fails, remove the flattest component "
                         "anyway (re-runs only the items left uncleaned)")
    ap.add_argument("--lfp-root", default="Q:/hc997/SocialFieldRat2026/3rd_rat/analysis/lfp")
    ap.add_argument("--night-run", default=None, help="night_sleep_wiser run (zones_smoothed_*.csv.gz); default from its manifest")
    ap.add_argument("--swr-root", default=SWR_ROOT)
    ap.add_argument("--sleep-root", default="Q:/hc997/SocialFieldRat2026/3rd_rat/analysis/sleep/imu_fixch")
    ap.add_argument("--states-root", default="D:/3rd_rat_spikes/analysis/sleep_server/states_1s_final")
    ap.add_argument("--quality", default=str(report_dir(COHORT) / f"ephys_spikes_swr_quality_{COHORT}.csv"))
    ap.add_argument("--review", default=str(report_dir(COHORT) / f"ephys_spikes_sleep_review_{COHORT}.csv"))
    ap.add_argument("--cohort-yaml", default=str(REPO / f"cohorts/{COHORT}.yaml"))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    if a.night_run is None:
        a.night_run = json.loads((report_dir(COHORT) / f"run_manifest_night_sleep_wiser_{COHORT}.json").read_text())["run_dir"]
    if a.cmd == "phase0":
        phase0(a)
    elif a.cmd == "review":
        review(a)
    elif a.cmd == "rerender":
        rerender(a)
    elif a.cmd == "emgica":
        emgica(a)
    elif a.cmd == "phase2":
        import awake_ripple_phase2
        awake_ripple_phase2.run(a)
    elif a.cmd == "night":
        import awake_ripple_phase2
        awake_ripple_phase2.night_trials(a)
    elif a.cmd == "nights":
        import awake_ripple_phase2
        awake_ripple_phase2.nights_grid(a)


if __name__ == "__main__":
    main()
