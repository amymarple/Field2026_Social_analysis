r"""PILOT (description only): in-house microphone levels around wakes from NREM, cohort 2026c.
Plan: implementation_plan/2026-10-07-sleep-internal-schedule.md, section 4 D (D2 house assignment, D3 pilot).
Nothing here labels a sound as external or animal-made; the candidate classes are for the user's listening check.

Inputs: FINAL 1-s sleep states (states_1s_final) + the review table (exclusions as the sleep-cycle drivers), the head-IMU
seconds cache (state 0 unusable / 1 still / 2 active / 3 locomoting), the WISER default tracks (house zone per second:
`wiser_rois.json` house_1 / house_2 grown by 14 in), and ephys/mic_band_levels.py output.

Definitions (pilot choices, not tuned on outcomes):
  wake event     an NREM -> WAKE transition in the FINAL states after >= 60 s of NREM, before 2026-09-11 19:40.
  zone           the focal animal's WISER zone 5 s before the score's wake onset; only house events are kept.
  movement onset m = the first second in [onset - 20, onset + 20] with IMU state >= 2 in it and the next second, after
                 >= 10 s of IMU state 1 (still); events without one are dropped (no clear movement onset).
  housemate first another implanted animal in the same house had its own movement onset (same rule) in [m - 30, m - 1].
  transient      per mic and band b in {b0, b1, b2}: max over [m - 10, m - 1] of max_db(b) minus the median of max_db(b)
                 over [m - 60, m - 20]; "sound first" if >= 10 dB in any of b0-b2 on the focal house's mic.
  common         a sound-first event whose other-house mic also shows a >= 10 dB transient in the same window.
  outdoor        the CH01 / CH02 camera audio (bands c0-c2, 50 Hz-8 kHz, decoded on the stream timestamps): the same
                 transient rule, max over the two cameras.
  classes        housemate_first > sound_first_outdoor (own house + outdoor) > sound_first_common (both houses) >
                 sound_first_own_only > none_observed (first match wins).
  chance reference the same housemate and transient checks at r = m - 120 s (the focal animal is asleep then: every event
                 follows >= 60 s of NREM, most far longer), reported next to the event rates; a cue only means something
                 if it is more frequent before the movement onset than at r.
  mic per house  the working assignment (MIC01 = house_2, MIC02 = house_1) unless --assign says otherwise; D2 below
                 reports the per-day evidence for it.
  D2             per date: Spearman correlation of each mic's b1 / b3 per-second level with log(summed VeDBA + 0.01) of the
                 animals in each house.

Usage: python ephys/mic_wake_pilot.py --mic-root <mic_band_levels dir> [--assign MIC01=house_2 MIC02=house_1]
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "wiser" / "src"))
sys.path.insert(0, str(ROOT / "common"))
sys.path.insert(0, str(Path(__file__).parent))

OUT = Path("D:/Field2026_analysis_out/2026c")
STATES = Path("D:/3rd_rat_spikes/analysis/sleep_server/states_1s_final")
REVIEW = ROOT / "results/2026c/ephys_spikes/reports/ephys_spikes_sleep_review_2026c.csv"
CUTOFF = pd.Timestamp("2026-09-11 19:40")
ANIMALS = ["SF07", "SF08", "SF09", "SF10", "SF11", "SF12"]
W, N = 1, 3
BANDS = ("b0", "b1", "b2")
TH_DB = 10.0


def included_sessions() -> pd.DataFrame:
    from sleep_quant import MIN_SESSION_H, PADDOCK_END
    rv = pd.read_csv(REVIEW)
    rv["start"] = pd.to_datetime(rv.start_local)
    keep = []
    for r in rv.itertuples():
        tags = r.tags if isinstance(r.tags, str) else ""
        keep.append((STATES / r.animal / f"{r.session}.states.npz").exists() and r.verdict != "noise"
                    and "SF12_contact_failing" not in tags and (r.duration_h or 0) >= MIN_SESSION_H)
    rv = rv[keep].copy()
    ends = []
    for r in rv.itertuples():
        e = PADDOCK_END
        for t in (r.tags if isinstance(r.tags, str) else "").split(";"):
            if t.startswith("valid_until "):
                e = min(e, pd.Timestamp(t[len("valid_until "):]))
        ends.append(min(e, CUTOFF))
    rv["end_cut"] = ends
    return rv


def wake_events(rv: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for r in rv.itertuples():
        with np.load(STATES / r.animal / f"{r.session}.states.npz") as z:
            st = z["state"]
        n_ok = int(max(0, min(len(st), (r.end_cut - r.start).total_seconds())))
        st = st[:n_ok]
        if n_ok < 120:
            continue
        chg = np.flatnonzero(np.diff(st.astype(int)) != 0) + 1
        starts = np.r_[0, chg]
        for i in range(1, len(starts)):
            a = starts[i]
            if st[a] == W and st[a - 1] == N and (a - starts[i - 1]) >= 60:
                rows.append({"animal": r.animal, "session": r.session,
                             "onset": (r.start + pd.Timedelta(seconds=int(a))).floor("1s")})
    return pd.DataFrame(rows)


def load_imu(an: str, dates) -> pd.DataFrame:
    fs = [OUT / f"imu_seconds_cache/{an}/{d}.csv.gz" for d in dates]
    fs = [f for f in fs if f.exists()]
    if not fs:
        return pd.DataFrame(columns=["state", "vedba_1s"])
    d = pd.concat([pd.read_csv(f, usecols=["sec", "ok", "state", "vedba_1s"]) for f in fs])
    d["t"] = pd.to_datetime(d.sec, unit="s") - pd.Timedelta(hours=4)
    return d.drop_duplicates("t").set_index("t")


def load_zone(an: str, dates, rois) -> pd.Series:
    import wiser_analysis_utils as Wu
    fs = [OUT / f"wiser_default_tracks/{an}/{d}.csv.gz" for d in dates]
    fs = [f for f in fs if f.exists()]
    if not fs:
        return pd.Series(dtype=object)
    tr = pd.concat([pd.read_csv(f, usecols=["t_ms", "x", "y"]) for f in fs])
    tr["t"] = (pd.to_datetime(tr.t_ms, unit="ms") - pd.Timedelta(hours=4)).dt.floor("1s")
    pos = tr.groupby("t")[["x", "y"]].median()
    grid = pd.date_range(pos.index.min(), pos.index.max(), freq="1s")
    pos = pos.reindex(grid).ffill(limit=30)
    z = pd.Series("field", index=grid, dtype=object)
    fin = pos.x.notna().to_numpy()
    for h, roi in rois.items():
        _, inb = Wu._rect_membership(pos.x.fillna(0).to_numpy(), pos.y.fillna(0).to_numpy(), roi, 14.0)
        z[fin & inb] = h
    z[~fin] = "unknown"
    return z


def movement_onset(state: pd.Series, t: pd.Timestamp, lo: int, hi: int):
    win = state.reindex(pd.date_range(t + pd.Timedelta(seconds=lo - 12), t + pd.Timedelta(seconds=hi + 1), freq="1s"))
    s = win.to_numpy()
    for k in range(12, len(s) - 1):
        if s[k] >= 2 and s[k + 1] >= 2 and np.all(s[k - 10:k] == 1):
            return win.index[k]
    return None


def main() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from _common import git_commit, write_json
    from output_paths import run_dir
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mic-root", default=str(OUT / "audio_levels"))
    ap.add_argument("--assign", nargs="*", default=["MIC01=house_2", "MIC02=house_1"])
    a = ap.parse_args()
    out = run_dir("mic_wake_pilot", "2026c")
    house_mic = {v: k for k, v in (s.split("=") for s in a.assign)}
    rois = {r["name"]: r for r in json.load(open(ROOT / "wiser/configs/wiser_rois.json"))["rois"] if r["name"] in ("house_1", "house_2")}

    mic = {}
    for m in ("MIC01", "MIC02", "CH01", "CH02"):
        fs = sorted(glob.glob(str(Path(a.mic_root) / m / "*.csv.gz")))
        d = pd.concat([pd.read_csv(f, parse_dates=["t_pc"]) for f in fs])
        mic[m] = d.drop_duplicates("t_pc").set_index("t_pc").sort_index()
        print(m, len(fs), "files", d.t_pc.min(), "->", d.t_pc.max(), flush=True)
    dates = sorted({t.strftime("%Y%m%d") for t in pd.date_range("2026-08-30", "2026-09-11")})
    imu = {an: load_imu(an, dates) for an in ANIMALS}
    zone = {an: load_zone(an, dates, rois) for an in ANIMALS}
    print("IMU / WISER loaded", flush=True)

    # ---------------- D2: per-date mic vs per-house movement
    rows = []
    for d in dates:
        day = pd.date_range(pd.Timestamp(d), pd.Timestamp(d) + pd.Timedelta(hours=24), freq="1s", inclusive="left")
        act = {h: pd.Series(0.0, index=day) for h in rois}
        n_h = {h: pd.Series(0, index=day) for h in rois}
        for an in ANIMALS:
            if imu[an].empty or zone[an].empty:
                continue
            v = imu[an].vedba_1s.where(imu[an].ok.astype(bool)).reindex(day)
            z = zone[an].reindex(day)
            for h in rois:
                sel = (z == h) & v.notna()
                act[h] = act[h] + v.where(sel, 0.0).fillna(0)
                n_h[h] = n_h[h] + sel.astype(int)
        for m, md in ((k, v) for k, v in mic.items() if k.startswith("MIC")):
            lv = md.reindex(day)
            for h in rois:
                ok = n_h[h] > 0
                if ok.sum() < 600 or lv.b1_mean_db.notna().sum() < 600:
                    continue
                aa = np.log10(act[h][ok] + 0.01)
                rows.append({"date": d, "mic": m, "house": h, "animal_seconds": int(n_h[h].sum()),
                             "seconds_with_animals": int(ok.sum()),
                             "rho_b1": lv.b1_mean_db[ok].corr(aa, method="spearman"),
                             "rho_b3": lv.b3_mean_db[ok].corr(aa, method="spearman")})
    d2 = pd.DataFrame(rows)
    d2.to_csv(out / "d2_mic_vs_house_movement_by_date.csv", index=False)
    print(d2.pivot_table(index="date", columns=["mic", "house"], values="rho_b3").round(2), flush=True)

    # ---------------- D3: wake events
    ev = wake_events(included_sessions())
    print("wake events after >= 60 s NREM:", len(ev), flush=True)
    recs = []
    for e in ev.itertuples():
        z = zone[e.animal].get(e.onset - pd.Timedelta(seconds=5), "unknown") if not zone[e.animal].empty else "unknown"
        if z not in rois or imu[e.animal].empty:
            continue
        m_on = movement_onset(imu[e.animal]["state"], e.onset, -20, 20)
        if m_on is None:
            continue
        own, other = house_mic[z], house_mic["house_1" if z == "house_2" else "house_2"]
        r = {"animal": e.animal, "session": e.session, "score_onset": e.onset, "move_onset": m_on, "house": z, "own_mic": own}
        for pfx, t_ref in (("", m_on), ("ref_", m_on - pd.Timedelta(seconds=120))):
            mates = []
            for an in ANIMALS:
                if an == e.animal or imu[an].empty or zone[an].empty:
                    continue
                if zone[an].get(t_ref - pd.Timedelta(seconds=5), "") != z:
                    continue
                mo = movement_onset(imu[an]["state"], t_ref, -30, -1)
                if mo is not None:
                    mates.append((an, (t_ref - mo).total_seconds()))
            r[f"{pfx}housemates_first"] = ";".join(f"{an}:{s:.0f}" for an, s in mates)
            for tag, mname in (("own", own), ("other", other)):
                md = mic[mname]
                base = md.loc[t_ref - pd.Timedelta(seconds=60):t_ref - pd.Timedelta(seconds=20)]
                pre = md.loc[t_ref - pd.Timedelta(seconds=10):t_ref - pd.Timedelta(seconds=1)]
                for b in BANDS:
                    col = f"{b}_max_db"
                    r[f"{pfx}{tag}_{b}_jump_db"] = (pre[col].max() - base[col].median()) if len(base) >= 20 and len(pre) >= 5 else np.nan
            outj = []
            for cam in ("CH01", "CH02"):
                if cam not in mic:
                    continue
                md = mic[cam]
                base = md.loc[t_ref - pd.Timedelta(seconds=60):t_ref - pd.Timedelta(seconds=20)]
                pre = md.loc[t_ref - pd.Timedelta(seconds=10):t_ref - pd.Timedelta(seconds=1)]
                if len(base) >= 20 and len(pre) >= 5:
                    outj += [pre[f"{c}_max_db"].max() - base[f"{c}_max_db"].median() for c in ("c0", "c1", "c2")]
            r[f"{pfx}outdoor_jump_db"] = float(np.nanmax(outj)) if outj else np.nan
        recs.append(r)
    E = pd.DataFrame(recs)
    jo = E[[f"own_{b}_jump_db" for b in BANDS]].max(axis=1)
    jx = E[[f"other_{b}_jump_db" for b in BANDS]].max(axis=1)
    jout = E.outdoor_jump_db
    cls = np.where(E.housemates_first != "", "housemate_first",
                   np.where(jo >= TH_DB, np.where(jout >= TH_DB, "sound_first_outdoor",
                                                  np.where(jx >= TH_DB, "sound_first_common", "sound_first_own_only")),
                            np.where(jo.isna(), "no_mic_data", "none_observed")))
    E["candidate_class"] = cls
    E.to_csv(out / "d3_wake_events.csv", index=False)
    summ = E.groupby(["house", "candidate_class"]).size().unstack(fill_value=0)
    summ.to_csv(out / "d3_class_counts.csv")
    print(summ, flush=True)
    rjo = E[[f"ref_own_{b}_jump_db" for b in BANDS]].max(axis=1)
    rjx = E[[f"ref_other_{b}_jump_db" for b in BANDS]].max(axis=1)
    m_ok, r_ok = jo.notna(), rjo.notna()
    rates = pd.DataFrame([
        {"cue": "housemate moved in the 30 s before", "before_movement_onset": (E.housemates_first != "").mean(),
         "chance_reference_m_minus_120s": (E.ref_housemates_first != "").mean(), "n": len(E)},
        {"cue": "own-house mic transient >= 10 dB (b0-b2) in the 10 s before",
         "before_movement_onset": (jo[m_ok] >= TH_DB).mean(), "chance_reference_m_minus_120s": (rjo[r_ok] >= TH_DB).mean(),
         "n": int(m_ok.sum())},
        {"cue": "transient on both house mics", "before_movement_onset": ((jo >= TH_DB) & (jx >= TH_DB))[m_ok].mean(),
         "chance_reference_m_minus_120s": ((rjo >= TH_DB) & (rjx >= TH_DB))[r_ok].mean(), "n": int(m_ok.sum())},
        {"cue": "own-house transient + outdoor (CH01/CH02) transient", "before_movement_onset": ((jo >= TH_DB) & (E.outdoor_jump_db >= TH_DB))[m_ok].mean(),
         "chance_reference_m_minus_120s": ((rjo >= TH_DB) & (E.ref_outdoor_jump_db >= TH_DB))[r_ok].mean(), "n": int(m_ok.sum())},
        {"cue": "outdoor transient alone (either camera)", "before_movement_onset": (E.outdoor_jump_db >= TH_DB).mean(),
         "chance_reference_m_minus_120s": (E.ref_outdoor_jump_db >= TH_DB).mean(), "n": int(E.outdoor_jump_db.notna().sum())},
    ])
    rates.to_csv(out / "d3_cue_rates_vs_chance.csv", index=False)
    print(rates.round(3).to_string(index=False), flush=True)

    # event-triggered medians (own / other mic, aligned on the movement onset), per class
    lags = np.arange(-60, 61)
    fig, axes = plt.subplots(2, 3, figsize=(15, 7), sharex=True)
    for j, b in enumerate(BANDS):
        for i, tag in enumerate(("own", "other")):
            ax = axes[i, j]
            for c in ("housemate_first", "sound_first_outdoor", "sound_first_common", "sound_first_own_only", "none_observed"):
                sub = E[E.candidate_class == c]
                if len(sub) < 5:
                    continue
                M = []
                for r in sub.itertuples():
                    md = mic[r.own_mic if tag == "own" else ("MIC01" if r.own_mic == "MIC02" else "MIC02")]
                    s = md[f"{b}_max_db"].reindex(r.move_onset + pd.to_timedelta(lags, unit="s")).to_numpy()
                    M.append(s - np.nanmedian(s[:40]))
                ax.plot(lags, np.nanmedian(np.array(M), axis=0), label=f"{c} (n={len(sub)})")
            ax.axvline(0, color="k", lw=0.8)
            ax.set_title(f"{tag}-house mic, {b} max level")
            ax.set_ylabel("dB vs baseline (median)")
            if i == 1:
                ax.set_xlabel("s from the focal animal's movement onset")
    axes[0, 0].legend(fontsize=7)
    fig.suptitle("PILOT - in-house mic levels around wakes from NREM (candidate classes, not validated)")
    fig.tight_layout()
    fig.savefig(out / "d3_event_triggered_levels.png", dpi=120)
    rng = np.random.default_rng(0)
    sample = pd.concat([g.iloc[rng.permutation(len(g))[:8]] for _, g in E.groupby("candidate_class")])
    sample.to_csv(out / "d3_listening_sample.csv", index=False)
    write_json(out / "run_info.json", {"git_commit": git_commit(), "assign": a.assign, "threshold_db": TH_DB,
                                       "n_events_house": len(E), "pilot": True})
    print("written", out)


if __name__ == "__main__":
    main()
