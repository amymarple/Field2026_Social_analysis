r"""Sleep scoring pass 2: per-animal rescaling and thresholds on the raw metrics of the fixed-channel scores
(plan: implementation_plan/2026-10-07-sleep-fixed-thresholds.md).

Input: a sleep tree with variant `imu_fixch` (score_sleep.py; fixed per-animal channels) whose session folders hold the
scorer's state file and <session>.SleepScoreRaw.npz (raw sw / th / emg on the stored t_clus grid, captured just before the
scorer's per-session min-max rescaling). Uses PreprocessPipeline's own functions (imported unmodified) for the threshold
search, the classification and every post-processing step.

Steps:
  1. Reproduction gate. Per session: rescale the raw metrics with the session's own min-max (_norm_to_range), take the
     session's stored thresholds, run classify_chain -> must equal the stored states epoch for epoch; the threshold search
     (dip_thresholds) on the same rescaled metrics must give the stored thresholds. Any mismatch stops (unless --force).
  2. Per-animal rescaling, for metric m of animal a, pooled over its POOL sessions (scored, not user `noise`, not tagged
     SF12_contact_failing, >= 0.5 h):  m~ = clip((m - q_0.001) / (q_0.999 - q_0.001), 0, 1).
  3. Per-animal thresholds = the scorer's own histogram-dip search (same bin loops, EMG alpha 1, theta on non-moving
     epochs) on the pooled rescaled metrics.
  4. Reclassify every session (pooled or not) with its animal's scale + thresholds through classify_chain, then the
     imu_remclean REM rules (score_sleep.remclean_states) -> variant `pass2_remclean`: the scorer's state file with the new
     idx / ints / metrics / thresholds, theta epochs + episodes + figures by the scorer's own functions, score_sleep.json,
     the review copy.
  5. Reports: the gate, the per-animal scale + thresholds, a change table vs imu_remclean (kappa, delta REM / NREM share),
     and the probe-advance check (the raw-metric quantiles before / after each advance, as % of the pooled range).

Usage (server or local): python ephys/sleep_pass2.py --cohort 2026c --src <sleep root> [--sessions A:S ...] [--force]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat

sys.path.insert(0, str(Path(__file__).parent))
from score_sleep import IMU_STILL_THR, STATENAMES, load_imu, pipeline_module, remclean_states, session_struct, summarize  # noqa: E402
from _common import git_commit, report_dir, resolve_cohort, utc_now_iso  # noqa: E402

Q_LO, Q_HI = 0.001, 0.999
MIN_LEN = 6.0                    # the scorer's state_min_state_length
BASE, OUT = "imu_fixch", "pass2_remclean"


def dip_thresholds(ss, bb: np.ndarray, th: np.ndarray, emg: np.ndarray, emg_alpha: float = 1.0) -> dict:
    """The scorer's histogram-dip threshold search (state_scoring.py _compute_sleep_state, lines 1925-1974 at eb3dad4)."""
    numpeaks, numbins = 1, 12
    while numpeaks != 2 and numbins <= 200:
        swhist, swbins = ss._hist_counts_centers(bb, numbins)
        sw_locs = ss._find_peak_locs_for_threshold(swhist, mode="top2", prepend_zero=False)
        numpeaks, numbins = int(sw_locs.size), numbins + 1
    swthresh = ss._find_hist_dip_threshold_between(swhist, swbins, sw_locs)
    nrem_times = bb > swthresh
    numpeaks, numbins = 1, 12
    while numpeaks != 2 and numbins <= 200:
        emghist, emgbins = ss._hist_counts_centers(emg, numbins)
        emg_locs = ss._find_peak_locs_for_threshold(emghist, mode="leftmost2", prepend_zero=True)
        numpeaks, numbins = int(emg_locs.size), numbins + 1
    emgthresh = float(np.clip(ss._find_hist_dip_threshold_between(emghist, emgbins, emg_locs) * float(emg_alpha), 0.0, 1.0))
    mov_times = (bb < swthresh) & (emg > emgthresh)
    numpeaks, numbins = 1, 12
    th_for = th[~mov_times] if np.any(~mov_times) else th
    while numpeaks != 2 and numbins <= 25:
        thhist, thbins = ss._hist_counts_centers(th_for, numbins)
        th_locs = ss._find_peak_locs_for_threshold(thhist, mode="top2", prepend_zero=False)
        numpeaks, numbins = int(th_locs.size), numbins + 1
    if numpeaks != 2:
        numbins = 12
        th_for = th[(~nrem_times) & (~mov_times)] if np.any((~nrem_times) & (~mov_times)) else th
        while numpeaks != 2 and numbins <= 25:
            thhist, thbins = ss._hist_counts_centers(th_for, numbins)
            th_locs = ss._find_peak_locs_for_threshold(thhist, mode="top2", prepend_zero=False)
            numpeaks, numbins = int(th_locs.size), numbins + 1
    ththresh = ss._find_hist_dip_threshold_between(thhist, thbins, th_locs) if numpeaks == 2 else 0.0
    return {"swthresh": float(swthresh), "EMGthresh": emgthresh, "THthresh": float(ththresh),
            "swhist": swhist, "swhistbins": swbins, "EMGhist": emghist, "EMGhistbins": emgbins, "THhist": thhist, "THhistbins": thbins}


