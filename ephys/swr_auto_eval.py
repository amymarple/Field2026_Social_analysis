"""Can the manual `check` step of DetectSWR be replaced by an automatic classifier? Evaluated on the user's reference
sessions (`configs/swr_reference_sessions.yaml`; plan implementation_plan/2026-10-07-swr-detection-automation.md).

Per session (faithful port `swr_detect.py`, the session's own DetectSWR parameters):
  candidates  (swDiff, ripPower) per 40-ms window, identical to MATLAB
  bad_auto    CleanLFP port with the helper's fixed thresholds [8 5] on the ripple channel (no keyboard step)
  methods     each yields a candidate mask, then the same localisation + trough step as the user's check runs:
    user_replay          the user's idx1 (sanity: must reproduce the final events)
    detectswr_auto       DetectSWR without check: k-means on raw features + percentile thresholds + useSPW = true
    kmeans_raw           the raw k-means minority cluster minus bad_auto, check path (useSPW = false)
    kmeans_z             k-means on standardised features (mean/SD over non-bad candidates), check path
    gmm_z                2-component full-covariance Gaussian mixture on the same features, check path
    clf_loso             gradient-boosted classifier on per-session robust-normalised features, trained on the OTHER
                         sessions' idx1 labels (leave-one-session-out), check path
  metrics     candidate level vs idx1 (where labelled) and event level vs the user's final events (peak match +-10 ms)

Writes the run to $FIELD2026_ANALYSIS_OUT_ROOT/2026c/swr_auto_eval_<ts>/ (candidate caches, per-session events, figures),
the report + CSV to results/2026c/ephys_spikes/reports/ and figures to .../figures/.

  python ephys/swr_auto_eval.py [--sessions NAME ...] [--config ephys/configs/swr_reference_sessions.yaml]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import swr_detect as sd  # noqa: E402
from _common import figure_dir, git_commit, report_dir, utc_now_iso, write_json  # noqa: E402
from output_paths import run_dir  # noqa: E402

COHORT = "2026c"
SR = 1250.0
MATCH_TOL = 0.010  # s
METHODS = ["user_replay", "detectswr_auto", "kmeans_raw", "kmeans_z", "gmm_z", "clf_loso"]


def robust_norm(sw, rp, ok):
    """Per-session robust normalisation over non-bad candidates: (x - median) / (1.4826 MAD)."""
    out = []
    for x in (sw, rp):
        med = np.median(x[ok])
        mad = 1.4826 * np.median(np.abs(x[ok] - med))
        out.append((x - med) / mad)
    return np.column_stack(out)


def zfeat(sw, rp, ok):
    X = np.column_stack([sw, rp])
    return (X - X[ok].mean(0)) / X[ok].std(0, ddof=1)


def minority_kmeans(X, seed=0):
    from sklearn.cluster import KMeans
    lab = KMeans(n_clusters=2, n_init=10, random_state=seed).fit_predict(X)
    return lab == (0 if np.sum(lab == 0) <= np.sum(lab == 1) else 1)


def gmm_mask(X, seed=0):
    from sklearn.mixture import GaussianMixture
    g = GaussianMixture(2, covariance_type="full", n_init=3, random_state=seed).fit(X)
    rip = int(np.argmax(g.means_[:, 1]))
    return g.predict_proba(X)[:, rip] > 0.5


def prf(pred, ref):
    tp = int(np.sum(pred & ref))
    p = tp / max(int(pred.sum()), 1)
    r = tp / max(int(ref.sum()), 1)
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def event_prf(ev_peaks, ref_peaks):
    a, b = np.sort(ref_peaks), np.sort(ev_peaks)
    ia, ib = sd.match_peaks(a, b, MATCH_TOL)
    p = ia.size / max(b.size, 1)
    r = ia.size / max(a.size, 1)
    return p, r, (2 * p * r / (p + r) if p + r else 0.0), int(ia.size)


def load_session(root: Path, s: dict, cache_dir: Path):
    d = root / s["dir"]
    p = sd.Params(**{k: (tuple(v) if isinstance(v, list) else v) for k, v in s.get("params", {}).items()})
    lfp_path = d / f"{s['base']}.lfp"
    t0 = time.time()
    lfp3 = sd.load_channels(str(lfp_path), s["nchan"], s["channels"])
    swDiff, rp0 = sd.features(lfp3, SR, p)
    ts, swA, rpA = sd.candidates(swDiff, rp0, SR, p)
    bad_auto = sd.in_intervals(ts / SR, sd.clean_lfp_intervals(lfp3[:, 0], SR))
    sess = dict(name=s["name"], params=p, lfp_rip=lfp3[:, 0], fe=dict(swDiff=swDiff, ripPower0=rp0, featureTs=ts,
                swDiffAll=swA, ripPowerAll=rpA), bad_auto=bad_auto, ctx=sd.trough_context(lfp3[:, 0], SR, p))
    if s.get("scoring"):
        sc = sd.load_scoring(str(d / "DetectSWR_manual_scoring.mat"))
        same = np.array_equal(np.round(sc["t"] * SR).astype(int), ts)
        if not same:
            raise RuntimeError(f"{s['name']}: candidates differ from the MATLAB scoring file")
        sess.update(idx1=sc["idx1"].astype(bool), bad=sc["bad"].astype(bool), scores=np.asarray(sc["scores"], float))
    ref = sd.load_ripples(str(d / s.get("ripples", f"{s['base']}.ripples.events.mat")))
    sess["ref"] = ref
    if s.get("ripples_before_spiking"):
        sess["ref_before_spiking"] = sd.load_ripples(str(d / s["ripples_before_spiking"]))
    np.savez_compressed(cache_dir / f"{s['name']}_candidates.npz", featureTs=ts, swDiffAll=swA, ripPowerAll=rpA,
                        bad_auto=bad_auto, **{k: sess[k] for k in ("idx1", "bad", "scores") if k in sess})
    sess["load_s"] = time.time() - t0
    return sess


def run_method(sess, method, model=None):
    fe, p, bad_auto = sess["fe"], sess["params"], sess["bad_auto"]
    sw, rp = fe["swDiffAll"], fe["ripPowerAll"]
    ok = ~bad_auto
    pc = sd.Params(**{**p.__dict__, "useSPW": False})
    if method == "user_replay":
        mask, pp = sess["idx1"], pc
    elif method == "detectswr_auto":
        idx1, idx2 = sd.split_kmeans(sw, rp)
        thS, thR = sd.prctile(sw[idx1], p.per_thresswD), sd.prctile(rp[idx2], p.per_thresRip)
        mask, pp = idx1 & (sw > thS) & (rp > thR), p
    elif method == "kmeans_raw":
        mask, pp = minority_kmeans(np.column_stack([sw, rp])) & ok, pc
    elif method == "kmeans_z":
        X = zfeat(sw, rp, ok)
        m = np.zeros(sw.size, bool)
        m[ok] = minority_kmeans(X[ok])
        mask, pp = m, pc
    elif method == "gmm_z":
        X = zfeat(sw, rp, ok)
        m = np.zeros(sw.size, bool)
        m[ok] = gmm_mask(X[ok])
        mask, pp = m, pc
    elif method == "clf_loso":
        X = robust_norm(sw, rp, ok)
        m = np.zeros(sw.size, bool)
        m[ok] = model.predict(X[ok]).astype(bool)
        mask, pp = m, pc
    else:
        raise ValueError(method)
    ev, loc = sd.events_from_mask(fe, sess["lfp_rip"], mask, SR, pp, sess["ctx"])
    return mask, ev, loc


def train_clf(train_sessions):
    from sklearn.ensemble import HistGradientBoostingClassifier
    X, y = [], []
    for s in train_sessions:
        fe = s["fe"]
        ok = ~s["bad"]
        X.append(robust_norm(fe["swDiffAll"], fe["ripPowerAll"], ok)[ok])
        y.append(s["idx1"][ok])
    return HistGradientBoostingClassifier(max_iter=200, random_state=0).fit(np.concatenate(X), np.concatenate(y))


def scatter_fig(sess, masks, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fe = sess["fe"]
    sw, rp = fe["swDiffAll"], fe["ripPowerAll"]
    ref = sess["idx1"]
    rng = np.random.default_rng(0)
    neg = np.flatnonzero(~ref)
    sub = rng.choice(neg, size=min(neg.size, 30000), replace=False)
    names = [m for m in masks if m != "user_replay"]
    fig, axes = plt.subplots(1, len(names) + 1, figsize=(4.2 * (len(names) + 1), 4.2), sharex=True, sharey=True)
    xl = np.percentile(sw, [0.05, 99.97])
    yl = np.percentile(rp, [0.05, 99.97])
    ax = axes[0]
    ax.scatter(sw[sub], rp[sub], s=1, c="0.75", rasterized=True)
    ax.scatter(sw[ref], rp[ref], s=1, c="tab:green", rasterized=True)
    clicked = ~np.isnan(sess["scores"])
    ax.scatter(sw[clicked], rp[clicked], s=22, facecolors="none",
               edgecolors=np.where(sess["scores"][clicked] > 0.1, "k", "tab:red"), linewidths=1.0)
    ax.set_title(f"user: idx1 (green), clicks 1 black / 0 red", fontsize=8)
    for ax, m in zip(axes[1:], names):
        pm = masks[m]
        ax.scatter(sw[sub], rp[sub], s=1, c="0.8", rasterized=True)
        for sel, col in ((pm & ref, "tab:green"), (ref & ~pm, "tab:red"), (pm & ~ref, "tab:blue")):
            ax.scatter(sw[sel], rp[sel], s=1, c=col, rasterized=True)
        p, r, f = prf(pm & ~sess["bad"], ref)
        ax.set_title(f"{m}: both green, user-only red, method-only blue\ncand P {p:.2f} R {r:.2f}", fontsize=8)
    for ax in axes:
        ax.set_xlim(*xl)
        ax.set_ylim(*yl)
        ax.set_xlabel("swDiff (sharp-wave depth)")
    axes[0].set_ylabel("ripPower (ripple - noise envelope)")
    fig.suptitle(sess["name"], fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(Path(__file__).resolve().parent / "configs/swr_reference_sessions.yaml"))
    ap.add_argument("--sessions", nargs="*")
    a = ap.parse_args()
    cfg = yaml.safe_load(open(a.config))
    root = Path(cfg["root"])
    todo = [s for s in cfg["sessions"] if not a.sessions or s["name"] in a.sessions]
    rd = run_dir("swr_auto_eval", COHORT)
    cache = rd / "candidates"
    cache.mkdir(parents=True, exist_ok=True)
    rep, fig = report_dir(COHORT), figure_dir(COHORT)
    sessions = []
    for s in todo:
        if not (root / s["dir"] / f"{s['base']}.lfp").exists():
            print(f"skip {s['name']}: LFP not local yet", flush=True)
            continue
        print(f"load {s['name']} ...", flush=True)
        sessions.append(load_session(root, s, cache))
        print(f"   {sessions[-1]['load_s']:.0f} s, {sessions[-1]['fe']['featureTs'].size} candidates", flush=True)
    labelled = [s for s in sessions if "idx1" in s]
    rows = []
    for sess in sessions:
        train = [t for t in labelled if t["name"] != sess["name"]]
        model = train_clf(train) if train else None
        masks = {}
        for m in METHODS:
            if (m == "user_replay" and "idx1" not in sess) or (m == "clf_loso" and model is None):
                continue
            t0 = time.time()
            mask, ev, loc = run_method(sess, m, model)
            masks[m] = mask
            P, R, F, nm = event_prf(ev["peak"], sess["ref"]["peak"])
            row = dict(session=sess["name"], method=m, n_candidates=int(mask.size), n_selected=int(mask.sum()),
                       n_events=int(ev["peak"].size), n_user_events=int(sess["ref"]["peak"].size), n_matched=nm,
                       event_precision=round(P, 4), event_recall=round(R, 4), event_f1=round(F, 4),
                       trained_on="+".join(t["name"] for t in train) if m == "clf_loso" else "")
            if "idx1" in sess:
                cp, cr, cf = prf(mask & ~sess["bad"], sess["idx1"])
                row.update(cand_precision=round(cp, 4), cand_recall=round(cr, 4), cand_f1=round(cf, 4))
            if "ref_before_spiking" in sess:
                P2, R2, F2, _ = event_prf(ev["peak"], sess["ref_before_spiking"]["peak"])
                row.update(before_spiking_precision=round(P2, 4), before_spiking_recall=round(R2, 4))
            rows.append(row)
            np.savez_compressed(rd / f"{sess['name']}_{m}_events.npz", **ev)
            print(f"   {sess['name']:18s} {m:15s} events {row['n_events']:6d} vs user {row['n_user_events']:6d}"
                  f"  P {P:.3f} R {R:.3f} F1 {F:.3f}  ({time.time()-t0:.0f} s)", flush=True)
        if "idx1" in sess:
            bad_p, bad_r, _ = prf(sess["bad_auto"], sess["bad"])
            rows.append(dict(session=sess["name"], method="bad_auto_vs_user_bad", n_selected=int(sess["bad_auto"].sum()),
                             n_user_events=int(sess["bad"].sum()), cand_precision=round(bad_p, 4),
                             cand_recall=round(bad_r, 4)))
            scatter_fig(sess, masks, rd / "figures" / f"swr_auto_eval_{sess['name']}.png")
            np.save(rd / f"{sess['name']}_masks.npy", np.array([masks[k] for k in masks]))
    import pandas as pd
    df = pd.DataFrame(rows)
    df.to_csv(rd / "swr_auto_eval_metrics.csv", index=False)
    df.to_csv(rep / f"ephys_spikes_swr_auto_eval_{COHORT}.csv", index=False)
    write_json(rd / "run_info.json", dict(created_utc=utc_now_iso(), git_commit=git_commit(), config=a.config,
                                         sessions=[s["name"] for s in sessions], match_tol_s=MATCH_TOL))
    write_json(rep / f"run_manifest_swr_auto_eval_{COHORT}.json", dict(run_dir=str(rd.resolve()), driver="ephys/swr_auto_eval.py",
                                                                     git_commit=git_commit(), created_utc=utc_now_iso()))
    print(df.to_string(index=False))
    print(f"run dir: {rd}")


if __name__ == "__main__":
    main()
