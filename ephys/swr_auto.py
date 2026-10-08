"""Automatic SWR detection for cohort 3 (plan: implementation_plan/2026-10-07-swr-detection-automation.md).

Replaces the manual `check` step of the lab's DetectSWR with standardized k-means. This was chosen because, against the
user's manual check runs, it agreed at event F1 0.87-0.92 on two cohort-3 sessions and median ~0.91 on 17 lab sessions.
That matches the user's own day-to-day consistency (~0.92). Waveform classifiers did not do better
(`swr_judge.py evaluate-c3`, results/2026c/ephys_spikes/reports/ephys_spikes_swr_judge_c3_2026c.csv).

Per session (channels per animal x probe block from configs/swr_channels_<c>.yaml):
  1. DetectSWR candidates and features on [ripple, sharp-wave, noise] (`swr_detect.py`, identical to the MATLAB).
  2. bad = the CleanLFP port with the helper's fixed thresholds [8 5].
  3. Labels = the smaller cluster of a 2-cluster k-means on the helper's z, both FITTED ON NREM CANDIDATES ONLY (z
     from NREM non-bad candidates; < 10 min NREM -> all candidates, flagged) and applied to every non-bad candidate as
     the nearest centre. On wake-heavy nights an all-candidate fit drifted to 20-25 % of candidates. A session with
     < 10 min NREM borrows the boundary (z parameters + centres, raw feature units: same channels, same gain) of the
     NREM-fitted session of the same animal x channel block nearest in time (main() runs NREM-rich sessions first);
     the summary records `boundary_fit_on` (nrem | donor | all) and `boundary_from`.
  4. Events = DetectSWR's check-mode localisation + troughs (useSPW = false; rat parameters thresSD [0.25 0.5],
     maxDurSW 0.8, as in the lab's rat runs).
  5. Exclusion flags (user 2026-10-08; nothing is deleted, `excluded` = any of them):
     x_rem (REM second), x_theta (theta/delta in +-0.5 s above the session's NREM 95th percentile), x_moving (head-IMU
     movement above the sleep scorer's own EMG threshold), x_emg_lfp (cross-shank 300-450 Hz correlation = the
     pipeline's EMGFromLFP, one site per shank, above the NREM 95th percentile; `swr_emg.py`). Sessions with < 10 min
     NREM take the theta / EMG thresholds of their boundary donor.
  6. Per event, flags only (nothing is deleted):
     - SwMax / RipMax (DetectSWR's local z = strength; strict/inclusive tiers are cut downstream);
     - sleep state and head-IMU movement (`emg` of the final 1-s states) at the peak second;
     - ripple-band envelope ratio (at the peak / session median) on every shank's own ripple site and on the noise
       column; n_shanks_ripple = shanks with ratio >= 2.
Outputs per session in <out>/<SFxx>/<session>/:
  <session>.swr_events.csv / .npz  the events
  <session>.SWR.evt                Neuroscope events, ms from the first sample
  <session>.swr_summary.json       counts, k-means centres, rates per state
  <session>.swr_qc.png             a scatter + events-per-10-min figure for the user to review
A failed session leaves <out>/_errors/<session>.json, and the exit code is non-zero, so that
`PART=swr run_then_store.sh` copies nothing.

  python ephys/swr_auto.py --animal SF10 --sessions 6_20260906_080449.175 [...] [--all] --out DIR
         [--lfp-root Q:/hc997/SocialFieldRat2026/3rd_rat/analysis/lfp] [--states-root .../states_1s_final] [--workers N]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import swr_detect as sd  # noqa: E402
import swr_emg  # noqa: E402
from swr_channel_scan import XML  # noqa: E402

SR = 1250.0
COHORT = "2026c"
RAT = dict(thresSDswD=(0.25, 0.5), thresSDrip=(0.25, 0.5), maxDurSW=0.8)
MIN_NREM_MIN = 10  # minutes of NREM needed to fit the boundary on NREM candidates
STATE = {0: "unscored", 1: "WAKE", 3: "NREM", 5: "REM"}
HERE = Path(__file__).resolve().parent


def session_start(session: str) -> datetime:
    """Session start from its name <slot>_<YYYYMMDD>_<HHMMSS>.<ms>, WITH the milliseconds (block boundaries are exact)."""
    _, ymd, hms = session.split("_")
    hh, ms = (hms.split(".") + ["0"])[:2]
    return datetime.strptime(ymd + hh, "%Y%m%d%H%M%S").replace(microsecond=int(ms.ljust(3, "0")[:3]) * 1000)


def parse_valid_from(v) -> datetime:
    v = str(v)
    return datetime.strptime(v, "%Y-%m-%d %H:%M:%S.%f" if "." in v else "%Y-%m-%d %H:%M:%S")


def channels_for(cfg: dict, animal: str, session: str) -> dict:
    t0 = session_start(session)
    blocks = [b for b in cfg[animal] if b.get("valid_from") is None or t0 >= parse_valid_from(b["valid_from"])]
    if not blocks:
        raise ValueError(f"{animal} {session}: no channel block")
    return blocks[-1]


def ripple_env(x: np.ndarray, p: sd.Params) -> np.ndarray:
    h1, h2 = sd.makegausslpfir(p.ripBP[0], SR, 6), sd.makegausslpfir(p.ripBP[1], SR, 6)
    pw = sd.makegausslpfir(1 / (np.pi / np.mean(p.ripBP)), SR, 6)
    r = sd.firfilt(x.astype(float), h2)
    return sd.firfilt(np.abs(r - sd.firfilt(r, h1)), pw)


def nrem_minutes(st_path: Path) -> float:
    if not st_path.exists():
        return 0.0
    return float(np.sum(np.load(st_path)["state"] == 3) / 60)


def find_donor(out: Path, animal: str, session: str, blk: dict) -> dict | None:
    """The NREM-fitted summary of the same animal and channel block closest in time to `session`."""
    t0 = session_start(session)
    best, best_dt = None, None
    for f in (out / animal).glob("*/*.swr_summary.json"):
        d = json.loads(f.read_text())
        if d.get("boundary_fit_on") != "nrem" or d.get("channel_block_valid_from") != str(blk.get("valid_from")):
            continue
        dt = abs((session_start(d["session"]) - t0).total_seconds())
        if best is None or dt < best_dt:
            best, best_dt = d, dt
    return best


def kmeans_minority(Z: np.ndarray, seed: int = 0):
    from sklearn.cluster import KMeans
    km = KMeans(2, n_init=10, random_state=seed).fit(Z)
    lab = km.labels_
    k = 0 if np.sum(lab == 0) <= np.sum(lab == 1) else 1
    return lab == k, km.cluster_centers_[k], km.cluster_centers_[1 - k]


def run_session(animal: str, session: str, lfp_root: str, states_root: str, out: str, ch_cfg: dict,
                fit_mode: str = "nrem") -> dict:
    t0 = time.time()
    p = sd.Params(**RAT)
    blk = channels_for(ch_cfg, animal, session)
    if blk.get("skip"):  # a block without channels (e.g. no usable session to choose them): an empty summary, not an error
        out_dir = Path(out) / animal / session
        out_dir.mkdir(parents=True, exist_ok=True)
        summary = dict(animal=animal, session=session, skipped=True, reason=blk.get("source"), n_events=0,
                       kmeans_selected_frac=0.0, boundary_fit_on="none", boundary_from=None, rate_per_min={}, seconds=0.0)
        (out_dir / f"{session}.swr_summary.json").write_text(json.dumps(summary, indent=1))
        return summary
    lfp_path = Path(lfp_root) / animal / f"{session}.lfp"
    nchan = int(json.loads(Path(str(lfp_path) + ".json").read_text())["n_channels"])
    cols3 = [blk["ripple_col"], blk["sharpwave_col"], blk["noise_col"]]
    shank_cols = {int(k): int(v) for k, v in blk["shank_ripple"].items()}
    extra = sorted(set(shank_cols.values()) - set(cols3))
    emg_cols = swr_emg.emg_channels(HERE / "configs/xml" / XML[animal], skip=set(blk.get("exclude_cols", [])))
    allcols = cols3 + extra
    allcols += [c for c in emg_cols if c not in allcols]
    lfp = sd.load_channels(str(lfp_path), nchan, [c + 1 for c in allcols])
    lfp3 = lfp[:, :3]
    swDiff, rp0 = sd.features(lfp3, SR, p)
    ts, swA, rpA = sd.candidates(swDiff, rp0, SR, p)
    bad = sd.in_intervals(ts / SR, sd.clean_lfp_intervals(lfp3[:, 0], SR))
    ok = ~bad
    # candidate state (final 1-s states); the boundary is fitted on NREM candidates only (2026-10-07: on wake-heavy
    # nights the all-candidate k-means drifted to 20-25 % of candidates and 110-150 wake events/min)
    st_path = Path(states_root) / animal / f"{session}.states.npz"
    cstate = np.zeros(ts.size, np.int16)
    if st_path.exists():
        st = np.load(st_path)
        csec = (ts / SR).astype(int)
        ci = np.clip(np.searchsorted(st["ts"], csec), 0, st["ts"].size - 1)
        chit = st["ts"][ci] == csec
        cstate[chit] = st["state"][ci[chit]]
    fit = ok & (cstate == 3)
    X = np.column_stack([swA, rpA])
    donor_from = None
    if fit_mode == "all":
        fit, fit_on = ok, "all"
    elif nrem_minutes(st_path) >= MIN_NREM_MIN:
        fit_on = "nrem"
    else:  # too little NREM: the boundary of the nearest NREM-fitted session of the same animal x channel block
        donor = find_donor(Path(out), animal, session, blk)
        if donor is None:
            fit, fit_on = ok, "all"
        else:
            fit_on, donor_from = "donor", donor["session"]
    if fit_on == "donor":
        b = donor["boundary"]
        mu, sdv = np.array(b["mu"]), np.array(b["sd"])
        c_sel, c_rest = np.array(b["c_sel"]), np.array(b["c_rest"])
        Z = (X - mu) / sdv
    else:
        mu, sdv = X[fit].mean(0), X[fit].std(0, ddof=1)
        Z = (X - mu) / sdv
        m, c_sel, c_rest = kmeans_minority(Z[fit])
    # nearest centre = the k-means boundary (perpendicular bisector), applied to every non-bad candidate
    d_sel = np.sum((Z - c_sel) ** 2, axis=1)
    d_rest = np.sum((Z - c_rest) ** 2, axis=1)
    sel = ok & (d_sel < d_rest)
    fe = dict(swDiff=swDiff, ripPower0=rp0, featureTs=ts, swDiffAll=swA, ripPowerAll=rpA)
    pc = sd.Params(**{**p.__dict__, "useSPW": False})
    ev, loc = sd.events_from_mask(fe, lfp3[:, 0], sel, SR, pc)
    pk = np.clip(np.round(ev["peak"] * SR).astype(int) - 1, 0, swDiff.size - 1)
    # flags: state / IMU at the peak second
    state = np.zeros(pk.size, np.int16)
    emg = np.full(pk.size, np.nan)
    minutes = {}
    if st_path.exists():
        st = np.load(st_path)
        sec = (pk / SR).astype(int)
        i = np.clip(np.searchsorted(st["ts"], sec), 0, st["ts"].size - 1)
        hit = st["ts"][i] == sec
        state[hit], emg[hit] = st["state"][i[hit]], st["emg"][i[hit]]
        minutes = {STATE.get(int(k), str(k)): float(np.sum(st["state"] == k) / 60) for k in np.unique(st["state"])}
    # flags: ripple-band envelope ratio at the peak (max within +-20 ms) per shank site and on the noise column
    lag = np.arange(-25, 26)
    win = np.clip(pk[:, None] + lag[None, :], 0, swDiff.size - 1)
    ratios = {}
    for name, col in [("noise", cols3[2])] + [(f"shank{k}", v) for k, v in sorted(shank_cols.items())]:
        e = ripple_env(lfp[:, allcols.index(col)], p)
        ratios[name] = e[win].max(1) / np.median(e)
    n_sh = np.sum(np.column_stack([ratios[k] for k in ratios if k.startswith("shank")]) >= 2, axis=1)
    # exclusion flags (user 2026-10-08: ripples cannot co-occur with theta; use sleep state, IMU and EMG). Thresholds:
    # theta and LFP-EMG above the 95th percentile of the session's own NREM time (a donor session's if < 10 min NREM),
    # IMU movement above the sleep scorer's own EMG threshold of the session
    E = swr_emg.LfpEmg(lfp[:, [allcols.index(c) for c in emg_cols]])
    t2, e2 = E.trace()
    ev_emg = E.at(pk)
    td = swr_emg.theta_delta_log(lfp3[:, 0])
    ev_theta = td[pk]
    thr_emg = swr_emg.nrem_threshold(t2, e2, st_path)
    thr_theta = swr_emg.nrem_pct_threshold(td, st_path)
    thr_src = "nrem"
    if (thr_emg is None or thr_theta is None) and fit_on == "donor":
        thr_emg = donor.get("thresholds", {}).get("emg_lfp") if thr_emg is None else thr_emg
        thr_theta = donor.get("thresholds", {}).get("theta_delta_log") if thr_theta is None else thr_theta
        thr_src = f"donor {donor_from}"
    thr_imu = float(np.load(st_path)["thresholds"][1]) if st_path.exists() else None
    x_rem = state == 5
    x_theta = ev_theta > thr_theta if thr_theta is not None else np.zeros(pk.size, bool)
    x_moving = emg > thr_imu if thr_imu is not None else np.zeros(pk.size, bool)
    x_emg = ev_emg > thr_emg if thr_emg is not None else np.zeros(pk.size, bool)
    excluded = x_rem | x_theta | x_moving | x_emg
    out_dir = Path(out) / animal / session
    out_dir.mkdir(parents=True, exist_ok=True)
    cols = dict(start_s=ev["start"], stop_s=ev["stop"], peak_s=ev["peak"], duration_ms=(ev["stop"] - ev["start"]) * 1000,
                amplitude=ev["amplitude"], frequency_hz=ev["frequency"], SwMax_z=ev["SwMax"], RipMax_z=ev["RipMax"],
                state=[STATE.get(int(s), str(s)) for s in state], imu_emg=emg, n_shanks_ripple=n_sh,
                emg_lfp=ev_emg, theta_delta_log=ev_theta, x_rem=x_rem, x_theta=x_theta, x_moving=x_moving, x_emg_lfp=x_emg,
                excluded=excluded,
                **{f"env_ratio_{k}": v for k, v in ratios.items()})
    import pandas as pd
    df = pd.DataFrame(cols)
    out_csv = df.copy()  # times to 0.1 ms (a global 5-significant-digit format loses the seconds), other floats 5 digits
    for c in out_csv.columns:
        if c.endswith("_s"):
            out_csv[c] = out_csv[c].round(4)
        elif out_csv[c].dtype.kind == "f":
            out_csv[c] = out_csv[c].map(lambda x: float(format(x, ".5g")))
    out_csv.to_csv(out_dir / f"{session}.swr_events.csv", index=False)
    np.savez_compressed(out_dir / f"{session}.swr_events.npz", **{k: np.asarray(v) for k, v in cols.items()},
                        candidate_index=ev["cand"])
    with open(out_dir / f"{session}.SWR.evt", "w") as f:  # Neuroscope: ms from the first sample (DetectSWR time - 1 sample)
        for a, b, c in zip(ev["start"], ev["peak"], ev["stop"]):
            f.write(f"{(a - 1 / SR) * 1000:.1f}\tstart\n{(b - 1 / SR) * 1000:.1f}\tpeak\n{(c - 1 / SR) * 1000:.1f}\tstop\n")
    by_state = {s: int(np.sum(df.state == s)) for s in sorted(set(df.state))}
    summary = dict(animal=animal, session=session, session_start=str(session_start(session)), channels_0based=dict(
        ripple=cols3[0], sharpwave=cols3[1], noise=cols3[2], shank_ripple=shank_cols), channel_block=blk.get("source"),
        params={**pc.__dict__}, n_samples=int(swDiff.size), hours=round(swDiff.size / SR / 3600, 3),
        n_candidates=int(ts.size), n_bad=int(bad.sum()), boundary_fit_on=fit_on, boundary_from=donor_from,
        n_fit_candidates=int(fit.sum()) if fit_on != "donor" else 0, nrem_minutes=round(nrem_minutes(st_path), 1),
        channel_block_valid_from=str(blk.get("valid_from")),
        boundary=dict(mu=np.round(mu, 6).tolist(), sd=np.round(sdv, 6).tolist(), c_sel=np.round(c_sel, 6).tolist(),
                      c_rest=np.round(c_rest, 6).tolist()),
        kmeans_selected=int(sel.sum()),
        kmeans_selected_frac=round(float(sel[ok].mean()), 5), kmeans_centre_selected_z=c_sel.round(3).tolist(),
        kmeans_centre_rest_z=c_rest.round(3).tolist(), n_events=int(len(df)), localisation_rejects=loc.reasons,
        state_minutes={k: round(v, 1) for k, v in minutes.items()}, events_by_state=by_state,
        rate_per_min={s: round(by_state.get(s, 0) / minutes[s], 3) for s in minutes if minutes[s] > 0},
        median_SwMax_z=round(float(df.SwMax_z.median()), 3) if len(df) else None,
        median_RipMax_z=round(float(df.RipMax_z.median()), 3) if len(df) else None,
        median_noise_env_ratio=round(float(np.median(ratios["noise"])), 3) if len(df) else None,
        frac_events_all_shanks=round(float(np.mean(n_sh == len(shank_cols))), 3) if len(df) else None,
        emg_channels_0based=emg_cols,
        thresholds=dict(emg_lfp=thr_emg, theta_delta_log=thr_theta, imu_emg=thr_imu, source=thr_src),
        n_excluded=int(excluded.sum()), excluded_by=dict(rem=int(x_rem.sum()), theta=int(x_theta.sum()),
                                                         moving=int(x_moving.sum()), emg_lfp=int(x_emg.sum())),
        kept_by_state={st_: int(np.sum((df.state == st_) & ~df.excluded)) for st_ in sorted(set(df.state))},
        kept_rate_per_min={st_: round(int(np.sum((df.state == st_) & ~df.excluded)) / minutes[st_], 3)
                           for st_ in minutes if minutes[st_] > 0},
        seconds=round(time.time() - t0, 1), lfp=str(lfp_path), states=str(st_path) if st_path.exists() else None)
    (out_dir / f"{session}.swr_summary.json").write_text(json.dumps(summary, indent=1, default=float))
    qc_figure(out_dir / f"{session}.swr_qc.png", session, animal, Z, ok, sel, df, st_path)
    return summary


def qc_figure(path, session, animal, Z, ok, sel, df, st_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rng = np.random.default_rng(0)
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.5), gridspec_kw=dict(width_ratios=[1, 2]))
    i0 = np.flatnonzero(ok & ~sel)
    i0 = rng.choice(i0, min(i0.size, 40000), replace=False)
    ax[0].scatter(Z[i0, 0], Z[i0, 1], s=1, c="0.7", rasterized=True)
    ax[0].scatter(Z[sel, 0], Z[sel, 1], s=1, c="tab:green", rasterized=True)
    ax[0].set_xlim(np.percentile(Z[ok, 0], [0.05, 99.95]))
    ax[0].set_ylim(np.percentile(Z[ok, 1], [0.05, 99.95]))
    ax[0].set_xlabel("swDiff (z)")
    ax[0].set_ylabel("ripPower (z)")
    ax[0].set_title("candidates: k-means selected (green)", fontsize=9)
    if st_path.exists():
        st = np.load(st_path)
        nrem = st["state"] == 3
        e = np.diff(np.concatenate([[0], nrem.astype(int), [0]]))
        for a, b in zip(np.flatnonzero(e == 1), np.flatnonzero(e == -1)):
            ax[1].axvspan(st["ts"][a] / 3600, st["ts"][b - 1] / 3600, color="tab:blue", alpha=0.12, lw=0)
    if len(df):
        h, edges = np.histogram(df.peak_s / 3600, bins=np.arange(0, df.peak_s.max() / 3600 + 1 / 6, 1 / 6))
        ax[1].step(edges[:-1], h / 10, where="post", color="k")
    ax[1].set_xlabel("session time (h)")
    ax[1].set_ylabel("events / min (10-min bins)")
    ax[1].set_title("NREM shaded", fontsize=9)
    fig.suptitle(f"{animal} {session}: {len(df)} events", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)


def _one(args):
    animal, session, lfp_root, states_root, out, ch_cfg, fit_mode = args
    try:
        return session, run_session(animal, session, lfp_root, states_root, out, ch_cfg, fit_mode), None
    except Exception:
        return session, None, traceback.format_exc()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--animal", required=True)
    ap.add_argument("--sessions", nargs="*")
    ap.add_argument("--all", action="store_true", help="every session of the animal that has an LFP")
    ap.add_argument("--min-minutes", type=float, default=10.0, help="with --all: skip shorter sessions (blips, test records)")
    ap.add_argument("--lfp-root", default="D:/3rd_rat_spikes/analysis/lfp")
    ap.add_argument("--states-root", default="D:/3rd_rat_spikes/analysis/sleep_server/states_1s_final")
    ap.add_argument("--channels", default=str(HERE / f"configs/swr_channels_{COHORT}.yaml"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--fit", choices=["nrem", "all"], default="nrem",
                    help="fit the k-means boundary on NREM candidates (default) or on all candidates")
    a = ap.parse_args()
    ch_cfg = yaml.safe_load(open(a.channels))
    sessions = list(a.sessions or [])
    if a.all:
        sessions = []
        for f in sorted((Path(a.lfp_root) / a.animal).glob("*.lfp")):
            dur = json.loads(Path(str(f) + ".json").read_text()).get("duration_s", 0)
            if dur >= 60 * a.min_minutes:
                sessions.append(f.name[:-4])
            else:
                print(f"skip {f.name[:-4]}: {dur / 60:.1f} min < --min-minutes {a.min_minutes}", flush=True)
    todo = [s for s in sessions if a.redo or not (Path(a.out) / a.animal / s / f"{s}.swr_summary.json").exists()]
    print(f"{a.animal}: {len(todo)} of {len(sessions)} sessions to run", flush=True)
    rich = [s for s in todo if nrem_minutes(Path(a.states_root) / a.animal / f"{s}.states.npz") >= MIN_NREM_MIN]
    poor = [s for s in todo if s not in rich]
    n_err = 0
    err_dir = Path(a.out) / "_errors"
    for phase, group in (("NREM-rich", rich), ("low-NREM (borrowed boundary)", poor)):
        if not group:
            continue
        print(f"{phase}: {len(group)} sessions", flush=True)
        jobs = [(a.animal, s, a.lfp_root, a.states_root, a.out, ch_cfg, a.fit) for s in group]
        with ProcessPoolExecutor(max_workers=max(a.workers, 1)) as ex:
            for fut in as_completed([ex.submit(_one, j) for j in jobs]):
                s, summ, err = fut.result()
                if err:
                    n_err += 1
                    err_dir.mkdir(parents=True, exist_ok=True)
                    (err_dir / f"{a.animal}_{s}.json").write_text(json.dumps(dict(animal=a.animal, session=s, error=err), indent=1))
                    print(f"FAIL {s}: {err.splitlines()[-1]}", flush=True)
                else:
                    src = summ["boundary_fit_on"] + (f" <- {summ['boundary_from']}" if summ["boundary_from"] else "")
                    print(f"ok   {s}: {summ['n_events']} events, selected {100*summ['kmeans_selected_frac']:.2f} %, "
                          f"boundary {src}, rates {summ['rate_per_min']} ({summ['seconds']:.0f} s)", flush=True)
    sys.exit(1 if n_err else 0)


if __name__ == "__main__":
    main()
