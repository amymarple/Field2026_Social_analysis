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
    print(f"selftest PASS ({time.time() - t0:.0f} s)", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["L1"])
    ap.add_argument("--scorings", nargs="+", default=["final", "pass2med"], choices=["final", "pass2med"])
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    elif a.cmd == "L1":
        L1(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