def classify_chain(ss, bb, th, emg, t_clus, thr: dict, use_emg_nrem: bool = True, min_len: float = MIN_LEN):
    """The scorer's classification + post-processing (lines 1976-2032 at eb3dad4; block_wake_to_rem off = the default)."""
    nrem, rem, wake, forced = ss._classify_sleep_states(broadband=bb, thratio=th, emg=emg, swthresh=thr["swthresh"],
                                                        emgthresh=thr["EMGthresh"], ththresh=thr["THthresh"], use_emg_nrem=use_emg_nrem)
    forced_int = ss._intervals_from_mask(forced, t_clus) if use_emg_nrem and np.any(forced) else np.empty((0, 2))
    states = np.zeros(t_clus.size, np.uint8)
    states[wake], states[nrem], states[rem] = 1, 3, 5
    ints = ss._idx_to_int(states=states, timestamps=t_clus, statenames=STATENAMES)
    idx = ss._int_to_idx(ints=ints, statenames=STATENAMES, sf=1.0)
    states = np.asarray(idx["states"], np.uint8).reshape(-1)
    ts = np.asarray(idx["timestamps"], np.float64).reshape(-1)
    states = ss._apply_minimum_state_durations(states, ts, STATENAMES, min_len)
    if np.asarray(forced_int).size:
        ss._assign_state_on_intervals(states, ts, forced_int, 1)
        states = ss._apply_minimum_state_durations(states, ts, STATENAMES, min_len)
    return ss._fill_unassigned_states(states), ts


def load_session(src: Path, animal: str, session: str) -> dict | None:
    bp = src / BASE / animal / session
    raw = bp / f"{session}.SleepScoreRaw.npz"
    if not raw.exists():
        return None
    st = loadmat(bp / f"{session}.SleepState.states.mat", simplify_cells=True)["SleepState"]
    m = st["detectorinfo"]["detectionparms"]["SleepScoreMetrics"]
    with np.load(raw) as z:
        d = {k: z[k] for k in z.files}
    d.update({"animal": animal, "session": session, "bp": bp, "st": st,
              "stored_states": np.asarray(st["idx"]["states"]).reshape(-1), "stored_ts": np.asarray(st["idx"]["timestamps"], float).reshape(-1),
              "stored_thr": {k: float(m["histsandthreshs"][k]) for k in ("swthresh", "EMGthresh", "THthresh")},
              "stored_norm": {k: np.asarray(m[k], float).reshape(-1) for k in ("broadbandSlowWave", "thratio", "EMG")}})
    return d


_SS = None


def _ss(pipeline_root):
    global _SS
    if _SS is None:
        _SS = pipeline_module(pipeline_root)
    return _SS


