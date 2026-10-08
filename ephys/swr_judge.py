"""Automate the user's manual DetectSWR `check` step: a single-example judge + auto-click
(plan: implementation_plan/2026-10-07-swr-detection-automation.md).

The user's check run labels candidates in the 2-D (swDiff, ripPower) scatter by clicking 20-76 examples: for each click
the helper shows the +-0.5 s trace (ripple, sharp-wave, noise channel; swDiff; ripPower) and the user scores it 1/0;
every other candidate takes the score of the nearest click in z-space (`swr_detect.propagate_clicks`, reproduced exactly
on 17 sessions). So the user's waveform judgement lives in the clicks; the 2-D boundary follows from where they fall.

This module:
  extract   per session, features of EVERY candidate computed from what the helper shows around it (cached npz):
            2-D z (the helper's own normalisation), ripple-band envelope on the ripple and the noise channel and their
            ratio, narrow-band vs 250-400 Hz broadband ratio, ripple frequency and duration (cycles), sharp-wave level
            on each channel, the largest derivative / amplitude in the +-0.5 s window per channel (artifacts), the
            noise context of that window and of +-5 s (DetectSWR's local statistics), and the sleep state
  evaluate  leave-one-ANIMAL-out: the judge (gradient boosting) is trained on the clicks of the other animals only and
            then, on the held-out session,
              judge_all   labels every non-bad candidate (p > 0.5)
              autoclick   clicks K candidates spread over the upper part of the scatter and propagates with the
                          helper's own 1-NN rule
            each mask goes through the same localisation as the user's check run (useSPW = false) and is compared with
            the user's final events (peak +-10 ms); reference rows: user_replay (must be 1.0) and kmeans_z
Bad candidates come from the CleanLFP port with the helper's fixed thresholds (identical to the user's `bad` on the
3 sessions checked). Bulk outputs under $FIELD2026_ANALYSIS_OUT_ROOT/2026c/swr_judge_<ts>/, feature caches under
<reference root>/cache/, report + CSV under results/2026c/ephys_spikes/reports/.

  python ephys/swr_judge.py extract [--sessions ...]
  python ephys/swr_judge.py evaluate [--sessions ...] [--k-clicks 200] [--context] [--with-state]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import yaml
from scipy import signal
from scipy.ndimage import maximum_filter1d, median_filter, uniform_filter1d

sys.path.insert(0, str(Path(__file__).resolve().parent))
import swr_detect as sd  # noqa: E402
from _common import git_commit, report_dir, utc_now_iso, write_json  # noqa: E402
from output_paths import run_dir  # noqa: E402

COHORT = "2026c"
SR = 1250.0
FEAT_VERSION = 2  # v2 (2026-10-07, Fable audit): guarded logs, duration no longer counts the centre twice
EPS = 1e-9
CONFIG = Path(__file__).resolve().parent / "configs/swr_reference_sessions.yaml"
WIN = 625  # +-0.5 s, the helper's example window
STATE_CODES = {"WAKEstate": 1, "NREMstate": 3, "REMstate": 5}
FEATURES = ["z_sw", "z_rp", "lenv_r", "lenv_n", "lratio_rn", "lnarrow_r", "lhf_n", "freq", "dur_ms", "cycles",
            "low_r", "low_s", "lart_d_r", "lart_d_s", "lart_d_n", "art_a_r", "ctx_rp_05", "ctx_nhigh_05",
            "loc_rp_z", "loc_sw_z", "state"]


def params_of(s):
    return sd.Params(**{k: (tuple(v) if isinstance(v, list) else v) for k, v in s.get("params", {}).items()})


def load_states(sdir: Path, base: str, t: np.ndarray, states_npz: str | None = None) -> np.ndarray:
    out = np.zeros(t.size, np.int8)
    if states_npz:  # cohort 3: the final 1-s states (states_1s_final), session seconds
        st = np.load(states_npz)
        sec = t.astype(int)
        i = np.clip(np.searchsorted(st["ts"], sec), 0, st["ts"].size - 1)
        hit = st["ts"][i] == sec
        out[hit] = st["state"][i[hit]]
        return out
    f = sdir / f"{base}.SleepState.states.mat"
    if not f.exists():
        return out
    import scipy.io as sio
    try:
        ss = sio.loadmat(str(f), squeeze_me=True, struct_as_record=False)["SleepState"]
    except Exception:
        return out
    ints = getattr(ss, "ints", None)
    if ints is None:
        return out
    for name, code in STATE_CODES.items():
        iv = np.atleast_2d(np.asarray(getattr(ints, name, np.zeros((0, 2))), float))
        if iv.size:
            out[sd.in_intervals(t, iv[np.argsort(iv[:, 0])])] = code
    return out


def band_env(x, lo, hi, SR, smooth):
    sos = signal.butter(3, [lo, hi], btype="bandpass", fs=SR, output="sos")
    return sd.firfilt(np.abs(signal.sosfiltfilt(sos, x)), smooth)


def rolling_stats(x, half, dec=25):
    """Rolling median and SD over +-half samples, computed on dec-sample block means (so the SD is that of 20-ms means,
    smaller than DetectSWR's per-sample local SD: a feature, not a DetectSWR threshold)."""
    n = x.size // dec * dec
    b = x[:n].reshape(-1, dec).mean(1)
    w = 2 * (half // dec) + 1
    med = median_filter(b, size=w, mode="nearest")
    m1 = uniform_filter1d(b, w, mode="nearest")
    m2 = uniform_filter1d(b * b, w, mode="nearest")
    sdv = np.sqrt(np.maximum(m2 - m1 * m1, 1e-12))
    idx = np.minimum(np.arange(x.size) // dec, b.size - 1)
    return med, sdv, idx


def extract_session(root: Path, s: dict, cache: Path, force=False) -> Path | None:
    out = cache / f"judge_features_v{FEAT_VERSION}_{s['name']}.npz"
    if out.exists() and not force:
        return out
    sdir = root / s["dir"]
    lfp_path = sdir / f"{s['base']}.lfp"
    if not lfp_path.exists():
        print(f"skip {s['name']}: LFP not local", flush=True)
        return None
    t0 = time.time()
    p = params_of(s)
    lfp3 = sd.load_channels(str(lfp_path), s["nchan"], s["channels"])
    swDiff, rp0 = sd.features(lfp3, SR, p)
    ts, swA, rpA = sd.candidates(swDiff, rp0, SR, p)
    c = ts - 1
    N = swDiff.size
    bad = sd.in_intervals(ts / SR, sd.clean_lfp_intervals(lfp3[:, 0], SR))
    ok = ~bad
    # labels
    lab = {}
    if s.get("scoring"):
        sc = sd.load_scoring(str(sdir / "DetectSWR_manual_scoring.mat"))
        if not np.array_equal(np.round(sc["t"] * SR).astype(int), ts):
            raise RuntimeError(f"{s['name']}: candidates differ from the MATLAB scoring file")
        scores = np.asarray(sc["scores"], float)
        ubad = sc["bad"].astype(bool)
        idx1 = sc["idx1"].astype(bool) if "idx1" in sc else sd.propagate_clicks(swA, rpA, scores, ubad)[0]
        lab = dict(idx1=idx1, user_bad=ubad, scores=scores)
    elif s.get("gui_scores"):  # cohort 3: clicks from ephys/swr_check_gui.py, bad = the same CleanLFP port
        import json
        scores = np.full(ts.size, np.nan)
        for k, v in json.loads(Path(s["gui_scores"]).read_text())["scores"].items():
            scores[int(k)] = float(v)
        lab = dict(idx1=sd.propagate_clicks(swA, rpA, scores, bad)[0], user_bad=bad, scores=scores)
    # helper z
    X = np.column_stack([swA, rpA])
    z = (X - X[ok].mean(0)) / X[ok].std(0, ddof=1)
    # channel arrays (raw channels: ripple, sharp wave, noise-or-sharp-wave)
    x_r, x_s = lfp3[:, 0].astype(float), lfp3[:, 1].astype(float)
    x_n = lfp3[:, 2].astype(float) if lfp3.shape[1] > 2 else x_s
    hR1, hR2 = sd.makegausslpfir(p.ripBP[0], SR, 6), sd.makegausslpfir(p.ripBP[1], SR, 6)
    pw = sd.makegausslpfir(1 / (np.pi / np.mean(p.ripBP)), SR, 6)

    def renv(x):
        r = sd.firfilt(x, hR2)
        return sd.firfilt(np.abs(r - sd.firfilt(r, hR1)), pw)

    env_r, env_n = renv(x_r), renv(x_n)
    hf_r, hf_n = band_env(x_r, 250, 400, SR, pw), band_env(x_n, 250, 400, SR, pw)
    hS1, hS2 = sd.makegausslpfir(p.swBP[0], SR, 6), sd.makegausslpfir(p.swBP[1], SR, 6)
    low = sd.firfilt(np.column_stack([x_r, x_s]), hS2)
    low = low - sd.firfilt(low, hS1)
    ctx = sd.trough_context(lfp3[:, 0], SR, p)
    inst_f = np.append(np.diff(ctx["unw"]), 0) * SR / (2 * np.pi)
    del ctx
    W = int(np.floor(p.WinSize * SR / 1000))
    half = W // 2
    # ripple peak per candidate: argmax of ripPower0 within +-half
    offs = np.arange(-half, half + 1)
    rows = np.clip(c[:, None] + offs[None, :], 0, N - 1)
    r = rows[np.arange(c.size), np.argmax(rp0[rows], axis=1)]
    med = lambda a: np.median(a[c[ok]])  # noqa: E731
    slog = lambda a, b: np.log(np.maximum(a, EPS) / np.maximum(b, EPS))  # noqa: E731  dead/flat segments -> finite
    f = {}
    f["z_sw"], f["z_rp"] = z[:, 0], z[:, 1]
    e_r, e_n = env_r[r], env_n[r]
    f["lenv_r"] = slog(e_r, med(env_r))
    f["lenv_n"] = slog(e_n, med(env_n))
    f["lratio_rn"] = slog(e_r, e_n)
    nar = slog(e_r, hf_r[r])
    f["lnarrow_r"] = nar - np.median(nar[ok])
    f["lhf_n"] = slog(hf_n[r], med(hf_n))
    k = np.arange(-12, 13)
    f["freq"] = np.median(inst_f[np.clip(r[:, None] + k, 0, N - 1)], axis=1)
    # duration where env_r stays above half of its peak (+-150 ms search)
    o2 = np.arange(-188, 189)
    seg = env_r[np.clip(r[:, None] + o2[None, :], 0, N - 1)] > 0.5 * e_r[:, None]
    mid = 188
    left = np.argmax(~seg[:, :mid + 1][:, ::-1], axis=1)
    right = np.argmax(~seg[:, mid:], axis=1)
    left[seg[:, :mid + 1].all(1)] = mid
    right[seg[:, mid:].all(1)] = mid
    f["dur_ms"] = (left + right - 1) / SR * 1000  # both runs include the centre sample
    f["cycles"] = f["dur_ms"] * np.clip(f["freq"], 0, None) / 1000
    f["low_r"] = low[c, 0] / np.std(low[:, 0])
    f["low_s"] = low[c, 1] / np.std(low[:, 1])
    for nm, x in (("r", x_r), ("s", x_s), ("n", x_n)):
        d = np.abs(np.diff(x, append=x[-1]))
        f[f"lart_d_{nm}"] = np.log((maximum_filter1d(d, 2 * WIN + 1)[c] + 1) / (np.median(d) + 1))
    a = np.abs(x_r - np.median(x_r))
    f["art_a_r"] = maximum_filter1d(a, 2 * WIN + 1)[c] / (1.4826 * np.median(a) + 1e-9)
    mad_rp = 1.4826 * np.median(np.abs(rp0 - np.median(rp0)))
    m05, _, i05 = rolling_stats(rp0, WIN)
    f["ctx_rp_05"] = (m05[i05[c]] - np.median(rp0)) / mad_rp
    hi = z[:, 1] > 2
    tsec = ts / SR
    cnt = np.searchsorted(tsec[hi], tsec + 0.5) - np.searchsorted(tsec[hi], tsec - 0.5)
    f["ctx_nhigh_05"] = cnt.astype(float)
    m5, s5, i5 = rolling_stats(rp0, 6250)
    f["loc_rp_z"] = (rpA - m5[i5[c]]) / np.maximum(s5[i5[c]], EPS)
    m5s, s5s, i5s = rolling_stats(swDiff, 6250)
    f["loc_sw_z"] = (swA - m5s[i5s[c]]) / np.maximum(s5s[i5s[c]], EPS)
    f["state"] = load_states(sdir, s["base"], tsec, s.get("states_npz")).astype(float)
    F = np.column_stack([f[k] for k in FEATURES]).astype(np.float32)
    np.savez_compressed(out, F=F, featureTs=ts, swDiffAll=swA, ripPowerAll=rpA, bad=bad,
                        feature_names=np.array(FEATURES), **lab)
    print(f"extract {s['name']}: {ts.size} candidates, {time.time()-t0:.0f} s", flush=True)
    return out


CONTEXT_FEATURES = ["lth_de_s", "lth_de_r", "lgs_s", "lgf_s", "lgf_r", "lth_s"]


def window_power(x, lo, hi, half=WIN):
    """Mean band power (zero-phase Butterworth) over +-half samples around every sample."""
    sos = signal.butter(3, [lo, hi], btype="bandpass", fs=SR, output="sos")
    y = signal.sosfiltfilt(sos, x)
    return uniform_filter1d(y * y, 2 * half + 1, mode="nearest")


def extract_context(root: Path, s: dict, cache: Path, force=False) -> Path | None:
    """What the user reads in the +-0.5 s popup besides the event itself: theta (and theta mixed with gamma) means
    'not a ripple' (user, 2026-10-07). Per candidate, on the sharp-wave (radiatum) and the ripple channel:
    log theta(6-10 Hz)/delta(1-4 Hz) power, log theta power vs the session median, log slow (30-55 Hz) and fast
    (60-100 Hz) gamma power vs the session median, all averaged over +-0.5 s."""
    out = cache / f"judge_context_v{FEAT_VERSION}_{s['name']}.npz"
    if out.exists() and not force:
        return out
    feats = cache / f"judge_features_v{FEAT_VERSION}_{s['name']}.npz"
    if not feats.exists():
        return None
    t0 = time.time()
    c = np.load(feats)["featureTs"] - 1
    lfp3 = sd.load_channels(str(root / s["dir"] / f"{s['base']}.lfp"), s["nchan"], s["channels"])
    x_r, x_s = lfp3[:, 0].astype(float), lfp3[:, 1].astype(float)
    th_s, de_s = window_power(x_s, 6, 10), window_power(x_s, 1, 4)
    th_r, de_r = window_power(x_r, 6, 10), window_power(x_r, 1, 4)
    gs_s, gf_s, gf_r = window_power(x_s, 30, 55), window_power(x_s, 60, 100), window_power(x_r, 60, 100)
    lg = lambda a, b: np.log(np.maximum(a, EPS) / np.maximum(b, EPS))  # noqa: E731
    f = {"lth_de_s": lg(th_s[c], de_s[c]), "lth_de_r": lg(th_r[c], de_r[c]),
         "lgs_s": lg(gs_s[c], np.median(gs_s)), "lgf_s": lg(gf_s[c], np.median(gf_s)),
         "lgf_r": lg(gf_r[c], np.median(gf_r)), "lth_s": lg(th_s[c], np.median(th_s))}
    np.savez_compressed(out, C=np.column_stack([f[k] for k in CONTEXT_FEATURES]).astype(np.float32),
                        feature_names=np.array(CONTEXT_FEATURES))
    print(f"context {s['name']}: {time.time()-t0:.0f} s", flush=True)
    return out


# ----------------------------------------------------------------------------------------------------- evaluation
def judge_model(Xtr, ytr, seed=0):
    from sklearn.ensemble import HistGradientBoostingClassifier
    return HistGradientBoostingClassifier(max_depth=3, max_iter=300, learning_rate=0.05, l2_regularization=1.0,
                                          min_samples_leaf=10, random_state=seed).fit(Xtr, ytr)


def autoclick_mask(Z, prob, ok, k, rng):
    """Spread k clicks over the upper part of the scatter (z_sw > 0 or z_rp > 0), density-flattened on a z grid, plus
    the judge's verdict; then the helper's own 1-NN propagation."""
    cand = np.flatnonzero(ok & ((Z[:, 0] > 0) | (Z[:, 1] > 0)))
    gx = np.floor(np.clip(Z[cand, 0], -2, 12) / 0.5).astype(int)
    gy = np.floor(np.clip(Z[cand, 1], -2, 12) / 0.5).astype(int)
    cell = gx * 1000 + gy
    order = rng.permutation(cand.size)
    _, first = np.unique(cell[order], return_index=True)
    picks = cand[order[first]]
    if picks.size > k:
        picks = rng.choice(picks, size=k, replace=False)
    elif picks.size < k:
        rest = np.setdiff1d(cand, picks)
        picks = np.concatenate([picks, rng.choice(rest, size=min(k - picks.size, rest.size), replace=False)])
    scores = np.full(Z.shape[0], np.nan)
    scores[picks] = (prob[picks] > 0.5).astype(float)
    # anchor the bulk: the most typical candidate is a non-ripple
    scores[np.argmin(np.sum(Z ** 2, axis=1))] = 0.0
    from scipy.spatial import cKDTree
    sc = np.flatnonzero(~np.isnan(scores))
    _, nn = cKDTree(Z[sc]).query(Z, k=1)
    return (scores[sc][nn] > 0.1) & ok, picks


def midclick_mask(Z, rp, prob, ok, k, rng, zone=(85.0, 99.5)):
    """The user's own strategy (2026-10-07): the boundary sits in the middle of the plot, so click there and check
    both sides. The user's 741 clicks lie at the 93-98th ripPower percentile (25-40 % of the plotted swDiff range).
    Here: k judged clicks spread (density-flattened on a z grid) over the candidates whose ripPower percentile is in
    `zone`, k/6 judged clicks in the far tail (> zone[1]) and k/6 bulk anchors (< 50th percentile, scored 0 as the
    bulk is never a ripple); then the helper's 1-NN propagation."""
    okr = np.flatnonzero(ok)
    pct = np.zeros(rp.size)
    pct[okr] = np.argsort(np.argsort(rp[okr])) / max(okr.size - 1, 1) * 100

    def spread(pool, n):
        if pool.size <= n:
            return pool
        g = np.floor(Z[pool] / 0.25).astype(int)
        cell = g[:, 0] * 100000 + g[:, 1]
        order = rng.permutation(pool.size)
        _, first = np.unique(cell[order], return_index=True)
        picks = pool[order[first]]
        if picks.size > n:
            return rng.choice(picks, size=n, replace=False)
        rest = np.setdiff1d(pool, picks)
        return np.concatenate([picks, rng.choice(rest, size=n - picks.size, replace=False)])

    mid = spread(okr[(pct[okr] >= zone[0]) & (pct[okr] <= zone[1])], k)
    tail = spread(okr[pct[okr] > zone[1]], max(k // 6, 1))
    bulk = rng.choice(okr[pct[okr] < 50], size=max(k // 6, 1), replace=False)
    scores = np.full(rp.size, np.nan)
    judged = np.concatenate([mid, tail])
    scores[judged] = (prob[judged] > 0.5).astype(float)
    scores[bulk] = 0.0
    from scipy.spatial import cKDTree
    sc = np.flatnonzero(~np.isnan(scores))
    _, nn = cKDTree(Z[sc]).query(Z, k=1)
    return (scores[sc][nn] > 0.1) & ok, judged


def evaluate(cfg, session_names, k_clicks, use_state, use_context=False):
    root = Path(cfg["root"])
    cache = root / "cache"
    S = {s["name"]: s for s in cfg["sessions"] if s.get("scoring") is True}  # partial scoring files are excluded
    if session_names:
        S = {k: v for k, v in S.items() if k in session_names}
    data = {}
    names = list(FEATURES) + (list(CONTEXT_FEATURES) if use_context else [])
    for n, s in S.items():
        f = cache / f"judge_features_v{FEAT_VERSION}_{n}.npz"
        if f.exists():
            data[n] = dict(np.load(f, allow_pickle=False))
            if use_context:
                data[n]["F"] = np.hstack([data[n]["F"], np.load(cache / f"judge_context_v{FEAT_VERSION}_{n}.npz")["C"]])
    cols = [i for i, nm in enumerate(names) if use_state or nm != "state"]
    rd = run_dir("swr_judge", COHORT)
    print("features:", [names[i] for i in cols], flush=True)
    rng = np.random.default_rng(0)
    rows, click_rows, replay_fail = [], [], []
    for n, d in data.items():
        s = S[n]
        tr = [m for m in data if S[m]["animal"] != s["animal"]]
        Xtr = np.concatenate([data[m]["F"][~np.isnan(data[m]["scores"])][:, cols] for m in tr])
        ytr = np.concatenate([data[m]["scores"][~np.isnan(data[m]["scores"])] > 0.1 for m in tr])
        model = judge_model(Xtr, ytr)
        F = d["F"][:, cols]
        ok = ~d["bad"]
        prob = model.predict_proba(F)[:, 1]
        clicked = ~np.isnan(d["scores"])
        from sklearn.metrics import roc_auc_score
        yc = d["scores"][clicked] > 0.1
        acc = float(np.mean((prob[clicked] > 0.5) == yc))
        auc = float(roc_auc_score(yc, prob[clicked])) if 0 < yc.sum() < yc.size else float("nan")
        click_rows.append(dict(session=n, animal=s["animal"], n_train_clicks=int(ytr.size), n_clicks=int(clicked.sum()),
                               click_accuracy=round(acc, 3), click_auc=round(auc, 3)))
        Z = d["F"][:, :2].astype(float)  # the helper's z (z_sw, z_rp)
        # idx1_model: the same features, trained on the other animals' full candidate labels (idx1, all positives +
        # an equal-size random draw of 4x negatives per session)
        Xi, yi = [], []
        for m in tr:
            okm = ~data[m]["bad"]
            pos = np.flatnonzero(okm & data[m]["idx1"])
            neg = np.flatnonzero(okm & ~data[m]["idx1"])
            neg = rng.choice(neg, size=min(neg.size, 4 * pos.size), replace=False)
            sel = np.concatenate([pos, neg])
            Xi.append(data[m]["F"][sel][:, cols])
            yi.append(data[m]["idx1"][sel])
        wneg = np.concatenate([np.where(y, 1.0, (~data[m]["idx1"] & ~data[m]["bad"]).sum() / max(1, (~y).sum()))
                               for y, m in zip(yi, tr)])
        from sklearn.ensemble import HistGradientBoostingClassifier
        m_idx1 = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.1, random_state=0).fit(
            np.concatenate(Xi), np.concatenate(yi), sample_weight=wneg)
        masks = {"user_replay": d["idx1"], "judge_all": (prob > 0.5) & ok,
                 "idx1_model": (m_idx1.predict_proba(F)[:, 1] > 0.5) & ok}
        masks["autoclick"], picks = autoclick_mask(Z, prob, ok, k_clicks, rng)
        masks["midclick"], _ = midclick_mask(Z, d["ripPowerAll"], prob, ok, 60, rng)
        from sklearn.cluster import KMeans
        km = np.zeros(ok.size, bool)
        lab = KMeans(2, n_init=10, random_state=0).fit_predict(Z[ok])
        km[ok] = lab == (0 if np.sum(lab == 0) <= np.sum(lab == 1) else 1)
        masks["kmeans_z"] = km
        # judge_at_clicks: the user's click positions, the judge's verdicts, the helper's propagation
        sj = np.full(ok.size, np.nan)
        sj[clicked] = (prob[clicked] > 0.5).astype(float)
        masks["judge_at_clicks"] = sd.propagate_clicks(d["swDiffAll"], d["ripPowerAll"], sj, d["user_bad"])[0]
        # user_same_animal: the user's own clicks (z position + verdict) from the other days of this animal
        sib = [m for m in data if m != n and S[m]["animal"] == s["animal"]]
        if sib:
            cz = np.concatenate([data[m]["F"][~np.isnan(data[m]["scores"]), :2] for m in sib]).astype(float)
            cy = np.concatenate([data[m]["scores"][~np.isnan(data[m]["scores"])] > 0.1 for m in sib])
            from scipy.spatial import cKDTree
            _, nn = cKDTree(cz).query(Z, k=1)
            masks["user_same_animal"] = cy[nn] & ~d["user_bad"]
        # sensitivity of the user's own result to one click (candidate level, % of idx1 that changes)
        ci = np.flatnonzero(clicked)
        drop, flip = [], []
        for j in ci:
            s2 = d["scores"].copy()
            s2[j] = np.nan
            drop.append(np.sum(sd.propagate_clicks(d["swDiffAll"], d["ripPowerAll"], s2, d["user_bad"])[0] != d["idx1"]))
            s2[j] = 0.0 if d["scores"][j] > 0.1 else 1.0
            flip.append(np.sum(sd.propagate_clicks(d["swDiffAll"], d["ripPowerAll"], s2, d["user_bad"])[0] != d["idx1"]))
        nid = max(int(d["idx1"].sum()), 1)
        click_rows[-1].update(drop_one_click_median_pct=round(100 * np.median(drop) / nid, 2),
                              drop_one_click_max_pct=round(100 * np.max(drop) / nid, 2),
                              flip_one_click_median_pct=round(100 * np.median(flip) / nid, 2),
                              flip_one_click_max_pct=round(100 * np.max(flip) / nid, 2), n_sibling_days=len(sib))
        # localisation needs the full-rate features again
        p = params_of(s)
        lfp3 = sd.load_channels(str(root / s["dir"] / f"{s['base']}.lfp"), s["nchan"], s["channels"])
        swDiff, rp0 = sd.features(lfp3, SR, p)
        fe = dict(swDiff=swDiff, ripPower0=rp0, featureTs=d["featureTs"], swDiffAll=d["swDiffAll"],
                  ripPowerAll=d["ripPowerAll"])
        ctx = sd.trough_context(lfp3[:, 0], SR, p)
        pc = sd.Params(**{**p.__dict__, "useSPW": False})
        ref_ev, _ = sd.events_from_mask(fe, lfp3[:, 0], d["idx1"], SR, pc, ctx)
        final = sd.load_ripples(str(root / s["dir"] / s.get("ripples", f"{s['base']}.ripples.events.mat")))
        ia0, _ = sd.match_peaks(np.sort(final["peak"]), np.sort(ref_ev["peak"]), 0.0005)
        click_rows[-1].update(n_final_file=int(final["peak"].size), n_replay=int(ref_ev["peak"].size),
                              replay_identical=int(ia0.size))
        print(f"{n:12s} replay vs final file: {ia0.size} identical of {final['peak'].size} / {ref_ev['peak'].size}", flush=True)
        if not (ia0.size == final["peak"].size == ref_ev["peak"].size):
            replay_fail.append(n)  # the reference is not the user's final result -> the run fails at the end
        for m, mask in masks.items():
            ev = ref_ev if m == "user_replay" else sd.events_from_mask(fe, lfp3[:, 0], mask, SR, pc, ctx)[0]
            a, b = np.sort(ref_ev["peak"]), np.sort(ev["peak"])
            ia, _ = sd.match_peaks(a, b, 0.010)
            P, R = ia.size / max(b.size, 1), ia.size / max(a.size, 1)
            tp = np.sum(mask & d["idx1"])
            rows.append(dict(session=n, animal=s["animal"], species=s["species"], method=m, n_events=int(b.size),
                             n_user=int(a.size), event_precision=round(P, 4), event_recall=round(R, 4),
                             event_f1=round(2 * P * R / max(P + R, 1e-9), 4),
                             cand_precision=round(tp / max(mask.sum(), 1), 4), cand_recall=round(tp / max(d["idx1"].sum(), 1), 4)))
            np.savez_compressed(rd / f"{n}_{m}_events.npz", **ev)
            print(f"{n:12s} {m:12s} events {b.size:6d} vs user {a.size:6d}  P {P:.3f} R {R:.3f}", flush=True)
        np.savez_compressed(rd / f"{n}_judge.npz", prob=prob.astype(np.float32), autoclick_picks=picks)
        print(f"{n:12s} judge on held-out clicks: acc {acc:.3f} auc {auc:.3f} (trained on {ytr.size} clicks)", flush=True)
    import pandas as pd
    df, dc = pd.DataFrame(rows), pd.DataFrame(click_rows)
    df.to_csv(rd / "swr_judge_events.csv", index=False)
    dc.to_csv(rd / "swr_judge_clicks.csv", index=False)
    rep = report_dir(COHORT)
    df.to_csv(rep / f"ephys_spikes_swr_judge_{COHORT}.csv", index=False)
    dc.to_csv(rep / f"ephys_spikes_swr_judge_clicks_{COHORT}.csv", index=False)
    write_json(rep / f"run_manifest_swr_judge_{COHORT}.json", dict(run_dir=str(rd.resolve()), driver="ephys/swr_judge.py",
               git_commit=git_commit(), created_utc=utc_now_iso(), k_clicks=k_clicks, use_state=use_state, use_context=use_context,
               feature_version=FEAT_VERSION))
    # three separate layers (never one "accuracy"): the user's clicks / the propagated candidate labels / final events
    print("LAYER 1  judge vs the user's actual clicks (waveform judgement):")
    print(dc[["session", "n_clicks", "click_accuracy", "click_auc"]].to_string(index=False))
    print("LAYER 2  candidate labels vs idx1 (the 1-NN propagation of the clicks): recall / precision")
    print(df.pivot_table(index="session", columns="method", values="cand_recall").round(3).to_string())
    print(df.pivot_table(index="session", columns="method", values="cand_precision").round(3).to_string())
    print("LAYER 3  final events vs the replayed user result (peak +-10 ms): F1")
    print(df.pivot_table(index="session", columns="method", values="event_f1").round(3).to_string())
    print(dc.to_string(index=False))
    print("run dir:", rd)
    if replay_fail:
        raise SystemExit(f"REPLAY MISMATCH (reference is not the user's final file): {replay_fail}")


def load_cache(cache: Path, name: str, use_context: bool) -> dict:
    d = dict(np.load(cache / f"judge_features_v{FEAT_VERSION}_{name}.npz", allow_pickle=False))
    if use_context:
        d["F"] = np.hstack([d["F"], np.load(cache / f"judge_context_v{FEAT_VERSION}_{name}.npz")["C"]])
    return d


def evaluate_c3(cfg3: dict, cfg_ref: dict, use_context: bool):
    """In-domain test on the cohort-3 sessions the user scored in the GUI. For each held-out session H, judges trained
    on (a) the other cohort-3 session's clicks, (b) the reference (lab) clicks, (c) both; no sleep-state feature.
    Methods: judge_all (every non-bad candidate, p > 0.5); judge_at_clicks (H's click positions, the judge's verdicts,
    the helper's propagation); kmeans_z (no labels); user_other_animal (the other session's clicks, z position + verdict,
    applied directly). Three separate layers: H's clicks / H's propagated labels / H's events (replay of the clicks)."""
    import pandas as pd
    from scipy.spatial import cKDTree
    from sklearn.cluster import KMeans
    from sklearn.metrics import roc_auc_score
    names = list(FEATURES) + (list(CONTEXT_FEATURES) if use_context else [])
    cols = [i for i, nm in enumerate(names) if nm != "state"]
    c3cache = Path(cfg3["cache"])
    S3 = {s["name"]: s for s in cfg3["sessions"]}
    D3 = {n: load_cache(c3cache, n, use_context) for n in S3}
    ref_cache = Path(cfg_ref["root"]) / "cache"
    clicked = lambda d: ~np.isnan(d["scores"])  # noqa: E731
    Xr, yr = [], []
    for s in cfg_ref["sessions"]:
        if s.get("scoring") is True:
            d = load_cache(ref_cache, s["name"], use_context)
            Xr.append(d["F"][clicked(d)][:, cols])
            yr.append(d["scores"][clicked(d)] > 0.1)
    Xref, yref = np.concatenate(Xr), np.concatenate(yr)
    rd = run_dir("swr_judge_c3", COHORT)
    rows, crow = [], []
    for H, d in D3.items():
        s = S3[H]
        O = [n for n in D3 if n != H]
        cH = clicked(d)
        yH = d["scores"][cH] > 0.1
        ok = ~d["bad"]
        Z = d["F"][:, :2].astype(float)
        Xo = np.concatenate([D3[n]["F"][clicked(D3[n])][:, cols] for n in O])
        yo = np.concatenate([D3[n]["scores"][clicked(D3[n])] > 0.1 for n in O])
        train = {"other_c3": (Xo, yo), "reference": (Xref, yref),
                 "other_c3+reference": (np.vstack([Xo, Xref]), np.concatenate([yo, yref]))}
        masks = {"user_replay": d["idx1"]}
        km = np.zeros(ok.size, bool)
        lab = KMeans(2, n_init=10, random_state=0).fit_predict(Z[ok])
        km[ok] = lab == (0 if np.sum(lab == 0) <= np.sum(lab == 1) else 1)
        masks["kmeans_z"] = km
        cz = np.concatenate([D3[n]["F"][clicked(D3[n]), :2] for n in O]).astype(float)
        _, nn = cKDTree(cz).query(Z, k=1)
        masks["user_other_animal"] = yo[nn] & ok
        for tname, (Xt, yt) in train.items():
            m = judge_model(Xt, yt)
            prob = m.predict_proba(d["F"][:, cols])[:, 1]
            acc = float(np.mean((prob[cH] > 0.5) == yH))
            auc = float(roc_auc_score(yH, prob[cH])) if 0 < yH.sum() < yH.size else float("nan")
            crow.append(dict(session=H, trained_on=tname, n_train_clicks=int(yt.size), n_clicks=int(cH.sum()),
                             click_accuracy=round(acc, 3), click_auc=round(auc, 3)))
            masks[f"judge_all[{tname}]"] = (prob > 0.5) & ok
            sj = np.full(ok.size, np.nan)
            sj[cH] = (prob[cH] > 0.5).astype(float)
            masks[f"judge_at_clicks[{tname}]"] = sd.propagate_clicks(d["swDiffAll"], d["ripPowerAll"], sj, d["user_bad"])[0]
        prm = params_of(s)
        lfp3 = sd.load_channels(str(Path(cfg3["root"]) / s["dir"] / f"{s['base']}.lfp"), s["nchan"], s["channels"])
        swDiff, rp0 = sd.features(lfp3, SR, prm)
        fe = dict(swDiff=swDiff, ripPower0=rp0, featureTs=d["featureTs"], swDiffAll=d["swDiffAll"],
                  ripPowerAll=d["ripPowerAll"])
        ctx = sd.trough_context(lfp3[:, 0], SR, prm)
        pc = sd.Params(**{**prm.__dict__, "useSPW": False})
        ref_ev, _ = sd.events_from_mask(fe, lfp3[:, 0], d["idx1"], SR, pc, ctx)
        for mname, mask in masks.items():
            ev = ref_ev if mname == "user_replay" else sd.events_from_mask(fe, lfp3[:, 0], mask, SR, pc, ctx)[0]
            ua, ub = np.sort(ref_ev["peak"]), np.sort(ev["peak"])
            ia, _ = sd.match_peaks(ua, ub, 0.010)
            prec, rec = ia.size / max(ub.size, 1), ia.size / max(ua.size, 1)
            tp = np.sum(mask & d["idx1"])
            rows.append(dict(session=H, method=mname, n_events=int(ub.size), n_user=int(ua.size),
                             event_precision=round(prec, 4), event_recall=round(rec, 4),
                             event_f1=round(2 * prec * rec / max(prec + rec, 1e-9), 4),
                             cand_precision=round(tp / max(mask.sum(), 1), 4),
                             cand_recall=round(tp / max(d["idx1"].sum(), 1), 4)))
            fname = mname.replace("[", "_").replace("]", "").replace("+", "_")
            np.savez_compressed(rd / f"{H}_{fname}_events.npz", **ev)
            print(f"{H:16s} {mname:34s} events {ub.size:6d} vs user {ua.size:6d}  prec {prec:.3f} rec {rec:.3f}", flush=True)
    df, dc = pd.DataFrame(rows), pd.DataFrame(crow)
    df.to_csv(rd / "swr_judge_c3_events.csv", index=False)
    dc.to_csv(rd / "swr_judge_c3_clicks.csv", index=False)
    rep = report_dir(COHORT)
    df.to_csv(rep / f"ephys_spikes_swr_judge_c3_{COHORT}.csv", index=False)
    dc.to_csv(rep / f"ephys_spikes_swr_judge_c3_clicks_{COHORT}.csv", index=False)
    write_json(rep / f"run_manifest_swr_judge_c3_{COHORT}.json", dict(
        run_dir=str(rd.resolve()), driver="ephys/swr_judge.py evaluate-c3", git_commit=git_commit(),
        created_utc=utc_now_iso(), use_context=use_context, feature_version=FEAT_VERSION))
    print("LAYER 1  judge vs the user's clicks on the held-out session:")
    print(dc.to_string(index=False))
    for lay, col in (("LAYER 2  candidate recall", "cand_recall"), ("LAYER 2  candidate precision", "cand_precision"),
                     ("LAYER 3  event F1 (peak +-10 ms)", "event_f1"), ("LAYER 3  event precision", "event_precision"),
                     ("LAYER 3  event recall", "event_recall")):
        print(lay)
        print(df.pivot_table(index="method", columns="session", values=col).round(3).to_string())
    print("run dir:", rd)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["extract", "context", "evaluate", "evaluate-c3"])
    ap.add_argument("--config", default=str(CONFIG))
    ap.add_argument("--sessions", nargs="*")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--k-clicks", type=int, default=200)
    ap.add_argument("--with-state", action="store_true",
                    help="add the sleep state as a feature (off by default: a state feature would put a state effect "
                         "into later ripple-rate-by-state comparisons)")
    ap.add_argument("--context", action="store_true", help="add the theta/gamma context features")
    a = ap.parse_args()
    cfg = yaml.safe_load(open(a.config))
    if a.cmd in ("extract", "context"):
        root = Path(cfg["root"])
        cache = Path(cfg.get("cache", root / "cache"))
        cache.mkdir(parents=True, exist_ok=True)
        fn = extract_session if a.cmd == "extract" else extract_context
        for s in cfg["sessions"]:
            if (s.get("scoring") or s.get("gui_scores")) and (not a.sessions or s["name"] in a.sessions):
                fn(root, s, cache, a.force)
    elif a.cmd == "evaluate-c3":
        evaluate_c3(cfg, yaml.safe_load(open(CONFIG)), a.context)
    else:
        evaluate(cfg, a.sessions, a.k_clicks, a.with_state, a.context)


if __name__ == "__main__":
    main()
