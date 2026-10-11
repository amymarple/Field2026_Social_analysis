"""Delta-wave (cortical DOWN-state) rate per NREM time, per day and within a day - the twin of the SWR figure
(swr_temperature.py `figure`, ephys_spikes_swr_rate_day_and_hour_2026c.png; the user 2026-10-10: "画个类似的").

Same definitions as the SWR figure, by importing its functions (swr_temperature.settle_windows / keep_mask / build_bins /
hour_profile / periods; sleep_quant.sun_times): clock = session start_local + s (field-PC local time); NREM = the final
1-s states (state 3); exclusions = the first 30 min of every session (handling), from use_until (and the cohort's
valid_until), from 09-11 19:40 (females), probe-advance settle windows (cohorts/2026c.yaml probe_moves + settle_h);
30-min bins per animal x probe block with >= 5 NREM min, rate r = events / NREM min; day / night by the bin centre
(NOAA sunrise / sunset at the paddock), bins containing sunrise or sunset dropped; weather = the SWR run's
weather_anomaly.csv.gz (the same on-site series, not re-extracted).
Delta-specific: events = the storage delta production (3rd_rat/analysis/delta/), `verified == 1` (raw multi-unit firing at
the peak <= 0.5 x baseline) and after_use_until == 0; sessions = those with the MUA check (FM65; FM64 is on hold),
excluding the user's 'noise' sleep sessions; probe block = the SWR quality table's block (as for the ripples).
`--events all` draws every detected delta wave instead (no DOWN-state check; FM64 sessions included).
`--mask-after-rounds H` (sensitivity, SWRdetection / sleep-model suggestion 2026-10-10): also drops every operator-in-arena
window of cv/configs/cohort3_handling_windows.json (battery rounds, probe handling; all animals) and the H hours after it -
post-round sleep is not ordinary sleep (the sleep model: ~1.3-1.4x waking in the first hour, REM repayment after).

  python ephys/delta_circadian.py [--events verified|all] [--mask-after-rounds H] [--delta-root Q:/…/analysis/delta]
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
import swr_temperature as st  # noqa: E402
from _common import figure_dir, git_commit, report_dir, write_json  # noqa: E402
from swr_auto import session_start  # noqa: E402

COHORT = "2026c"


def delta_sessions(table: Path, review: Path, cohort_yaml: Path, events: str) -> pd.DataFrame:
    """One row per delta session (reports/..._delta_sessions_<c>.csv) with start_t, use_until_t, block_from."""
    import yaml
    q = pd.read_csv(table)
    q = q[q.n_events > 0]
    if events == "verified":
        q = q[q.n_testable > 0]
    q = q[q.sleep_verdict.fillna("") != "noise"].copy()
    rv = pd.read_csv(review)[["animal", "session", "start_local"]]
    q = q.merge(rv, on=["animal", "session"], how="left")
    q["start_t"] = pd.to_datetime(q.start_local).fillna(pd.Series([pd.Timestamp(session_start(s)) for s in q.session], index=q.index))
    uu = pd.to_datetime(q.use_until.fillna("").astype(str).str.slice(0, 19), errors="coerce")
    vu = {(v["animal"], v["session"]): pd.Timestamp(v["valid_until"])
          for v in yaml.safe_load(open(cohort_yaml, encoding="utf-8"))["ephys"].get("valid_until", [])}
    q["use_until_t"] = [min([x for x in (u, vu.get((a, s))) if pd.notna(x)], default=pd.NaT)
                        for u, a, s in zip(uu, q.animal, q.session)]
    q["block_from"] = q.block.fillna("start").astype(str)
    q["tier"] = "delta"
    return q.reset_index(drop=True)


def load_delta_session(row, delta_root: Path, states_root: Path, end: pd.Timestamp, windows, events: str):
    """(NREM delta events, NREM seconds) of one session after the SWR figure's exclusions. f (ripple frequency) = 0 and
    amp = amp_z are finite placeholders: the SWR helpers average every outcome and fail on all-NaN columns; only the rate
    is used here."""
    sf = states_root / row.animal / f"{row.session}.states.npz"
    if not sf.exists():
        return None, None
    d = pd.read_csv(delta_root / row.animal / row.session / f"{row.session}.delta_events.csv")
    m = d.after_use_until == 0
    if events == "verified":
        m &= d.verified == 1
    d = d[m]
    ev = pd.DataFrame({"t": row.start_t + pd.to_timedelta(d.t_peak.to_numpy(), unit="s"), "f": 0.0,
                       "d": d.dur_ms.to_numpy(float), "amp": d.amp_z.to_numpy(float)})
    with np.load(sf) as s:
        ts = s["ts"][s["state"] == 3].astype(float)
    nrem = pd.Series(row.start_t + pd.to_timedelta(ts, unit="s"))
    ev = ev[st.keep_mask(ev.t, row, end, windows)]
    nrem = nrem[st.keep_mask(nrem, row, end, windows)]
    for c, v in (("animal", row.animal), ("session", row.session), ("block", row.block_from), ("tier", row.tier)):
        ev[c] = v
    return ev, pd.DataFrame({"t": nrem.values, "animal": row.animal, "block": row.block_from})


def figure(b: pd.DataFrame, per: pd.DataFrame, wx: pd.DataFrame, events: str, out: Path, mask_h=None) -> pd.DataFrame:
    """The layout of swr_temperature.rate_day_hour_figure, for delta waves."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from sleep_quant import sun_times
    per = per.copy()
    per["mid"] = pd.to_datetime("2026-" + per.bio) + np.where(per.phase == "day", pd.Timedelta(hours=13), pd.Timedelta(hours=25))
    animals = sorted(b.animal.unique())
    cmap = plt.get_cmap("tab10")
    colr = {an: cmap(i) for i, an in enumerate(["SF07", "SF08", "SF09", "SF10", "SF11", "SF12"])}
    fig = plt.figure(figsize=(14, 10))
    gs = fig.add_gridspec(3, 2, height_ratios=[1.3, 0.7, 1.3], hspace=0.38, wspace=0.22)
    ax1 = fig.add_subplot(gs[0, :])
    ax2 = fig.add_subplot(gs[1, :], sharex=ax1)
    d0, d1 = pd.Timestamp("2026-08-31"), pd.Timestamp("2026-09-12")
    for D in pd.date_range(d0 - pd.Timedelta(days=1), d1):
        ss = pd.Timestamp(sun_times(D.date())[1])
        sr2 = pd.Timestamp(sun_times((D + pd.Timedelta(days=1)).date())[0])
        for ax in (ax1, ax2):
            ax.axvspan(ss, sr2, color="0.85", alpha=0.5, lw=0)
    lo = np.nanpercentile(per.R, 1)
    tick = (lo - 0.08 * (per.R.max() - lo), lo - 0.02 * (per.R.max() - lo))
    for an in animals:
        g = per[per.animal == an].sort_values("mid")
        for ab, gg in g.groupby("ab"):
            ax1.plot(gg.mid, gg.R, "-", color=colr[an], lw=1, alpha=0.7)
            dd, nn = gg[gg.phase == "day"], gg[gg.phase == "night"]
            ax1.plot(dd.mid, dd.R, "o", color=colr[an], ms=5, label=an if ab == g.ab.iloc[0] else None)
            ax1.plot(nn.mid, nn.R, "o", mfc="white", mec=colr[an], ms=5)
        for ab in g.ab.unique()[1:]:  # probe-block change: a short tick at the bottom in the animal's colour
            ax1.plot([g[g.ab == ab].mid.min()] * 2, list(tick), color=colr[an], lw=2)
    lab = "verified delta waves" if events == "verified" else "delta waves (all detected)"
    ax1.set_ylabel(f"NREM rate of {lab}\n(events / NREM min)", fontsize=9)
    ax1.set_title("A  Per day: each animal's day period (filled, sunrise-sunset) and night period (open, sunset-sunrise); "
                  "lines join one probe block, a coloured tick at the bottom = new block; grey = night", fontsize=9, loc="left")
    ax1.legend(fontsize=8, ncol=6, frameon=False, loc="upper left")
    ax1.set_ylim(tick[0] - 0.02 * (per.R.max() - lo), per.R.max() * 1.12)
    ax2.plot(wx.t, wx.temp_C, color="0.35", lw=0.7)
    ax2.set_ylabel("outdoor T (degC)", fontsize=9)
    ax2.set_title("B  Outdoor temperature (on-site weather station)", fontsize=9, loc="left")
    ax2.set_xlim(d0 + pd.Timedelta(hours=12), pd.Timestamp("2026-09-11 20:00"))
    ax2.xaxis.set_major_locator(mdates.DayLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    plt.setp(ax1.get_xticklabels(), visible=False)
    for ax in (ax1, ax2):
        ax.tick_params(labelsize=8)
    ax3 = fig.add_subplot(gs[2, 0])
    ax4 = fig.add_subplot(gs[2, 1])
    b = b.copy()
    b["h"] = (b.b0 + pd.Timedelta(minutes=15)).dt.hour
    mu = b.groupby("ab").apply(lambda g: g.n.sum() / g.N.sum())
    b["r_dm"] = b.r - b.ab.map(mu)
    srs = [sun_times(D.date()) for D in pd.date_range(d0, pd.Timestamp("2026-09-11"))]
    sr_h = np.mean([x[0].hour + x[0].minute / 60 for x in srs])
    ss_h = np.mean([x[1].hour + x[1].minute / 60 for x in srs])
    prof = []
    for an in animals:
        g = b[b.animal == an]
        hh = g.groupby("h").apply(lambda x: pd.Series({"R": x.n.sum() / x.N.sum(), "N": x.N.sum(),
                                                       "dm": np.average(x.r_dm, weights=x.N)}))
        hh = hh[hh.N >= 20]
        ax3.plot(hh.index + 0.5, hh.R, "-o", color=colr[an], ms=3, lw=1, label=an)
        prof.append(hh.dm.rename(an))
    P = pd.concat(prof, axis=1)
    m, se, nA = P.mean(1), P.std(1, ddof=1) / np.sqrt(P.notna().sum(1)), P.notna().sum(1)
    keep = nA >= 3
    P, m, se, nA = P[keep], m[keep], se[keep], nA[keep]
    ax4.bar(P.index + 0.5, m, width=0.8, color=["#2b4f8a" if (h < sr_h or h >= ss_h) else "#d98c00" for h in P.index], alpha=0.8)
    ax4.errorbar(P.index + 0.5, m, yerr=se, fmt="none", ecolor="0.2", lw=0.8, capsize=2)
    ax4.axhline(0, color="0.4", lw=0.6)
    th = wx.assign(h=wx.t.dt.hour).groupby("h").temp_C.mean()
    ax5 = ax4.twinx()
    ax5.plot(th.index + 0.5, th.values, color="0.3", lw=1.2, ls="--")
    ax5.set_ylabel("outdoor T, mean by hour (degC, dashed)", fontsize=8)
    for ax in (ax3, ax4):
        ax.axvspan(0, sr_h, color="0.85", alpha=0.5, lw=0)
        ax.axvspan(ss_h, 24, color="0.85", alpha=0.5, lw=0)
        ax.set_xlim(0, 24)
        ax.set_xticks(range(0, 25, 3))
        ax.set_xlabel("clock hour (EDT)", fontsize=9)
        ax.tick_params(labelsize=8)
    ax5.tick_params(labelsize=8)
    ax3.set_ylabel("NREM delta rate (events / NREM min)", fontsize=9)
    ax3.set_title("C  Within a day, per animal (all its days pooled; hours with >= 20 NREM min)", fontsize=9, loc="left")
    ax3.legend(fontsize=7, ncol=3, frameon=False)
    ax4.set_ylabel("rate - the block's mean (events / NREM min)", fontsize=9)
    ax4.set_title("D  Within a day, shared profile: mean +- SEM over animals of the block-demeaned rate (hours with >= 3 animals)",
                  fontsize=9, loc="left")
    what = ("verified delta waves (raw MUA at the peak <= 0.5 x baseline; sessions with the check, FM65)" if events == "verified"
            else "all detected delta waves (no DOWN-state check)")
    extra = "" if mask_h is None else f"; ALSO every handling window + {mask_h:g} h after it (battery rounds, probe handling)"
    fig.suptitle(f"NREM delta-wave rate per NREM time, cohort {COHORT}: {what}; 08-31 -> 09-11 19:40; first 30 min of each file, "
                 f"probe-advance settle windows, user 'noise' sessions excluded{extra}", fontsize=10)
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)
    tab = pd.DataFrame({"mean_dm": m, "sem": se, "animals": nA}).sort_index()
    tab.index.name = "hour"
    return tab


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--events", choices=["verified", "all"], default="verified")
    ap.add_argument("--delta-root", default="Q:/hc997/SocialFieldRat2026/3rd_rat/analysis/delta")
    ap.add_argument("--states-root", default="D:/3rd_rat_spikes/analysis/sleep_server/states_1s_final")
    ap.add_argument("--table", default=str(report_dir(COHORT) / f"ephys_spikes_delta_sessions_{COHORT}.csv"))
    ap.add_argument("--review", default=str(report_dir(COHORT) / f"ephys_spikes_sleep_review_{COHORT}.csv"))
    ap.add_argument("--cohort-yaml", default=str(REPO / f"cohorts/{COHORT}.yaml"))
    ap.add_argument("--mask-after-rounds", type=float, default=None, help="hours after each handling window to drop")
    ap.add_argument("--handling", default=str(REPO / "cv/configs/cohort3_handling_windows.json"))
    a = ap.parse_args()
    from output_paths import run_dir
    rd = report_dir(COHORT)
    suf = ("" if a.events == "verified" else "_all") + (f"_mask{a.mask_after_rounds:g}h" if a.mask_after_rounds is not None else "")
    out = run_dir(f"delta_circadian_{a.events}{suf}", COHORT)
    q = delta_sessions(Path(a.table), Path(a.review), Path(a.cohort_yaml), a.events)
    win = st.settle_windows(Path(a.cohort_yaml))
    if a.mask_after_rounds is not None:
        hw = json.loads(Path(a.handling).read_text(encoding="utf-8"))["windows"]
        win += [(an, pd.Timestamp(w0), pd.Timestamp(w1) + pd.Timedelta(hours=a.mask_after_rounds))
                for an in sorted(q.animal.unique()) for w0, w1, *_ in hw]
    evs, nrs = [], []
    for row in q.itertuples():
        e, n = load_delta_session(row, Path(a.delta_root), Path(a.states_root), st.FEMALES, win, a.events)
        if e is not None:
            evs.append(e)
            nrs.append(n)
    ev, nr = pd.concat(evs, ignore_index=True), pd.concat(nrs, ignore_index=True)
    man = json.loads((rd / f"run_manifest_swr_temperature_{COHORT}.json").read_text())
    wx = pd.read_csv(Path(man["run_dir"]) / "weather_anomaly.csv.gz", parse_dates=["t"])
    refamp = {k: 1.0 for k in ev.groupby(["animal", "block"]).groups}  # placeholder (amplitude unused)
    b = st.build_bins(ev, nr, refamp, wx, "30min")
    hp = st.hour_profile(b)
    per = st.periods(b, hp)
    b.to_csv(out / "bins_30min.csv.gz", index=False)
    fig_path = figure_dir(COHORT) / f"ephys_spikes_delta_rate_day_and_hour{suf}_{COHORT}.png"
    tab = figure(b, per, wx.dropna(subset=["temp_C"]), a.events, fig_path, a.mask_after_rounds)
    tab.round(2).to_csv(rd / f"ephys_spikes_delta_rate_by_hour{suf}_{COHORT}.csv")
    per.to_csv(rd / f"ephys_spikes_delta_rate_by_period{suf}_{COHORT}.csv", index=False)
    write_json(rd / f"run_manifest_delta_circadian{suf}_{COHORT}.json",
               dict(name=f"delta_circadian_{a.events}{suf}", run_dir=str(out), git=git_commit(), sessions=int(len(q)),
                    mask_after_rounds_h=a.mask_after_rounds,
                    events_loaded=int(len(ev)), events_in_bins=int(b.n.sum()), bins=int(len(b)),
                    animals=sorted(b.animal.unique()), figure=str(fig_path), twin_of="swr_temperature.py figure"))
    print(f"{len(q)} sessions, {len(ev)} events loaded, {int(b.n.sum())} in {len(b)} bins ({b.animal.nunique()} animals, "
          f"{b.date.nunique()} dates) -> {fig_path}")
    print(tab.round(1).to_string())


if __name__ == "__main__":
    main()