def gate_one(job: dict) -> dict:
    ss = _ss(job["pipeline_root"])[0]
    d = load_session(Path(job["src"]), job["animal"], job["session"])
    bb, th, emg = (ss._norm_to_range(d[k], 0.0, 1.0) for k in ("sw", "th", "emg"))
    same_norm = all(np.allclose(x, d["stored_norm"][k], rtol=0, atol=1e-12) for x, k in
                    zip((bb, th, emg), ("broadbandSlowWave", "thratio", "EMG")))
    thr_found = dip_thresholds(ss, bb, th, emg)
    same_thr = all(abs(thr_found[k] - d["stored_thr"][k]) < 1e-12 for k in d["stored_thr"])
    states, ts = classify_chain(ss, bb, th, emg, d["t_clus"], d["stored_thr"])
    n = min(len(states), len(d["stored_states"]))
    return {"animal": d["animal"], "session": d["session"], "same_rescaled_metrics": same_norm, "same_thresholds": same_thr,
            "same_states": len(states) == len(d["stored_states"]) and np.array_equal(states, d["stored_states"]),
            "n_epochs": len(d["stored_states"]), "n_diff": int(np.sum(states[:n] != d["stored_states"][:n]))}


def finish_one(job: dict) -> dict:
    """Reclassify one session with its animal's scale + thresholds, REM rules, write the pass-2 outputs."""
    ss, Cfg, pp_commit, _ = _ss(job["pipeline_root"])
    src, imu_root, c = Path(job["src"]), Path(job["imu_root"]), job["cohort"]
    d = load_session(src, job["animal"], job["session"])
    an, se = d["animal"], d["session"]
    t0 = time.time()
    b, thr = job["bounds"], job["thr"]
    bb, th, emg = (np.clip((d[k] - b[k][0]) / (b[k][1] - b[k][0]), 0.0, 1.0) for k in ("sw", "th", "emg"))
    states, ts = classify_chain(ss, bb, th, emg, d["t_clus"], thr)
    imu = load_imu(imu_root, an, se)
    states, counts = remclean_states(ss, states, ts, imu["vedba_1s"], IMU_STILL_THR[an])
    bp = src / OUT / an / se
    (bp / "StateScoreFigures").mkdir(parents=True, exist_ok=True)
    for name in (f"{se}.session.mat", f"{se}.EMGFromLFP.LFP.mat", f"{se}.SleepScoreLFP.LFP.mat", f"{se}.lfp"):
        if (d["bp"] / name).exists() and not (bp / name).exists():
            try:
                os.link(d["bp"] / name, bp / name)       # never written by this script or the editor
            except OSError:
                shutil.copy2(d["bp"] / name, bp / name)
    st = d["st"]
    st["idx"]["states"], st["idx"]["timestamps"] = states.reshape(-1, 1), ts.reshape(-1, 1)
    for k, v in ss._idx_to_int(states, ts, STATENAMES).items():
        st["ints"][k] = v
    m = st["detectorinfo"]["detectionparms"]["SleepScoreMetrics"]
    m["broadbandSlowWave"], m["thratio"], m["EMG"] = bb.reshape(-1, 1), th.reshape(-1, 1), emg.reshape(-1, 1)
    h = m["histsandthreshs"]
    for k in ("swthresh", "EMGthresh", "THthresh"):
        h[k] = thr[k]
    for x, key in ((bb, "sw"), (emg, "EMG"), (th, "TH")):
        hh, bins = ss._hist_counts_centers(x, 20)
        h[f"{key}hist" if key != "sw" else "swhist"], h[f"{key}histbins" if key != "sw" else "swhistbins"] = hh, bins
    st["detectorinfo"]["pass2"] = {"base_variant": BASE, "driver": "ephys/sleep_pass2.py", "git_commit": git_commit(),
                                   "rescale": f"per animal, pooled q{Q_LO}..q{Q_HI}", "remclean": counts}
    ss._append_theta_epochs(st, bp, se)                        # writes the state file
    ss._states_to_episodes(st, bp, se, microarousal_sec=float(Cfg(basepath=bp).state_microarousal_sec), overwrite=True)
    ss._save_state_figures(bp, se, st, overwrite=True)
    info = summarize(bp, an, se, OUT, imu_root, pp_commit, session_struct(c, an)["_xml"], t0,
                     extra={"derived_from": BASE, **counts, **{f"{k}_animal": thr[k] for k in ("swthresh", "EMGthresh", "THthresh")}})
    old = src / "imu_remclean" / an / se / f"{se}.SleepState.states.mat"
    row = {"animal": an, "session": se, "frac_rem_pass2": info["frac_rem"], "frac_nrem_pass2": info["frac_nrem"]}
    if old.exists():
        so = np.asarray(loadmat(old, simplify_cells=True)["SleepState"]["idx"]["states"]).reshape(-1)
        row.update({"kappa_vs_imu_remclean": round(kappa(so, states), 4), "frac_rem_old": round(float(np.mean(so == 5)), 4),
                    "frac_nrem_old": round(float(np.mean(so == 3)), 4)})
        row["d_rem_pp"] = round(100 * (row["frac_rem_pass2"] - row["frac_rem_old"]), 2)
        row["d_nrem_pp"] = round(100 * (row["frac_nrem_pass2"] - row["frac_nrem_old"]), 2)
    return row


