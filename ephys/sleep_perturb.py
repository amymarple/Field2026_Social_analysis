r"""Part P of Amendment 2 of the sleep-behaviour explore (plan implementation_plan/2026-10-08-sleep-behaviour-explore.md
§10, written before results): the perturbation dynamics — does a decaying arousal after the battery rounds, fitted only
on whether the rats woke, capture the acute waking excess (#44) and explain the later first REM (#47) without any
REM-side variable?

Usage:  python ephys/sleep_perturb.py run [--scorings final pass2med] [--reps 100] [--workers 8]
        python ephys/sleep_perturb.py --selftest

Definitions (records, 10-s NREM steps, usable round gaps and the two scorings as sleep_model.py / sleep_stability.py):
  arousal term   on the NREM -> WAKE logit only: eta_WAKE += a * exp(-s / tau_A), s = seconds from the start of the
                 post-round record to the step start; tau_A in {600, 1200, 2400, 4800} s. The stay and REM logits are
                 untouched, so P(REM | not WAKE) is unchanged. With the base model's p_WAKE as offset,
                 P(WAKE) = sigmoid(logit p_WAKE + a h(s)), h = exp(-s / tau_A); a = the maximum-likelihood estimate of this
                 binary likelihood (Newton), (a, tau_A) = the grid point with the highest likelihood. Applied to a base
                 prediction: p'_W = sigmoid(logit p_W + a h), p'_stay = p_stay (1 - p'_W) / (1 - p_W), p'_REM likewise.
  base (step level)   B-full at P_tw600_k0 (Step B's spec) fitted on all NREM steps except those in the 3 h after a
                 usable round gap ("blind"). The symmetric base also leaves out the 3 h after natural wakes >= 30 min
                 inside records (steps already post-round count as post-round).
  base (generative)   sleep_sim v2 fitted on the records with every post-round 3 h masked (= S3 blind); the arousal is
                 estimated against its NREM model's predictions of the (unseen) post-round steps.
  cross-fit      rounds split by the parity of the round record's start date (days since 2026-08-30); every round is
                 predicted / simulated with (a, tau_A) fitted on the other half.
  P1   cross-fitted blind + A vs blind on the post-round steps (0-3 h): Delta log-loss % = 100 (sum nll_A - sum nll_b) /
       sum nll_b, 95 % CI by block bootstrap (2000 resamples of day-half blocks), animals better = mean per-step
       difference < 0; pass = CI < 0 and >= 5/6. And the 0-1 h WAKE O/E with A (sum [y = WAKE] / sum p'_W, block
       bootstrap CI) in [0.8, 1.25] with CI including 1.
  P1b  a_round - a_nat, both fitted on all events against the symmetric base, a_nat at the round's tau_A (a_nat at its
       own best tau_A reported); 95 % CI by block bootstrap with a refitted at the fixed tau_A per resample; pass = CI > 0.
  P2   100 replicates of the cross-fitted simulation with A (seeds as S3); per round S3's measures
       (sleep_stability.round_metrics: REM / NREM min and REM bouts in 1 / 3 / 6 h, first-REM latency, KM median over
       rounds); pass = the observed first-REM KM median inside the simulated 2.5-97.5 % range for morning AND evening
       rounds, and >= 12 of the 14 measures (REM / NREM min at 1, 3, 6 h and the latency, x 2 kinds) inside.
  P3   Step E's checks (i), (iii), (iv) (sleep_sim.metrics, Step E's tolerances) on all records simulated with A:
       >= 27 of 28 pass and not fewer than the same blind model without A.
  P4   gap-length tertiles within each kind (gap = the usable round gap before the record; cut points from the observed
       rounds): observed vs simulated (with A) REM / NREM min at 1 and 3 h and the latency; description.
  residual   with A: S3's morning REM at 3 h, and D2's morning REM payback (sleep_explore_d.payback_from_records, slope of
       pay_rem on debt_rem, day-demeaned, B = 1 / 3 h) on the simulated records vs observed. Part Q is warranted only if
       a REM residual lies outside the simulated range in the same direction on both scorings.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from sleep_cycles import bouts  # noqa: E402
from sleep_schedule import W  # noqa: E402

KEY = "P_tw600_k0"
SPEC = {"L1": True, "hist": KEY}
POST_S = 3 * 3600
NAT_S = 1800
TAUS = [600.0, 1200.0, 2400.0, 4800.0]
DAY0 = pd.Timestamp("2026-08-30")
E_TOL = {"rem_h_per_24h": 0.25, "nrem_h_per_24h": 0.10, "sd_rem_daily": 0.25, "sd_nrem_daily": 0.25,
         "rem_share_light": 0.20, "rem_share_dark": 0.20, "rem_per_h_nrem_light": 0.20, "rem_per_h_nrem_dark": 0.20}


# ------------------------------------------------------------------ the arousal term (pure; selftested)
def logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return np.log(p / (1 - p))


def sig(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def newton_a(o: np.ndarray, h: np.ndarray, yw: np.ndarray) -> tuple[float, float, float]:
    a, H = 0.0, 0.0
    for _ in range(100):
        p = sig(o + a * h)
        g = float(np.sum((yw - p) * h))
        H = float(np.sum(p * (1 - p) * h * h))
        if H <= 0:
            break
        st = g / H
        a += st
        if abs(st) < 1e-9:
            break
    p = np.clip(sig(o + a * h), 1e-12, 1 - 1e-12)
    ll = float(np.sum(yw * np.log(p) + (1 - yw) * np.log(1 - p)))
    return a, ll, (1 / np.sqrt(H)) if H > 0 else np.nan


def fit_arousal(pw: np.ndarray, s: np.ndarray, y: np.ndarray, taus=TAUS) -> tuple[dict, pd.DataFrame]:
    o, yw = logit(pw), (y == 2).astype(float)
    rows = []
    for tau in taus:
        a, ll, se = newton_a(o, np.exp(-s / tau), yw)
        rows.append({"tau_s": tau, "a": a, "se": se, "ll": ll, "n": len(y), "wakes": int(yw.sum())})
    G = pd.DataFrame(rows)
    return G.loc[G.ll.idxmax()].to_dict(), G


def apply_arousal(P: np.ndarray, a: float, tau: float, s: np.ndarray) -> np.ndarray:
    pw = np.clip(P[:, 2], 1e-12, 1 - 1e-12)
    pw2 = sig(logit(pw) + a * np.exp(-s / tau))
    sc = (1 - pw2) / (1 - pw)
    out = P.copy()
    out[:, 0] *= sc
    out[:, 1] *= sc
    out[:, 2] = pw2
    return out


def nll(P: np.ndarray, y: np.ndarray) -> np.ndarray:
    return -np.log(np.clip(P[np.arange(len(y)), y], 1e-12, None))


def crossfit(Pb: np.ndarray, s: np.ndarray, y: np.ndarray, half: np.ndarray) -> tuple[np.ndarray, dict]:
    """par[h] = (a, tau) fitted on the half != h and applied to half h."""
    PA, par = Pb.copy(), {}
    for h in (0, 1):
        tr, te = half != h, half == h
        best, _ = fit_arousal(Pb[tr, 2], s[tr], y[tr])
        par[h] = best
        PA[te] = apply_arousal(Pb[te], best["a"], best["tau_s"], s[te])
    return PA, par


# ------------------------------------------------------------------ data
def round_info(recs: list[dict], gaps: pd.DataFrame) -> pd.DataFrame:
    g = gaps[gaps.usable & gaps.cause.isin(["round_logged", "round_inferred"])]
    rows = []
    for rc in recs:
        m = g[(g.animal == rc["animal"]) & ((g.gap_end - rc["start"]).abs() <= pd.Timedelta(seconds=5))]
        if len(m):
            r = m.iloc[0]
            rows.append({"record_id": rc["record_id"], "animal": rc["animal"], "kind": str(r.kind),
                         "gap_min": (r.gap_end - r.gap_start).total_seconds() / 60,
                         "half": int((rc["start"].normalize() - DAY0).days % 2)})
    return pd.DataFrame(rows)


def step_table(recs: list[dict], RI: pd.DataFrame, post_s: int = POST_S) -> dict:
    from sleep_model import build_data, to_arrays, variant_specs
    steps = build_data(recs, {KEY: variant_specs()[KEY]})
    D = to_arrays(steps)
    s = (steps.bout_start + steps.elapsed).to_numpy(float)
    rmap = RI.set_index("record_id")
    is_r = steps.record_id.isin(rmap.index).to_numpy()
    post = is_r & (s < post_s)
    half = np.full(len(steps), -1)
    half[is_r] = steps.record_id[is_r].map(rmap.half).to_numpy()
    s_nat = np.full(len(steps), np.inf)
    half_nat = np.full(len(steps), -1)
    byrid = {rc["record_id"]: rc for rc in recs}
    for rid, idx in steps.groupby("record_id").indices.items():
        rc = byrid[rid]
        ends = np.array([b for st_, a_, b in bouts(rc["state"]) if st_ == W and (b - a_) >= NAT_S])
        if not len(ends):
            continue
        t = s[idx]
        k = np.searchsorted(ends, t, side="right") - 1
        ok = k >= 0
        e = ends[k[ok]]
        s_nat[idx[ok]] = t[ok] - e
        half_nat[idx[ok]] = ((rc["start"] + pd.to_timedelta(e, unit="s")).normalize() - DAY0).days.to_numpy() % 2
    nat = (s_nat < POST_S) & ~post
    return {"steps": steps, "D": D, "s": s, "post": post, "half": half, "s_nat": s_nat, "nat": nat, "half_nat": half_nat}


def fit_base(D: dict, mask: np.ndarray):
    from sklearn.linear_model import LogisticRegression
    from sleep_model import design
    tr = np.flatnonzero(mask)
    levels = sorted(set(D["animal"][tr]))
    X, st = design(D, tr, SPEC, None, levels)
    m = LogisticRegression(C=1e4, max_iter=3000).fit(X, D["y"][tr])
    return m, st, levels


def predict(D: dict, idx: np.ndarray, m, st, levels) -> np.ndarray:
    from sleep_model import design
    X, _ = design(D, idx, SPEC, st, levels)
    P = np.full((len(idx), 3), 1e-12)
    P[:, m.classes_] = m.predict_proba(X)
    return P / P.sum(1, keepdims=True)


# ------------------------------------------------------------------ P1 / P1b
def step_part(lab: str, T: dict, boot: int = 2000) -> dict:
    from sleep_stability import boot_blocks
    D, s, post, half = T["D"], T["s"], T["post"], T["half"]
    pr = np.flatnonzero(post)
    m, st, lv = fit_base(D, ~post)
    Pb = predict(D, pr, m, st, lv)
    y, sp, hp = D["y"][pr].astype(int), s[pr], half[pr]
    PA, par = crossfit(Pb, sp, y, hp)
    best_all, grid_all = fit_arousal(Pb[:, 2], sp, y)
    df = pd.DataFrame({"block": D["block"][pr], "animal": D["animal"][pr], "y": y, "s": sp, "nll_b": nll(Pb, y), "nll_a": nll(PA, y),
                       "pw_b": Pb[:, 2], "pw_a": PA[:, 2], "pr_b": Pb[:, 1], "pr_a": PA[:, 1]})
    est, lo, hi = boot_blocks(df, lambda q: 100 * (q.nll_a.sum() - q.nll_b.sum()) / q.nll_b.sum(), n=boot)
    pa = df.groupby("animal").apply(lambda q: (q.nll_a - q.nll_b).mean(), include_groups=False)
    held = {"scores": lab, "steps": len(df), "wakes": int((df.y == 2).sum()), "rems": int((df.y == 1).sum()), "delta_pct": est, "ci_lo": lo,
            "ci_hi": hi, "animals_better": int((pa < 0).sum()), "animals": len(pa), "holds": bool(hi < 0 and (pa < 0).sum() >= 5)}
    oe = []
    for wname, a0, a1 in (("0-1 h", 0, 3600), ("1-3 h", 3600, POST_S)):
        g = df[(df.s >= a0) & (df.s < a1)]
        for tr, yc, cb, ca in (("WAKE", 2, "pw_b", "pw_a"), ("REM", 1, "pr_b", "pr_a")):
            for mod, c in (("blind", cb), ("blind + A (cross-fitted)", ca)):
                e, l_, h_ = boot_blocks(g, lambda q, yc=yc, c=c: (q.y == yc).sum() / q[c].sum(), n=boot)
                pa2 = g.groupby("animal").apply(lambda q, yc=yc, c=c: (q.y == yc).sum() / q[c].sum(), include_groups=False)
                oe.append({"scores": lab, "window": wname, "transition": tr, "model": mod, "steps": len(g), "observed": int((g.y == yc).sum()),
                           "expected": float(g[c].sum()), "OE": e, "ci_lo": l_, "ci_hi": h_, "animals_OE_gt_1": int((pa2 > 1).sum()), "animals": len(pa2)})
    # time course (10-min bins) for the figure
    df["bin"] = (df.s // 600).astype(int)
    tc = df.groupby("bin").agg(obs=("y", lambda v: (v == 2).sum()), exp_b=("pw_b", "sum"), exp_a=("pw_a", "sum"), n=("y", "size")).reset_index()
    tc.insert(0, "scores", lab)
    # P1b: symmetric base, round vs natural
    nat = T["nat"]
    ms, sts, lvs = fit_base(D, ~post & ~nat)
    nr = np.flatnonzero(nat)
    Pr, Pn = predict(D, pr, ms, sts, lvs), predict(D, nr, ms, sts, lvs)
    yn, sn = D["y"][nr].astype(int), T["s_nat"][nr]
    br, gr = fit_arousal(Pr[:, 2], sp, y)
    bn, gn = fit_arousal(Pn[:, 2], sn, yn)
    tau_r = br["tau_s"]
    a_n_at_r, _, se_n = newton_a(logit(Pn[:, 2]), np.exp(-sn / tau_r), (yn == 2).astype(float))
    rng = np.random.default_rng(0)
    blk_r, blk_n = D["block"][pr], D["block"][nr]
    blocks = np.unique(np.r_[blk_r, blk_n])
    ir = {b: np.flatnonzero(blk_r == b) for b in blocks}
    inn = {b: np.flatnonzero(blk_n == b) for b in blocks}
    o_r, h_r, w_r = logit(Pr[:, 2]), np.exp(-sp / tau_r), (y == 2).astype(float)
    o_n, h_n, w_n = logit(Pn[:, 2]), np.exp(-sn / tau_r), (yn == 2).astype(float)
    diffs = []
    for _ in range(boot):
        bs = rng.choice(blocks, len(blocks), replace=True)
        jr = np.concatenate([ir[b] for b in bs])
        jn = np.concatenate([inn[b] for b in bs])
        if len(jr) < 50 or len(jn) < 50:
            continue
        diffs.append(newton_a(o_r[jr], h_r[jr], w_r[jr])[0] - newton_a(o_n[jn], h_n[jn], w_n[jn])[0])
    dlo, dhi = np.percentile(diffs, [2.5, 97.5])
    sym = {"scores": lab, "tau_round_s": tau_r, "a_round": br["a"], "a_round_se": br["se"], "steps_round": len(y),
           "a_nat_at_round_tau": a_n_at_r, "a_nat_se": se_n, "a_nat_own_tau_s": bn["tau_s"], "a_nat_own": bn["a"], "steps_nat": len(yn),
           "diff": br["a"] - a_n_at_r, "diff_ci_lo": dlo, "diff_ci_hi": dhi, "holds": bool(dlo > 0)}
    params = []
    for h, b in par.items():
        params.append({"scores": lab, "base": "step-level blind", "fit_on": f"half != {h}", "applied_to": f"half {h}", **{k: b[k] for k in ("tau_s", "a", "se", "ll", "n", "wakes")}})
    params.append({"scores": lab, "base": "step-level blind", "fit_on": "all rounds", "applied_to": "-", **{k: best_all[k] for k in ("tau_s", "a", "se", "ll", "n", "wakes")}})
    grids = pd.concat([grid_all.assign(scores=lab, fit="step-level blind, all rounds"), gr.assign(scores=lab, fit="symmetric base, rounds"),
                       gn.assign(scores=lab, fit="symmetric base, natural wakes >= 30 min")], ignore_index=True)
    return {"held": held, "oe": pd.DataFrame(oe), "tc": tc, "sym": sym, "params": pd.DataFrame(params), "grids": grids}


# ------------------------------------------------------------------ P2-P4 + residual (generative)
def _rep(rep: int, recs: list[dict], M: dict, rs: dict, gaps: pd.DataFrame, AR: dict, lab: str) -> dict:
    from sleep_explore_d import payback_from_records
    from sleep_sim import metrics, simulate_records
    from sleep_stability import round_metrics
    out = {}
    for var, ar in (("blind", None), ("blind + A", AR)):
        sim = simulate_records(recs, M, 50_000 + rep, arousal=ar)
        out[var] = {"rm": round_metrics(sim, rs).assign(rep=rep), "E": {"rep": rep, **metrics(sim)},
                    "pb": payback_from_records(sim, gaps, f"{lab}_P_{var}_{rep}").assign(rep=rep)}
    return out


def gen_part(lab: str, recs: list[dict], RI: pd.DataFrame, gaps: pd.DataFrame, T: dict, reps: int, workers: int) -> dict:
    from joblib import Parallel, delayed
    from sleep_explore_d import payback_from_records
    from sleep_schedule_phase3 import km_median
    from sleep_sim import build_model, metrics, record_inputs, simulate_records
    from sleep_stability import round_metrics
    rs = dict(zip(RI.record_id, RI.kind))
    masked = []
    for rc in recs:
        st = rc["state"].copy()
        if rc["record_id"] in rs:
            st[:POST_S] = 0
        masked.append({**rc, "state": st})
    M = build_model(masked)
    M["inputs"] = [record_inputs(rc, M["levels"]) for rc in recs]
    pr = np.flatnonzero(T["post"])
    Pg = predict(T["D"], pr, M["mN"], M["stN"], M["levels"])
    y, sp, hp = T["D"]["y"][pr].astype(int), T["s"][pr], T["half"][pr]
    par = {}
    for h in (0, 1):
        par[h], _ = fit_arousal(Pg[hp != h, 2], sp[hp != h], y[hp != h])
    best_all, _ = fit_arousal(Pg[:, 2], sp, y)
    AR = {r.record_id: (float(par[r.half]["a"]), float(par[r.half]["tau_s"])) for r in RI.itertuples()}
    params = [{"scores": lab, "base": "generative (S3 blind)", "fit_on": f"half != {h}", "applied_to": f"half {h}",
               **{k: par[h][k] for k in ("tau_s", "a", "se", "ll", "n", "wakes")}} for h in (0, 1)]
    params.append({"scores": lab, "base": "generative (S3 blind)", "fit_on": "all rounds", "applied_to": "-",
                   **{k: best_all[k] for k in ("tau_s", "a", "se", "ll", "n", "wakes")}})
    simulate_records(recs[:1], M, 0)
    res = Parallel(n_jobs=workers, backend="loky")(delayed(_rep)(r, recs, M, rs, gaps, AR, lab) for r in range(reps))
    obs_rm = round_metrics(recs, rs).merge(RI[["record_id", "gap_min"]], on="record_id")
    obs_E = metrics(recs)
    obs_pb = payback_from_records(recs, gaps, f"{lab}_P_observed")
    S3, EC, TER, RES = [], [], [], []
    mets = [f"{q}_min_{h}h" for h in (1, 3, 6) for q in ("rem", "nrem")]
    for var in ("blind", "blind + A"):
        S = pd.concat([r[var]["rm"] for r in res], ignore_index=True).merge(RI[["record_id", "gap_min"]], on="record_id")
        for kind in ("morning", "evening"):
            o, sk = obs_rm[obs_rm.kind == kind], S[S.kind == kind]
            for c in mets + ["rem_bouts_1h", "rem_bouts_3h"]:
                ov = o[c].dropna()
                sv = sk.groupby("rep")[c].mean()
                lo, hi = np.percentile(sv, [2.5, 97.5])
                S3.append({"scores": lab, "variant": var, "kind": kind, "metric": c, "rounds": len(ov), "observed": float(ov.mean()),
                           "sim_mean": float(sv.mean()), "sim_2.5%": lo, "sim_97.5%": hi, "inside": bool(lo <= ov.mean() <= hi)})
            olat = km_median(o.lat_s.to_numpy(), o.lat_ev.to_numpy())
            sl = sk.groupby("rep").apply(lambda g: km_median(g.lat_s.to_numpy(), g.lat_ev.to_numpy()), include_groups=False)
            lo, hi = np.nanpercentile(sl, [2.5, 97.5])
            S3.append({"scores": lab, "variant": var, "kind": kind, "metric": "first_REM_latency_KM_median_s", "rounds": len(o), "observed": olat,
                       "sim_mean": float(np.nanmean(sl)), "sim_2.5%": lo, "sim_97.5%": hi, "inside": bool(lo <= olat <= hi)})
            if var == "blind + A":                                  # P4: gap-length tertiles within the kind
                cuts = np.quantile(o.gap_min, [0, 1 / 3, 2 / 3, 1])
                cuts[0], cuts[-1] = -np.inf, np.inf
                o2 = o.assign(ter=pd.cut(o.gap_min, cuts, labels=["short", "middle", "long"]))
                s2 = sk.assign(ter=pd.cut(sk.gap_min, cuts, labels=["short", "middle", "long"]))
                for ter in ("short", "middle", "long"):
                    ot, stt = o2[o2.ter == ter], s2[s2.ter == ter]
                    row = {"scores": lab, "kind": kind, "tertile": ter, "rounds": len(ot), "gap_min_median": float(ot.gap_min.median())}
                    for c in ("rem_min_1h", "nrem_min_1h", "rem_min_3h", "nrem_min_3h"):
                        sv = stt.groupby("rep")[c].mean()
                        row[f"{c}_obs"], row[f"{c}_sim"] = float(ot[c].mean()), float(sv.mean())
                        row[f"{c}_lo"], row[f"{c}_hi"] = np.percentile(sv, [2.5, 97.5]) if len(sv) else (np.nan, np.nan)
                    row["lat_obs_s"] = km_median(ot.lat_s.to_numpy(), ot.lat_ev.to_numpy())
                    slt = stt.groupby("rep").apply(lambda g: km_median(g.lat_s.to_numpy(), g.lat_ev.to_numpy()), include_groups=False)
                    row["lat_sim_s"] = float(np.nanmean(slt))
                    row["lat_lo_s"], row["lat_hi_s"] = np.nanpercentile(slt, [2.5, 97.5])
                    TER.append(row)
        E = pd.DataFrame([r[var]["E"] for r in res])
        tol = dict(E_TOL, **{k: 0.25 for k in obs_E if k.startswith("lat_med_")})
        for k, tl in tol.items():
            ov = obs_E.get(k, np.nan)
            sv = E[k].to_numpy(dtype=float) if k in E else np.array([np.nan])
            if not np.isfinite(ov) or not np.isfinite(sv).any():
                continue
            mean = float(np.nanmean(sv))
            EC.append({"scores": lab, "variant": var, "metric": k, "observed": ov, "sim_mean": mean, "rel_diff": mean / ov - 1,
                       "tolerance": tl, "pass": bool(abs(mean / ov - 1) <= tl)})
        PB = pd.concat([r[var]["pb"] for r in res], ignore_index=True)
        for B in (1, 3):
            for dd, stat in ((True, "slope"), (False, "mean_y")):
                sel = lambda t: t[(t.kind == "morning") & (t.B_h == B) & (t.outcome == "pay_rem") & (t.predictors == "debt_rem") & (t.day_demeaned == dd)]
                ov = float(sel(obs_pb)[stat].iloc[0])
                sv = sel(PB)[stat].to_numpy(float)
                lo, hi = np.nanpercentile(sv, [2.5, 97.5])
                RES.append({"scores": lab, "variant": var, "quantity": f"morning REM payback {stat} ({'day-demeaned' if dd else 'raw'}), B = {B} h",
                            "observed": ov, "sim_mean": float(np.nanmean(sv)), "sim_2.5%": lo, "sim_97.5%": hi,
                            "side": "above" if ov > hi else ("below" if ov < lo else "inside")})
    S3 = pd.DataFrame(S3)
    for _, r in S3[(S3.metric == "rem_min_3h") & (S3.kind == "morning")].iterrows():
        lo, hi = r["sim_2.5%"], r["sim_97.5%"]
        RES.append({"scores": lab, "variant": r.variant, "quantity": "S3 morning REM min in 3 h", "observed": r.observed, "sim_mean": r.sim_mean,
                    "sim_2.5%": lo, "sim_97.5%": hi, "side": "above" if r.observed > hi else ("below" if r.observed < lo else "inside")})
    return {"params": pd.DataFrame(params), "s3": S3, "echecks": pd.DataFrame(EC), "tertiles": pd.DataFrame(TER), "residual": pd.DataFrame(RES)}


# ------------------------------------------------------------------ run
def run(a) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from _common import git_commit, write_json
    from output_paths import figure_dir, report_dir, run_dir
    from sleep_model import PASS2MED, STATES, records_for
    from sleep_quant import md_table, save_fig
    from sleep_stability import gaps_table
    out = run_dir("sleep_explore_P", "2026c")
    rd, fd = report_dir("2026c", "ephys_spikes"), figure_dir("2026c", "ephys_spikes")
    gc = git_commit()
    t0 = time.time()
    gaps = gaps_table()
    HELD, OE, TC, SYM, PAR, GR, S3, EC, TER, RES = ([] for _ in range(10))
    for lab in a.scorings:
        recs = records_for(STATES if lab == "final" else PASS2MED)
        RI = round_info(recs, gaps)
        T = step_table(recs, RI)
        sp = step_part(lab, T, boot=a.boot)
        HELD.append(sp["held"])
        OE.append(sp["oe"])
        TC.append(sp["tc"])
        SYM.append(sp["sym"])
        PAR.append(sp["params"])
        GR.append(sp["grids"])
        print(f"[{lab}] step level {time.time() - t0:.0f} s: {sp['held']}", flush=True)
        gp = gen_part(lab, recs, RI, gaps, T, a.reps, a.workers)
        PAR.append(gp["params"])
        S3.append(gp["s3"])
        EC.append(gp["echecks"])
        TER.append(gp["tertiles"])
        RES.append(gp["residual"])
        print(f"[{lab}] generative {time.time() - t0:.0f} s", flush=True)
    HELD, SYM = pd.DataFrame(HELD), pd.DataFrame(SYM)
    OE, TC, PAR, GR, S3, EC, TER, RES = (pd.concat(x, ignore_index=True) for x in (OE, TC, PAR, GR, S3, EC, TER, RES))
    for name, Tb in (("heldout", HELD), ("oe", OE), ("timecourse", TC), ("round_vs_natural", SYM), ("params", PAR), ("grids", GR),
                     ("s3", S3), ("echecks", EC), ("tertiles", TER), ("residual", RES)):
        Tb.to_csv(rd / f"ephys_spikes_sleep_explore_P_{name}_2026c.csv", index=False)
    v = []
    for lab in a.scorings:
        h = HELD[HELD.scores == lab].iloc[0]
        w = OE[(OE.scores == lab) & (OE.window == "0-1 h") & (OE.transition == "WAKE") & OE.model.str.startswith("blind + A")].iloc[0]
        ok = bool(h.holds and 0.8 <= w.OE <= 1.25 and w.ci_lo <= 1 <= w.ci_hi)
        v.append({"scores": lab, "part": "P1", "pass": ok, "numbers": f"Delta {h.delta_pct:+.2f} % [{h.ci_lo:+.2f}, {h.ci_hi:+.2f}], {h.animals_better}/{h.animals}; "
                  f"0-1 h WAKE O/E with A {w.OE:.2f} [{w.ci_lo:.2f}, {w.ci_hi:.2f}]"})
        s = SYM[SYM.scores == lab].iloc[0]
        v.append({"scores": lab, "part": "P1b", "pass": bool(s.holds), "numbers": f"a_round {s.a_round:+.2f} (tau {s.tau_round_s / 60:.0f} min) - a_nat {s.a_nat_at_round_tau:+.2f} "
                  f"= {s['diff']:+.2f} [{s.diff_ci_lo:+.2f}, {s.diff_ci_hi:+.2f}]"})
        q = S3[(S3.scores == lab) & (S3.variant == "blind + A")]
        need = q[q.metric.str.match(r"(rem|nrem)_min_\dh$") | (q.metric == "first_REM_latency_KM_median_s")]
        lat = need[need.metric == "first_REM_latency_KM_median_s"]
        ok = bool(lat.inside.all() and need.inside.sum() >= 12)
        v.append({"scores": lab, "part": "P2", "pass": ok, "numbers": f"{int(need.inside.sum())}/{len(need)} inside (blind without A: "
                  f"{int(S3[(S3.scores == lab) & (S3.variant == 'blind') & S3.metric.isin(need.metric)].inside.sum())}); latency " +
                  "; ".join(f"{r.kind} obs {r.observed / 60:.1f} min vs {r['sim_2.5%'] / 60:.1f}-{r['sim_97.5%'] / 60:.1f}" for _, r in lat.iterrows())})
        e = EC[EC.scores == lab]
        na, nb = int(e[e.variant == "blind + A"]["pass"].sum()), int(e[e.variant == "blind"]["pass"].sum())
        nt = int((e.variant == "blind + A").sum())
        v.append({"scores": lab, "part": "P3", "pass": bool(na >= nt - 1 and na >= nb), "numbers": f"with A {na}/{nt}, without A {nb}/{nt}"})
        r_ = RES[(RES.scores == lab) & (RES.variant == "blind + A")]
        v.append({"scores": lab, "part": "residual", "pass": None, "numbers": "; ".join(f"{x.quantity}: obs {x.observed:+.2f} vs {x['sim_2.5%']:+.2f}..{x['sim_97.5%']:+.2f} ({x.side})"
                                                                              for _, x in r_.iterrows())})
    V = pd.DataFrame(v)
    V.to_csv(rd / "ephys_spikes_sleep_explore_P_verdicts_2026c.csv", index=False)
    # figure
    fig, axs = plt.subplots(1, 2 + len(a.scorings) - 1, figsize=(6 * (1 + len(a.scorings)), 4.5))
    for ax, lab in zip(axs, a.scorings):
        q = TC[TC.scores == lab]
        x = (q.bin + 0.5) * 10
        ax.plot(x, q.obs / q.exp_b, "ko-", ms=3, label="observed / blind expected")
        ax.plot(x, q.exp_a / q.exp_b, "r-", label="cross-fitted A / blind expected")
        ax.axhline(1, color="grey", lw=0.6)
        ax.set_xlabel("min after the post-round record start")
        ax.set_ylabel("NREM -> WAKE, ratio to the blind model")
        ax.set_title(lab, fontsize=9)
        ax.legend(fontsize=7)
    ax = axs[-1]
    q = S3[S3.metric == "first_REM_latency_KM_median_s"].reset_index(drop=True)
    xs = np.arange(len(q))
    ax.errorbar(xs, q.sim_mean / 60, yerr=[(q.sim_mean - q["sim_2.5%"]) / 60, (q["sim_97.5%"] - q.sim_mean) / 60], fmt="o", label="simulated 95 %")
    ax.plot(xs, q.observed / 60, "rs", label="observed")
    ax.set_xticks(xs, [f"{r.scores}\n{r.kind}\n{r.variant}" for r in q.itertuples()], fontsize=6)
    ax.set_ylabel("first-REM latency after the round, KM median (min)")
    ax.legend(fontsize=7)
    fig.suptitle(f"P: a decaying arousal after the rounds (NREM -> WAKE only), fitted on waking only  {gc}", fontsize=9)
    save_fig(fig, fd / "ephys_spikes_sleep_explore_P_2026c.png")
    L = ["# Sleep-behaviour explore — P: perturbation dynamics (a decaying arousal after the battery rounds), cohort 2026c", "",
         "Plan [implementation_plan/2026-10-08-sleep-behaviour-explore.md](../../../../implementation_plan/2026-10-08-sleep-behaviour-explore.md) "
         f"§10 Amendment 2 (rules written before results). Driver `ephys/sleep_perturb.py` (commit {gc}); bulk `{out}`; {a.reps} replicates; "
         f"runtime {(time.time() - t0) / 60:.0f} min. **Technical ledger.**", "",
         "## Definitions", "", "```", (__doc__ or "").strip(), "```", "",
         "## Verdicts", "", *md_table(V), "",
         "## Arousal parameters", "", *md_table(PAR.round(4)), "", "Likelihood by tau_A:", "", *md_table(GR.round(3)), "",
         "## P1: held-out (cross-fitted) prediction of the post-round steps", "", *md_table(HELD.round(4)), "", *md_table(OE.round(4)), "",
         "## P1b: rounds vs natural wakes >= 30 min (symmetric base)", "", *md_table(SYM.round(4)), "",
         "## P2: the simulated post-round response, without and with A", "", *md_table(S3.round(3)), "",
         "## P3: Step E's checks without and with A", "", *md_table(EC.round(4)), "",
         "## P4: gap-length tertiles (with A)", "", *md_table(TER.round(3)), "",
         "## The REM residual (decides part Q)", "", *md_table(RES.round(4)), "",
         "![](../figures/ephys_spikes_sleep_explore_P_2026c.png)", ""]
    (rd / "ephys_spikes_sleep_explore_P_2026c.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    write_json(rd / "run_manifest_sleep_explore_P_2026c.json", {"run_dir": str(out), "git_commit": gc, "reps": a.reps, "scorings": a.scorings})
    print(V.to_string(index=False), flush=True)
    print("written", rd / "ephys_spikes_sleep_explore_P_2026c.md", flush=True)


# ------------------------------------------------------------------ part T: the two-phase arousal (plan §11, Amendment 3)
DOC_T = r"""Part T of the sleep-behaviour explore (plan §11, Amendment 3, written before results): a two-phase arousal after the
battery rounds — an early excess and a delayed consolidation phase — fitted on waking only. Does the second phase exist,
and does it produce the later sleep recovery (part P: more sleep 1-6 h after a round than the one-phase simulation)?

