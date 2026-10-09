"""When do the rats sleep at night, and where are they? Night sleep / wake (ephys states) with WISER location, the main
sleep onset, and the NREM ripple rate / depth as a function of time since that onset (cohort 2026c).
Plan (written before computing): implementation_plan/2026-10-09-night-sleep-wiser.md.

Data: FINAL 1-s states (sleep_schedule.included_sessions + sleep_cycles_v2.build_records; clock = start_local + s); WISER
default tracks (house membership only: the confirmed house_1 / house_2 rectangles of wiser/configs/wiser_rois.json grown
by 14 in; masked fixes ignored; nearest fix within +-5 s else unknown); head-IMU locomotion from the tracks; ripples =
the swr_temperature run's kept NREM events; depth = the raw spectral slope of imu_fixch (swr_depth).
Definitions: SLEEP units (no wake > 120 s, >= 20 min); long wake = wake runs merged across sleep interruptions < 120 s,
>= 30 min; main sleep onset (MSO) of night D = the first sleep second after the last long wake ending in
[sunset D, sunrise D+1 + 2 h]; naps = night sleep before MSO; tau = time since MSO until the next long wake.

  python ephys/night_sleep_wiser.py run [--long-wake-min 30]
  python ephys/night_sleep_wiser.py --selftest
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "wiser" / "src"))
from _common import figure_dir, git_commit, report_dir, write_json  # noqa: E402

COHORT = "2026c"
W, N, R = 1, 3, 5
BREAK_S = 120          # sleep interruptions shorter than this do not end a wake run
HOUSE_BUF = 14.0
ZONES = {0: "unknown", 1: "house_1", 2: "house_2", 3: "field"}


# ------------------------------------------------------------------ pure helpers (selftested)
def runs(x: np.ndarray) -> list[tuple[int, int, int]]:
    """(value, a, b) maximal runs of equal values."""
    if not len(x):
        return []
    ch = np.flatnonzero(np.diff(x)) + 1
    st = np.r_[0, ch]
    en = np.r_[ch, len(x)]
    return [(int(x[a]), int(a), int(b)) for a, b in zip(st, en)]


def long_wakes(state: np.ndarray, min_s: float, brk: int = BREAK_S) -> list[tuple[int, int]]:
    """Wake runs merged across sleep interruptions shorter than `brk` s (unknown epochs end a run); kept if >= min_s."""
    out, cur = [], None
    for v, a, b in runs(np.where(state == W, 1, np.where((state == N) | (state == R), 2, 0))):
        if v == 1:
            cur = (cur[0], b) if cur else (a, b)
        elif v == 2 and cur is not None and (b - a) < brk:
            continue  # brief sleep inside a wake run: bridged only if the run resumes; decided at the next wake
        else:
            if cur:
                out.append(cur)
            cur = None
    if cur:
        out.append(cur)
    # a bridged short sleep that was NOT followed by wake leaves cur ending at the last wake: correct by construction
    return [(a, b) for a, b in out if (b - a) >= min_s]


def main_sleep_onset(state: np.ndarray, t0: pd.Timestamp, lw: list, win: tuple, min_after_s: int, reach: pd.Timestamp):
    """Index of the MSO in a record: the first sleep epoch after the last long wake whose end lies in win; None if none;
    ('censored', i) if the record covers < min_after_s after it and does not reach `reach`."""
    ends = [b for a, b in lw if win[0] <= t0 + pd.Timedelta(seconds=b) < win[1]]
    if not ends:
        return None
    b = max(ends)
    sl = np.flatnonzero((state[b:] == N) | (state[b:] == R))
    if not sl.size:
        return None
    i = b + int(sl[0])
    cens = (len(state) - i) < min_after_s and t0 + pd.Timedelta(seconds=len(state)) < reach
    return ("censored", i) if cens else ("ok", i)


# ------------------------------------------------------------------ data
def load_records(a) -> list[dict]:
    from sleep_cycles_v2 import build_records
    from sleep_schedule import included_sessions
    inc = included_sessions(Path(a.review), Path(a.states_root))
    inc["start"] = pd.to_datetime(inc.start_local)
    return build_records(inc, Path(a.states_root))


def wiser_seconds(animal: str, t_sec: pd.Series, houses: list) -> pd.DataFrame:
    """Zone (0 unknown / 1 house_1 / 2 house_2 / 3 field) and IMU state at the nearest valid fix within +-5 s."""
    from default_tracks import list_default_tracks, load_default_track
    import wiser_analysis_utils as Wu
    idx = list_default_tracks(COHORT)
    parts = []
    for d in idx[idx.label == animal].date:
        df = load_default_track(animal, d)
        df = df[~(df.m_handling | df.m_silence | df.m_off_animal)]
        z = np.full(len(df), 3, np.int8)
        for k, roi in enumerate(houses, start=1):
            _, inb = Wu._rect_membership(df.x.to_numpy(), df.y.to_numpy(), roi, HOUSE_BUF)
            z[inb & (z == 3)] = k
        parts.append(pd.DataFrame({"t": pd.to_datetime(df.t_ms, unit="ms", utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None),
                                   "zone": z, "imu": df.imu_state.astype(np.int8)}))
    f = pd.concat(parts, ignore_index=True).sort_values("t")
    left = pd.DataFrame({"t": t_sec.values}).reset_index().sort_values("t")
    m = pd.merge_asof(left, f, on="t", direction="nearest", tolerance=pd.Timedelta(seconds=5)).sort_values("index")
    return pd.DataFrame({"zone": m.zone.fillna(0).astype(np.int8).to_numpy(), "imu": m.imu.fillna(0).astype(np.int8).to_numpy()})


def sun(d: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    from sleep_quant import sun_times
    sr, ss = sun_times(d.date())
    return pd.Timestamp(sr), pd.Timestamp(ss)


# ------------------------------------------------------------------ run
def run(a):
    from output_paths import run_dir
    out = run_dir("night_sleep_wiser", COHORT)
    rd = report_dir(COHORT)
    recs = load_records(a)
    rois = json.loads((REPO / "wiser/configs/wiser_rois.json").read_text(encoding="utf-8"))
    houses = [r for r in rois["rois"] if r["name"] in ("house_1", "house_2")]
    min_lw = a.long_wake_min * 60
    sec_tabs, nights, lw_rows = {}, [], []
    for an in sorted({r["animal"] for r in recs}):
        R_ = [r for r in recs if r["animal"] == an]
        parts = []
        for r in R_:
            n = len(r["state"])
            parts.append(pd.DataFrame({"t": r["start"] + pd.to_timedelta(np.arange(n), unit="s"), "state": r["state"],
                                       "rec": r["record_id"]}))
        S = pd.concat(parts, ignore_index=True)
        wz = wiser_seconds(an, S.t, houses)
        S["zone"], S["imu"] = wz.zone.to_numpy(), wz.imu.to_numpy()
        S["mso_flag"] = 0
        # long wakes and MSO per biological night
        msos = []
        for r in R_:
            lw = long_wakes(r["state"], min_lw)
            for a_, b_ in lw:
                lw_rows.append(dict(animal=an, rec=r["record_id"], start=r["start"] + pd.Timedelta(seconds=a_),
                                    end=r["start"] + pd.Timedelta(seconds=b_), min=(b_ - a_) / 60))
            r["lw"] = lw
        for D in pd.date_range("2026-08-30", "2026-09-11"):
            _, ss = sun(D)
            sr2, _ = sun(D + pd.Timedelta(days=1))
            win = (ss, sr2 + pd.Timedelta(hours=2))
            best = None
            for r in R_:
                res = main_sleep_onset(r["state"], r["start"], r["lw"], win, 3 * 3600, sr2)
                if res is not None:
                    tt = r["start"] + pd.Timedelta(seconds=res[1])
                    if best is None or tt > best[1]:
                        best = (res[0], tt, r)
            rec_night = S[(S.t >= ss) & (S.t < sr2)]
            cover = len(rec_night) / max((sr2 - ss).total_seconds(), 1)
            row = dict(animal=an, night=D.strftime("%m-%d"), sunset=ss, sunrise=sr2, coverage=cover)
            if best is not None:
                status, mso, r = best
                row.update(mso=mso, mso_status=status, mso_clock=mso.hour + mso.minute / 60 + (24 if mso.hour < 12 else 0))
                lwp = [(r["start"] + pd.Timedelta(seconds=a_), r["start"] + pd.Timedelta(seconds=b_)) for a_, b_ in r["lw"]
                       if r["start"] + pd.Timedelta(seconds=b_) <= mso]
                if lwp:
                    la, lb = lwp[-1]
                    g = S[(S.t >= la) & (S.t < lb)]
                    kz = g.zone[g.zone > 0]
                    row.update(last_wake_start=la, last_wake_min=(lb - la).total_seconds() / 60,
                               last_wake_field_share=float((kz == 3).mean()) if len(kz) else np.nan,
                               last_wake_known_share=float((g.zone > 0).mean()) if len(g) else np.nan)
                nt = rec_night
                sl = nt.state.isin([N, R])
                nr = nt.state == N
                row.update(nap_min=float((sl & (nt.t < mso)).sum() / 60), main_min=float((sl & (nt.t >= mso)).sum() / 60),
                           nrem_night_min=float(nr.sum() / 60),
                           nrem_after_mso_share=float((nr & (nt.t >= mso)).sum() / max(nr.sum(), 1)),
                           nrem_00_04_min=float((nr & (nt.t.dt.hour < 4)).sum() / 60),
                           nrem_00_04_after_mso_share=float((nr & (nt.t.dt.hour < 4) & (nt.t >= mso)).sum() / max((nr & (nt.t.dt.hour < 4)).sum(), 1)))
                g = S[(S.t >= mso) & (S.t < mso + pd.Timedelta(minutes=5))]
                kz = g.zone[g.zone > 0]
                row["zone_at_mso"] = ZONES[int(kz.mode().iloc[0])] if len(kz) else "unknown"
                msos.append(mso)
            else:
                row.update(mso=pd.NaT, mso_status="no long wake in the window" if cover > 0.5 else "no record")
            nights.append(row)
        # tau per second: time since the latest MSO, until the next long wake starts after it
        S["tau_h"] = np.nan
        lw_starts = sorted(x["start"] for x in lw_rows if x["animal"] == an)
        for mso in sorted(msos):
            nxt = [s for s in lw_starts if s > mso]
            end = nxt[0] if nxt else S.t.max()
            m = (S.t >= mso) & (S.t < end)
            S.loc[m, "tau_h"] = (S.t[m] - mso).dt.total_seconds() / 3600
        sec_tabs[an] = S
        S.to_parquet(out / f"seconds_{an}.parquet", index=False) if _has_parquet() else S.to_csv(out / f"seconds_{an}.csv.gz", index=False)
        print(f"{an}: {len(S)} s, {len(msos)} MSOs", flush=True)
    NT = pd.DataFrame(nights)
    LW = pd.DataFrame(lw_rows)
    NT.to_csv(rd / f"ephys_spikes_night_sleep_wiser_nights_{COHORT}.csv", index=False)
    LW.to_csv(out / "long_wakes.csv", index=False)
    hourly = hourly_profile(sec_tabs)
    hourly.to_csv(rd / f"ephys_spikes_night_sleep_wiser_hourly_{COHORT}.csv", index=False)
    rip = ripple_tau(a, sec_tabs, out)
    figs = [raster(an, sec_tabs[an], NT[NT.animal == an]) for an in sorted(sec_tabs)]
    figs.append(summary_figure(NT, hourly, rip))
    report(a, NT, hourly, rip, figs, rd, out)
    write_json(rd / f"run_manifest_night_sleep_wiser_{COHORT}.json",
               dict(name="night_sleep_wiser", run_dir=str(out), git=git_commit(), long_wake_min=a.long_wake_min,
                    plan="implementation_plan/2026-10-09-night-sleep-wiser.md"))
    print(f"wrote {rd / f'ephys_spikes_night_sleep_wiser_{COHORT}.md'}")


def _has_parquet() -> bool:
    try:
        import pyarrow  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def hourly_profile(sec_tabs: dict) -> pd.DataFrame:
    """Per clock hour, per animal then mean +- SEM over animals: P(sleep), P(field | known zone) for wake and sleep seconds,
    P(locomoting | wake, IMU usable), the share of seconds with an unknown zone."""
    rows = []
    for an, S in sec_tabs.items():
        S = S[S.state > 0]
        h = S.t.dt.hour
        for hh, g in S.groupby(h):
            sl = g.state.isin([N, R])
            kz = g.zone > 0
            wk = g[~sl]
            rows.append(dict(animal=an, hour=hh, p_sleep=float(sl.mean()), p_nrem=float((g.state == N).mean()),
                             p_field_wake=float((wk.zone[wk.zone > 0] == 3).mean()) if (wk.zone > 0).any() else np.nan,
                             p_field_sleep=float((g[sl].zone[g[sl].zone > 0] == 3).mean()) if (g[sl].zone > 0).any() else np.nan,
                             p_loco_wake=float((wk.imu == 3).sum() / max((wk.imu > 0).sum(), 1)),
                             p_zone_unknown=float((~kz).mean()), seconds=len(g)))
    P = pd.DataFrame(rows)
    agg = {c: ["mean", lambda v: v.std(ddof=1) / np.sqrt(v.notna().sum())] for c in ("p_sleep", "p_nrem", "p_field_wake", "p_field_sleep", "p_loco_wake", "p_zone_unknown")}
    H = P.groupby("hour").agg(agg)
    H.columns = [f"{c}_{'mean' if s == 'mean' else 'sem'}" for c, s in H.columns]
    H["animals"] = P.groupby("hour").animal.nunique()
    return H.reset_index()


def ripple_tau(a, sec_tabs: dict, out: Path) -> dict:
    """Kept NREM ripple rate and depth by time since MSO (30-min tau bins), naps vs the first 2 h of the main sleep, and
    the clock-vs-tau model comparison (leave-one-date-out)."""
    import swr_temperature as stp
    rd = report_dir(COHORT)
    man = json.loads((rd / f"run_manifest_swr_temperature_{COHORT}.json").read_text())
    ev = pd.read_csv(Path(man["run_dir"]) / "nrem_events.csv.gz", parse_dates=["t"], usecols=["t", "animal", "block"])
    q = stp.sessions(Path(a.quality), Path(a.review), ["validated", "good"])
    win = stp.settle_windows(Path(a.cohort_yaml))
    nparts = []
    for row in q.itertuples():
        sf = Path(a.states_root) / row.animal / f"{row.session}.states.npz"
        rf = Path(a.sleep_root) / row.animal / row.session / f"{row.session}.SleepScoreRaw.npz"
        if not sf.exists() or not rf.exists():
            continue
        with np.load(sf) as s_, np.load(rf) as r_:
            ts, state = s_["ts"].astype(int), s_["state"]
            raw = pd.Series(r_["sw"].astype(float), index=r_["t_clus"].astype(int))
        sec = ts[state == N]
        t = pd.Series(row.start_t + pd.to_timedelta(sec, unit="s"))
        k = stp.keep_mask(t, row, stp.FEMALES, win)
        nparts.append(pd.DataFrame({"animal": row.animal, "block": row.block_from, "t": t[k].dt.floor("s").values,
                                    "sw": raw.reindex(sec[k]).to_numpy()}))
    NS = pd.concat(nparts, ignore_index=True)
    NS["block"] = NS.block.astype(str)
    ev["block"] = ev.block.astype(str)
    ev["t"] = ev.t.dt.floor("s")
    tau_parts = []
    for an, S in sec_tabs.items():
        sm = S[["t", "tau_h"]].sort_values("t")
        def _tau(df):  # nearest record second within 2 s (joined records round their split gaps)
            df = df.sort_values("t")
            return pd.merge_asof(df, sm, on="t", direction="nearest", tolerance=pd.Timedelta(seconds=2))
        nsa = _tau(NS[NS.animal == an])
        eva = _tau(ev[ev.animal == an])
        # naps: night sleep before the night's MSO = NREM seconds between sunset and MSO (tau NaN, night hours)
        tau_parts.append((nsa, eva))
    NSt = pd.concat([x[0] for x in tau_parts], ignore_index=True)
    EVt = pd.concat([x[1] for x in tau_parts], ignore_index=True)
    NSt["Dz"] = (NSt.sw - NSt.groupby(["animal", "block"]).sw.transform("mean")) / NSt.groupby(["animal", "block"]).sw.transform("std")
    # tau bins
    NSt["tb"] = np.floor(NSt.tau_h * 2) / 2
    EVt["tb"] = np.floor(EVt.tau_h * 2) / 2
    nb = NSt.dropna(subset=["tb"]).groupby(["animal", "block", "tb"]).agg(N=("t", "size"), Dz=("Dz", "mean"))
    eb = EVt.dropna(subset=["tb"]).groupby(["animal", "block", "tb"]).size().rename("n")
    TB = nb.join(eb).fillna({"n": 0}).reset_index()
    TB["N"] = TB.N / 60
    TB = TB[TB.N >= 5]
    TB["r"] = TB.n / TB.N
    TB["r_dm"] = TB.r - TB.groupby(["animal", "block"]).r.transform("mean")
    prof = TB.groupby(["animal", "tb"]).apply(lambda g: pd.Series({"r_dm": np.average(g.r_dm, weights=g.N),
                                                                  "Dz": np.average(g.Dz, weights=g.N)})).reset_index()
    TP = prof.groupby("tb").agg(animals=("animal", "nunique"), r_dm=("r_dm", "mean"),
                                r_sem=("r_dm", lambda v: v.std(ddof=1) / np.sqrt(len(v))), Dz=("Dz", "mean"),
                                Dz_sem=("Dz", lambda v: v.std(ddof=1) / np.sqrt(len(v)))).reset_index()
    TP = TP[TP.animals >= 3]
    TP.to_csv(rd / f"ephys_spikes_night_sleep_wiser_tau_profile_{COHORT}.csv", index=False)
    # naps vs main-sleep start, per animal
    nap_rows = []
    for an, S in sec_tabs.items():
        nsa = NSt[NSt.animal == an]
        eva = EVt[EVt.animal == an]
        night = (nsa.t.dt.hour >= 19) | (nsa.t.dt.hour < 7)
        night_e = (eva.t.dt.hour >= 19) | (eva.t.dt.hour < 7)
        nap_n, nap_N = int((eva.tau_h.isna() & night_e).sum()), float((nsa.tau_h.isna() & night).sum() / 60)
        ms_n, ms_N = int((eva.tau_h < 2).sum()), float((nsa.tau_h < 2).sum() / 60)
        nap_rows.append(dict(animal=an, nap_nrem_min=nap_N, nap_rate=nap_n / nap_N if nap_N >= 10 else np.nan,
                             nap_depth=float(nsa[nsa.tau_h.isna() & night].Dz.mean()) if nap_N >= 10 else np.nan,
                             mso2h_nrem_min=ms_N, mso2h_rate=ms_n / ms_N if ms_N >= 10 else np.nan,
                             mso2h_depth=float(nsa[nsa.tau_h < 2].Dz.mean()) if ms_N >= 10 else np.nan))
    NP = pd.DataFrame(nap_rows)
    NP.to_csv(rd / f"ephys_spikes_night_sleep_wiser_naps_{COHORT}.csv", index=False)
    # clock vs tau: 30-min clock bins inside the main sleep (tau defined), leave-one-date-out weighted RMSE per animal
    NSt["b0"] = NSt.t.dt.floor("30min")
    EVt["b0"] = EVt.t.dt.floor("30min")
    cb = NSt.dropna(subset=["tau_h"]).groupby(["animal", "block", "b0"]).agg(N=("t", "size"), tau=("tau_h", "mean"))
    ce = EVt.dropna(subset=["tau_h"]).groupby(["animal", "block", "b0"]).size().rename("n")
    CB = cb.join(ce).fillna({"n": 0}).reset_index()
    CB["N"] = CB.N / 60
    CB = CB[CB.N >= 5]
    CB["r"] = CB.n / CB.N
    h = (CB.b0 + pd.Timedelta(minutes=15))
    hh = h.dt.hour + h.dt.minute / 60
    for k in (1, 2):
        CB[f"hs{k}"], CB[f"hc{k}"] = np.sin(2 * np.pi * k * hh / 24), np.cos(2 * np.pi * k * hh / 24)
    CB["tau2"] = CB.tau ** 2
    CB["date"] = (h - pd.to_timedelta((hh < 12) * 24, unit="h")).dt.strftime("%m-%d")
    cmp_rows = []
    for an, g in CB.groupby("animal"):
        res = {"animal": an, "bins": len(g)}
        for nm, X in (("clock", ["hs1", "hc1", "hs2", "hc2"]), ("tau", ["tau", "tau2"]), ("both", ["hs1", "hc1", "hs2", "hc2", "tau", "tau2"])):
            err, wsum = 0.0, 0.0
            for d_ in g.date.unique():
                tr, te = g[g.date != d_], g[g.date == d_]
                if len(tr) < 10 or not len(te):
                    continue
                Xtr = pd.get_dummies(tr.block).astype(float).join(tr[X])
                Xte = pd.get_dummies(te.block).astype(float).reindex(columns=pd.get_dummies(tr.block).columns, fill_value=0).join(te[X])
                wv = np.sqrt(tr.N.to_numpy())
                beta, *_ = np.linalg.lstsq(Xtr.to_numpy() * wv[:, None], tr.r.to_numpy() * wv, rcond=None)
                pred = Xte.to_numpy() @ beta
                err += float(np.sum(te.N * (te.r - pred) ** 2))
                wsum += float(te.N.sum())
            res[f"rmse_{nm}"] = np.sqrt(err / wsum) if wsum else np.nan
        cmp_rows.append(res)
    CMP = pd.DataFrame(cmp_rows)
    CMP.to_csv(rd / f"ephys_spikes_night_sleep_wiser_clock_vs_tau_{COHORT}.csv", index=False)
    return dict(TP=TP, NP=NP, CMP=CMP)


# ------------------------------------------------------------------ figures
def raster(an: str, S: pd.DataFrame, NT: pd.DataFrame) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    nights = [pd.Timestamp("2026-" + n) for n in NT.night]
    M = 20 * 60  # minutes from 17:00 D to 13:00 D+1
    st_img = np.full((len(nights), M), 0, np.int8)
    zn_img = np.full((len(nights), M), 0, np.int8)
    lo_img = np.zeros((len(nights), M))
    Sm = S.assign(m=S.t.dt.floor("min"))
    gm = Sm.groupby("m").agg(state=("state", lambda v: int(pd.Series(v[v > 0]).mode().iloc[0]) if (v > 0).any() else 0),
                             zone=("zone", lambda v: int(pd.Series(v[v > 0]).mode().iloc[0]) if (v > 0).any() else 0),
                             loco=("imu", lambda v: float((v == 3).mean())))
    for i, D in enumerate(nights):
        t0 = D + pd.Timedelta(hours=17)
        sub = gm[(gm.index >= t0) & (gm.index < t0 + pd.Timedelta(minutes=M))]
        j = ((sub.index - t0).total_seconds() // 60).astype(int)
        st_img[i, j] = sub.state.map({1: 1, 3: 2, 5: 3}).fillna(0).astype(int).to_numpy()
        zn_img[i, j] = sub.zone.to_numpy()
        lo_img[i, j] = sub.loco.to_numpy()
    fig, ax = plt.subplots(figsize=(15, 0.62 * len(nights) + 1.5))
    cst = ListedColormap(["white", "#d9d9d9", "#3a6fb0", "#d62728"])
    czn = ListedColormap(["white", "#f0a020", "#2ca02c", "#8c564b"])
    for i in range(len(nights)):
        y = len(nights) - 1 - i
        ax.imshow(st_img[i:i + 1], aspect="auto", cmap=cst, vmin=0, vmax=3, extent=(0, M / 60, y + 0.45, y + 0.95), interpolation="nearest")
        ax.imshow(zn_img[i:i + 1], aspect="auto", cmap=czn, vmin=0, vmax=3, extent=(0, M / 60, y + 0.22, y + 0.42), interpolation="nearest")
        ax.imshow((lo_img[i:i + 1] > 0.3).astype(float), aspect="auto", cmap=ListedColormap(["white", "black"]), vmin=0, vmax=1,
                  extent=(0, M / 60, y + 0.05, y + 0.18), interpolation="nearest")
        r = NT.iloc[i]
        t0 = nights[i] + pd.Timedelta(hours=17)
        for tt, c in ((r.sunset, "#ff7f0e"), (r.sunrise, "#ff7f0e")):
            ax.plot([(tt - t0).total_seconds() / 3600] * 2, [y + 0.02, y + 0.98], color=c, lw=1)
        if pd.notna(r.get("mso")):
            x = (r.mso - t0).total_seconds() / 3600
            ax.plot(x, y + 0.98, marker="v", color="k" if r.mso_status == "ok" else "0.6", ms=7)
    ax.set_ylim(0, len(nights))
    ax.set_xlim(0, M / 60)
    ax.set_yticks([len(nights) - 1 - i + 0.5 for i in range(len(nights))])
    ax.set_yticklabels([f"{n:%m-%d}" for n in nights], fontsize=8)
    ax.set_xticks(range(0, 21, 1))
    ax.set_xticklabels([f"{(17 + h) % 24:02d}" for h in range(0, 21)], fontsize=8)
    ax.set_xlabel("clock hour (17:00 of the night's date -> 13:00 next day)", fontsize=9)
    ax.set_title(f"{an}: per night - top strip sleep state (grey wake, blue NREM, red REM, white no record); middle WISER zone "
                 "(orange house_1, green house_2, brown field, white unknown); bottom black = head-IMU locomotion; orange lines "
                 "sunset / sunrise; triangle = main sleep onset (grey = censored)", fontsize=8, loc="left")
    fig.tight_layout()
    out = figure_dir(COHORT) / f"ephys_spikes_night_sleep_wiser_raster_{an}_{COHORT}.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def summary_figure(NT: pd.DataFrame, H: pd.DataFrame, rip: dict) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    ax = axes[0, 0]
    ok = NT[NT.mso_status == "ok"]
    for i, (an, g) in enumerate(ok.groupby("animal")):
        ax.scatter(g.mso_clock, np.full(len(g), i) + np.random.default_rng(i).uniform(-0.15, 0.15, len(g)), s=25)
    ax.set_yticks(range(ok.animal.nunique()))
    ax.set_yticklabels(sorted(ok.animal.unique()))
    xt = list(range(18, 36, 2))
    ax.set_xticks(xt)
    ax.set_xticklabels([f"{h % 24:02d}" for h in xt])
    ax.axvline(np.mean([s.hour + s.minute / 60 for s in NT.sunset]), color="#ff7f0e", lw=1)
    ax.axvline(24 + np.mean([s.hour + s.minute / 60 for s in NT.sunrise]), color="#ff7f0e", lw=1)
    ax.set_title("A  Main sleep onset per night (dots), sunset / sunrise (orange)", fontsize=9, loc="left")
    ax.set_xlabel("clock hour", fontsize=9)
    ax = axes[0, 1]
    hh = H.copy()
    hh["x"] = np.where(hh.hour < 13, hh.hour + 24, hh.hour)
    hh = hh[(hh.x >= 17)].sort_values("x")
    for c, lab, col in (("p_sleep", "P(asleep)", "#3a6fb0"), ("p_field_wake", "P(in field | awake)", "#8c564b"),
                        ("p_field_sleep", "P(in field | asleep)", "#bcbd22"), ("p_loco_wake", "P(locomoting | awake)", "k")):
        ax.errorbar(hh.x + 0.5, hh[f"{c}_mean"], yerr=hh[f"{c}_sem"], fmt="-o", ms=3, capsize=2, color=col, label=lab)
    ax.set_xticks(range(17, 38, 2))
    ax.set_xticklabels([f"{h % 24:02d}" for h in range(17, 38, 2)])
    ax.set_ylim(0, 1)
    ax.legend(fontsize=7, frameon=False)
    ax.set_title("B  By clock hour, mean +- SEM over animals", fontsize=9, loc="left")
    ax = axes[1, 0]
    TP = rip["TP"]
    ax.errorbar(TP.tb + 0.25, TP.r_dm, yerr=TP.r_sem, fmt="-s", color="#2b7a2b", ms=4, capsize=2)
    ax.set_ylabel("NREM ripple rate - block mean (/NREM min)", fontsize=9, color="#2b7a2b")
    ax2 = ax.twinx()
    ax2.errorbar(TP.tb + 0.25, TP.Dz, yerr=TP.Dz_sem, fmt="-o", color="#6a3d9a", ms=4, capsize=2)
    ax2.set_ylabel("NREM depth (z)", fontsize=9, color="#6a3d9a")
    ax.set_xlabel("time since main sleep onset (h)", fontsize=9)
    ax.set_title("C  Ripple rate (green) and depth (purple) vs time since the main sleep onset", fontsize=9, loc="left")
    ax = axes[1, 1]
    NP = rip["NP"].dropna(subset=["nap_rate", "mso2h_rate"])
    for r in NP.itertuples():
        ax.plot([0, 1], [r.nap_rate, r.mso2h_rate], "-o", label=r.animal)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["night naps (before onset)", "main sleep, first 2 h"])
    ax.set_ylabel("NREM ripple rate (/NREM min)", fontsize=9)
    ax.legend(fontsize=7, frameon=False)
    ax.set_title("D  Naps vs the start of the main sleep, per animal", fontsize=9, loc="left")
    for a_ in axes.ravel():
        a_.tick_params(labelsize=8)
    fig.suptitle(f"Night sleep, WISER location and ripples relative to the main sleep onset, cohort {COHORT}", fontsize=10)
    fig.tight_layout()
    out = figure_dir(COHORT) / f"ephys_spikes_night_sleep_wiser_summary_{COHORT}.png"
    fig.savefig(out, dpi=125)
    plt.close(fig)
    return out


def report(a, NT, H, rip, figs, rd, out):
    L = []
    w = L.append
    ok = NT[NT.mso_status == "ok"]
    w(f"# When do the rats sleep at night? Night sleep / wake with WISER, and the main sleep onset ({COHORT})")
    w("")
    w(f"Generated by `ephys/night_sleep_wiser.py run` (repo `{git_commit()}`), long wake >= {a.long_wake_min} min; plan "
      f"[`implementation_plan/2026-10-09-night-sleep-wiser.md`](../../../../implementation_plan/2026-10-09-night-sleep-wiser.md) "
      f"(written before computing). Run folder (per-second tables): `{out}`.")
    w("")
    w("## Answer")
    w("")
    w(f"- **Main sleep onset (MSO)**: defined (not censored) on {len(ok)} of {len(NT)} animal-nights; clock time median "
      f"{_hm(ok.mso_clock.median())} (IQR {_hm(ok.mso_clock.quantile(0.25))} - {_hm(ok.mso_clock.quantile(0.75))}); per animal "
      + ", ".join(f"{an} {_hm(g.mso_clock.median())}" for an, g in ok.groupby("animal")) + ".")
    w(f"- **Night NREM (sunset -> sunrise) after the MSO**: {100 * ok.nrem_after_mso_share.mean():.0f} % (mean over nights; "
      f"per animal " + ", ".join(f"{an} {100 * g.nrem_after_mso_share.mean():.0f} %" for an, g in ok.groupby("animal")) + "). "
      f"**NREM between 00:00 and 04:00 after the MSO: {100 * np.nansum(ok.nrem_00_04_after_mso_share * ok.nrem_00_04_min) / max(ok.nrem_00_04_min.sum(), 1):.0f} %** "
      f"(NREM-weighted).")
    w(f"- **Naps before the MSO**: median {ok.nap_min.median():.0f} min of sleep per night (IQR {ok.nap_min.quantile(0.25):.0f} - "
      f"{ok.nap_min.quantile(0.75):.0f}); main sleep inside the night median {ok.main_min.median():.0f} min.")
    if "last_wake_field_share" in ok:
        w(f"- **The last long wake before the MSO**: median {ok.last_wake_min.median():.0f} min, in the field for a median "
          f"{100 * ok.last_wake_field_share.median():.0f} % of its seconds with a known zone (known for {100 * ok.last_wake_known_share.median():.0f} %); "
          f"zone at MSO: " + ", ".join(f"{k} {v}" for k, v in ok.zone_at_mso.value_counts().items()) + ".")
    CMP = rip["CMP"]
    better = int((CMP.rmse_tau < CMP.rmse_clock).sum())
    w(f"- **Ripples vs time since onset (C, D)**: held-out-date RMSE of the main-sleep ripple rate - clock harmonics vs time "
      f"since MSO: tau better in {better} / {len(CMP)} animals (" + ", ".join(
          f"{r.animal} {r.rmse_clock:.1f} vs {r.rmse_tau:.1f}" for r in CMP.itertuples()) + ").")
    NP = rip["NP"]
    v = NP.dropna(subset=["nap_rate", "mso2h_rate"])
    w(f"- **Naps vs the first 2 h of the main sleep**: " + "; ".join(
        f"{r.animal} {r.nap_rate:.0f} vs {r.mso2h_rate:.0f} /NREM min (depth {r.nap_depth:+.2f} vs {r.mso2h_depth:+.2f})" for r in v.itertuples())
      + f"; main-sleep start higher in {int((v.mso2h_rate > v.nap_rate).sum())} / {len(v)}.")
    w("")
    for p in figs:
        w(f"![{p.stem}](../figures/{p.name})")
        w("")
    w("## Per night")
    w("")
    w("| Animal | Night | Record coverage | MSO | Status | Last long wake (min, field share) | Nap min | Main-sleep min (night) | Night NREM after MSO | Zone at MSO |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for r in NT.itertuples():
        mso = f"{r.mso:%H:%M}" if pd.notna(r.mso) else ""
        lw = f"{getattr(r, 'last_wake_min', np.nan):.0f}, {100 * getattr(r, 'last_wake_field_share', np.nan):.0f} %" if pd.notna(getattr(r, "last_wake_min", np.nan)) else ""
        w(f"| {r.animal} | {r.night} | {100 * r.coverage:.0f} % | {mso} | {r.mso_status} | {lw} | "
          f"{_f(getattr(r, 'nap_min', np.nan), 0)} | {_f(getattr(r, 'main_min', np.nan), 0)} | "
          f"{_f(100 * getattr(r, 'nrem_after_mso_share', np.nan), 0)} % | {getattr(r, 'zone_at_mso', '')} |")
    w("")
    w("## By clock hour (mean over animals)")
    w("")
    w("| Hour | Animals | P(asleep) | P(NREM) | P(field given awake) | P(field given asleep) | P(locomoting given awake) | Zone unknown |")
    w("|---|---|---|---|---|---|---|---|")
    for r in H.itertuples():
        w(f"| {r.hour:02d} | {r.animals} | {r.p_sleep_mean:.2f} | {r.p_nrem_mean:.2f} | {_f(r.p_field_wake_mean)} | "
          f"{_f(r.p_field_sleep_mean)} | {_f(r.p_loco_wake_mean)} | {r.p_zone_unknown_mean:.2f} |")
    w("")
    w("## Ripple rate and depth by time since MSO")
    w("")
    w("| tau (h) | Animals | Rate - block mean | SEM | Depth (z) | SEM |")
    w("|---|---|---|---|---|---|")
    for r in rip["TP"].itertuples():
        w(f"| {r.tb:.1f} | {r.animals} | {r.r_dm:+.1f} | {_f(r.r_sem, 1)} | {r.Dz:+.2f} | {_f(r.Dz_sem)} |")
    w("")
    w("## Definitions")
    w("")
    w("- **State**: FINAL 1-s sleep states (WAKE / NREM / REM), records = included sessions joined across splits <= 60 s "
      "(`sleep_cycles_v2.build_records`; inclusion `sleep_schedule.included_sessions`, to 09-11 19:40).")
    w(f"- **Long wake**: maximal WAKE runs merged across sleep interruptions < {BREAK_S} s (an unknown epoch ends a run), kept if "
      f">= {a.long_wake_min} min.")
    w("- **Main sleep onset (MSO)** of night D: the first sleep epoch (NREM / REM) after the last long wake that ends between "
      "sunset D and sunrise D+1 + 2 h; 'censored' when its record covers < 3 h after it and ends before sunrise.")
    w("- **Naps**: sleep seconds between sunset D and the MSO; **main sleep (in the night)**: sleep seconds from the MSO to sunrise.")
    w("- **Time since MSO** tau: from the MSO until the next long wake starts (across the morning-round gap).")
    w("- **WISER zone** per second: the nearest valid fix within +-5 s of the default track (V3 / B2), house_1 / house_2 = inside the "
      f"confirmed house rectangle grown by {HOUSE_BUF:.0f} in (jitter ~7 in median, p95 ~15 in), else field; fixes flagged "
      "handling / all-tag silence / off-animal ignored; no fix = unknown (never 'outside'). Positions are in the UNVERIFIED "
      "WISER inch frame: only house membership is used, no physical position.")
    w("- **Locomoting** = the head-IMU state of the fix (3 = locomoting; 0 = unusable excluded).")
    w("- **Ripple rate / depth**: kept NREM SWR events (tiers validated / good, the temperature analysis' exclusions) per NREM "
      "minute; depth = the raw spectral slope of `imu_fixch`, z within animal x block; tau bins 30 min, block-demeaned.")
    w("- **Clock vs tau**: per animal, 30-min bins inside the main sleep; weighted least squares with block intercepts + 2 clock "
      "harmonics, or + tau and tau^2, or both; leave-one-date-out RMSE weighted by NREM minutes.")
    w("")
    w("## WISER measurement notes (regime-aware-wiser-tracking)")
    w("")
    w("- Frame: inches, unverified offset; only rectangle membership with a 14-in buffer is used (no spatial claim beyond house vs field).")
    w("- Unknown zone share by hour is in the hourly table; gaps are unknown, not 'left the house'.")
    w("- Rain nights degrade UWB (fewer anchors); zone claims on those nights are weaker.")
    (rd / f"ephys_spikes_night_sleep_wiser_{COHORT}.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def _hm(x):
    if x is None or not np.isfinite(x):
        return ""
    x = x % 24
    return f"{int(x):02d}:{int(round((x % 1) * 60)) % 60:02d}"


def _f(x, nd=2):
    return "" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{nd}f}"


def selftest():
    s = np.array([W] * 2000 + [N] * 60 + [W] * 1000 + [N] * 3000 + [R] * 200 + [W] * 50 + [N] * 4000, np.int8)
    lw = long_wakes(s, 1800)
    ok1 = lw == [(0, 3060)]
    t0 = pd.Timestamp("2026-09-05 22:00")
    res = main_sleep_onset(s, t0, lw, (t0, t0 + pd.Timedelta(hours=12)), 3600, t0 + pd.Timedelta(hours=8))
    ok2 = res == ("ok", 3060)
    print(f"{'PASS' if ok1 else 'FAIL'} long wake bridges a 60-s sleep: {lw}")
    print(f"{'PASS' if ok2 else 'FAIL'} MSO at the first sleep after the last long wake: {res}")
    ok = ok1 and ok2
    print("SELFTEST " + ("PASS" if ok else "FAIL"))
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["run"])
    ap.add_argument("--long-wake-min", type=float, default=30.0)
    ap.add_argument("--states-root", default="D:/3rd_rat_spikes/analysis/sleep_server/states_1s_final")
    ap.add_argument("--sleep-root", default="Q:/hc997/SocialFieldRat2026/3rd_rat/analysis/sleep/imu_fixch")
    ap.add_argument("--quality", default=str(report_dir(COHORT) / f"ephys_spikes_swr_quality_{COHORT}.csv"))
    ap.add_argument("--review", default=str(report_dir(COHORT) / f"ephys_spikes_sleep_review_{COHORT}.csv"))
    ap.add_argument("--cohort-yaml", default=str(REPO / f"cohorts/{COHORT}.yaml"))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    if a.cmd == "run":
        run(a)


if __name__ == "__main__":
    main()
