r"""Part S of Amendment 1 of the sleep-behaviour explore (plan implementation_plan/2026-10-08-sleep-behaviour-explore.md §9,
written before results; S2b / S3 added on the user's request before any S result): can the counter model predict
sleep stability — which movements end in waking, and how sleep responds to the battery rounds (a systematic
perturbation)?

Usage:  python ephys/sleep_stability.py predict [--scorings final pass2med] [--workers 6]
        python ephys/sleep_stability.py analyse [--scorings final pass2med] [--reps 100] [--workers 8]
        python ephys/sleep_stability.py --selftest

Definitions:
  held-out step predictions (`predict`)   per 10-s NREM step of the forward-chained test blocks (block k predicted
      by the fit on blocks < k; the first 6 blocks are never predicted), three multinomial models (stay / REM / WAKE):
        B-full  base + L1 + spline ln(1 + P), P = P_tw600_k0 (Step B)          -> p_stay, p_rem, p_wake
        gate    base + L1, no counter                                           -> p_rem_gate, p_wake_gate
        blind   B-full trained WITHOUT the steps in the 3 h after a usable round gap (the perturbation is never seen)
                                                                                -> pb_rem, pb_wake
      post_round = the step lies in the 3 h after the end of a usable round gap (cause round_logged / round_inferred;
      the record starts there). File: <OUT>/2026c/sleep_heldout_steps/heldout_steps_<scoring>.csv.gz.
  S1  Phase-6 event library (events / participants / control_* csv.gz): every participant with pre-state NREM is
      mapped to its animal's NREM step containing the event time t0 (step start <= t0 < start + 10 s); propensity =
      p_wake (or p_wake_gate) of that step.
      (a) AUC of the propensity for woke60 among first movers; bootstrap CI over blocks (2000 resamples of blocks);
          the B-full - gate AUC difference with its CI; per-animal AUC. Late-wake control (A5): events whose first wake
          starts < 15 s after t0 are dropped and the outcome is a wake starting 15-60 s after t0.
      (b) expected woke60 = 1 - (1 - p_wake)^6; O/E for each role and the controls; movement effect = O/E(first
          movers) / O/E(controls).
      Pass (plan): AUC >= 0.60 with CI > 0.5; above gate (difference CI > 0); >= 5/6 rats AUC > 0.5; both scorings.
  S2 / S2b  windows of NREM steps 0-1 h and 1-3 h after (a) the start of a round record and (b) the end of a natural
      wake >= 30 min inside a record (until the next wake >= 30 min or the record end): O/E of NREM -> WAKE (y = 2)
      and NREM -> REM (y = 1) transitions, expected = the sum of the per-step probabilities (S2: B-full; S2b: blind);
      bootstrap CI over blocks; per-animal O/E. Pass (S2 / S2b): WAKE O/E after rounds in [0.8, 1.25] with CI
      including 1 (S2b also REM O/E), both scorings.
  S3  the generative model (sleep_sim v2) refitted on the records with the 3 h after every round masked out (the
      perturbation is never seen), 100 replicates conditional on the observed long wakes and gaps. Per round (from the
      round record's first second): REM min, NREM min and REM bouts in 1 / 3 / 6 h (rounds whose record is shorter
      than the window are dropped from that window), first-REM latency (s; censored at the record end, KM median over
      rounds); observed mean vs the simulated distribution of the mean (2.5-97.5 %), morning and evening separately.
      Pass: the observed means inside the simulated range at 1, 3 and 6 h for REM and NREM minutes and the latency
      median, both scorings. Also reported with the model fitted on all data.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from sleep_schedule import N, R, ROOT, W  # noqa: E402

KEY = "P_tw600_k0"
POST_S = 3 * 3600
OUTD = Path("D:/Field2026_analysis_out/2026c/sleep_heldout_steps")
LIB = Path("D:/Field2026_analysis_out/2026c/sleep_events_20261008_1721")


def gaps_table() -> pd.DataFrame:
    p0 = json.load(open(ROOT / "results/2026c/ephys_spikes/reports/run_manifest_sleep_schedule_phase0_2026c.json"))["run_dir"]
    return pd.read_csv(Path(p0) / "gaps.csv", parse_dates=["gap_start", "gap_end"])


def round_starts(recs: list[dict], gaps: pd.DataFrame) -> dict[int, str]:
    """record_id -> 'morning' / 'evening' / 'other' for records that start at the end of a usable round gap."""
    g = gaps[gaps.usable & gaps.cause.isin(["round_logged", "round_inferred"])]
    out = {}
    for rc in recs:
        m = g[(g.animal == rc["animal"]) & ((g.gap_end - rc["start"]).abs() <= pd.Timedelta(seconds=5))]
        if len(m):
            out[rc["record_id"]] = str(m.kind.iloc[0])
    return out


# ------------------------------------------------------------------ predict
def _fit_predict(D: dict, tr: np.ndarray, te: np.ndarray, spec: dict) -> np.ndarray:
    from sklearn.linear_model import LogisticRegression
    from sleep_model import design
    levels = sorted(set(D["animal"][tr]))
    Xtr, st = design(D, tr, spec, None, levels)
    m = LogisticRegression(C=1e4, max_iter=3000).fit(Xtr, D["y"][tr])
    Xte, _ = design(D, te, spec, st, levels)
    p = np.full((len(te), 3), 1e-12)
    p[:, m.classes_] = m.predict_proba(Xte)
    return p / p.sum(1, keepdims=True)


def _fold(k: int, tr: np.ndarray, te: np.ndarray, D: dict) -> tuple[int, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    te = te[np.isin(D["animal"][te], np.unique(D["animal"][tr]))]
    full = {"L1": True, "hist": KEY}
    pf = _fit_predict(D, tr, te, full)
    pg = _fit_predict(D, tr, te, {"L1": True, "hist": None})
    trb = tr[~D["post_round"][tr]]
    pb = _fit_predict(D, trb, te, full)
    return k, te, pf, pg, pb


def predict(scorings: list[str], workers: int) -> None:
    from joblib import Parallel, delayed
    from sleep_model import PASS2MED, STATES, build_data, folds_of, records_for, to_arrays, variant_specs
    OUTD.mkdir(parents=True, exist_ok=True)
    gaps = gaps_table()
    for lab in scorings:
        t0 = time.time()
        recs = records_for(STATES if lab == "final" else PASS2MED)
        rs = round_starts(recs, gaps)
        steps = build_data(recs, {KEY: variant_specs()[KEY]})
        steps["s_since_rec_start"] = steps.bout_start + steps.elapsed
        steps["post_round"] = steps.record_id.isin(list(rs)) & (steps.s_since_rec_start < POST_S)
        steps["round_kind"] = steps.record_id.map(rs).fillna("")
        D = to_arrays(steps)
        D["post_round"] = steps.post_round.to_numpy()
        res = Parallel(n_jobs=workers, backend="loky")(delayed(_fold)(k, tr, te, D) for k, (tr, te) in enumerate(folds_of(D)))
        cols = {c: np.full(len(steps), np.nan) for c in ("p_stay", "p_rem", "p_wake", "p_rem_gate", "p_wake_gate", "pb_rem", "pb_wake")}
        for k, te, pf, pg, pb in res:
            cols["p_stay"][te], cols["p_rem"][te], cols["p_wake"][te] = pf[:, 0], pf[:, 1], pf[:, 2]
            cols["p_rem_gate"][te], cols["p_wake_gate"][te] = pg[:, 1], pg[:, 2]
            cols["pb_rem"][te], cols["pb_wake"][te] = pb[:, 1], pb[:, 2]
        out = steps[["animal", "record_id", "block", "bout_start", "elapsed", "t", "y", "post_round", "round_kind", "s_since_rec_start",
                     "d_prev", "dark"]].copy()
        for c, v in cols.items():
            out[c] = v
        out = out[out.p_wake.notna()]
        out["t"] = out.t.dt.strftime("%Y-%m-%d %H:%M:%S")
        out.to_csv(OUTD / f"heldout_steps_{lab}.csv.gz", index=False)
        print(f"[{lab}] {len(out)} held-out steps ({int(out.post_round.sum())} post-round), {len(rs)} round records; {time.time() - t0:.0f} s", flush=True)
    (OUTD / "README.md").write_text(
        "Held-out per-step predictions of the counter model (ephys/sleep_stability.py predict; definitions in its docstring).\n"
        "Columns: animal, record_id, block, bout_start, elapsed, t (field-PC), y (0 stay / 1 REM / 2 WAKE), post_round, round_kind,\n"
        "s_since_rec_start, d_prev, dark; p_stay, p_rem, p_wake (B-full at P_tw600_k0, forward chaining); p_rem_gate, p_wake_gate\n"
        "(clock + L1, no counter); pb_rem, pb_wake (B-full trained without the 3 h after round gaps).\n", encoding="utf-8")


# ------------------------------------------------------------------ helpers
def boot_blocks(df: pd.DataFrame, fn, n: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    blocks = df.block.unique()
    est = fn(df)
    vals = []
    by = {b: g for b, g in df.groupby("block")}
    for _ in range(n):
        s = rng.choice(blocks, len(blocks), replace=True)
        d = pd.concat([by[b] for b in s])
        try:
            vals.append(fn(d))
        except ValueError:
            continue
    lo, hi = np.nanpercentile(vals, [2.5, 97.5])
    return float(est), float(lo), float(hi)


def map_events(H: pd.DataFrame, ev: pd.DataFrame) -> pd.DataFrame:
    """Attach the held-out step (p_wake etc.) containing each (animal, t0)."""
    H = H.copy()
    H["t"] = pd.to_datetime(H.t)
    out = []
    for an, g in ev.groupby("animal"):
        h = H[H.animal == an].sort_values("t")
        if h.empty:
            continue
        idx = np.searchsorted(h.t.to_numpy(), g.t0.to_numpy(), side="right") - 1
        ok = idx >= 0
        hh = h.iloc[np.clip(idx, 0, len(h) - 1)]
        ok &= ((g.t0.to_numpy() - hh.t.to_numpy()) < np.timedelta64(10, "s"))
        gg = g.copy()
        for c in ("p_wake", "p_wake_gate", "p_rem", "block"):
            gg[c] = np.where(ok, hh[c].to_numpy(), np.nan if c != "block" else None)
        out.append(gg[ok])
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


# ------------------------------------------------------------------ S1
def s1(H: pd.DataFrame, lab: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    from sklearn.metrics import roc_auc_score
    E = pd.read_csv(LIB / "events.csv.gz", parse_dates=["t0"])
    Pp = pd.read_csv(LIB / "participants.csv.gz")
    CE = pd.read_csv(LIB / "control_events.csv.gz", parse_dates=["t0"])
    CP = pd.read_csv(LIB / "control_participants.csv.gz")
    A = Pp.merge(E[["event_id", "t0", "source"]], on=["event_id", "source"], how="left")
    A = A[(A.source == "movement") & (A.pre_state == "NREM")]
    C = CP.merge(CE[["event_id", "t0"]], on="event_id", how="left")
    C = C[C.pre_state == "NREM"].assign(role="control")
    X = map_events(H, pd.concat([A, C], ignore_index=True))
    X["woke60"] = X.woke60.astype(bool)
    X["late_ok"] = ~(X.woke60 & (X.wake_latency_s < 15))
    X["woke_late"] = X.woke60 & (X.wake_latency_s >= 15)
    rows = []
    fm = X[X.role == "first"]
    for out_name, d, ycol in (("woke60", fm, "woke60"), ("wake 15-60 s (A5 control)", fm[fm.late_ok], "woke_late")):
        for pcol, mod in (("p_wake", "B-full"), ("p_wake_gate", "gate")):
            est, lo, hi = boot_blocks(d, lambda q, y=ycol, p=pcol: roc_auc_score(q[y], q[p]))
            pa = d.groupby("animal").apply(lambda q, y=ycol, p=pcol: roc_auc_score(q[y], q[p]) if q[y].nunique() == 2 else np.nan,
                                           include_groups=False)
            rows.append({"scores": lab, "outcome": out_name, "model": mod, "n": len(d), "events_woke": int(d[ycol].sum()),
                         "auc": est, "ci_lo": lo, "ci_hi": hi, "animals_auc_gt_0.5": int((pa > 0.5).sum()), "animals": int(pa.notna().sum())})
        est, lo, hi = boot_blocks(d, lambda q, y=ycol: roc_auc_score(q[y], q.p_wake) - roc_auc_score(q[y], q.p_wake_gate))
        rows.append({"scores": lab, "outcome": out_name, "model": "B-full - gate", "n": len(d), "auc": est, "ci_lo": lo, "ci_hi": hi})
    T = pd.DataFrame(rows)
    X["exp60"] = 1 - (1 - X.p_wake) ** 6
    oe = X.groupby("role").apply(lambda g: pd.Series({"n": len(g), "observed": g.woke60.mean(), "expected": g.exp60.mean(),
                                                     "OE": g.woke60.mean() / g.exp60.mean()}), include_groups=False).reset_index()
    oe.insert(0, "scores", lab)
    c_oe = float(oe.loc[oe.role == "control", "OE"].iloc[0]) if (oe.role == "control").any() else np.nan
    oe["OE_vs_control"] = oe.OE / c_oe
    return T, oe


# ------------------------------------------------------------------ S2 / S2b
def s2(H: pd.DataFrame, recs: list[dict], lab: str) -> pd.DataFrame:
    from sleep_cycles import bouts
    H = H.copy()
    H["win"] = ""
    rr = H.round_kind.astype(str) != ""
    for name, lo, hi in (("0-1 h", 0, 3600), ("1-3 h", 3600, 3 * 3600)):
        m = rr & (H.s_since_rec_start >= lo) & (H.s_since_rec_start < hi)
        H.loc[m, "win"] = "round " + name
    # natural wakes >= 30 min inside records
    nat = []
    for rc in recs:
        bl = bouts(rc["state"])
        ends = [b for s, a, b in bl if s == W and (b - a) >= 1800]
        for k, e in enumerate(ends):
            nxt = [a for s, a, b in bl if s == W and (b - a) >= 1800 and a > e]
            stop = nxt[0] if nxt else len(rc["state"])
            nat.append((rc["record_id"], e, stop))
    NW = pd.DataFrame(nat, columns=["record_id", "e", "stop"])
    for rid, g in NW.groupby("record_id"):
        m = H.record_id == rid
        if not m.any():
            continue
        s = H.loc[m, "s_since_rec_start"].to_numpy()
        lab_arr = H.loc[m, "win"].to_numpy().astype(object)
        for r in g.itertuples():
            for name, lo, hi in (("0-1 h", 0, 3600), ("1-3 h", 3600, 3 * 3600)):
                mm = (s >= r.e + lo) & (s < min(r.e + hi, r.stop)) & (lab_arr == "")
                lab_arr[mm] = "natural wake >= 30 min " + name
        H.loc[m, "win"] = lab_arr
    rows = []
    for w, g in H[H.win != ""].groupby("win"):
        for ycode, ename in ((2, "WAKE"), (1, "REM")):
            for pcol, mod in ((f"p_{'wake' if ycode == 2 else 'rem'}", "S2 (seen)"), (f"pb_{'wake' if ycode == 2 else 'rem'}", "S2b (blind)")):
                est, lo, hi = boot_blocks(g, lambda q, yc=ycode, pc=pcol: (q.y == yc).sum() / q[pc].sum())
                pa = g.groupby("animal").apply(lambda q, yc=ycode, pc=pcol: (q.y == yc).sum() / q[pc].sum(), include_groups=False)
                rows.append({"scores": lab, "window": w, "transition": ename, "model": mod, "steps": len(g), "observed": int((g.y == ycode).sum()),
                             "expected": float(g[pcol].sum()), "OE": est, "ci_lo": lo, "ci_hi": hi,
                             "animals_OE_lt_1": int((pa < 1).sum()), "animals": len(pa)})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ S3
def round_metrics(recs: list[dict], rs: dict[int, str]) -> pd.DataFrame:
    from sleep_cycles import bouts
    rows = []
    for rc in recs:
        if rc["record_id"] not in rs:
            continue
        st = rc["state"]
        L = len(st)
        r = {"record_id": rc["record_id"], "animal": rc["animal"], "kind": rs[rc["record_id"]], "len_s": L}
        for h in (1, 3, 6):
            n = h * 3600
            if L >= n:
                seg = st[:n]
                r[f"rem_min_{h}h"] = (seg == R).sum() / 60
                r[f"nrem_min_{h}h"] = (seg == N).sum() / 60
                r[f"rem_bouts_{h}h"] = sum(1 for s, a, b in bouts(seg) if s == R)
        on = np.flatnonzero(st == R)
        r["lat_s"], r["lat_ev"] = (int(on[0]), 1) if len(on) else (L, 0)
        rows.append(r)
    return pd.DataFrame(rows)


def _s3_rep(rep: int, recs: list[dict], M: dict, rs: dict) -> pd.DataFrame:
    from sleep_sim import simulate_records
    return round_metrics(simulate_records(recs, M, 50_000 + rep), rs).assign(rep=rep)


def s3(recs: list[dict], rs: dict[int, str], lab: str, reps: int, workers: int) -> pd.DataFrame:
    from joblib import Parallel, delayed
    from sleep_schedule_phase3 import km_median
    from sleep_sim import build_model, record_inputs, simulate_records
    masked = []
    for rc in recs:
        st = rc["state"].copy()
        if rc["record_id"] in rs:
            st[:POST_S] = 0
        masked.append({**rc, "state": st})
    obs = round_metrics(recs, rs)
    out = []
    for variant, fit_recs in (("blind (post-round 3 h masked in the fit)", masked), ("fitted on all data", recs)):
        M = build_model(fit_recs)
        M["inputs"] = [record_inputs(rc, M["levels"]) for rc in recs]          # forced blocks from the ORIGINAL records
        simulate_records(recs[:1], M, 0)
        S = pd.concat(Parallel(n_jobs=workers, backend="loky")(delayed(_s3_rep)(r, recs, M, rs) for r in range(reps)), ignore_index=True)
        mets = [c for c in obs.columns if c.endswith(("h",)) and c.startswith(("rem_", "nrem_"))]
        for kind in ("morning", "evening"):
            o = obs[obs.kind == kind]
            s = S[S.kind == kind]
            for c in mets:
                ov = o[c].dropna()
                sv = s.groupby("rep")[c].mean()
                lo, hi = np.percentile(sv, [2.5, 97.5])
                out.append({"scores": lab, "variant": variant, "kind": kind, "metric": c, "rounds": len(ov), "observed": float(ov.mean()),
                            "sim_mean": float(sv.mean()), "sim_2.5%": lo, "sim_97.5%": hi, "inside": bool(lo <= ov.mean() <= hi)})
            olat = km_median(o.lat_s.to_numpy(), o.lat_ev.to_numpy())
            sl = s.groupby("rep").apply(lambda g: km_median(g.lat_s.to_numpy(), g.lat_ev.to_numpy()), include_groups=False)
            lo, hi = np.nanpercentile(sl, [2.5, 97.5])
            out.append({"scores": lab, "variant": variant, "kind": kind, "metric": "first_REM_latency_KM_median_s", "rounds": len(o),
                        "observed": olat, "sim_mean": float(np.nanmean(sl)), "sim_2.5%": lo, "sim_97.5%": hi, "inside": bool(lo <= olat <= hi)})
        print(f"[{lab}] S3 {variant} done", flush=True)
    return pd.DataFrame(out)


# ------------------------------------------------------------------ analyse
def analyse(a) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from _common import git_commit, write_json
    from output_paths import figure_dir, report_dir, run_dir
    from sleep_model import PASS2MED, STATES, records_for
    from sleep_quant import md_table, save_fig
    out = run_dir("sleep_explore_S", "2026c")
    rd, fd = report_dir("2026c", "ephys_spikes"), figure_dir("2026c", "ephys_spikes")
    gc = git_commit()
    t0 = time.time()
    gaps = gaps_table()
    T1, OE, T2, T3 = [], [], [], []
    for lab in a.scorings:
        H = pd.read_csv(OUTD / f"heldout_steps_{lab}.csv.gz")
        H["round_kind"] = H.round_kind.fillna("")
        recs = records_for(STATES if lab == "final" else PASS2MED)
        rs = round_starts(recs, gaps)
        t1, oe = s1(H, lab)
        T1.append(t1)
        OE.append(oe)
        T2.append(s2(H, recs, lab))
        print(f"[{lab}] S1 / S2 {time.time() - t0:.0f} s", flush=True)
        T3.append(s3(recs, rs, lab, a.reps, a.workers))
    T1, OE, T2, T3 = (pd.concat(x, ignore_index=True) for x in (T1, OE, T2, T3))
    for name, T in (("S1_auc", T1), ("S1_oe", OE), ("S2_oe", T2), ("S3_response", T3)):
        T.to_csv(rd / f"ephys_spikes_sleep_explore_S_{name}_2026c.csv", index=False)
    # verdicts
    v = []
    for lab in a.scorings:
        q = T1[(T1.scores == lab) & (T1.outcome == "woke60")]
        bf = q[q.model == "B-full"].iloc[0]
        df_ = q[q.model == "B-full - gate"].iloc[0]
        ok = bf.auc >= 0.6 and bf.ci_lo > 0.5 and df_.ci_lo > 0 and bf["animals_auc_gt_0.5"] >= 5
        v.append({"scores": lab, "part": "S1", "rule": "AUC >= 0.60, CI > 0.5, above gate (diff CI > 0), >= 5/6 rats",
                  "pass": ok, "numbers": f"AUC {bf.auc:.3f} [{bf.ci_lo:.3f}, {bf.ci_hi:.3f}], gate diff {df_.auc:+.3f} [{df_.ci_lo:+.3f}, {df_.ci_hi:+.3f}], rats {bf['animals_auc_gt_0.5']:.0f}/{bf.animals:.0f}"})
        for mod, part in (("S2 (seen)", "S2"), ("S2b (blind)", "S2b")):
            for tr in (("WAKE",) if part == "S2" else ("WAKE", "REM")):
                rows = T2[(T2.scores == lab) & (T2.model == mod) & (T2.transition == tr) & T2.window.str.startswith("round")]
                ok = bool(((rows.OE >= 0.8) & (rows.OE <= 1.25) & (rows.ci_lo <= 1) & (rows.ci_hi >= 1)).all())
                v.append({"scores": lab, "part": f"{part} {tr}", "rule": "post-round O/E in [0.8, 1.25], CI includes 1 (0-1 h and 1-3 h)", "pass": ok,
                          "numbers": "; ".join(f"{r.window}: {r.OE:.2f} [{r.ci_lo:.2f}, {r.ci_hi:.2f}]" for r in rows.itertuples())})
        rows = T3[(T3.scores == lab) & T3.variant.str.startswith("blind")]
        need = rows[rows.metric.str.match(r"(rem|nrem)_min_\dh") | (rows.metric == "first_REM_latency_KM_median_s")]
        v.append({"scores": lab, "part": "S3", "rule": "observed inside the simulated 95 % range: REM / NREM min at 1, 3, 6 h and the latency (blind fit)",
                  "pass": bool(need.inside.all()), "numbers": f"{int(need.inside.sum())}/{len(need)} inside; outside: " +
                  ", ".join(f"{r.kind} {r.metric} obs {r.observed:.1f} vs {r['sim_2.5%']:.1f}-{r['sim_97.5%']:.1f}" for _, r in need[~need.inside].iterrows())})
    V = pd.DataFrame(v)
    V.to_csv(rd / "ephys_spikes_sleep_explore_S_verdicts_2026c.csv", index=False)
    # figure: S3 observed vs simulated
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.5))
    for ax, kind in zip(axs, ("morning", "evening")):
        q = T3[(T3.scores == a.scorings[0]) & T3.variant.str.startswith("blind") & (T3.kind == kind) & T3.metric.str.contains("_min_")]
        x = np.arange(len(q))
        ax.errorbar(x, q.sim_mean, yerr=[q.sim_mean - q["sim_2.5%"], q["sim_97.5%"] - q.sim_mean], fmt="o", label="simulated (blind fit), 95 %")
        ax.plot(x, q.observed, "rs", label="observed")
        ax.set_xticks(x, q.metric, rotation=60, fontsize=7)
        ax.set_title(f"{kind} rounds", fontsize=9)
        ax.legend(fontsize=7)
    fig.suptitle(f"S3: sleep after the battery rounds, observed vs the counter rules never fitted on post-round data  {gc}", fontsize=9)
    save_fig(fig, fd / "ephys_spikes_sleep_explore_S_response_2026c.png")
    L = ["# Sleep-behaviour explore — S: can the counter model predict sleep stability? (cohort 2026c)", "",
         "Plan [implementation_plan/2026-10-08-sleep-behaviour-explore.md](../../../../implementation_plan/2026-10-08-sleep-behaviour-explore.md) "
         f"§9 Amendment 1 + addendum (rules written before results). Driver `ephys/sleep_stability.py` (commit {gc}); bulk `{out}`; "
         f"held-out steps `{OUTD}`; runtime {(time.time() - t0) / 60:.0f} min. **Technical ledger.**", "",
         "## Definitions", "", "```", (__doc__ or "").strip(), "```", "",
         "## Verdicts", "", *md_table(V), "",
         "## S1 (a): which movements end in waking — AUC of the model's propensity", "", *md_table(T1.round(4)), "",
         "## S1 (b): observed / expected waking by role", "", *md_table(OE.round(4)), "",
         "## S2 / S2b: transitions after rounds and after natural long wakes, observed / expected", "", *md_table(T2.round(4)), "",
         "## S3: the simulated perturbation response", "", *md_table(T3.round(3)), "",
         "![](../figures/ephys_spikes_sleep_explore_S_response_2026c.png)", ""]
    (rd / "ephys_spikes_sleep_explore_S_2026c.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    write_json(rd / "run_manifest_sleep_explore_S_2026c.json", {"run_dir": str(out), "git_commit": gc, "heldout_steps": str(OUTD), "reps": a.reps})
    print(V.to_string(index=False), flush=True)
    print("written", rd / "ephys_spikes_sleep_explore_S_2026c.md", flush=True)


# ------------------------------------------------------------------ selftest
def selftest() -> None:
    from sklearn.metrics import roc_auc_score
    rng = np.random.default_rng(1)
    n = 6000
    df = pd.DataFrame({"block": rng.integers(0, 20, n).astype(str), "animal": rng.choice(list("ABCDEF"), n)})
    df["p_wake"] = rng.uniform(0.01, 0.2, n)
    df["p_wake_gate"] = df.p_wake.mean()
    df["y"] = np.where(rng.random(n) < df.p_wake, 2, 0)
    est, lo, hi = boot_blocks(df, lambda q: (q.y == 2).sum() / q.p_wake.sum(), n=300)
    assert lo <= 1 <= hi and abs(est - 1) < 0.1, (est, lo, hi)
    df["woke"] = df.y == 2
    auc = roc_auc_score(df.woke, df.p_wake)
    assert auc > 0.6, auc
    H = pd.DataFrame({"animal": ["A"] * 3, "t": ["2026-09-01 00:00:00", "2026-09-01 00:00:10", "2026-09-01 00:00:20"],
                      "p_wake": [0.1, 0.2, 0.3], "p_wake_gate": [0.1] * 3, "p_rem": [0.0] * 3, "block": ["b"] * 3})
    ev = pd.DataFrame({"animal": ["A", "A", "A"], "t0": pd.to_datetime(["2026-09-01 00:00:15", "2026-09-01 00:00:29", "2026-09-01 00:00:45"])})
    m = map_events(H, ev)
    assert list(m.p_wake) == [0.2, 0.3], m
    print("selftest PASS: block bootstrap O/E ~ 1 under the model; AUC of an informative propensity > 0.6; event -> step mapping", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["predict", "analyse"])
    ap.add_argument("--scorings", nargs="+", default=["final", "pass2med"], choices=["final", "pass2med"])
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--reps", type=int, default=100)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    elif a.cmd == "predict":
        predict(a.scorings, a.workers)
    elif a.cmd == "analyse":
        analyse(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
