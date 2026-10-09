"""Two follow-ups of the night-sleep analysis (cohort 2026c; plan implementation_plan/2026-10-09-night-sleep-wiser.md,
Amendment 3, written before computing):
  N1  does the strict naps' higher ripple rate survive controlling NREM depth? (unit model + depth-matched quintiles)
  R1  REM share per NREM by clock hour, drawn into the circadian figure (panel C) with depth and ripple rate
  R2  across 30-min bins within animal x block: ripple rate ~ REM share + depth + hour harmonics
  R3  ripple rate in the last 60 s of NREM runs >= 300 s before REM vs before WAKE, relative to the run's own -300..-120 s
      baseline (pooled per animal x outcome)
Inputs (no re-extraction): the night_sleep_wiser run (per-second state / tau, strict naps), the swr_temperature run (kept
NREM events), the raw spectral slope of imu_fixch (depth, storage read-only), the final 1-s states.

  python ephys/swr_rem_naps.py run
  python ephys/swr_rem_naps.py macro   (Amendment 4: REM vs SWR at the macro scale - sleep periods, days)
  python ephys/swr_rem_naps.py --selftest
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
from _common import figure_dir, git_commit, report_dir, write_json  # noqa: E402

COHORT = "2026c"
W, N, R = 1, 3, 5
HARM = ["hs1", "hc1", "hs2", "hc2"]


def harmonics(t: pd.Series) -> pd.DataFrame:
    h = t.dt.hour + t.dt.minute / 60
    return pd.DataFrame({f"h{s}{k}": f(2 * np.pi * k * h / 24) for k in (1, 2) for s, f in (("s", np.sin), ("c", np.cos))}, index=t.index)


def wls(d: pd.DataFrame, formula: str, terms: list[str], group: str = "date") -> dict:
    import statsmodels.formula.api as smf
    from scipy import stats
    G = d[group].nunique()
    m = smf.wls(formula, data=d, weights=d.N).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d[group])[0], "use_correction": True})
    tq = stats.t.ppf(0.975, G - 1)
    out = {"n": len(d), "clusters": G}
    for t in terms:
        if t in m.params:
            e, se = float(m.params[t]), float(m.bse[t])
            out.update({t: e, f"{t}_lo": e - tq * se, f"{t}_hi": e + tq * se, f"{t}_p": float(2 * stats.t.sf(abs(e / se), G - 1))})
    return out


def transitions(state: np.ndarray, min_nrem: int = 120, min_next: int = 30) -> list[tuple[int, int, int]]:
    """(nrem_start, nrem_end, next_state) for NREM runs >= min_nrem s followed directly by >= min_next s of REM or WAKE."""
    from night_sleep_wiser import runs
    rr = runs(state)
    out = []
    for i in range(len(rr) - 1):
        v, a, b = rr[i]
        v2, a2, b2 = rr[i + 1]
        if v == N and (b - a) >= min_nrem and v2 in (R, W) and (b2 - a2) >= min_next:
            out.append((a, b, v2))
    return out


# ------------------------------------------------------------------ data
def eligible_nrem_depth(a) -> pd.DataFrame:
    """Ripple-eligible NREM seconds (tiers validated / good, the temperature analysis' exclusions) with the raw slope and its
    z within animal x block."""
    import swr_temperature as stp
    q = stp.sessions(Path(a.quality), Path(a.review), ["validated", "good"])
    win = stp.settle_windows(Path(a.cohort_yaml))
    parts = []
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
        parts.append(pd.DataFrame({"animal": row.animal, "block": str(row.block_from), "t": t[k].dt.floor("s").values,
                                   "sw": raw.reindex(sec[k]).to_numpy()}))
    NS = pd.concat(parts, ignore_index=True).dropna(subset=["sw"])
    g = NS.groupby(["animal", "block"]).sw
    NS["Dz"] = (NS.sw - g.transform("mean")) / g.transform("std")
    NS["ab"] = NS.animal + "|" + NS.block
    return NS.sort_values("t").reset_index(drop=True)


def all_nrem_events(a) -> pd.DataFrame:
    """Every detected event whose peak second is NREM, the flags (theta / movement / LFP-EMG) ignored - the check that the
    theta exclusion does not create a pre-REM drop. Same sessions and time exclusions as the kept events."""
    import swr_temperature as stp
    q = stp.sessions(Path(a.quality), Path(a.review), ["validated", "good"])
    win = stp.settle_windows(Path(a.cohort_yaml))
    parts = []
    for row in q.itertuples():
        f = Path(a.swr_root) / row.animal / row.session / f"{row.session}.swr_events.npz"
        if not f.exists():
            continue
        z = np.load(f, allow_pickle=True)
        m = z["state"] == "NREM"
        t = pd.Series(row.start_t + pd.to_timedelta(z["peak_s"][m], unit="s"))
        k = stp.keep_mask(t, row, stp.FEMALES, win)
        parts.append(pd.DataFrame({"animal": row.animal, "t": t[k].dt.floor("s").values}))
    return pd.concat(parts, ignore_index=True)


def bio_date(t: pd.Series) -> pd.Series:
    """Biological night label: before 12:00 -> the previous date."""
    return (t - pd.to_timedelta((t.dt.hour < 12).astype(int), unit="D")).dt.strftime("%m-%d")


def load_inputs(a) -> dict:
    rd = report_dir(COHORT)
    man = json.loads((rd / f"run_manifest_night_sleep_wiser_{COHORT}.json").read_text())
    run_dir = Path(man["run_dir"])
    man_t = json.loads((rd / f"run_manifest_swr_temperature_{COHORT}.json").read_text())
    ev = pd.read_csv(Path(man_t["run_dir"]) / "nrem_events.csv.gz", parse_dates=["t"], usecols=["t", "animal"])
    ev["t"] = ev.t.dt.floor("s")
    naps = pd.read_csv(rd / f"ephys_spikes_night_naps_{COHORT}.csv", parse_dates=["start", "end"])
    naps = naps[naps.strict].reset_index(drop=True)
    NS = eligible_nrem_depth(a)
    print(f"eligible NREM seconds {len(NS)}, events {len(ev)}, strict naps {len(naps)}", flush=True)
    secs = {}
    for f in sorted(run_dir.glob("seconds_*.csv.gz")):
        an = f.name.split("_")[1].split(".")[0]
        secs[an] = pd.read_csv(f, usecols=["t", "state", "rec", "tau_h"], parse_dates=["t"]).sort_values("t").reset_index(drop=True)
    # category of each eligible NREM second and each event: nap / main (tau) / other
    cat_parts, evc_parts = [], []
    for an, S in secs.items():
        sm = S[["t", "tau_h"]].assign(t=S.t.dt.floor("s"))
        ns = pd.merge_asof(NS[NS.animal == an], sm, on="t", direction="nearest", tolerance=pd.Timedelta(seconds=2))
        evs = pd.merge_asof(ev[ev.animal == an].sort_values("t"), sm, on="t", direction="nearest", tolerance=pd.Timedelta(seconds=2))
        evs = pd.merge_asof(evs, NS[NS.animal == an][["t", "Dz", "block", "ab"]], on="t", direction="nearest", tolerance=pd.Timedelta(seconds=1))
        for df in (ns, evs):
            df["kind"] = np.where(df.tau_h.notna(), "main", "other")
            df["nap_id"] = -1
        for i, r in naps[naps.animal == an].iterrows():
            for df in (ns, evs):
                m = (df.t >= r.start) & (df.t < r.end)
                df.loc[m, "kind"] = "nap"
                df.loc[m, "nap_id"] = i
        cat_parts.append(ns)
        evc_parts.append(evs)
    NSc = pd.concat(cat_parts, ignore_index=True)
    EVc = pd.concat(evc_parts, ignore_index=True).dropna(subset=["ab"])
    return dict(rd=rd, run_dir=run_dir, ev=ev, naps=naps, NS=NS, secs=secs, NSc=NSc, EVc=EVc)


def run(a):
    I = load_inputs(a)
    rd, run_dir, ev, naps, NS, secs, NSc, EVc = (I[k] for k in ("rd", "run_dir", "ev", "naps", "NS", "secs", "NSc", "EVc"))
    N1 = nap_vs_main(NSc, EVc, naps)
    R1 = rem_share_by_hour(secs)
    R2 = rem_across_bins(NSc, EVc, secs)
    R3 = rem_transitions(secs, NS, ev)
    eva = all_nrem_events(a)
    R3a = rem_transitions(secs, NS, eva)
    evca = []
    for an, S in secs.items():
        sm = S[["t", "tau_h"]].assign(t=S.t.dt.floor("s"))
        e = pd.merge_asof(eva[eva.animal == an].sort_values("t"), NS[NS.animal == an][["t", "Dz", "block", "ab"]], on="t",
                          direction="nearest", tolerance=pd.Timedelta(seconds=1))
        evca.append(e)
    R2a = rem_across_bins(NSc, pd.concat(evca, ignore_index=True).dropna(subset=["ab"]), secs)
    R3["all_events"], R2["all_events"] = R3a, R2a
    figs = [circadian_figure(R1, rd), rem_figure(N1, R2, R3)]
    report(N1, R1, R2, R3, figs, rd)
    write_json(rd / f"run_manifest_swr_rem_naps_{COHORT}.json", dict(name="swr_rem_naps", git=git_commit(), night_run=str(run_dir),
                                                                     plan="implementation_plan/2026-10-09-night-sleep-wiser.md (Amendment 3)"))
    print(f"wrote {rd / f'ephys_spikes_swr_rem_naps_{COHORT}.md'}")


# ------------------------------------------------------------------ N1
def nap_vs_main(NSc: pd.DataFrame, EVc: pd.DataFrame, naps: pd.DataFrame) -> dict:
    from scipy import stats
    units = []
    nn = NSc[NSc.kind == "nap"].groupby(["nap_id", "animal", "ab"]).agg(N=("t", "size"), Dz=("Dz", "mean"), t0=("t", "min")).reset_index()
    ne = EVc[EVc.kind == "nap"].groupby("nap_id").size().rename("n")
    nn = nn.join(ne, on="nap_id").fillna({"n": 0})
    nn["kind"], nn["first2h"] = "nap", False
    units.append(nn)
    mm = NSc[NSc.kind == "main"].copy()
    mm["mso"] = (mm.t - pd.to_timedelta(mm.tau_h, unit="h")).dt.round("min")
    mm["tb"] = np.floor(mm.tau_h * 2) / 2
    mu = mm.groupby(["animal", "ab", "mso", "tb"]).agg(N=("t", "size"), Dz=("Dz", "mean"), t0=("t", "min")).reset_index()
    me = EVc[EVc.kind == "main"].copy()
    me["mso"] = (me.t - pd.to_timedelta(me.tau_h, unit="h")).dt.round("min")
    me["tb"] = np.floor(me.tau_h * 2) / 2
    mu = mu.merge(me.groupby(["ab", "mso", "tb"]).size().rename("n").reset_index(), on=["ab", "mso", "tb"], how="left").fillna({"n": 0})
    mu["kind"], mu["first2h"] = "main", mu.tb < 2
    units.append(mu)
    U = pd.concat(units, ignore_index=True)
    U["N"] = U.N / 60
    U = U[U.N >= 5].copy()
    U["r"] = U.n / U.N
    U["nap"] = (U.kind == "nap").astype(float)
    U["date"] = bio_date(U.t0)
    res = {}
    for nm, d in (("vs all main sleep", U), ("vs main sleep, first 2 h", U[(U.kind == "nap") | U.first2h])):
        r0 = wls(d, "r ~ C(ab) + nap", ["nap"])
        r1 = wls(d, "r ~ C(ab) + nap + Dz", ["nap", "Dz"])
        pa = []
        for an, g in d.groupby("animal"):
            if g.nap.sum() >= 2 and (g.nap == 0).sum() >= 2 and g.date.nunique() >= 3:
                f = wls(g, ("r ~ C(ab) + nap + Dz" if g.ab.nunique() > 1 else "r ~ nap + Dz"), ["nap"])
                pa.append(dict(animal=an, gamma=f.get("nap"), lo=f.get("nap_lo"), hi=f.get("nap_hi")))
        res[nm] = dict(without=r0, with_depth=r1, per_animal=pd.DataFrame(pa), units=len(d), naps=int(d.nap.sum()))
    # depth-matched quintiles (second level)
    rows = []
    for ab, g in NSc[NSc.kind.isin(["nap", "main"])].groupby("ab"):
        if (g.kind == "nap").sum() < 600:
            continue
        edges = np.quantile(g.Dz, [0, .2, .4, .6, .8, 1])
        g = g.assign(qd=np.clip(np.searchsorted(edges, g.Dz, side="right") - 1, 0, 4))
        e = EVc[EVc.ab == ab].dropna(subset=["Dz"])
        e = e.assign(qd=np.clip(np.searchsorted(edges, e.Dz, side="right") - 1, 0, 4))
        for qd in range(5):
            Nn = ((g.kind == "nap") & (g.qd == qd)).sum() / 60
            Nm = ((g.kind == "main") & (g.qd == qd)).sum() / 60
            if Nn >= 5 and Nm >= 5:
                rn = ((e.kind == "nap") & (e.qd == qd)).sum() / Nn
                rm = ((e.kind == "main") & (e.qd == qd)).sum() / Nm
                rows.append(dict(ab=ab, animal=ab.split("|")[0], quintile=qd + 1, nap_rate=rn, main_rate=rm, diff=rn - rm, w=min(Nn, Nm),
                                 nap_min=Nn, main_min=Nm))
    DM = pd.DataFrame(rows)
    per_an = DM.groupby("animal").apply(lambda g: np.average(g["diff"], weights=g.w)).rename("matched_diff")
    t_ = stats.ttest_1samp(per_an, 0) if len(per_an) >= 3 else None
    by_q = DM.groupby("quintile").apply(lambda g: pd.Series({"diff": np.average(g["diff"], weights=g.w), "blocks": len(g)}))
    res["matched"] = dict(DM=DM, per_animal=per_an, mean=float(per_an.mean()), p=float(t_.pvalue) if t_ else np.nan,
                          positive=int((per_an > 0).sum()), animals=len(per_an), by_quintile=by_q,
                          ci=(float(per_an.mean() - stats.t.ppf(0.975, len(per_an) - 1) * per_an.std(ddof=1) / np.sqrt(len(per_an))),
                              float(per_an.mean() + stats.t.ppf(0.975, len(per_an) - 1) * per_an.std(ddof=1) / np.sqrt(len(per_an)))))
    res["U"] = U
    return res


# ------------------------------------------------------------------ R1-R3
def rem_share_by_hour(secs: dict) -> pd.DataFrame:
    rows = []
    for an, S in secs.items():
        for hh, g in S.groupby(S.t.dt.hour):
            nr, rm = int((g.state == N).sum()), int((g.state == R).sum())
            rows.append(dict(animal=an, hour=hh, rem_per_nrem=rm / nr if nr >= 300 else np.nan, rem_share_sleep=rm / (nr + rm) if nr + rm >= 300 else np.nan))
    P = pd.DataFrame(rows)
    return P.groupby("hour").agg(animals=("rem_per_nrem", lambda v: int(v.notna().sum())), rem_per_nrem=("rem_per_nrem", "mean"),
                                 rem_per_nrem_sem=("rem_per_nrem", lambda v: v.std(ddof=1) / np.sqrt(v.notna().sum())),
                                 rem_share=("rem_share_sleep", "mean")).reset_index()


def rem_across_bins(NSc: pd.DataFrame, EVc: pd.DataFrame, secs: dict) -> dict:
    nb = NSc.assign(b0=NSc.t.dt.floor("30min")).groupby(["animal", "ab", "b0"]).agg(N=("t", "size"), Dz=("Dz", "mean")).reset_index()
    eb = EVc.assign(b0=EVc.t.dt.floor("30min")).groupby(["ab", "b0"]).size().rename("n").reset_index()
    B = nb.merge(eb, on=["ab", "b0"], how="left").fillna({"n": 0})
    sh = []
    for an, S in secs.items():
        g = S.assign(b0=S.t.dt.floor("30min")).groupby("b0").state
        sh.append(pd.DataFrame({"animal": an, "remsh": g.apply(lambda v: (v == R).sum() / max(((v == N) | (v == R)).sum(), 1))}).reset_index())
    B = B.merge(pd.concat(sh), on=["animal", "b0"], how="left")
    B["N"] = B.N / 60
    B = B[B.N >= 5].copy()
    B["r"] = B.n / B.N
    B["s10"] = B.remsh * 10           # per 10 percentage points of REM share
    B = B.join(harmonics(B.b0 + pd.Timedelta(minutes=15)))
    B["date"] = B.b0.dt.strftime("%m-%d")
    f0 = wls(B, "r ~ C(ab) + s10", ["s10"])
    f1 = wls(B, "r ~ C(ab) + s10 + Dz + " + " + ".join(HARM), ["s10", "Dz"])
    pa = []
    for an, g in B.groupby("animal"):
        f = wls(g, ("r ~ C(ab) + " if g.ab.nunique() > 1 else "r ~ ") + "s10 + Dz + " + " + ".join(HARM), ["s10"])
        pa.append(dict(animal=an, beta=f.get("s10"), lo=f.get("s10_lo"), hi=f.get("s10_hi"), bins=len(g)))
    return dict(B=B, without=f0, with_controls=f1, per_animal=pd.DataFrame(pa))


def rem_transitions(secs: dict, NS: pd.DataFrame, ev: pd.DataFrame) -> dict:
    """Ripple rate in 15-s bins before the end of NREM runs ending in REM vs WAKE, relative to -300..-120 s."""
    from scipy import stats
    edges = np.arange(-300, 1, 15)
    rows = []
    for an, S in secs.items():
        el = set(NS[NS.animal == an].t.values.astype("datetime64[s]").astype(np.int64))
        evt = np.sort(ev[ev.animal == an].t.values.astype("datetime64[s]").astype(np.int64))
        for rec, g in S.groupby("rec", sort=False):
            st = g.state.to_numpy()
            t0 = g.t.iloc[0].floor("s").value // 10**9
            for a_, b_, nxt in transitions(st, min_nrem=300):
                T = t0 + b_
                for k in range(len(edges) - 1):
                    lo, hi = T + edges[k], T + edges[k + 1]
                    nel = sum(1 for s in range(lo, hi) if s in el)
                    nev = int(np.searchsorted(evt, hi) - np.searchsorted(evt, lo))
                    rows.append(dict(animal=an, nxt="REM" if nxt == R else "WAKE", T=T, bin=edges[k], el_s=nel, n=nev))
    X = pd.DataFrame(rows)
    X = X[X.groupby(["animal", "T"]).el_s.transform("sum") >= 200]  # transitions in ripple-eligible NREM
    agg = X.groupby(["animal", "nxt", "bin"]).agg(el_s=("el_s", "sum"), n=("n", "sum")).reset_index()
    agg["rate"] = agg.n / (agg.el_s / 60).replace(0, np.nan)
    base = agg[agg.bin < -120].groupby(["animal", "nxt"]).apply(lambda g: g.n.sum() / (g.el_s.sum() / 60)).rename("base")
    last = agg[agg.bin >= -60].groupby(["animal", "nxt"]).apply(lambda g: g.n.sum() / max(g.el_s.sum() / 60, 1e-9)).rename("last60")
    Q = pd.concat([base, last], axis=1).reset_index()
    Q["ratio"] = Q.last60 / Q.base
    W_ = Q.pivot(index="animal", columns="nxt", values="ratio").dropna()
    d = W_["REM"] - W_["WAKE"]
    tt = stats.ttest_1samp(d, 0) if len(d) >= 3 else None
    counts = X.drop_duplicates(["animal", "T"]).groupby(["animal", "nxt"]).size().unstack(fill_value=0)
    agg = agg.merge(base.reset_index(), on=["animal", "nxt"])
    agg["rel"] = agg.rate / agg.base
    curve = agg.groupby(["nxt", "bin"]).rel.agg(["mean", lambda v: v.std(ddof=1) / np.sqrt(v.notna().sum())]).rename(columns={"<lambda_0>": "sem"}).reset_index()
    return dict(Q=Q, W=W_, diff=d, p=float(tt.pvalue) if tt else np.nan, counts=counts, curve=curve)


# ------------------------------------------------------------------ figures + report
def circadian_figure(R1: pd.DataFrame, rd: Path) -> Path:
    """The naps' circadian figure with REM per NREM added to panel C."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    NT = pd.read_csv(rd / f"ephys_spikes_night_sleep_wiser_nights_{COHORT}.csv", parse_dates=["mso", "sunset", "sunrise"])
    C = pd.read_csv(rd / f"ephys_spikes_night_naps_nrem_composition_{COHORT}.csv")
    FR = pd.read_csv(rd / f"ephys_spikes_night_naps_frequency_{COHORT}.csv")
    hp = pd.read_csv(rd / f"ephys_spikes_swr_depth_hour_profile_{COHORT}.csv")
    Cm = C.groupby("hour")[["p_nrem_main", "p_nrem_nap", "p_nrem_other"]].mean()
    FRm = FR.groupby("hour").naps_per_night.agg(["mean", lambda v: v.std(ddof=1) / np.sqrt(len(v))]).rename(columns={"<lambda_0>": "sem"})
    sr_h = np.mean([s.hour + s.minute / 60 for s in NT.sunrise])
    ss_h = np.mean([s.hour + s.minute / 60 for s in NT.sunset])
    msoh = NT.mso.dropna()
    msoh = msoh.dt.hour + msoh.dt.minute / 60
    fig, axes = plt.subplots(3, 1, figsize=(12, 10.5), sharex=True, gridspec_kw={"height_ratios": [1.2, 0.8, 1.4]})
    x = Cm.index + 0.5
    ax = axes[0]
    ax.bar(x, Cm.p_nrem_main, width=0.85, color="#3a6fb0", label="NREM in the main sleep (from its onset)")
    ax.bar(x, Cm.p_nrem_nap, width=0.85, bottom=Cm.p_nrem_main, color="#f28e2b", label="NREM in strict naps")
    ax.bar(x, Cm.p_nrem_other, width=0.85, bottom=Cm.p_nrem_main + Cm.p_nrem_nap, color="#bdbdbd", label="other NREM")
    ax.plot(msoh, np.full(len(msoh), 0.78), "|", color="k", ms=10)
    ax.set_ylim(0, 1)
    ax.set_ylabel("share of recorded time", fontsize=9)
    ax.legend(fontsize=8, frameon=False, loc="upper right")
    ax.set_title("A  Circadian NREM by kind (mean over animals); ticks = main sleep onsets", fontsize=9, loc="left")
    ax = axes[1]
    ax.bar(FRm.index + 0.5, FRm["mean"], yerr=FRm["sem"], width=0.85, color="#f28e2b", capsize=2)
    ax.set_ylabel("strict-nap onsets\nper night per hour", fontsize=9)
    ax.set_title("B  Nap frequency (mean +- SEM over animals)", fontsize=9, loc="left")
    ax = axes[2]
    ax.bar(FRm.index + 0.5, FRm["mean"] / max(FRm["mean"].max(), 1e-9), width=0.85, color="#f28e2b", alpha=0.2)
    ax.set_yticks([])
    a1 = ax.twinx()
    a1.errorbar(hp.h + 0.5, hp.Dz, yerr=hp.Dz_sem, fmt="-o", color="#6a3d9a", ms=4, capsize=2)
    a1.set_ylabel("NREM depth (z)", fontsize=9, color="#6a3d9a")
    a2 = ax.twinx()
    a2.spines["right"].set_position(("axes", 1.07))
    a2.errorbar(hp.h + 0.5, hp.r_dm, yerr=hp.r_sem, fmt="-s", color="#2b7a2b", ms=4, capsize=2)
    a2.set_ylabel("ripple rate - block mean (/NREM min)", fontsize=9, color="#2b7a2b")
    a3 = ax.twinx()
    a3.spines["right"].set_position(("axes", 1.15))
    rr = R1[R1.animals >= 3]
    a3.errorbar(rr.hour + 0.5, rr.rem_per_nrem, yerr=rr.rem_per_nrem_sem, fmt="-^", color="#d62728", ms=4, capsize=2)
    a3.set_ylabel("REM per NREM (s / s)", fontsize=9, color="#d62728")
    ax.set_title("C  NREM depth (purple), ripple rate (green), REM per NREM (red), nap frequency (orange background)",
                 fontsize=9, loc="left")
    for a_ in axes:
        a_.axvspan(0, sr_h, color="0.9", lw=0, zorder=0)
        a_.axvspan(ss_h, 24, color="0.9", lw=0, zorder=0)
        a_.set_xlim(0, 24)
        a_.set_xticks(range(0, 25, 2))
        a_.tick_params(labelsize=8)
    axes[2].set_xlabel("clock hour (EDT); grey = night", fontsize=9)
    fig.suptitle(f"Naps, NREM depth, ripple rate and REM per NREM by clock hour, cohort {COHORT}", fontsize=10)
    fig.tight_layout()
    out = figure_dir(COHORT) / f"ephys_spikes_night_naps_circadian_rem_{COHORT}.png"
    fig.savefig(out, dpi=125)
    plt.close(fig)
    return out


def rem_figure(N1: dict, R2: dict, R3: dict) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))
    ax = axes[0]
    bq = N1["matched"]["by_quintile"]
    ax.bar(bq.index, bq["diff"], color="#f28e2b")
    ax.axhline(0, color="0.4", lw=0.6)
    ax.set_xlabel("NREM depth quintile (within animal x block)", fontsize=9)
    ax.set_ylabel("nap - main sleep ripple rate (/NREM min)", fontsize=9)
    ax.set_title("A  Naps vs main sleep at matched depth", fontsize=9, loc="left")
    ax = axes[1]
    B = R2["B"].copy()
    B["r_dm"] = B.r - B.groupby("ab").r.transform("mean")
    B["q"] = pd.qcut(B.remsh.rank(method="first"), 8)
    s = B.groupby("q", observed=True).apply(lambda g: pd.Series({"x": g.remsh.mean(), "y": np.average(g.r_dm, weights=g.N),
                                                                "se": g.r_dm.std(ddof=1) / np.sqrt(len(g))}))
    ax.errorbar(100 * s.x, s.y, yerr=s.se, fmt="-o", color="#d62728", capsize=2)
    ax.axhline(0, color="0.4", lw=0.6)
    ax.set_xlabel("REM share of sleep in the 30-min bin (%)", fontsize=9)
    ax.set_ylabel("ripple rate - block mean (/NREM min)", fontsize=9)
    ax.set_title("B  Ripple rate vs REM share across bins (raw, octiles)", fontsize=9, loc="left")
    ax = axes[2]
    for nxt, c in (("REM", "#d62728"), ("WAKE", "0.4")):
        g = R3["curve"][R3["curve"].nxt == nxt]
        ax.errorbar(g.bin + 7.5, g["mean"], yerr=g["sem"], fmt="-o", color=c, ms=3, capsize=2, label=f"NREM -> {nxt}")
    ax.axhline(1, color="0.5", lw=0.6)
    ax.axvline(-120, color="0.7", lw=0.6, ls="--")
    ax.set_xlabel("time to the end of the NREM run (s)", fontsize=9)
    ax.set_ylabel("ripple rate / the run's -300..-120 s rate", fontsize=9)
    ax.set_title("C  Ripples before NREM -> REM vs NREM -> WAKE", fontsize=9, loc="left")
    ax.legend(fontsize=8, frameon=False)
    for a_ in axes:
        a_.tick_params(labelsize=8)
    fig.tight_layout()
    out = figure_dir(COHORT) / f"ephys_spikes_swr_rem_naps_{COHORT}.png"
    fig.savefig(out, dpi=125)
    plt.close(fig)
    return out


