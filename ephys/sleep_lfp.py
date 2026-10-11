r"""Sleep LFP stage, step L1 (plan implementation_plan/2026-10-10-sleep-lfp-stage.md, revision 1, written before results):
NREM depth and the REM-entry count P — is P a behavioural proxy for depth, a parallel process, or is depth redundant?

Usage:  python ephys/sleep_lfp.py L1 [--scorings final pass2med] [--workers 6]
        python ephys/sleep_lfp.py --selftest

Definitions (records, 10-s NREM steps, folds and the B-full spec as ephys/sleep_model.py; t = the step start, s into
its record; the depth reading reuses ephys/rem_ripple_model.py):
  depth d       per second, the raw slow-wave slope `sw` of the fixed-channel rescore imu_fixch (SleepScoreRaw.npz on
                storage; the scorer's negative IRASA slope on the per-animal sw_channel; larger = deeper), over the
                sessions of the SWR quality guide except tier `exclude`; masked outside NREM, after `use_until` and in the
                probe-advance settle windows; z within animal x probe block (`block_from`) over its NREM seconds.
  dep           mean z over the NREM seconds with a value in [t - 150, t - 30) s (missing if < 60 such seconds)
  dep60         the same over [t - 180, t - 60) s (lag sensitivity)
  depc          the same over [t - 3750, t - 3630) s (negative control: the same width 1 h earlier)
  dep_fut       the same over [t + 30, t + 150) s (outcome of rule (e))
  models        multinomial stay / REM / WAKE on identical held-out steps (forward chaining, folds 1..):
                P = B-full; D = B-full with the P spline replaced by a spline of dep; P+D = B-full + dep (linear);
                P+D+Dd = P+D + dep x dark. Lag and control comparisons on their own subsets (P vs P+dep60, P vs P+depc).
                Delta = held-out log-loss change in % of the smaller model, fold bootstrap CI, for the total and for the
                binary REM and WAKE log-loss (rem_ripple_model.outcome_split); holds = CI upper < 0 and >= n - 1 of n
                animals better.
  rules (both scorings)
    (a) depth adds         P+D vs P holds, and the control P+depc vs P has CI covering 0
    (b) P is a proxy       P+D vs D does not hold, AND D vs P: D's log-loss <= P's (Delta <= 0)
    (c) two processes      (a) AND P+D vs D holds
    (d) night via depth    the full-data REM-vs-stay dark coefficient falls from P to P+D AND P+D+Dd vs P+D holds
                           (a smaller dark coefficient alone = reallocation)
    (e) depth reads the homeostat   held-out OLS of dep_fut on [clock, dark, day, L1, has_anchor, elapsed spline,
                           animal] + spline(ln(1 + P)) beats the same without P (Delta MSE % CI < 0) and the per-animal
                           linear P slope has the pooled sign in >= n - 1 of n animals
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "common"))

KEY = "P_tw600_k0"
B = {"L1": True, "hist": KEY}
N_STATE = 3
WINDOWS = {"dep": (150, 30), "dep60": (180, 60), "depc": (3750, 3630)}
FUT = (30, 150)
MIN_S = 60


def window_mean(cS: np.ndarray, cSn: np.ndarray, t: np.ndarray, lo_back: int, hi_back: int, n: int) -> np.ndarray:
    """Mean over [t - lo_back, t - hi_back) given cumulative sums (len n + 1); NaN if < MIN_S values or out of range."""
    x0, x1 = t - lo_back, t - hi_back
    ok = (x0 >= 0) & (x1 <= n) & (x1 > x0)
    x0c, x1c = np.clip(x0, 0, n), np.clip(x1, 0, n)
    k = cSn[x1c] - cSn[x0c]
    out = np.where(ok & (k >= MIN_S), (cS[x1c] - cS[x0c]) / np.maximum(k, 1), np.nan)
    return out


def load_sw(Q: dict, sleep_root: Path, cache_file: Path) -> dict:
    """Per session: t_clus, sw, th of imu_fixch (read once from storage, then from the local cache); empty ripple arrays
    so that rem_ripple_model.record_arrays can be reused unchanged."""
    if cache_file.exists():
        c = pd.read_pickle(cache_file)
        if all(k in c for k in Q):
            return c
    out = {}
    for (an, s) in Q:
        rf = sleep_root / an / s / f"{s}.SleepScoreRaw.npz"
        d = {"peak_s": np.zeros(0), "excluded": np.zeros(0, bool)}
        if rf.exists():
            with np.load(rf) as r_:
                d["t_clus"], d["sw"] = r_["t_clus"].astype(np.int64), r_["sw"].astype(np.float32)
                if "th" in r_.files:
                    d["th"] = r_["th"].astype(np.float32)
        out[(an, s)] = d
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    pd.to_pickle(out, cache_file)
    return out


def step_features(steps: pd.DataFrame, recs: list[dict], arrs: dict, BT: dict) -> pd.DataFrame:
    from rem_ripple_model import depth_z
    byrid = {rc["record_id"]: rc for rc in recs}
    parts = []
    for rid, g in steps.groupby("record_id"):
        rc, A = byrid[rid], arrs[rid]
        n = len(rc["state"])
        dz = depth_z(A, BT)
        fin = np.isfinite(dz) & (rc["state"] == N_STATE)
        cS, cSn = np.r_[0, np.cumsum(np.where(fin, dz, 0.0))], np.r_[0, np.cumsum(fin)]
        t = (g.bout_start.to_numpy() + g.elapsed.to_numpy()).astype(np.int64)
        F = {k: window_mean(cS, cSn, t, lo, hi, n) for k, (lo, hi) in WINDOWS.items()}
        F["dep_fut"] = window_mean(cS, cSn, t, -FUT[0], -FUT[1], n)
        parts.append(pd.DataFrame(F, index=g.index))
    return pd.concat(parts).reindex(steps.index)


def arrays_for(steps: pd.DataFrame, F: pd.DataFrame, mask: np.ndarray) -> dict:
    from sleep_model import to_arrays
    s, f = steps[mask].reset_index(drop=True), F[mask].reset_index(drop=True)
    D = to_arrays(s)
    for c in f.columns:
        D[c] = f[c].to_numpy().astype(float)
    D["lP_dep"] = D["dep"]
    D["dep_dark"] = D["dep"] * D["dark"]
    return D


def run_compare(D: dict, specs: dict, pairs: list[tuple[str, str]], workers: int, label: str, lab: str) -> pd.DataFrame:
    from joblib import Parallel, delayed
    from rem_ripple_model import outcome_split, pred_job
    from sleep_model import folds_of
    res = Parallel(n_jobs=workers, backend="loky")(delayed(pred_job)(k, tr, te, D, specs) for k, (tr, te) in enumerate(folds_of(D)))
    res = sorted(res, key=lambda r: r["k"])
    rows = []
    for lo, hi in pairs:
        for r in outcome_split(D, res, lo, hi):
            r["holds"] = bool(r["ci_hi_pct"] < 0 and r["animals"] > 0 and r["animals_better"] >= r["animals"] - 1)
            rows.append({"scores": lab, "subset": label, **r})
    return pd.DataFrame(rows)


def dark_coefs(D: dict) -> dict:
    from sklearn.linear_model import LogisticRegression
    from sleep_model import design
    idx = np.arange(len(D["y"]))
    levels = sorted(set(D["animal"]))
    out = {}
    for name, sp in (("P", B), ("P+D", {**B, "extra": ("dep",)})):
        X, st = design(D, idx, sp, None, levels)
        m = LogisticRegression(C=1e4, max_iter=3000).fit(X, D["y"])
        cl = list(m.classes_)
        # dark is the 3rd linear column: after the splines and the 4 harmonics; locate it from the design's lin order
        n_spl = sum(st[k].n_features_out_ for k in st if k.startswith("spl_"))
        j = n_spl + 4 + 2                                                  # lin = [T_day, has_anchor, dark, ...]
        out[name] = float(m.coef_[cl.index(1), j] - m.coef_[cl.index(0), j]) / st["sd"]["dark"]
    return out


def ols_outcome(D: dict, boot: int = 2000) -> dict:
    """Rule (e): held-out OLS of dep_fut with vs without the P spline (forward chaining), and per-animal P slopes."""
    from sklearn.preprocessing import SplineTransformer
    from sleep_cycles import boot_ci
    from sleep_model import folds_of
    y = D["dep_fut"]
    ok = np.isfinite(y)
    animals = np.array(sorted(set(D["animal"])))

    def X(idx, with_p, spl_e=None, spl_p=None):
        cols = [D[f"{f}{k}"][idx] for k in (1, 2) for f in ("sin", "cos")]
        cols += [D[c][idx] for c in ("T_day", "dark", "has_anchor", "l_dprev", "prev_rem", "prev_unk", "fW10")]
        cols += [(D["animal"][idx] == a).astype(float) for a in animals[1:]]
        M = [np.column_stack(cols), spl_e.transform(D["l_elapsed"][idx, None])]
        if with_p:
            M.append(spl_p.transform(D[f"lP_{KEY}"][idx, None]))
        return np.column_stack([np.ones(len(idx))] + M)

    per = []
    for k, (tr, te) in enumerate(folds_of(D)):
        tr, te = tr[ok[tr]], te[ok[te]]
        if k == 0 or len(te) < 50:
            continue
        se = SplineTransformer(n_knots=4, degree=3, include_bias=False).fit(D["l_elapsed"][tr, None])
        sp = SplineTransformer(n_knots=4, degree=3, include_bias=False).fit(D[f"lP_{KEY}"][tr, None])
        mse = {}
        for wp in (False, True):
            b, *_ = np.linalg.lstsq(X(tr, wp, se, sp), y[tr], rcond=None)
            mse[wp] = float(np.mean((y[te] - X(te, wp, se, sp) @ b) ** 2))
        per.append({"fold": k, "n": len(te), "d": mse[True] - mse[False], "base": mse[False]})
    Pf = pd.DataFrame(per)
    est, lo, hi = boot_ci(Pf, "d")
    base = float(np.sum(Pf.base * Pf.n) / Pf.n.sum())
    idx = np.flatnonzero(ok)
    xl = D[f"lP_{KEY}"]
    cols = lambda ii: np.column_stack([np.ones(len(ii))] + [D[f"{f}{k}"][ii] for k in (1, 2) for f in ("sin", "cos")]
                                      + [D[c][ii] for c in ("T_day", "dark", "has_anchor", "l_dprev", "fW10", "l_elapsed")] + [xl[ii]])
    bp, *_ = np.linalg.lstsq(cols(idx), y[idx], rcond=None)
    slopes = {}
    for a in animals:
        ii = idx[D["animal"][idx] == a]
        if len(ii) > 200:
            ba, *_ = np.linalg.lstsq(cols(ii), y[ii], rcond=None)
            slopes[a] = float(ba[-1])
    same = sum(np.sign(v) == np.sign(bp[-1]) for v in slopes.values())
    return {"steps": int(ok.sum()), "delta_mse_pct": 100 * est / base, "ci_lo_pct": 100 * lo / base, "ci_hi_pct": 100 * hi / base,
            "pooled_P_slope": float(bp[-1]), "animals_same_sign": int(same), "animals": len(slopes),
            "per_animal_slopes": "; ".join(f"{a} {v:+.3f}" for a, v in slopes.items())}


def L1(a) -> None:
    import swr_temperature as stp
    from _common import git_commit, write_json
    from output_paths import out_root, report_dir, run_dir
    from rem_ripple_model import SLEEP_ROOT, block_tables, record_arrays
    from sleep_model import PASS2MED, build_data, records_for, variant_specs
    from sleep_quant import md_table
    from sleep_schedule import REVIEW, STATES, included_sessions
    out = run_dir("sleep_lfp_L1", "2026c")
    rd = report_dir("2026c", "ephys_spikes")
    gc = git_commit()
    t0 = time.time()
    tiers = ["validated", "good", "check", "low_contrast"]
    q = stp.sessions(rd / "ephys_spikes_swr_quality_2026c.csv", REVIEW, tiers)
    Q = {(r.animal, r.session): {"use_until_t": r.use_until_t, "block_from": r.block_from} for r in q.itertuples()}
    codes = {k: i for i, k in enumerate(sorted({(r.animal, r.block_from) for r in q.itertuples()}))}
    settle = stp.settle_windows(REPO / "cohorts/2026c.yaml")
    cache = load_sw(Q, Path(SLEEP_ROOT), out_root() / "2026c" / "sleep_lfp_inputs" / "sw_imu_fixch.pkl")
    print(f"sessions {len(Q)} ({sum(1 for v in cache.values() if 'sw' in v)} with sw); {time.time() - t0:.0f} s", flush=True)
    CMP, DARK, OUTC, COV = [], [], [], []
    for lab in a.scorings:
        root = STATES if lab == "final" else PASS2MED
        recs = records_for(root)
        starts = {(r.animal, r.session): r.start for r in included_sessions(REVIEW, root).itertuples()}
        steps = build_data(recs, {KEY: variant_specs()[KEY]})
        arrs = {rc["record_id"]: record_arrays(rc, starts, Q, settle, cache, codes) for rc in recs}
        BT = block_tables(recs, arrs)
        F = step_features(steps, recs, arrs, BT)
        m_main = np.isfinite(F.dep.to_numpy())
        m_lag = np.isfinite(F.dep60.to_numpy())
        m_ctl = np.isfinite(F.depc.to_numpy()) & m_main
        COV.append({"scores": lab, "steps_all": len(steps), "steps_dep": int(m_main.sum()), "steps_dep60": int(m_lag.sum()),
                    "steps_control": int(m_ctl.sum()), "rem_ends_dep": int(((steps.y == 1).to_numpy() & m_main).sum()),
                    "animals": int(steps.animal[m_main].nunique())})
        print(f"[{lab}] features {time.time() - t0:.0f} s: {COV[-1]}", flush=True)
        D = arrays_for(steps, F, m_main)
        specs = {"P": B, "D": {"L1": True, "hist": "dep"}, "P+D": {**B, "extra": ("dep",)}, "P+D+Dd": {**B, "extra": ("dep", "dep_dark")}}
        CMP.append(run_compare(D, specs, [("P", "P+D"), ("D", "P+D"), ("P", "D"), ("P+D", "P+D+Dd")], a.workers, "main (dep, lag 30 s)", lab))
        print(f"[{lab}] main {time.time() - t0:.0f} s", flush=True)
        Dl = arrays_for(steps, F, m_lag)
        CMP.append(run_compare(Dl, {"P": B, "P+D60": {**B, "extra": ("dep60",)}}, [("P", "P+D60")], a.workers, "lag 60 s (dep60)", lab))
        Dc = arrays_for(steps, F, m_ctl)
        CMP.append(run_compare(Dc, {"P": B, "P+D": {**B, "extra": ("dep",)}, "P+Dc": {**B, "extra": ("depc",)}},
                               [("P", "P+D"), ("P", "P+Dc")], a.workers, "control subset (depc, 1 h earlier)", lab))
        print(f"[{lab}] lag / control {time.time() - t0:.0f} s", flush=True)
        DARK.append({"scores": lab, **{f"dark_REM_coef_{k}": v for k, v in dark_coefs(D).items()}})
        OUTC.append({"scores": lab, **ols_outcome(D)})
        print(f"[{lab}] (d) / (e) {time.time() - t0:.0f} s", flush=True)
    CMP, DARK, OUTC, COV = (pd.concat(x, ignore_index=True) if isinstance(x[0], pd.DataFrame) else pd.DataFrame(x) for x in (CMP, DARK, OUTC, COV))
    v = []
    for lab in a.scorings:
        c = CMP[(CMP.scores == lab) & (CMP.metric == "total")]
        g = lambda sub, comp: c[(c.subset.str.startswith(sub)) & (c.comparison == comp)].iloc[0]
        pd_p, pd_d, d_p, dd = g("main", "P+D vs P"), g("main", "P+D vs D"), g("main", "D vs P"), g("main", "P+D+Dd vs P+D")
        ctl = g("control", "P+Dc vs P")
        ra = bool(pd_p.holds and ctl.ci_lo_pct <= 0 <= ctl.ci_hi_pct)
        rb = bool((not pd_d.holds) and d_p.delta_pct <= 0)
        rc_ = bool(ra and pd_d.holds)
        dk = DARK[DARK.scores == lab].iloc[0]
        rd_ = bool(dk["dark_REM_coef_P+D"] > dk["dark_REM_coef_P"] and dd.holds)          # REM-vs-stay dark coef is negative; falls in size = moves toward 0
        oc = OUTC[OUTC.scores == lab].iloc[0]
        re_ = bool(oc.ci_hi_pct < 0 and oc.animals_same_sign >= oc.animals - 1)
        fmt = lambda r: f"{r.delta_pct:+.3f} % [{r.ci_lo_pct:+.3f}, {r.ci_hi_pct:+.3f}], {int(r.animals_better)}/{int(r.animals)}"
        v += [{"scores": lab, "rule": "(a) depth adds", "pass": ra, "numbers": f"P+D vs P {fmt(pd_p)}; control P+Dc vs P {fmt(ctl)}"},
              {"scores": lab, "rule": "(b) P is a proxy", "pass": rb, "numbers": f"P+D vs D {fmt(pd_d)}; D vs P {fmt(d_p)}"},
              {"scores": lab, "rule": "(c) two processes", "pass": rc_, "numbers": f"(a) {ra}; P+D vs D holds {bool(pd_d.holds)}"},
              {"scores": lab, "rule": "(d) night via depth", "pass": rd_, "numbers": f"dark REM coef P {dk['dark_REM_coef_P']:+.3f} -> P+D {dk['dark_REM_coef_P+D']:+.3f}; P+D+Dd vs P+D {fmt(dd)}"},
              {"scores": lab, "rule": "(e) depth reads the homeostat", "pass": re_, "numbers": f"Delta MSE {oc.delta_mse_pct:+.2f} % [{oc.ci_lo_pct:+.2f}, {oc.ci_hi_pct:+.2f}]; P slope {oc.pooled_P_slope:+.3f}, same sign {int(oc.animals_same_sign)}/{int(oc.animals)}"}]
    V = pd.DataFrame(v)
    for name, T in (("compare", CMP), ("dark", DARK), ("outcome", OUTC), ("coverage", COV), ("verdicts", V)):
        T.to_csv(rd / f"ephys_spikes_sleep_lfp_L1_{name}_2026c.csv", index=False)
    L_ = ["# Sleep LFP stage — L1: NREM depth and the REM-entry count (cohort 2026c)", "",
          "Plan [implementation_plan/2026-10-10-sleep-lfp-stage.md](../../../../implementation_plan/2026-10-10-sleep-lfp-stage.md) "
          f"revision 1 (rules written before results). Driver `ephys/sleep_lfp.py L1` (commit {gc}); bulk `{out}`; runtime "
          f"{(time.time() - t0) / 60:.0f} min. **Technical ledger.**", "",
          "## Definitions", "", "```", (__doc__ or "").strip(), "```", "",
          "## Verdicts", "", *md_table(V), "",
          "## Coverage", "", *md_table(COV), "",
          "## Held-out comparisons (total, REM, WAKE log-loss)", "", *md_table(CMP.round(4)), "",
          "## (d) The dark coefficient (REM vs stay, per unit of dark, full data)", "", *md_table(DARK.round(4)), "",
          "## (e) Depth as the outcome", "", *md_table(OUTC.round(4)), ""]
    (rd / "ephys_spikes_sleep_lfp_L1_2026c.md").write_text("\n".join(L_) + "\n", encoding="utf-8")
    write_json(rd / "run_manifest_sleep_lfp_L1_2026c.json", {"run_dir": str(out), "git_commit": gc, "scorings": a.scorings, "tiers": tiers})
    print(V.to_string(index=False), flush=True)
    print("written", rd / "ephys_spikes_sleep_lfp_L1_2026c.md", flush=True)


# ------------------------------------------------------------------ L1b (plan revision 2)
NAPS_CSV = "results/2026c/ephys_spikes/reports/ephys_spikes_night_naps_2026c.csv"
NSW_RUN = Path("D:/Field2026_analysis_out/2026c/night_sleep_wiser_20261009_1051")


def prep_scoring(lab: str, ctx: dict) -> dict:
    from rem_ripple_model import block_tables, record_arrays
    from sleep_model import PASS2MED, build_data, records_for, variant_specs
    from sleep_schedule import REVIEW, STATES, included_sessions
    root = STATES if lab == "final" else PASS2MED
    recs = records_for(root)
    starts = {(r.animal, r.session): r.start for r in included_sessions(REVIEW, root).itertuples()}
    steps = build_data(recs, {KEY: variant_specs()[KEY]})
    arrs = {rc["record_id"]: record_arrays(rc, starts, ctx["Q"], ctx["settle"], ctx["cache"], ctx["codes"]) for rc in recs}
    BT = block_tables(recs, arrs)
    F = step_features(steps, recs, arrs, BT)
    byrid = {rc["record_id"]: rc for rc in recs}
    cont, cov = np.zeros(len(steps), bool), np.full(len(steps), np.nan)
    for rid, g in steps.groupby("record_id"):
        st = byrid[rid]["state"]
        n = len(st)
        cN = np.r_[0, np.cumsum(st == N_STATE)]
        tt = (g.bout_start.to_numpy() + g.elapsed.to_numpy()).astype(np.int64)
        e1 = np.minimum(tt + FUT[1], n)
        cont[steps.index.get_indexer(g.index)] = (tt + FUT[1] <= n) & ((cN[e1] - cN[tt]) == FUT[1])
        a0, a1 = np.minimum(tt + FUT[0], n), np.minimum(tt + FUT[1], n)
        cov[steps.index.get_indexer(g.index)] = (cN[a1] - cN[a0]) / (FUT[1] - FUT[0])
    F["cont_nrem"], F["fut_cov"] = cont, cov
    return {"recs": recs, "steps": steps, "F": F}


def label_steps(steps: pd.DataFrame, strict_only: bool = False) -> np.ndarray:
    """0 = main sleep, 1 = nap, -1 = neither (step start floored to the second)."""
    naps = pd.read_csv(REPO / NAPS_CSV, parse_dates=["start", "end"])
    if strict_only:
        naps = naps[naps.strict.astype(bool)]
    lab = np.full(len(steps), -1)
    ts = pd.to_datetime(steps.t).dt.floor("1s")
    for an, g in steps.groupby("animal"):
        idx = steps.index.get_indexer(g.index)
        tv = ts.iloc[idx].to_numpy()
        f = NSW_RUN / f"seconds_{an}.csv.gz"
        if f.exists():
            s = pd.read_csv(f, usecols=["t", "tau_h"], parse_dates=["t"])
            main = np.unique(s.t[s.tau_h.notna()].dt.floor("1s").to_numpy())
            lab[idx[np.isin(tv, main)]] = 0
        nn = naps[naps.animal == an].sort_values("start")
        if len(nn):
            st0, en0 = nn.start.dt.floor("1s").to_numpy(), nn.end.dt.floor("1s").to_numpy()
            j = np.searchsorted(st0, tv, side="right") - 1
            ok = j >= 0
            inn = np.zeros(len(tv), bool)
            inn[ok] = tv[ok] < en0[j[ok]]
            lab[idx[inn]] = 1
    return lab


def L1b(a) -> None:
    import swr_temperature as stp
    from _common import git_commit, write_json
    from output_paths import out_root, report_dir, run_dir
    from rem_ripple_model import SLEEP_ROOT
    from sklearn.linear_model import LogisticRegression
    from sleep_model import design
    from sleep_quant import md_table
    from sleep_schedule import REVIEW
    out = run_dir("sleep_lfp_L1b", "2026c")
    rd = report_dir("2026c", "ephys_spikes")
    gc = git_commit()
    t0 = time.time()
    tiers = ["validated", "good", "check", "low_contrast"]
    q = stp.sessions(rd / "ephys_spikes_swr_quality_2026c.csv", REVIEW, tiers)
    Q = {(r.animal, r.session): {"use_until_t": r.use_until_t, "block_from": r.block_from} for r in q.itertuples()}
    ctx = {"Q": Q, "codes": {k: i for i, k in enumerate(sorted({(r.animal, r.block_from) for r in q.itertuples()}))},
           "settle": stp.settle_windows(REPO / "cohorts/2026c.yaml"),
           "cache": load_sw(Q, Path(SLEEP_ROOT), out_root() / "2026c" / "sleep_lfp_inputs" / "sw_imu_fixch.pkl")}
    CMP, COEF, CNT, SEL = [], [], [], []
    for lab in a.scorings:
        S = prep_scoring(lab, ctx)
        steps, F = S["steps"], S["F"]
        print(f"[{lab}] prepared {time.time() - t0:.0f} s", flush=True)
        # ---- rule (e) on fixed continuing-NREM windows
        mfin = np.isfinite(F.dep.to_numpy())
        De = arrays_for(steps, F, mfin & F.cont_nrem.to_numpy())
        oc = ols_outcome(De)
        cov_main = F.fut_cov.to_numpy()[mfin & np.isfinite(F.dep_fut.to_numpy())]
        SEL.append({"scores": lab, "subset": "future window entirely NREM", **oc,
                    "fut_cov_main_median": float(np.median(cov_main)), "fut_cov_main_mean": float(np.mean(cov_main)),
                    "share_main_entirely_nrem": float(np.mean(cov_main >= 1.0))})
        print(f"[{lab}] (e) selection check {time.time() - t0:.0f} s", flush=True)
        if lab != "final":
            continue
        # ---- L1b: naps vs main sleep (FINAL labels)
        for variant, strict in (("all naps", False), ("strict naps", True)):
            labl = label_steps(steps, strict_only=strict)
            m = mfin & (labl >= 0)
            D = arrays_for(steps, F, m)
            D["nap"] = (labl[m] == 1).astype(float)
            lp = D[f"lP_{KEY}"]
            D["nap_lP"] = D["nap"] * (lp - lp.mean()) / lp.std()
            D["nap_dep"] = D["nap"] * D["dep"]
            for g, nm in ((1, "nap"), (0, "main")):
                sel = D["nap"] == g
                for an in sorted(set(D["animal"])):
                    mm = sel & (D["animal"] == an)
                    CNT.append({"variant": variant, "label": nm, "animal": an, "steps": int(mm.sum()), "rem_entries": int((D["y"][mm] == 1).sum())})
            specs = {"B+dep": {**B, "extra": ("dep",)}, "M0": {**B, "extra": ("dep", "nap")},
                     "M0+napP": {**B, "extra": ("dep", "nap", "nap_lP")}, "M0+napD": {**B, "extra": ("dep", "nap", "nap_dep")},
                     "M0+both": {**B, "extra": ("dep", "nap", "nap_lP", "nap_dep")}}
            CMP.append(run_compare(D, specs, [("B+dep", "M0"), ("M0", "M0+napP"), ("M0", "M0+napD"), ("M0", "M0+both")],
                                   a.workers, variant, lab))
            idx = np.arange(len(D["y"]))
            levels = sorted(set(D["animal"]))
            sp = specs["M0+both"]
            X, st = design(D, idx, sp, None, levels)
            mdl = LogisticRegression(C=1e4, max_iter=3000).fit(X, D["y"])
            cl = list(mdl.classes_)
            n_spl = sum(st[k].n_features_out_ for k in st if k.startswith("spl_"))
            lin = ["T_day", "has_anchor", "dark", "l_dprev", "prev_rem", "prev_unk", "fW10", "dep", "nap", "nap_lP", "nap_dep"]
            for j, nm in enumerate(lin):
                if nm in ("dep", "nap", "nap_lP", "nap_dep"):
                    col = n_spl + 4 + j
                    COEF.append({"variant": variant, "term": nm, "REM_vs_stay_per_unit": float(mdl.coef_[cl.index(1), col] - mdl.coef_[cl.index(0), col]) / st["sd"][nm],
                                 "WAKE_vs_stay_per_unit": float(mdl.coef_[cl.index(2), col] - mdl.coef_[cl.index(0), col]) / st["sd"][nm]})
            print(f"[{lab}] L1b {variant} {time.time() - t0:.0f} s", flush=True)
    CMP, COEF, CNT, SEL = (pd.concat(CMP, ignore_index=True), pd.DataFrame(COEF), pd.DataFrame(CNT), pd.DataFrame(SEL))
    v = []
    for variant in ("all naps", "strict naps"):
        c = CMP[(CMP.subset == variant) & (CMP.metric == "rem")]
        cn = CNT[(CNT.variant == variant) & (CNT.label == "nap")]
        n_an = int((cn.rem_entries > 0).sum())
        for comp, name in (("M0+napP vs M0", "nap x P"), ("M0+napD vs M0", "nap x depth"), ("M0 vs B+dep", "nap main effect")):
            r = c[c.comparison == comp].iloc[0]
            ok = bool(r.ci_hi_pct < 0 and r.animals_better >= n_an - 1)
            v.append({"variant": variant, "term": name, "pass": ok, "nap_rem_entries": int(cn.rem_entries.sum()), "animals_with_nap_rem": n_an,
                      "numbers": f"REM log-loss {r.delta_pct:+.3f} % [{r.ci_lo_pct:+.3f}, {r.ci_hi_pct:+.3f}], {int(r.animals_better)}/{int(r.animals)}"})
    V = pd.DataFrame(v)
    for name, T in (("compare", CMP), ("coef", COEF), ("counts", CNT), ("e_selection", SEL), ("verdicts", V)):
        T.to_csv(rd / f"ephys_spikes_sleep_lfp_L1b_{name}_2026c.csv", index=False)
    cs = CNT.groupby(["variant", "label"])[["steps", "rem_entries"]].sum().reset_index()
    L_ = ["# Sleep LFP stage — L1b: naps vs main sleep (P and depth), and the rule-(e) selection check (cohort 2026c)", "",
          "Plan [implementation_plan/2026-10-10-sleep-lfp-stage.md](../../../../implementation_plan/2026-10-10-sleep-lfp-stage.md) §8 "
          f"revision 2 (rules written before results). Driver `ephys/sleep_lfp.py L1b` (commit {gc}); bulk `{out}`; runtime "
          f"{(time.time() - t0) / 60:.0f} min. **Technical ledger.** Labels from the SWR session's night_sleep_wiser (FINAL only); "
          "outcome = REM entry (the labels look into the future, so WAKE differs by construction); naps are all dark, so a "
          "difference reads 'label or light'.", "",
          "## Verdicts (REM entry)", "", *md_table(V), "",
          "## Steps and REM entries per label", "", *md_table(cs), "", *md_table(CNT), "",
          "## Held-out comparisons (total, REM, WAKE)", "", *md_table(CMP.round(4)), "",
          "## Full-data coefficients (M0 + both; per unit)", "", *md_table(COEF.round(4)), "",
          "## Rule (e) on future windows entirely NREM (selection check)", "", *md_table(SEL.round(4)), ""]
    (rd / "ephys_spikes_sleep_lfp_L1b_2026c.md").write_text("\n".join(L_) + "\n", encoding="utf-8")
    write_json(rd / "run_manifest_sleep_lfp_L1b_2026c.json", {"run_dir": str(out), "git_commit": gc, "scorings": a.scorings})
    print(V.to_string(index=False), flush=True)
    print(SEL.round(3).to_string(index=False), flush=True)
    print("written", rd / "ephys_spikes_sleep_lfp_L1b_2026c.md", flush=True)


# ------------------------------------------------------------------ L2b (plan revision 3)
THETA_ROOT = Path("D:/Field2026_analysis_out/2026c/theta_seconds")
LONG_W = 1800
PRE_S = 600


def record_series(rc: dict, starts: dict, Q: dict, settle: list, cache: dict, codes: dict, key: str = "th"):
    """rem_ripple_model.record_arrays for one imu_fixch series over ALL states: coverage, block code, value per second."""
    st = rc["state"]
    n = len(st)
    cov, blk, val = np.zeros(n, bool), np.full(n, -1, np.int32), np.full(n, np.nan, np.float32)
    an, t0 = rc["animal"], rc["start"].value
    offs = [int(round((starts[(an, s)] - rc["start"]).total_seconds())) for s in rc["sessions"]]
    for s, o, e in zip(rc["sessions"], offs, offs[1:] + [n]):
        q, z = Q.get((an, s)), cache.get((an, s))
        if q is None or z is None:
            continue
        i = np.arange(max(o, 0), min(e, n))
        tn = t0 + i.astype(np.int64) * 1_000_000_000
        k = np.ones(len(i), bool)
        if pd.notna(q["use_until_t"]):
            k &= tn < q["use_until_t"].value
        for a_, a0, a1 in settle:
            if a_ == an:
                k &= ~((tn >= a0.value) & (tn < a1.value))
        cov[i[k]], blk[i[k]] = True, codes[(an, q["block_from"])]
        if key in z:
            ts = o + z["t_clus"]
            okd = (ts >= max(o, 0)) & (ts < min(e, n))
            val[ts[okd]] = z[key][okd]
    val[~cov] = np.nan
    return cov, blk, val


def theta_series(rc: dict, starts: dict) -> dict:
    """The theta session's per-second CA1 log_td / REM-like theta (theta_on & f_peak < 10 Hz), on the record's seconds."""
    n = len(rc["state"])
    td, rl, ok, still = np.full(n, np.nan), np.zeros(n, bool), np.zeros(n, bool), np.zeros(n, bool)
    an = rc["animal"]
    offs = [int(round((starts[(an, s)] - rc["start"]).total_seconds())) for s in rc["sessions"]]
    for s, o in zip(rc["sessions"], offs):
        f = THETA_ROOT / an / f"{s}.theta_seconds.csv.gz"
        if not f.exists():
            continue
        d = pd.read_csv(f, usecols=["s", "log_td", "theta_on", "f_peak", "block_skip", "settle", "after_end", "imu_state"])
        good = ~(d.block_skip.astype(bool) | d.settle.astype(bool) | d.after_end.astype(bool))
        sec = o + d.s.to_numpy().astype(np.int64)
        m = (sec >= 0) & (sec < n) & good.to_numpy()
        td[sec[m]] = d.log_td.to_numpy()[m]
        rl[sec[m]] = (d.theta_on.astype(bool) & (d.f_peak < 10)).to_numpy()[m]
        ok[sec[m]] = True
        still[sec[m]] = (d.imu_state == 1).to_numpy()[m]          # 1 = head IMU still (theta cache README)
    return {"td": td, "rl": rl, "ok": ok, "still": still}


def first_rem_events(rc: dict, kind_of_record: str | None, tH: float | None) -> list[dict]:
    """R-evening (record after an evening round, from its house entry) and natural long-wake events (any clock)."""
    from sleep_schedule import R as R_, W as W_
    st = rc["state"]
    bl = bouts_list(st)
    out = []

    def from_onset(t_from):
        tn = next((a for s_, a, b in bl if s_ == N_STATE and a >= t_from), None)
        if tn is None:
            return None
        for s_, a, b in bl:
            if a < tn:
                continue
            if s_ == W_ and (b - a) >= LONG_W:
                return None
            if s_ == R_:
                return tn, a
        return None

    if kind_of_record == "evening" and tH is not None:
        r = from_onset(int(tH))
        if r:
            out.append({"kind": "R-evening", "tN": r[0], "tR": r[1]})
    post_end = 3 * 3600 if kind_of_record is not None else 0
    for s_, a, b in bl:
        if s_ == W_ and (b - a) >= LONG_W and b >= post_end:
            r = from_onset(b)
            if r:
                hh = (rc["start"] + pd.Timedelta(seconds=int(b))).hour
                out.append({"kind": "N-any", "tN": r[0], "tR": r[1], "evening": 17 <= hh < 23})
    return out


def bouts_list(st: np.ndarray) -> list:
    from sleep_cycles import bouts
    return bouts(st)


def L2b(a) -> None:
    import json
    import swr_temperature as stp
    from _common import git_commit, write_json
    from output_paths import out_root, report_dir, run_dir
    from rem_ripple_model import SLEEP_ROOT
    from sleep_model import PASS2MED, records_for
    from sleep_quant import md_table
    from sleep_schedule import R as R_, REVIEW, STATES, included_sessions
    from sleep_stability import gaps_table
    from sleep_perturb import round_info
    out = run_dir("sleep_lfp_L2b", "2026c")
    rd = report_dir("2026c", "ephys_spikes")
    gc = git_commit()
    t0 = time.time()
    tiers = ["validated", "good", "check", "low_contrast"]
    q = stp.sessions(rd / "ephys_spikes_swr_quality_2026c.csv", REVIEW, tiers)
    Q = {(r.animal, r.session): {"use_until_t": r.use_until_t, "block_from": r.block_from} for r in q.itertuples()}
    codes = {k: i for i, k in enumerate(sorted({(r.animal, r.block_from) for r in q.itertuples()}))}
    settle = stp.settle_windows(REPO / "cohorts/2026c.yaml")
    cache = load_sw(Q, Path(SLEEP_ROOT), out_root() / "2026c" / "sleep_lfp_inputs" / "sw_imu_fixch.pkl")
    hrun = Path(json.load(open(rd / "run_manifest_sleep_explore_H_2026c.json"))["run_dir"])
    HE = pd.read_csv(hrun / "house_entries.csv", parse_dates=["record_start"])
    tH_by = {(r.animal, pd.Timestamp(r.record_start)): r.tH_s for r in HE.itertuples() if np.isfinite(r.tH_s)}
    gaps = gaps_table()
    EV, TRJ = [], []
    for lab in a.scorings:
        root = STATES if lab == "final" else PASS2MED
        recs = records_for(root)
        starts = {(r.animal, r.session): r.start for r in included_sessions(REVIEW, root).itertuples()}
        RI = round_info(recs, gaps)
        kind = dict(zip(RI.record_id, RI.kind))
        ser = {rc["record_id"]: record_series(rc, starts, Q, settle, cache, codes) for rc in recs}
        # block statistics of th: NREM mean / sd, REM 25th percentile
        acc = {}
        for rc in recs:
            cov, blk, th = ser[rc["record_id"]]
            for b in np.unique(blk[blk >= 0]):
                m = (blk == b) & np.isfinite(th)
                acc.setdefault(int(b), {"N": [], "R": []})
                acc[int(b)]["N"].append(th[m & (rc["state"] == N_STATE)])
                acc[int(b)]["R"].append(th[m & (rc["state"] == R_)])
        bstat = {b: {"mu": float(np.mean(np.concatenate(v["N"]))), "sd": float(np.std(np.concatenate(v["N"]))),
                     "r25": float(np.percentile(np.concatenate(v["R"]), 25)) if sum(len(x) for x in v["R"]) > 30 else np.nan}
                 for b, v in acc.items() if sum(len(x) for x in v["N"]) > 300}
        for rc in recs:
            rid = rc["record_id"]
            evs = first_rem_events(rc, kind.get(rid), tH_by.get((rc["animal"], rc["start"])))
            if not evs:
                continue
            cov, blk, th = ser[rid]
            TS = theta_series(rc, starts)
            st = rc["state"]
            for ev in evs:
                a0, a1 = max(ev["tR"] - PRE_S, ev["tN"]), ev["tR"] - 2
                if a1 <= a0:
                    continue
                sec = np.arange(a0, a1)
                sec = sec[(st[sec] == N_STATE)]
                bb = blk[sec]
                good = np.isfinite(th[sec]) & np.isin(bb, list(bstat))
                if good.sum() < 60:
                    continue
                s2, b2 = sec[good], bb[good]
                mu = np.array([bstat[int(x)]["mu"] for x in b2])
                sd = np.array([bstat[int(x)]["sd"] for x in b2])
                r25 = np.array([bstat[int(x)]["r25"] for x in b2])
                z = (th[s2] - mu) / sd
                okc = TS["ok"][sec]
                row = {"scores": lab, "animal": rc["animal"], "record_id": rid, "kind": ev["kind"], "evening": ev.get("evening", True),
                       "t_R": rc["start"] + pd.Timedelta(seconds=int(ev["tR"])), "n_nrem_s": int(good.sum()),
                       "z_th_mean": float(np.mean(z)), "remlike_th_share": float(np.nanmean(th[s2] >= r25)),
                       "ca1_n": int(okc.sum()), "ca1_remlike_share": float(TS["rl"][sec][okc].mean()) if okc.sum() >= 60 else np.nan,
                       "ca1_logtd_mean": float(np.nanmean(TS["td"][sec][okc])) if okc.sum() >= 60 else np.nan,
                       # post hoc (2026-10-10, after the first results): IMU-still CA1 seconds; z-th without the last 2 min
                       "ca1_remlike_share_still": float(TS["rl"][sec][okc & TS["still"][sec]].mean()) if (okc & TS["still"][sec]).sum() >= 60 else np.nan,
                       "z_th_early": float(np.mean(z[s2 < ev["tR"] - 120])) if (s2 < ev["tR"] - 120).sum() >= 60 else np.nan}
                EV.append(row)
                for k_ in range(10):
                    lo, hi = ev["tR"] - (k_ + 1) * 60, ev["tR"] - k_ * 60 - (2 if k_ == 0 else 0)
                    ss = s2[(s2 >= lo) & (s2 < hi)]
                    if len(ss) >= 15:
                        zz = (th[ss] - np.array([bstat[int(x)]["mu"] for x in blk[ss]])) / np.array([bstat[int(x)]["sd"] for x in blk[ss]])
                        TRJ.append({"scores": lab, "animal": rc["animal"], "kind": ev["kind"], "evening": ev.get("evening", True),
                                    "min_before_REM": k_ + 1, "z_th": float(np.mean(zz))})
        print(f"[{lab}] events {sum(1 for e in EV if e['scores'] == lab)}; {time.time() - t0:.0f} s", flush=True)
    E, TJ = pd.DataFrame(EV), pd.DataFrame(TRJ)
    E.to_csv(out / "events.csv", index=False)
    rng = np.random.default_rng(0)
    res = []
    hour = E.t_R.dt.hour
    for lab, (subset, hsel) in [(s_, h_) for s_ in a.scorings for h_ in (("all", None), ("posthoc: first REM 19-24 h", 19))]:
        e = E[(E.scores == lab) & ((hour >= hsel) if hsel else True)]
        R_ev = e[e.kind == "R-evening"]
        N_ev = e[(e.kind == "N-any") & e.evening]
        meas_list = ("remlike_th_share", "z_th_mean", "ca1_remlike_share", "ca1_logtd_mean", "z_th_early", "ca1_remlike_share_still")             if hsel is None else ("z_th_mean", "ca1_remlike_share")
        for meas in meas_list:
            for excl10 in ((False, True) if meas in ("ca1_remlike_share", "ca1_logtd_mean") and hsel is None else (False,)):
                rr, nn = R_ev, N_ev
                if excl10:
                    rr, nn = rr[rr.animal != "SF10"], nn[nn.animal != "SF10"]
                an = sorted(set(rr.dropna(subset=[meas]).animal) & set(nn.dropna(subset=[meas]).animal))
                if not an:
                    continue
                d_an = {x: rr[rr.animal == x][meas].mean() - nn[nn.animal == x][meas].mean() for x in an}
                est = float(np.mean(list(d_an.values())))
                boots = []
                for _ in range(2000):
                    ds = []
                    for x in an:
                        r_ = rr[rr.animal == x][meas].dropna().to_numpy()
                        n_ = nn[nn.animal == x][meas].dropna().to_numpy()
                        ds.append(rng.choice(r_, len(r_)).mean() - rng.choice(n_, len(n_)).mean())
                    boots.append(np.mean(ds))
                lo, hi = np.percentile(boots, [2.5, 97.5])
                tag = " (no SF10)" if excl10 else ""
                if meas in ("z_th_early", "ca1_remlike_share_still"):
                    tag += " [post hoc]"
                res.append({"scores": lab, "subset": subset, "measure": meas + tag, "R_evening_events": int(rr[meas].notna().sum()),
                            "N_evening_events": int(nn[meas].notna().sum()), "R_mean": float(rr[meas].mean()), "N_mean": float(nn[meas].mean()),
                            "diff_mean_of_animals": est, "ci_lo": lo, "ci_hi": hi, "animals_pos": int(sum(v > 0 for v in d_an.values())),
                            "animals": len(an), "per_animal": "; ".join(f"{x} {v:+.3f}" for x, v in d_an.items())})
    RES = pd.DataFrame(res)
    v = []
    for lab in a.scorings:
        r = RES[(RES.scores == lab) & (RES.subset == "all") & (RES.measure == "remlike_th_share")].iloc[0]
        c = RES[(RES.scores == lab) & (RES.subset == "all") & (RES.measure == "ca1_remlike_share")]
        c = c.iloc[0] if len(c) else None
        ok = bool(r.ci_lo > 0 and r.animals_pos >= r.animals - 1)
        v.append({"scores": lab, "pass": ok, "numbers": f"REM-like th share R {r.R_mean:.3f} vs N {r.N_mean:.3f}: diff {r.diff_mean_of_animals:+.3f} "
                  f"[{r.ci_lo:+.3f}, {r.ci_hi:+.3f}], {int(r.animals_pos)}/{int(r.animals)} animals higher; CA1 REM-like diff "
                  + (f"{c.diff_mean_of_animals:+.3f} [{c.ci_lo:+.3f}, {c.ci_hi:+.3f}]" if c is not None else "n/a")})
    V = pd.DataFrame(v)
    tj = TJ.assign(group=np.where(TJ.kind == "R-evening", "R-evening", np.where(TJ.evening, "N-evening", "N-other"))).groupby(
        ["scores", "group", "min_before_REM"]).z_th.agg(["mean", "count"]).reset_index()
    for name, T in (("results", RES), ("trajectory", tj), ("verdicts", V)):
        T.to_csv(rd / f"ephys_spikes_sleep_lfp_L2b_{name}_2026c.csv", index=False)
    L_ = ["# Sleep LFP stage — L2(b): REM-like theta before the first REM, evening rounds vs natural evening wakes (cohort 2026c)", "",
          "Plan [implementation_plan/2026-10-10-sleep-lfp-stage.md](../../../../implementation_plan/2026-10-10-sleep-lfp-stage.md) §9 "
          f"revision 3 (rules written before results). Driver `ephys/sleep_lfp.py L2b` (commit {gc}); bulk `{out}` (events.csv); runtime "
          f"{(time.time() - t0) / 60:.0f} min. **Technical ledger.** th = the scorer's theta / delta axis (imu_fixch); CA1 = the theta "
          "session's cache (theta_on & f_peak < 10 Hz). SF10's CA1 site is the scorer's theta channel in 19 of its sessions: CA1 rows "
          "are also given without SF10.", "",
          "## Verdicts", "", *md_table(V), "",
          "## R-evening vs N-evening (mean of the per-animal differences; bootstrap within animals)", "", *md_table(RES.round(4)), "",
          "## Trajectory: mean z-th per minute before the first REM", "", *md_table(tj.round(3)), ""]
    (rd / "ephys_spikes_sleep_lfp_L2b_2026c.md").write_text("\n".join(L_) + "\n", encoding="utf-8")
    write_json(rd / "run_manifest_sleep_lfp_L2b_2026c.json", {"run_dir": str(out), "git_commit": gc, "scorings": a.scorings})
    print(V.to_string(index=False), flush=True)
    print(RES.round(3).to_string(index=False), flush=True)


def selftest() -> None:
    t0 = time.time()
    # window means on a toy depth series
    n = 400
    dz = np.full(n, np.nan)
    dz[100:300] = np.arange(200, dtype=float)
    fin = np.isfinite(dz)
    cS, cSn = np.r_[0, np.cumsum(np.where(fin, dz, 0.0))], np.r_[0, np.cumsum(fin)]
    t = np.array([250, 120, 380])
    w = window_mean(cS, cSn, t, 150, 30, n)
    assert abs(w[0] - np.mean(dz[100:220])) < 1e-9 and np.isnan(w[1]) and abs(w[2] - np.mean(dz[230:300])) < 1e-9, w
    f = window_mean(cS, cSn, t, -30, -150, n)
    assert abs(f[1] - np.mean(dz[150:270])) < 1e-9 and np.isnan(f[2]), f
    print("PASS window means (past, future, coverage rule)", flush=True)
    # rule (e) machinery on synthetic arrays with a planted P effect and a null
    rng = np.random.default_rng(0)
    m = 30000
    D = {"animal": rng.choice(list("ABCDEF"), m), "block": np.repeat(np.arange(20).astype(str), m // 20)}
    h = rng.uniform(0, 24, m)
    for k in (1, 2):
        D[f"sin{k}"], D[f"cos{k}"] = np.sin(2 * np.pi * k * h / 24), np.cos(2 * np.pi * k * h / 24)
    for c in ("T_day", "dark", "has_anchor", "l_dprev", "prev_rem", "prev_unk", "fW10"):
        D[c] = rng.normal(size=m)
    D["l_elapsed"] = np.log(rng.uniform(0, 600, m) + 5)
    D[f"lP_{KEY}"] = np.log1p(rng.exponential(20, m))
    D["y"] = np.zeros(m, int)
    for eff, expect in ((0.6, True), (0.0, False)):
        D["dep_fut"] = eff * D[f"lP_{KEY}"] + rng.normal(size=m)
        r = ols_outcome(D)
        assert (r["ci_hi_pct"] < 0) == expect, r
        print(f"PASS rule (e) with P effect {eff}: Delta MSE {r['delta_mse_pct']:+.2f} % [{r['ci_lo_pct']:+.2f}, {r['ci_hi_pct']:+.2f}]", flush=True)
    # L1b: the continuing-NREM test of the future window on a toy record
    st_ = np.array([3] * 200 + [1] * 10 + [3] * 200, np.int8)
    cN = np.r_[0, np.cumsum(st_ == N_STATE)]
    tt = np.array([0, 50, 100])
    e1 = np.minimum(tt + FUT[1], len(st_))
    cont = (tt + FUT[1] <= len(st_)) & ((cN[e1] - cN[tt]) == FUT[1])
    assert list(cont) == [True, True, False], cont
    print("PASS L1b continuing-NREM window test", flush=True)
    # L2b: first-REM events on a toy record
    st3 = np.array([1] * 2000 + [3] * 300 + [1] * 20 + [3] * 400 + [5] * 60 + [3] * 100, np.int8)
    rc3 = {"state": st3, "start": pd.Timestamp("2026-09-05 18:00:00")}
    evs = first_rem_events(rc3, "evening", 100.0)
    kinds = {e["kind"]: (e["tN"], e["tR"]) for e in evs}
    assert kinds == {"R-evening": (2000, 2720)}, evs              # the 2000-s wake lies in the round record's first 3 h
    ev2 = first_rem_events(rc3, None, None)                        # not a round record: the long wake counts
    assert [(e["kind"], e["tN"], e["tR"], e["evening"]) for e in ev2] == [("N-any", 2000, 2720, True)], ev2
    st4 = np.array([1] * 2000 + [3] * 300 + [1] * 1900 + [3] * 100 + [5] * 60, np.int8)
    assert first_rem_events({"state": st4, "start": rc3["start"]}, None, None)[0]["tN"] == 4200   # a >= 30-min wake breaks the chain
    print("PASS L2b first-REM events (R-evening from the house entry; natural long wake)", flush=True)
    print(f"selftest PASS ({time.time() - t0:.0f} s)", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["L1", "L1b", "L2b"])
    ap.add_argument("--scorings", nargs="+", default=["final", "pass2med"], choices=["final", "pass2med"])
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    elif a.cmd == "L1":
        L1(a)
    elif a.cmd == "L1b":
        L1b(a)
    elif a.cmd == "L2b":
        L2b(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