def pool_map(fn, jobs: list[dict], workers: int) -> list:
    if workers <= 1:
        return [fn(j) for j in jobs]
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(workers) as ex:
        return list(ex.map(fn, jobs, chunksize=1))


def load_raw(src: Path, animal: str, session: str) -> dict | None:
    raw = src / BASE / animal / session / f"{session}.SleepScoreRaw.npz"
    if not raw.exists():
        return None
    with np.load(raw) as z:
        return {"animal": animal, "session": session, **{k: z[k] for k in z.files}}


def kappa(a: np.ndarray, b: np.ndarray) -> float:
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    m = (a > 0) & (b > 0)
    po = np.mean(a[m] == b[m])
    pe = sum(np.mean(a[m] == k) * np.mean(b[m] == k) for k in (1, 3, 5))
    return float((po - pe) / max(1e-9, 1 - pe))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cohort", default=None)
    ap.add_argument("--src", required=True, help="sleep tree holding imu_fixch (and imu_remclean for the change table)")
    ap.add_argument("--imu-root", required=True, help="IMU inputs (full make_imu layout or the bundles)")
    ap.add_argument("--sessions", nargs="*", default=[])
    ap.add_argument("--pipeline-root", default=None)
    ap.add_argument("--force", action="store_true", help="continue past a reproduction mismatch")
    ap.add_argument("--report-name", default="sleep_pass2")
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args()
    c = resolve_cohort(a.cohort)
    src, imu_root = Path(a.src), Path(a.imu_root)
    ss, Cfg, pp_commit, _ = pipeline_module(a.pipeline_root)
    rd = report_dir(c)
    specs = [s.split(":") for s in a.sessions] or [[p.parent.parent.name, p.parent.name] for p in sorted((src / BASE).glob("*/*/*.SleepScoreRaw.npz"))]
    S = [d for d in (load_raw(src, an, se) for an, se in specs) if d is not None]      # light: raw metrics only
    print(f"{len(S)} sessions with raw metrics in {src / BASE}", flush=True)

    # 1. reproduction gate
    base_job = {"src": str(src), "imu_root": str(imu_root), "cohort": c, "pipeline_root": a.pipeline_root}
    gate = pool_map(gate_one, [{**base_job, "animal": d["animal"], "session": d["session"]} for d in S], a.workers)
    gate = pd.DataFrame(gate)
    gate.to_csv(rd / f"ephys_spikes_{a.report_name}_gate_{c}.csv", index=False)
    ok = gate[["same_rescaled_metrics", "same_thresholds", "same_states"]].all(axis=1)
    print(f"reproduction gate: {int(ok.sum())}/{len(gate)} sessions reproduce the scorer exactly", flush=True)
    if not ok.all() and not a.force:
        print(gate[~ok].to_string())
        raise SystemExit("reproduction gate failed - stop (see the gate CSV)")

    # 2-3. per-animal scale + thresholds from the pooled sessions
    rv = pd.read_csv(rd / f"ephys_spikes_sleep_review_{c}.csv")
    rv["pool"] = (rv.verdict != "noise") & ~rv.tags.fillna("").str.contains("SF12_contact_failing") & (rv.duration_h >= 0.5)
    pool = set(map(tuple, rv[rv.pool][["animal", "session"]].to_numpy()))
    scale = {}
    for an in sorted({d["animal"] for d in S}):
        Ds = [d for d in S if d["animal"] == an and (an, d["session"]) in pool]
        if not Ds:
            continue
        bounds = {k: (float(np.quantile(np.concatenate([d[k] for d in Ds]), Q_LO)),
                      float(np.quantile(np.concatenate([d[k] for d in Ds]), Q_HI))) for k in ("sw", "th", "emg")}

        def resc(x, k, b=bounds):
            return np.clip((x - b[k][0]) / (b[k][1] - b[k][0]), 0.0, 1.0)
        pooled = {k: np.concatenate([resc(d[k], k) for d in Ds]) for k in ("sw", "th", "emg")}
        thr = dip_thresholds(ss, pooled["sw"], pooled["th"], pooled["emg"])
        scale[an] = {"bounds": bounds, "thr": thr, "n_sessions": len(Ds), "pooled_h": len(pooled["sw"]) / 3600}
        print(f"{an}: {len(Ds)} sessions, {scale[an]['pooled_h']:.0f} h; thresholds SW {thr['swthresh']:.3f} EMG {thr['EMGthresh']:.3f} "
              f"TH {thr['THthresh']:.3f}", flush=True)
    rows = [{"animal": an, "n_sessions": s["n_sessions"], "pooled_h": round(s["pooled_h"], 1),
             **{f"{k}_lo": s["bounds"][k][0] for k in ("sw", "th", "emg")}, **{f"{k}_hi": s["bounds"][k][1] for k in ("sw", "th", "emg")},
             **{k: s["thr"][k] for k in ("swthresh", "EMGthresh", "THthresh")}} for an, s in scale.items()]
    pd.DataFrame(rows).to_csv(rd / f"ephys_spikes_{a.report_name}_scale_{c}.csv", index=False)

    # 4. reclassify, REM rules, outputs
    jobs = [{**base_job, "animal": d["animal"], "session": d["session"], "bounds": scale[d["animal"]]["bounds"],
             "thr": {k: scale[d["animal"]]["thr"][k] for k in ("swthresh", "EMGthresh", "THthresh")}} for d in S if d["animal"] in scale]
    changes = pool_map(finish_one, jobs, a.workers)
    ch = pd.DataFrame(changes)
    ch["review"] = (ch.get("kappa_vs_imu_remclean", pd.Series(1.0, index=ch.index)) < 0.9) | (ch.get("d_rem_pp", pd.Series(0.0, index=ch.index)).abs() > 2)
    ch.to_csv(rd / f"ephys_spikes_{a.report_name}_changes_{c}.csv", index=False)
    print(f"changed materially (kappa < 0.9 or |d REM| > 2 pp): {int(ch.review.sum())}/{len(ch)}", flush=True)

    # 5. probe-advance check: raw-metric quantiles before / after each advance, as % of the pooled range
    from _common import ephys_block
    adv = []
    for mv in ephys_block(c).get("probe_moves") or []:
        an, t = mv["animal"], pd.Timestamp(mv["time"])
        if an not in scale:
            continue
        starts = {r.session: pd.Timestamp(r.start_local) for r in rv[rv.animal == an].itertuples()}
        pre = [d for d in S if d["animal"] == an and (an, d["session"]) in pool and starts.get(d["session"], t) < t]
        post = [d for d in S if d["animal"] == an and (an, d["session"]) in pool and starts.get(d["session"], t) >= t]
        if not pre or not post:
            continue
        for k in ("sw", "th"):
            lo, hi = scale[an]["bounds"][k]
            q = {nm: np.quantile(np.concatenate([d[k] for d in grp]), [0.1, 0.5, 0.9]) for nm, grp in (("pre", pre), ("post", post))}
            adv.append({"animal": an, "advance": mv["time"], "metric": k, **{f"shift_q{int(p * 100)}_pct_of_range":
                        round(100 * (q["post"][i] - q["pre"][i]) / (hi - lo), 1) for i, p in enumerate((0.1, 0.5, 0.9))}})
    pd.DataFrame(adv).to_csv(rd / f"ephys_spikes_{a.report_name}_probe_advance_check_{c}.csv", index=False)
    (rd / f"run_manifest_{a.report_name}_{c}.json").write_text(json.dumps(
        {"src": str(src), "base": BASE, "out_variant": OUT, "driver": "ephys/sleep_pass2.py", "git_commit": git_commit(),
         "scorer": f"PreprocessPipeline {pp_commit}", "q": [Q_LO, Q_HI], "written_utc": utc_now_iso()}, indent=2), encoding="utf-8")
    print("done", flush=True)


if __name__ == "__main__":
    main()