def _f(x, nd=2):
    return "" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{nd}f}"


def report(N1, R1, R2, R3, figs, rd):
    L = []
    w = L.append
    w(f"# Naps at equal NREM depth, and REM vs sharp-wave ripples ({COHORT})")
    w("")
    w(f"Generated by `ephys/swr_rem_naps.py run` (repo `{git_commit()}`); plan Amendment 3 of "
      "[`implementation_plan/2026-10-09-night-sleep-wiser.md`](../../../../implementation_plan/2026-10-09-night-sleep-wiser.md) "
      "(written before computing).")
    w("")
    w("## Answer")
    w("")
    for nm in ("vs main sleep, first 2 h", "vs all main sleep"):
        r = N1[nm]
        pa = r["per_animal"]
        w(f"- **N1 nap {nm}:** nap - main = {_f(r['without'].get('nap'), 1)} /NREM min [{_f(r['without'].get('nap_lo'), 1)}, "
          f"{_f(r['without'].get('nap_hi'), 1)}] without depth -> **{_f(r['with_depth'].get('nap'), 1)} [{_f(r['with_depth'].get('nap_lo'), 1)}, "
          f"{_f(r['with_depth'].get('nap_hi'), 1)}] with depth** (depth slope {_f(r['with_depth'].get('Dz'), 1)} per SD); positive in "
          f"{int((pa.gamma > 0).sum()) if len(pa) else 0} / {len(pa)} animals ({r['naps']} naps, {r['units']} units).")
    m = N1["matched"]
    w(f"- **N1 depth-matched (quintiles within block):** nap - main = {m['mean']:+.1f} /NREM min [{m['ci'][0]:+.1f}, {m['ci'][1]:+.1f}] "
      f"(animal-level t, p {m['p']:.3f}); positive in {m['positive']} / {m['animals']} animals.")
    w2, w3 = R2["with_controls"], R2["per_animal"]
    w(f"- **R2 ripple rate vs REM share (30-min bins, within block):** {_f(R2['without'].get('s10'), 2)} /NREM min per 10 % REM share "
      f"alone -> **{_f(w2.get('s10'), 2)} [{_f(w2.get('s10_lo'), 2)}, {_f(w2.get('s10_hi'), 2)}] with depth + hour** (p {_f(w2.get('s10_p'), 3)}); "
      f"negative in {int((w3.beta < 0).sum())} / {w3.beta.notna().sum()} animals.")
    d = R3["diff"]
    w(f"- **R3 transitions:** last-60-s ripple rate / the run's own baseline, NREM -> REM minus NREM -> WAKE = {d.mean():+.2f} "
      f"(animal-level p {R3['p']:.3f}; REM-bound lower in {int((d < 0).sum())} / {len(d)} animals). Per animal: "
      + "; ".join(f"{an} REM {R3['W'].loc[an, 'REM']:.2f} / WAKE {R3['W'].loc[an, 'WAKE']:.2f}" for an in R3["W"].index) + ".")
    r3a, r2a = R3["all_events"], R2["all_events"]["with_controls"]
    w(f"- **Check - all detected NREM events (theta / movement / LFP-EMG flags ignored):** R3 REM - WAKE = {r3a['diff'].mean():+.2f} "
      f"(p {r3a['p']:.3f}; REM-bound lower in {int((r3a['diff'] < 0).sum())} / {len(r3a['diff'])}; per animal "
      + "; ".join(f"{an} REM {r3a['W'].loc[an, 'REM']:.2f} / WAKE {r3a['W'].loc[an, 'WAKE']:.2f}" for an in r3a["W"].index)
      + f"); R2 with depth + hour {_f(r2a.get('s10'), 2)} [{_f(r2a.get('s10_lo'), 2)}, {_f(r2a.get('s10_hi'), 2)}] per 10 % REM, "
      f"negative in {int((R2['all_events']['per_animal'].beta < 0).sum())} / {R2['all_events']['per_animal'].beta.notna().sum()} animals.")
    w("- Reading rule (plan): the nap advantage survives depth when gamma with depth excludes 0, is positive in >= 4 animals "
      "and the depth-matched difference is positive; REM-SWR competition is supported when R2's REM-share slope is negative "
      "beyond depth and hour in >= 4 animals AND R3 shows a pre-REM drop the pre-WAKE runs do not.")
    w("")
    for p in figs:
        w(f"![{p.stem}](../figures/{p.name})")
        w("")
    w("## REM per NREM by clock hour (R1)")
    w("")
    w("| Hour | Animals | REM s per NREM s | SEM | REM share of sleep |")
    w("|---|---|---|---|---|")
    for r in R1.itertuples():
        w(f"| {r.hour:02d} | {r.animals} | {_f(r.rem_per_nrem, 3)} | {_f(r.rem_per_nrem_sem, 3)} | {_f(r.rem_share, 3)} |")
    w("")
    w("## Per animal")
    w("")
    pa1 = N1["vs main sleep, first 2 h"]["per_animal"].set_index("animal") if len(N1["vs main sleep, first 2 h"]["per_animal"]) else pd.DataFrame()
    pam = N1["matched"]["per_animal"]
    w("| Animal | Nap - main first 2 h, with depth [CI] | Depth-matched nap - main | R2 beta per 10 % REM [CI] | R3 REM ratio | R3 WAKE ratio | Transitions REM / WAKE |")
    w("|---|---|---|---|---|---|---|")
    r2 = R2["per_animal"].set_index("animal")
    for an in sorted(set(pam.index) | set(r2.index)):
        g = pa1.loc[an] if an in pa1.index else None
        cnt = R3["counts"].loc[an] if an in R3["counts"].index else None
        w(f"| {an} | {_f(g.gamma, 1) if g is not None else ''} [{_f(g.lo, 1) if g is not None else ''}, {_f(g.hi, 1) if g is not None else ''}] | "
          f"{_f(pam.get(an), 1)} | {_f(r2.beta.get(an), 2)} [{_f(r2.lo.get(an), 2)}, {_f(r2.hi.get(an), 2)}] | "
          f"{_f(R3['W']['REM'].get(an), 2)} | {_f(R3['W']['WAKE'].get(an), 2)} | "
          f"{int(cnt.get('REM', 0)) if cnt is not None else ''} / {int(cnt.get('WAKE', 0)) if cnt is not None else ''} |")
    w("")
    w("## Definitions")
    w("")
    w("- **Depth** = the raw spectral slope of the `imu_fixch` scores per NREM second, z within animal x block; **ripple rate** = kept "
      "NREM SWR events / ripple-eligible NREM minutes (tiers validated / good, the temperature analysis' exclusions).")
    w("- **N1 units**: each strict nap (night_naps primary), and each 30-min chunk of time since the main sleep onset; >= 5 NREM "
      "min. $r_u = \\alpha_{a,b} + \\gamma\\,\\mathrm{nap}_u (+ \\beta \\tilde D_u)$, WLS weights = NREM minutes, SEs clustered by "
      "biological night, $t(G-1)$. Depth-matched: quintiles of $\\tilde D$ over the block's nap + main NREM seconds; per quintile "
      "the nap and main rates; their difference averaged with weights min(nap, main) NREM minutes; per animal, then a one-sample t.")
    w("- **R1**: per clock hour, REM seconds / NREM seconds over all included records (hours with >= 5 NREM min), mean over animals.")
    w("- **R2**: 30-min clock bins within animal x block (>= 5 eligible NREM min); REM share $s_k$ = REM / (NREM + REM) seconds in the "
      "bin; $r_k = \\alpha_{a,b} + \\beta s_k + \\beta_D \\tilde D_k$ + 2 hour harmonics; beta per 10 percentage points.")
    w("- **R3**: NREM runs >= 300 s followed directly by >= 30 s REM or WAKE (1-s states; only runs with >= 200 ripple-eligible "
      "NREM seconds); rate in 15-s bins from -300 s to the transition; ratio = rate in the last 60 s / rate in -300..-120 s, pooled "
      "per animal and transition type; REM - WAKE difference per animal, one-sample t.")
    w("")
    w("## Limits")
    w("")
    w("- The last seconds of NREM before REM are intermediate sleep; the 1-s scoring can blur the boundary, and the detector "
      "excludes events in REM seconds - the R3 curve stops at the transition.")
    w("- Depth and REM come from the same scorer; REM share and ripple rate share the clock - hence the hour harmonics in R2.")
    (rd / f"ephys_spikes_swr_rem_naps_{COHORT}.md").write_text("\n".join(L) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ Amendment 4: macro-scale REM vs SWR
def macro(a):
    from scipy import stats
    I = load_inputs(a)
    rd, naps, secs, NSc, EVc = I["rd"], I["naps"], I["secs"], I["NSc"], I["EVc"]
    # block rate = all kept NREM events / all eligible NREM minutes of the animal x block
    brate = (EVc.groupby("ab").size() / (NSc.groupby("ab").size() / 60)).rename("brate")
    rows, days = [], []
    for an, S in secs.items():
        S = S.copy()
        S["unit"] = None
        S.loc[S.tau_h.notna(), "unit"] = "main " + (np.floor(S.tau_h[S.tau_h.notna()]).astype(int)).astype(str).str.zfill(2)
        night = (S.t.dt.hour >= 19) | (S.t.dt.hour < 7)
        S.loc[S.tau_h.isna() & night & S.state.isin([N, R]), "unit"] = "other night sleep"
        for r in naps[naps.animal == an].itertuples():
            S.loc[(S.t >= r.start) & (S.t < r.end), "unit"] = "naps"
        S["mso"] = (S.t - pd.to_timedelta(S.tau_h, unit="h")).dt.round("min")
        ns = NSc[NSc.animal == an].copy()
        evs = EVc[EVc.animal == an].copy()
        lab = S[["t", "unit", "mso"]].assign(t=S.t.dt.floor("s"))
        ns = pd.merge_asof(ns.drop(columns=[c for c in ("unit", "mso") if c in ns]).sort_values("t"), lab, on="t", direction="nearest", tolerance=pd.Timedelta(seconds=2))
        evs = pd.merge_asof(evs.drop(columns=[c for c in ("unit", "mso") if c in evs]).sort_values("t"), lab, on="t", direction="nearest", tolerance=pd.Timedelta(seconds=2))
        for u, g in S.dropna(subset=["unit"]).groupby("unit"):
            nr, rm = int((g.state == N).sum()), int((g.state == R).sum())
            gn = ns[ns.unit == u]
            ge = evs[evs.unit == u]
            if nr < 600 or len(gn) < 600:
                continue
            exp = float((gn.groupby("ab").size() / 60 * brate.reindex(gn.groupby("ab").size().index)).sum())
            rows.append(dict(animal=an, unit=u, rem_per_nrem=rm / nr, rem_share=rm / (nr + rm), nrem_min=nr / 60,
                             elig_min=len(gn) / 60, n=len(ge), rel_rate=len(ge) / exp if exp > 0 else np.nan, Dz=float(gn.Dz.mean())))
        # M3: per main sleep (one per day)
        mm = S[S.tau_h.notna()]
        for mso, g in mm.groupby("mso"):
            nr, rm = int((g.state == N).sum()), int((g.state == R).sum())
            gn = ns[(ns.mso == mso)]
            ge = evs[(evs.mso == mso)]
            if nr < 3600 or len(gn) < 1800:
                continue
            exp = float((gn.groupby("ab").size() / 60 * brate.reindex(gn.groupby("ab").size().index)).sum())
            days.append(dict(animal=an, mso=mso, rem_share=rm / (nr + rm), rem_per_nrem=rm / nr, rel_rate=len(ge) / exp if exp > 0 else np.nan,
                             Dz=float(gn.Dz.mean()), nrem_h=nr / 3600))
    U, D = pd.DataFrame(rows), pd.DataFrame(days)
    order = ["naps", "other night sleep"] + [f"main {k:02d}" for k in range(14)]
    M1 = U.groupby("unit").agg(animals=("animal", "nunique"), rem_per_nrem=("rem_per_nrem", "mean"),
                               rem_sem=("rem_per_nrem", lambda v: v.std(ddof=1) / np.sqrt(len(v))), rel_rate=("rel_rate", "mean"),
                               rate_sem=("rel_rate", lambda v: v.std(ddof=1) / np.sqrt(len(v))), Dz=("Dz", "mean")).reindex(order).dropna(how="all")

    def partial_rho(g):
        import statsmodels.api as sm
        X = sm.add_constant(g.Dz)
        ra = sm.OLS(g.rem_per_nrem, X).fit().resid
        rb = sm.OLS(g.rel_rate, X).fit().resid
        return stats.spearmanr(ra, rb)[0]

    M2 = []
    for an, g in U.groupby("animal"):
        if len(g) >= 5:
            M2.append(dict(animal=an, units=len(g), rho=stats.spearmanr(g.rem_per_nrem, g.rel_rate)[0], rho_partial_depth=partial_rho(g)))
    M2 = pd.DataFrame(M2)
    M3 = []
    for an, g in D.groupby("animal"):
        if len(g) >= 4:
            M3.append(dict(animal=an, days=len(g), rho=stats.spearmanr(g.rem_share, g.rel_rate)[0], rho_partial_depth=partial_rho(g)))
    M3 = pd.DataFrame(M3)

    def amean(v):
        v = pd.Series(v).dropna()
        t_ = stats.ttest_1samp(v, 0) if len(v) >= 3 else None
        return float(v.mean()), (float(t_.pvalue) if t_ else np.nan), int((v < 0).sum()), len(v)

    U.to_csv(rd / f"ephys_spikes_swr_rem_macro_units_{COHORT}.csv", index=False)
    D.to_csv(rd / f"ephys_spikes_swr_rem_macro_days_{COHORT}.csv", index=False)
    fig = macro_figure(M1, U, D)
    L = []
    w = L.append
    w(f"# REM vs sharp-wave ripples at the macro scale ({COHORT})")
    w("")
    w(f"Generated by `ephys/swr_rem_naps.py macro` (repo `{git_commit()}`); plan Amendment 4 of "
      "[`implementation_plan/2026-10-09-night-sleep-wiser.md`](../../../../implementation_plan/2026-10-09-night-sleep-wiser.md) "
      "(written before computing). The user: competition at the macro scale = REM is scarce in the night naps and abundant in "
      "the day sleep, ripples the opposite.")
    w("")
    w("## Answer")
    w("")
    nap = M1.loc["naps"] if "naps" in M1.index else None
    w(f"- **M1 allocation:** naps REM per NREM {nap.rem_per_nrem:.3f} with ripple rate {nap.rel_rate:.2f} x the block mean; the main "
      f"sleep goes from REM {M1.loc['main 00'].rem_per_nrem:.3f} / ripples {M1.loc['main 00'].rel_rate:.2f} in its first hour to "
      f"REM {M1.iloc[-1].rem_per_nrem:.3f} / ripples {M1.iloc[-1].rel_rate:.2f} in its last ({M1.index[-1]}).")
    m, p_, neg, n_ = amean(M2.rho)
    mp, pp, negp, _ = amean(M2.rho_partial_depth)
    w(f"- **M2 across sleep periods (naps, other night sleep, main-sleep hours):** Spearman rho(REM per NREM, ripple rate) mean "
      f"{m:+.2f} (p {p_:.3f}), negative in {neg} / {n_} animals; with depth partialled out {mp:+.2f} (p {pp:.3f}), negative in "
      f"{negp} / {n_}. Per animal: " + "; ".join(f"{r.animal} {r.rho:+.2f} ({r.rho_partial_depth:+.2f})" for r in M2.itertuples()) + ".")
    if len(M3):
        m3, p3, neg3, n3 = amean(M3.rho)
        m3p, p3p, neg3p, _ = amean(M3.rho_partial_depth)
        w(f"- **M3 across days (one main sleep per day):** rho(REM share, ripple rate) mean {m3:+.2f} (p {p3:.3f}), negative in "
          f"{neg3} / {n3}; depth partialled {m3p:+.2f} (p {p3p:.3f}). Per animal: " + "; ".join(
              f"{r.animal} {r.rho:+.2f} ({r.days} days)" for r in M3.itertuples()) + ".")
    w("- Reading rule (plan): macro reciprocity when M2 rho < 0 in >= 4 animals; the depth partial tells whether depth (sleep "
      "pressure) carries it; M3 tells whether it also holds from day to day, outside the clock.")
    w("")
    w(f"![macro REM vs SWR](../figures/{fig.name})")
    w("")
    w("## Allocation by sleep period (M1; mean over animals)")
    w("")
    w("| Period | Animals | REM per NREM | SEM | Ripple rate (x block mean) | SEM | Depth (z) |")
    w("|---|---|---|---|---|---|---|")
    for u, r in M1.iterrows():
        w(f"| {u} | {int(r.animals)} | {r.rem_per_nrem:.3f} | {_f(r.rem_sem, 3)} | {r.rel_rate:.2f} | {_f(r.rate_sem, 2)} | {r.Dz:+.2f} |")
    w("")
    w("## Definitions")
    w("")
    w("- **Units** per animal: its strict naps (pooled), its other night sleep (19:00-07:00, before the main sleep onset, not a "
      "strict nap), and its main sleep in 1-h bins of time since onset (`main 00` = the first hour); >= 10 NREM min and >= 10 "
      "ripple-eligible NREM min.")
    w("- **REM per NREM** = REM s / NREM s of the 1-s states in the unit; **REM share** = REM / (NREM + REM).")
    w("- **Relative ripple rate** = kept NREM events in the unit / the events expected at the animal x block's overall NREM rate "
      "for the unit's eligible NREM minutes (1 = the block mean).")
    w("- **M2** per animal Spearman rho over its units, and the partial version (both variables residualised on the unit's mean "
      "depth z); animal-level mean, one-sample t. **M3** the same over the animal's main sleeps (one per day; >= 1 h NREM).")
    (rd / f"ephys_spikes_swr_rem_macro_{COHORT}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[L.index("## Answer"):L.index("## Allocation by sleep period (M1; mean over animals)")]))


def macro_figure(M1: pd.DataFrame, U: pd.DataFrame, D: pd.DataFrame) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8), gridspec_kw={"width_ratios": [1.6, 1, 1]})
    ax = axes[0]
    x = np.arange(len(M1))
    ax.errorbar(x, M1.rem_per_nrem, yerr=M1.rem_sem, fmt="-^", color="#d62728", capsize=2)
    ax.set_ylabel("REM per NREM (s / s)", fontsize=9, color="#d62728")
    a2 = ax.twinx()
    a2.errorbar(x, M1.rel_rate, yerr=M1.rate_sem, fmt="-s", color="#2b7a2b", capsize=2)
    a2.axhline(1, color="0.6", lw=0.6)
    a2.set_ylabel("ripple rate (x block mean)", fontsize=9, color="#2b7a2b")
    ax.set_xticks(x)
    ax.set_xticklabels([u.replace("main ", "main h") for u in M1.index], rotation=60, fontsize=7)
    ax.set_title("A  REM and ripples by sleep period (mean +- SEM over animals)", fontsize=9, loc="left")
    ax = axes[1]
    for an, g in U.groupby("animal"):
        ax.scatter(g.rem_per_nrem, g.rel_rate, s=14, label=an)
        if len(g) >= 3:
            k = np.polyfit(g.rem_per_nrem, g.rel_rate, 1)
            xs = np.linspace(g.rem_per_nrem.min(), g.rem_per_nrem.max(), 5)
            ax.plot(xs, np.polyval(k, xs), lw=0.8)
    ax.set_xlabel("REM per NREM in the period", fontsize=9)
    ax.set_ylabel("ripple rate (x block mean)", fontsize=9)
    ax.set_title("B  Across sleep periods, per animal", fontsize=9, loc="left")
    ax.legend(fontsize=7, frameon=False)
    ax = axes[2]
    for an, g in D.groupby("animal"):
        ax.scatter(100 * g.rem_share, g.rel_rate, s=18, label=an)
    ax.set_xlabel("REM share of the day's main sleep (%)", fontsize=9)
    ax.set_ylabel("ripple rate (x block mean)", fontsize=9)
    ax.set_title("C  Across days (one main sleep per day)", fontsize=9, loc="left")
    for a_ in axes:
        a_.tick_params(labelsize=8)
    fig.tight_layout()
    out = figure_dir(COHORT) / f"ephys_spikes_swr_rem_macro_{COHORT}.png"
    fig.savefig(out, dpi=125)
    plt.close(fig)
    return out