Usage:  python ephys/sleep_perturb.py runT [--scorings final pass2med] [--reps 100] [--workers 8]

Definitions (as part P unless stated):
  two-phase term   on the NREM -> WAKE logit only: eta_WAKE += a exp(-s / tau1) + b (s / tau2) exp(1 - s / tau2), s = s since
                   the post-round record start; the second term is 0 at s = 0 and peaks at s = tau2 with value b.
                   tau1 in {600, 1200, 2400, 4800} s, tau2 in {3600, 5400, 7200, 10800} s; (a, b) = 2-D Newton on the
                   binary WAKE likelihood with the base logit as offset; the grid pair with the highest likelihood.
  one-phase term   part P's a exp(-s / tau) refitted on the same window and bases (comparator).
  window           the 6 h after the post-round record start; both bases (step-level B-full; the generative sleep_sim fit,
                   records masked) leave out these 6 h.
  cross-fit        rounds by date parity, as part P.
  T1   cross-fitted two-phase vs one-phase on the post-round steps 0-6 h: Delta log-loss % (block bootstrap CI) and animals
       better; pass = CI < 0, >= 5/6, and b < 0 in both halves.
  T2   100 replicates of the cross-fitted simulation with the two-phase term (REM rules untouched): pass = the observed mean
       REM and NREM minutes at 1, 3 and 6 h after morning and evening rounds (12 measures) all inside the simulated
       2.5-97.5 % range. Latencies reported.
  T3   Step E's checks with the two-phase term: >= 13/14 per scoring and not fewer than without.
  residual   FINAL's morning REM in 3 h and pass2med's day-demeaned morning REM payback slope at 3 h, with the two-phase term.