def selftest():
    s = np.array([W] * 100 + [N] * 400 + [R] * 60 + [N] * 100 + [W] * 40 + [N] * 350 + [W] * 50, np.int8)
    tr = transitions(s, min_nrem=300)
    ok = tr == [(100, 500, R), (700, 1050, W)]
    print(f"{'PASS' if ok else 'FAIL'} transitions {tr}")
    print("SELFTEST " + ("PASS" if ok else "FAIL"))
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["run", "macro"])
    ap.add_argument("--states-root", default="D:/3rd_rat_spikes/analysis/sleep_server/states_1s_final")
    ap.add_argument("--sleep-root", default="Q:/hc997/SocialFieldRat2026/3rd_rat/analysis/sleep/imu_fixch")
    ap.add_argument("--swr-root", default="Q:/hc997/SocialFieldRat2026/3rd_rat/analysis/swr")
    ap.add_argument("--quality", default=str(report_dir(COHORT) / f"ephys_spikes_swr_quality_{COHORT}.csv"))
    ap.add_argument("--review", default=str(report_dir(COHORT) / f"ephys_spikes_sleep_review_{COHORT}.csv"))
    ap.add_argument("--cohort-yaml", default=str(REPO / f"cohorts/{COHORT}.yaml"))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    if a.cmd == "run":
        run(a)
    if a.cmd == "macro":
        macro(a)


if __name__ == "__main__":
    main()