"""
POST_T = 6 * 3600
TAUS2 = [3600.0, 5400.0, 7200.0, 10800.0]


def h2(s: np.ndarray, tau2: float) -> np.ndarray:
    return (s / tau2) * np.exp(1.0 - s / tau2)


def newton2(o: np.ndarray, H: np.ndarray, yw: np.ndarray) -> tuple[np.ndarray, float, np.ndarray]:
    th = np.zeros(H.shape[1])
    A = np.eye(H.shape[1])
    for _ in range(100):
        p = sig(o + H @ th)
        g = H.T @ (yw - p)
        A = (H * (p * (1 - p))[:, None]).T @ H
        try:
            st = np.linalg.solve(A, g)
        except np.linalg.LinAlgError:
            break
        th += st
        if np.max(np.abs(st)) < 1e-9:
            break
    p = np.clip(sig(o + H @ th), 1e-12, 1 - 1e-12)
    ll = float(np.sum(yw * np.log(p) + (1 - yw) * np.log(1 - p)))
    try:
        se = np.sqrt(np.diag(np.linalg.inv(A)))
    except np.linalg.LinAlgError:
        se = np.full(H.shape[1], np.nan)
    return th, ll, se


def fit_two(pw: np.ndarray, s: np.ndarray, y: np.ndarray, taus1=TAUS, taus2=TAUS2) -> tuple[dict, pd.DataFrame]:
    o, yw = logit(pw), (y == 2).astype(float)
    rows = []
    for t1 in taus1:
        for t2 in taus2:
            th, ll, se = newton2(o, np.column_stack([np.exp(-s / t1), h2(s, t2)]), yw)
            rows.append({"tau1_s": t1, "tau2_s": t2, "a": th[0], "b": th[1], "se_a": se[0], "se_b": se[1], "ll": ll, "n": len(y),
                         "wakes": int(yw.sum())})
    G = pd.DataFrame(rows)
    return G.loc[G.ll.idxmax()].to_dict(), G


def two_term(s: np.ndarray, p: dict) -> np.ndarray:
    if "tau1_s" in p:
        return p["a"] * np.exp(-s / p["tau1_s"]) + p["b"] * h2(s, p["tau2_s"])
    return p["a"] * np.exp(-s / p["tau_s"])


def apply_add(P: np.ndarray, add: np.ndarray) -> np.ndarray:
    pw = np.clip(P[:, 2], 1e-12, 1 - 1e-12)
    pw2 = sig(logit(pw) + add)
    sc = (1 - pw2) / (1 - pw)
    out = P.copy()
    out[:, 0] *= sc
    out[:, 1] *= sc
    out[:, 2] = pw2
    return out


def crossfit_T(Pb: np.ndarray, s: np.ndarray, y: np.ndarray, half: np.ndarray):
    """One-phase and two-phase, each fitted on the half != h and applied to half h."""
    P1, P2, par1, par2 = Pb.copy(), Pb.copy(), {}, {}
    for h in (0, 1):
        tr, te = half != h, half == h
        par1[h], _ = fit_arousal(Pb[tr, 2], s[tr], y[tr])
        par2[h], _ = fit_two(Pb[tr, 2], s[tr], y[tr])
        P1[te] = apply_add(Pb[te], two_term(s[te], par1[h]))
        P2[te] = apply_add(Pb[te], two_term(s[te], par2[h]))
    return P1, P2, par1, par2


def step_part_T(lab: str, T: dict, boot: int = 2000) -> dict:
    from sleep_stability import boot_blocks
    D, s, post, half = T["D"], T["s"], T["post"], T["half"]
    pr = np.flatnonzero(post)
    m, st, lv = fit_base(D, ~post)
    Pb = predict(D, pr, m, st, lv)
    y, sp, hp = D["y"][pr].astype(int), s[pr], half[pr]
    P1, P2, par1, par2 = crossfit_T(Pb, sp, y, hp)
    b1, g1 = fit_arousal(Pb[:, 2], sp, y)
    b2, g2 = fit_two(Pb[:, 2], sp, y)
    df = pd.DataFrame({"block": D["block"][pr], "animal": D["animal"][pr], "y": y, "s": sp, "nll_b": nll(Pb, y), "nll_1": nll(P1, y),
                       "nll_2": nll(P2, y), "pw_b": Pb[:, 2], "pw_1": P1[:, 2], "pw_2": P2[:, 2], "pr_b": Pb[:, 1], "pr_1": P1[:, 1], "pr_2": P2[:, 1]})
    held = []
    for lo, hi, name in (("nll_1", "nll_2", "two-phase vs one-phase"), ("nll_b", "nll_1", "one-phase vs blind"), ("nll_b", "nll_2", "two-phase vs blind")):
        est, l_, h_ = boot_blocks(df, lambda q, lo=lo, hi=hi: 100 * (q[hi].sum() - q[lo].sum()) / q[lo].sum(), n=boot)
        pa = df.groupby("animal").apply(lambda q, lo=lo, hi=hi: (q[hi] - q[lo]).mean(), include_groups=False)
        held.append({"scores": lab, "comparison": name, "steps": len(df), "wakes": int((df.y == 2).sum()), "delta_pct": est, "ci_lo": l_,
                     "ci_hi": h_, "animals_better": int((pa < 0).sum()), "animals": len(pa), "holds": bool(h_ < 0 and (pa < 0).sum() >= 5)})
    oe = []
    for wname, a0, a1 in (("0-1 h", 0, 3600), ("1-3 h", 3600, 3 * 3600), ("3-6 h", 3 * 3600, POST_T)):
        g = df[(df.s >= a0) & (df.s < a1)]
        for tr, yc, pre in (("WAKE", 2, "pw"), ("REM", 1, "pr")):
            for mod, c in (("blind", f"{pre}_b"), ("one-phase (cross-fitted)", f"{pre}_1"), ("two-phase (cross-fitted)", f"{pre}_2")):
                e, l_, h_ = boot_blocks(g, lambda q, yc=yc, c=c: (q.y == yc).sum() / q[c].sum(), n=boot)
                oe.append({"scores": lab, "window": wname, "transition": tr, "model": mod, "steps": len(g), "observed": int((g.y == yc).sum()),
                           "expected": float(g[c].sum()), "OE": e, "ci_lo": l_, "ci_hi": h_})
    df["bin"] = (df.s // 900).astype(int)
    tc = df.groupby("bin").agg(obs=("y", lambda v: (v == 2).sum()), exp_b=("pw_b", "sum"), exp_1=("pw_1", "sum"), exp_2=("pw_2", "sum"),
                               n=("y", "size")).reset_index()
    tc.insert(0, "scores", lab)
    params = []
    for h in (0, 1):
        params.append({"scores": lab, "base": "step-level blind (6 h)", "model": "one-phase", "fit_on": f"half != {h}", "applied_to": f"half {h}",
                       **{k: par1[h][k] for k in ("tau_s", "a", "se", "ll")}})
        params.append({"scores": lab, "base": "step-level blind (6 h)", "model": "two-phase", "fit_on": f"half != {h}", "applied_to": f"half {h}",
                       **{k: par2[h][k] for k in ("tau1_s", "tau2_s", "a", "b", "se_a", "se_b", "ll")}})
    params.append({"scores": lab, "base": "step-level blind (6 h)", "model": "one-phase", "fit_on": "all rounds", **{k: b1[k] for k in ("tau_s", "a", "se", "ll")}})
    params.append({"scores": lab, "base": "step-level blind (6 h)", "model": "two-phase", "fit_on": "all rounds",
                   **{k: b2[k] for k in ("tau1_s", "tau2_s", "a", "b", "se_a", "se_b", "ll")}})
    grids = pd.concat([g1.assign(scores=lab, model="one-phase"), g2.assign(scores=lab, model="two-phase")], ignore_index=True)
    return {"held": pd.DataFrame(held), "oe": pd.DataFrame(oe), "tc": tc, "params": pd.DataFrame(params), "grids": grids,
            "b_halves": [par2[0]["b"], par2[1]["b"]]}


def _rep_T(rep: int, recs: list[dict], M: dict, rs: dict, gaps: pd.DataFrame, ARS: dict, lab: str) -> dict:
    from sleep_explore_d import payback_from_records
    from sleep_sim import metrics, simulate_records
    from sleep_stability import round_metrics
    out = {}
    for var, ar in ARS.items():
        sim = simulate_records(recs, M, 50_000 + rep, arousal=ar)
        out[var] = {"rm": round_metrics(sim, rs).assign(rep=rep), "E": {"rep": rep, **metrics(sim)},
                    "pb": payback_from_records(sim, gaps, f"{lab}_T_{var}_{rep}").assign(rep=rep)}
    return out


def gen_part_T(lab: str, recs: list[dict], RI: pd.DataFrame, gaps: pd.DataFrame, T: dict, reps: int, workers: int) -> dict:
    from joblib import Parallel, delayed
    from sleep_explore_d import payback_from_records
    from sleep_schedule_phase3 import km_median
    from sleep_sim import build_model, metrics, record_inputs, simulate_records
    from sleep_stability import round_metrics
    rs = dict(zip(RI.record_id, RI.kind))
    masked = []
    for rc in recs:
        st = rc["state"].copy()
        if rc["record_id"] in rs:
            st[:POST_T] = 0
        masked.append({**rc, "state": st})
    M = build_model(masked)
    M["inputs"] = [record_inputs(rc, M["levels"]) for rc in recs]
    pr = np.flatnonzero(T["post"])
    Pg = predict(T["D"], pr, M["mN"], M["stN"], M["levels"])
    y, sp, hp = T["D"]["y"][pr].astype(int), T["s"][pr], T["half"][pr]
    par1, par2 = {}, {}
    for h in (0, 1):
        par1[h], _ = fit_arousal(Pg[hp != h, 2], sp[hp != h], y[hp != h])
        par2[h], _ = fit_two(Pg[hp != h, 2], sp[hp != h], y[hp != h])
    ARS = {"blind": None,
           "one-phase": {r.record_id: (float(par1[r.half]["a"]), float(par1[r.half]["tau_s"])) for r in RI.itertuples()},
           "two-phase": {r.record_id: (float(par2[r.half]["a"]), float(par2[r.half]["tau1_s"]), float(par2[r.half]["b"]), float(par2[r.half]["tau2_s"]))
                         for r in RI.itertuples()}}
    params = [{"scores": lab, "base": "generative (6 h masked)", "model": "one-phase", "fit_on": f"half != {h}", "applied_to": f"half {h}",
               **{k: par1[h][k] for k in ("tau_s", "a", "se", "ll")}} for h in (0, 1)]
    params += [{"scores": lab, "base": "generative (6 h masked)", "model": "two-phase", "fit_on": f"half != {h}", "applied_to": f"half {h}",
                **{k: par2[h][k] for k in ("tau1_s", "tau2_s", "a", "b", "se_a", "se_b", "ll")}} for h in (0, 1)]
    simulate_records(recs[:1], M, 0)
    res = Parallel(n_jobs=workers, backend="loky")(delayed(_rep_T)(r, recs, M, rs, gaps, ARS, lab) for r in range(reps))
    obs_rm = round_metrics(recs, rs)
    obs_E = metrics(recs)
    obs_pb = payback_from_records(recs, gaps, f"{lab}_T_observed")
    S3, EC, RES = [], [], []
    mets = [f"{q}_min_{h}h" for h in (1, 3, 6) for q in ("rem", "nrem")]
    for var in ARS:
        S = pd.concat([r[var]["rm"] for r in res], ignore_index=True)
        for kind in ("morning", "evening"):
            o, sk = obs_rm[obs_rm.kind == kind], S[S.kind == kind]
            for c in mets:
                ov = o[c].dropna()
                sv = sk.groupby("rep")[c].mean()
                lo, hi = np.percentile(sv, [2.5, 97.5])
                S3.append({"scores": lab, "variant": var, "kind": kind, "metric": c, "rounds": len(ov), "observed": float(ov.mean()),
                           "sim_mean": float(sv.mean()), "sim_2.5%": lo, "sim_97.5%": hi, "inside": bool(lo <= ov.mean() <= hi)})
            olat = km_median(o.lat_s.to_numpy(), o.lat_ev.to_numpy())
            sl = sk.groupby("rep").apply(lambda g: km_median(g.lat_s.to_numpy(), g.lat_ev.to_numpy()), include_groups=False)
            lo, hi = np.nanpercentile(sl, [2.5, 97.5])
            S3.append({"scores": lab, "variant": var, "kind": kind, "metric": "first_REM_latency_KM_median_s", "rounds": len(o), "observed": olat,
                       "sim_mean": float(np.nanmean(sl)), "sim_2.5%": lo, "sim_97.5%": hi, "inside": bool(lo <= olat <= hi)})
        E = pd.DataFrame([r[var]["E"] for r in res])
        tol = dict(E_TOL, **{k: 0.25 for k in obs_E if k.startswith("lat_med_")})
        for k, tl in tol.items():
            ov = obs_E.get(k, np.nan)
            sv = E[k].to_numpy(dtype=float) if k in E else np.array([np.nan])
            if not np.isfinite(ov) or not np.isfinite(sv).any():
                continue
            mean = float(np.nanmean(sv))
            EC.append({"scores": lab, "variant": var, "metric": k, "observed": ov, "sim_mean": mean, "rel_diff": mean / ov - 1,
                       "tolerance": tl, "pass": bool(abs(mean / ov - 1) <= tl)})
        PB = pd.concat([r[var]["pb"] for r in res], ignore_index=True)
        for B in (1, 3):
            sel = lambda t_: t_[(t_.kind == "morning") & (t_.B_h == B) & (t_.outcome == "pay_rem") & (t_.predictors == "debt_rem") & (t_.day_demeaned == True)]  # noqa: E712
            ov = float(sel(obs_pb)["slope"].iloc[0])
            sv = sel(PB)["slope"].to_numpy(float)
            lo, hi = np.nanpercentile(sv, [2.5, 97.5])
            RES.append({"scores": lab, "variant": var, "quantity": f"morning REM payback slope (day-demeaned), B = {B} h", "observed": ov,
                        "sim_mean": float(np.nanmean(sv)), "sim_2.5%": lo, "sim_97.5%": hi, "side": "above" if ov > hi else ("below" if ov < lo else "inside")})
    S3 = pd.DataFrame(S3)
    for _, r in S3[(S3.metric == "rem_min_3h") & (S3.kind == "morning")].iterrows():
        lo, hi = r["sim_2.5%"], r["sim_97.5%"]
        RES.append({"scores": lab, "variant": r.variant, "quantity": "S3 morning REM min in 3 h", "observed": r.observed, "sim_mean": r.sim_mean,
                    "sim_2.5%": lo, "sim_97.5%": hi, "side": "above" if r.observed > hi else ("below" if r.observed < lo else "inside")})
    return {"params": pd.DataFrame(params), "s3": S3, "echecks": pd.DataFrame(EC), "residual": pd.DataFrame(RES)}


def runT(a) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from _common import git_commit, write_json
    from output_paths import figure_dir, report_dir, run_dir
    from sleep_model import PASS2MED, STATES, records_for
    from sleep_quant import md_table, save_fig
    from sleep_stability import gaps_table
    out = run_dir("sleep_explore_T", "2026c")
    rd, fd = report_dir("2026c", "ephys_spikes"), figure_dir("2026c", "ephys_spikes")
    gc = git_commit()
    t0 = time.time()
    gaps = gaps_table()
    HELD, OE, TC, PAR, GR, S3, EC, RES, BH = ([] for _ in range(9))
    for lab in a.scorings:
        recs = records_for(STATES if lab == "final" else PASS2MED)
        RI = round_info(recs, gaps)
        T = step_table(recs, RI, post_s=POST_T)
        sp = step_part_T(lab, T, boot=a.boot)
        for L_, k in ((HELD, "held"), (OE, "oe"), (TC, "tc"), (PAR, "params"), (GR, "grids")):
            L_.append(sp[k])
        BH.append({"scores": lab, "b_half0": sp["b_halves"][0], "b_half1": sp["b_halves"][1]})
        print(f"[{lab}] step level {time.time() - t0:.0f} s", flush=True)
        gp = gen_part_T(lab, recs, RI, gaps, T, a.reps, a.workers)
        for L_, k in ((PAR, "params"), (S3, "s3"), (EC, "echecks"), (RES, "residual")):
            L_.append(gp[k])
        print(f"[{lab}] generative {time.time() - t0:.0f} s", flush=True)
    HELD, OE, TC, PAR, GR, S3, EC, RES = (pd.concat(x, ignore_index=True) for x in (HELD, OE, TC, PAR, GR, S3, EC, RES))
    BH = pd.DataFrame(BH)
    for name, Tb in (("heldout", HELD), ("oe", OE), ("timecourse", TC), ("params", PAR), ("grids", GR), ("s3", S3), ("echecks", EC),
                     ("residual", RES), ("b_halves", BH)):
        Tb.to_csv(rd / f"ephys_spikes_sleep_explore_T_{name}_2026c.csv", index=False)
    v = []
    for lab in a.scorings:
        h = HELD[(HELD.scores == lab) & (HELD.comparison == "two-phase vs one-phase")].iloc[0]
        bh = BH[BH.scores == lab].iloc[0]
        ok = bool(h.holds and bh.b_half0 < 0 and bh.b_half1 < 0)
        v.append({"scores": lab, "part": "T1", "pass": ok, "numbers": f"two- vs one-phase Delta {h.delta_pct:+.3f} % [{h.ci_lo:+.3f}, {h.ci_hi:+.3f}], "
                  f"{h.animals_better}/{h.animals}; b by half {bh.b_half0:+.2f} / {bh.b_half1:+.2f}"})
        q = S3[(S3.scores == lab) & S3.metric.str.match(r"(rem|nrem)_min_\dh$")]
        n2, n1, n0 = (int(q[q.variant == vv].inside.sum()) for vv in ("two-phase", "one-phase", "blind"))
        out2 = q[(q.variant == "two-phase") & ~q.inside]
        v.append({"scores": lab, "part": "T2", "pass": bool(n2 == 12), "numbers": f"inside of 12: two-phase {n2}, one-phase {n1}, blind {n0}; outside (two-phase): " +
                  ", ".join(f"{r.kind} {r.metric} obs {r.observed:.1f} vs {r['sim_2.5%']:.1f}-{r['sim_97.5%']:.1f}" for _, r in out2.iterrows())})
        e = EC[EC.scores == lab]
        n_2, n_0, nt = int(e[e.variant == "two-phase"]["pass"].sum()), int(e[e.variant == "blind"]["pass"].sum()), int((e.variant == "two-phase").sum())
        v.append({"scores": lab, "part": "T3", "pass": bool(n_2 >= nt - 1 and n_2 >= n_0), "numbers": f"two-phase {n_2}/{nt}, blind {n_0}/{nt}"})
        r_ = RES[(RES.scores == lab) & (RES.variant == "two-phase")]
        v.append({"scores": lab, "part": "residual", "pass": None, "numbers": "; ".join(f"{x.quantity}: obs {x.observed:+.2f} vs {x['sim_2.5%']:+.2f}..{x['sim_97.5%']:+.2f} ({x.side})"
                                                                              for _, x in r_.iterrows())})
    V = pd.DataFrame(v)
    V.to_csv(rd / "ephys_spikes_sleep_explore_T_verdicts_2026c.csv", index=False)
    fig, axs = plt.subplots(1, len(a.scorings) + 1, figsize=(6 * (len(a.scorings) + 1), 4.5))
    for ax, lab in zip(axs, a.scorings):
        q = TC[TC.scores == lab]
        x = (q.bin + 0.5) * 15
        ax.plot(x, q.obs / q.exp_b, "ko-", ms=3, label="observed / blind expected")
        ax.plot(x, q.exp_1 / q.exp_b, "b-", label="one-phase / blind")
        ax.plot(x, q.exp_2 / q.exp_b, "r-", label="two-phase / blind")
        ax.axhline(1, color="grey", lw=0.6)
        ax.set_xlabel("min after the post-round record start")
        ax.set_ylabel("NREM -> WAKE, ratio to the blind model")
        ax.set_title(lab, fontsize=9)
        ax.legend(fontsize=7)
    ax = axs[-1]
    q = S3[S3.metric.str.match(r"(rem|nrem)_min_[36]h$")].reset_index(drop=True)
    q["rel"] = q.observed / q.sim_mean
    for i, (var, col) in enumerate((("blind", "grey"), ("one-phase", "b"), ("two-phase", "r"))):
        qq = q[q.variant == var].reset_index(drop=True)
        xs = np.arange(len(qq)) + 0.25 * (i - 1)
        ax.errorbar(xs, np.ones(len(qq)), yerr=[1 - qq["sim_2.5%"] / qq.sim_mean, qq["sim_97.5%"] / qq.sim_mean - 1], fmt="none", ecolor=col, alpha=0.6)
        ax.plot(xs, qq.rel, "o", color=col, ms=4, label=f"observed / simulated mean, {var}")
    ax.set_xticks(np.arange(len(q[q.variant == "blind"])), [f"{r.scores} {r.kind}\n{r.metric}" for r in q[q.variant == "blind"].itertuples()], rotation=70, fontsize=6)
    ax.axhline(1, color="k", lw=0.6)
    ax.legend(fontsize=6)
    fig.suptitle(f"T: a two-phase arousal after the rounds (NREM -> WAKE only), fitted on waking only  {gc}", fontsize=9)
    save_fig(fig, fd / "ephys_spikes_sleep_explore_T_2026c.png")
    L = ["# Sleep-behaviour explore — T: a two-phase arousal after the battery rounds, cohort 2026c", "",
         "Plan [implementation_plan/2026-10-08-sleep-behaviour-explore.md](../../../../implementation_plan/2026-10-08-sleep-behaviour-explore.md) "
         f"§11 Amendment 3 (rules written before results). Driver `ephys/sleep_perturb.py runT` (commit {gc}); bulk `{out}`; {a.reps} replicates; "
         f"runtime {(time.time() - t0) / 60:.0f} min. **Technical ledger.**", "",
         "## Definitions", "", "```", DOC_T.strip(), "```", "",
         "## Verdicts", "", *md_table(V), "",
         "## Parameters", "", *md_table(PAR.round(4)), "", "b in the halves:", "", *md_table(BH.round(4)), "",
         "Likelihood grids:", "", *md_table(GR.round(3)), "",
         "## T1: held-out comparison on the post-round steps (0-6 h)", "", *md_table(HELD.round(4)), "", *md_table(OE.round(4)), "",
         "## T2: the simulated post-round response", "", *md_table(S3.round(3)), "",
         "## T3: Step E's checks", "", *md_table(EC.round(4)), "",
         "## The REM residual", "", *md_table(RES.round(4)), "",
         "![](../figures/ephys_spikes_sleep_explore_T_2026c.png)", ""]
    (rd / "ephys_spikes_sleep_explore_T_2026c.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    write_json(rd / "run_manifest_sleep_explore_T_2026c.json", {"run_dir": str(out), "git_commit": gc, "reps": a.reps, "scorings": a.scorings})
    print(V.to_string(index=False), flush=True)
    print("written", rd / "ephys_spikes_sleep_explore_T_2026c.md", flush=True)


# ------------------------------------------------------------------ selftest
def selftest() -> None:
    t0 = time.time()
    rng = np.random.default_rng(3)
    n = 80_000
    s = rng.uniform(0, POST_S, n)
    raw = rng.dirichlet([30, 1, 1.5], n)
    P = raw / raw.sum(1, keepdims=True)
    # 1. apply_arousal: normalised, REM : stay unchanged, a = 0 identity
    Q = apply_arousal(P, 0.9, 1200, s)
    assert np.allclose(Q.sum(1), 1) and np.allclose(Q[:, 1] / Q[:, 0], P[:, 1] / P[:, 0]) and np.allclose(apply_arousal(P, 0.0, 1200, s), P)
    print("PASS apply_arousal: normalised, REM:stay ratio unchanged, a = 0 is the identity", flush=True)
    # 2. recovery of a planted (a, tau) and a null
    for a_true, tau_true in ((0.9, 1200.0), (0.0, 2400.0)):
        Pt = apply_arousal(P, a_true, tau_true, s)
        y = np.array([rng.choice(3, p=p) for p in Pt])
        best, G = fit_arousal(P[:, 2], s, y)
        if a_true:
            assert best["tau_s"] == tau_true and abs(best["a"] - a_true) < 3 * best["se"] + 0.05, best
        else:
            assert abs(best["a"]) < 3 * best["se"], best
        print(f"PASS recovery a {a_true} tau {tau_true:.0f}: fitted a {best['a']:+.3f} (se {best['se']:.3f}), tau {best['tau_s']:.0f}", flush=True)
    # 3. cross-fit uses the other half only
    half = (rng.random(n) < 0.5).astype(int)
    Pt = apply_arousal(P, 0.9, 1200, s)
    y = np.array([rng.choice(3, p=p) for p in Pt])
    y_neg = np.array([rng.choice(3, p=p) for p in apply_arousal(P, -1.0, 1200, s)])
    y2 = np.where(half == 1, y_neg, y)                             # half 0 planted a = +0.9, half 1 a = -1.0
    PA, par = crossfit(P, s, y2, half)
    assert abs(par[1]["a"] - 0.9) < 0.3 and abs(par[0]["a"] + 1.0) < 0.3, par   # par[h] = fitted on the OTHER half
    print(f"PASS cross-fit: half 1 predicted with half 0's fit (a {par[1]['a']:+.2f}), half 0 with half 1's (a {par[0]['a']:+.2f})", flush=True)
    # 4. the simulator: a = 0 identical to no arousal; a > 0 adds waking in the first hour
    from sleep_model import STATES, records_for
    from sleep_sim import build_model, simulate_records
    recs = records_for(STATES)
    sub = [rc for rc in recs if rc["animal"] == "SF07"][:6] + [rc for rc in recs if rc["animal"] == "SF10"][:6]
    M = build_model(sub)
    z = {rc["record_id"]: (0.0, 1200.0) for rc in sub}
    for rep in range(2):
        A_ = simulate_records(sub, M, rep)
        B_ = simulate_records(sub, M, rep, arousal=z)
        assert all(np.array_equal(x["state"], y_["state"]) for x, y_ in zip(A_, B_))
    big = {rc["record_id"]: (2.5, 1800.0) for rc in sub}
    w0 = np.mean([np.mean([(r["state"][:3600] == W).mean() for r in simulate_records(sub, M, rep)]) for rep in range(4)])
    w1 = np.mean([np.mean([(r["state"][:3600] == W).mean() for r in simulate_records(sub, M, rep, arousal=big)]) for rep in range(4)])
    assert w1 > w0, (w0, w1)
    print(f"PASS simulator: a = 0 identical to no arousal; a = 2.5 raises first-hour WAKE share {w0:.3f} -> {w1:.3f}", flush=True)
    # 5. part T: recovery of a planted two-phase term and a null second phase
    s6 = rng.uniform(0, POST_T, 120_000)
    raw6 = rng.dirichlet([30, 1, 1.5], len(s6))
    P6 = raw6 / raw6.sum(1, keepdims=True)
    for a_t, t1, b_t, t2 in ((0.8, 1200.0, -0.6, 7200.0), (0.8, 1200.0, 0.0, 7200.0)):
        y6 = np.array([rng.choice(3, p=p) for p in apply_add(P6, a_t * np.exp(-s6 / t1) + b_t * h2(s6, t2))])
        best, _ = fit_two(P6[:, 2], s6, y6)
        assert abs(best["a"] - a_t) < 3 * best["se_a"] + 0.1, best
        if b_t:
            assert best["tau1_s"] == t1 and best["tau2_s"] == t2 and abs(best["b"] - b_t) < 3 * best["se_b"] + 0.05, best
        else:
            assert abs(best["b"]) < 3 * best["se_b"], best
        print(f"PASS part T recovery a {a_t} b {b_t}: fitted a {best['a']:+.2f} b {best['b']:+.2f} (se {best['se_b']:.2f}), "
              f"tau1 {best['tau1_s']:.0f} tau2 {best['tau2_s']:.0f}", flush=True)
    long_ = [i for i, rc in enumerate(sub) if len(rc["state"]) >= 10800]
    w_lo = np.mean([np.mean([(r["state"][3600:10800] == W).mean() for i, r in enumerate(simulate_records(sub, M, rep)) if i in long_]) for rep in range(4)])
    neg = {rc["record_id"]: (0.0, 1200.0, -2.5, 7200.0) for rc in sub}
    w_lo2 = np.mean([np.mean([(r["state"][3600:10800] == W).mean() for i, r in enumerate(simulate_records(sub, M, rep, arousal=neg)) if i in long_]) for rep in range(4)])
    assert w_lo2 < w_lo, (w_lo, w_lo2)
    print(f"PASS simulator part T: b = -2.5 lowers the 1-3 h WAKE share {w_lo:.3f} -> {w_lo2:.3f}", flush=True)
    print(f"selftest PASS ({time.time() - t0:.0f} s)", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["run", "runT"])
    ap.add_argument("--scorings", nargs="+", default=["final", "pass2med"], choices=["final", "pass2med"])
    ap.add_argument("--reps", type=int, default=100)
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    elif a.cmd == "run":
        run(a)
    elif a.cmd == "runT":
        runT(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
