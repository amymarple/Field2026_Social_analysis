r"""Step E, held-out part, of the sleep-behaviour explore (plan implementation_plan/2026-10-08-sleep-behaviour-explore.md
sections 1, 3, 4 and 5 Steps B and E; the pass rules there are fixed):
  (1) does the REM-entry counter model (Step B's B-full) beat a 'momentum' alternative held out — a 2nd-order
      semi-Markov model with hazards on the previous two bouts' types and log durations (Stephenson 2025) — especially on
      NREM after wakes, and does momentum add anything beyond the counter?
  (2) does an NREM homeostat S (plan section 4) add to the counter model?

Usage:  python ephys/sleep_model_e.py heldout [--scorings final pass2med] [--workers 8] [--smoke]
        python ephys/sleep_model_e.py --selftest

Everything model-related is Step B's, imported from ephys/sleep_model.py and never edited: the records (sessions joined
across splits <= 60 s; everything from 2026-09-11 19:40 cut), the 10-s NREM steps with outcome stay / REM / WAKE, the
counter P, the design (`design`: B-spline of ln(elapsed + 5), 2-harmonic clock, z-scored experiment day, has_anchor, dark,
animal intercepts; L1 = ln(1 + preceding wake), previous bout REM, previous bout unknown, wake share of the last 10 min;
'extra' columns z-scored and linear), the engine (`fit_eval`: sklearn multinomial logit, C = 1e4), forward chaining over
the day-half blocks (`folds_of`; fold 0 only starts nested choices), the nested choice (`nested`) and the comparison
(`cmp`: Delta = held-out log-loss change in % of the smaller model, 95 % CI by bootstrap over folds, holds = CI < 0 and
>= 5 / 6 animals better). since_rem_class is Step B's post-hoc split (ephys/sleep_model_diag.py).

  B-full    = base + L1 + spline ln(1 + P_t), P = `P_tw600_k0` (tau_w = 600 s, kappa = 0: emptied by REM, discounted over
              a wake by exp(-d / 600 s)), the grid point chosen most often by Step B's nested forward chaining (FINAL);
              sensitivity: nested choice between tau_w = 300 and 600 s (kappa = 0) per fold.
  momentum  per NREM bout i (bouts = maximal runs of one state, unknown included), bout i-1 ('prev1', never NREM) and bout
            i-2 ('prev2'): prev2 type dummies WAKE / REM / unknown / none (reference: NREM, the commonest prev2), ln(1 + dur
            prev2) per prev2 type (NREM / WAKE / REM / unknown), ln(1 + dur prev1) for a REM or an unknown prev1 (a WAKE
            prev1's ln(1 + d) is already in L1).  M_mom = base + L1 + momentum (no counter); B+mom = B-full + momentum.
            Literal sensitivity M_mom_lit: one ln(1 + dur prev2) for every prev2 type.
  S         NREM homeostat, per second, exact exponential updates: WAKE S <- 1 - (1 - S) exp(-1 / tau_r); NREM or REM
            S <- S exp(-1 / tau_d); unknown: frozen. Each record starts at its animal's mean S over its recorded seconds
            (two passes: pass 1 from S = 0.5). At an NREM step S_t = S_bout_start * exp(-elapsed / tau_d). Grid tau_r in
            {1, 4, 16 h} x tau_d in {0.5, 2, 6 h}; B+S = B-full + S_t (z-scored, linear); the grid point by nested forward
            chaining (as Step B).
  subsets   since_rem_class at the bout start: after_long (a wake >= 420 s since the last REM / record start), after_medium
            (a 120-419-s wake, none longer), after_short (only wakes < 120 s); after_wake = long or medium. Supplementary:
            the type of prev1 (WAKE / REM / unknown or none).
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
import warnings  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(REPO / "common"))
from sleep_cycles import bouts  # noqa: E402
from sleep_model import (PASS2MED, STATES, build_data, cmp, design, fit_eval, folds_of, nested,  # noqa: E402
                         records_for, to_arrays, variant_specs)
from sleep_model_diag import since_rem_class  # noqa: E402
from sleep_schedule import N, R, W  # noqa: E402

PLAN = "implementation_plan/2026-10-08-sleep-behaviour-explore.md"
KEY, KEY_ALT = "P_tw600_k0", "P_tw300_k0"
TAU_R_H = (1.0, 4.0, 16.0)
TAU_D_H = (0.5, 2.0, 6.0)
GRID = [(r, d) for r in TAU_R_H for d in TAU_D_H]
S_INIT = 0.5
MOM = ("m2_W", "m2_R", "m2_U", "m2_none", "l2_N", "l2_W", "l2_R", "l2_U", "l1_R", "l1_U")
MOM_LIT = ("m2_W", "m2_R", "m2_U", "m2_none", "l2_any", "l1_R", "l1_U")
MOM_ALL = MOM + ("l2_any",)
TYPE = {N: "N", W: "W", R: "R", 0: "U"}
SUBSETS = ("all", "after_short", "after_medium", "after_long", "after_wake")
PREV1 = ("prev1_wake", "prev1_rem", "prev1_unknown_or_none")
NAME = "sleep_explore_E_heldout"
TAG = "ephys_spikes_sleep_explore_E_heldout"
COL = {"final": "#2a78d6", "pass2med": "#eb6834", "ink": "#52514e", "grey": "#9a9894"}
COMPS = [  # (part, lo, hi, label) ; Delta < 0 = hi better
    ("1", "mom", "B", "B-full (counter) vs M_mom (momentum)"),
    ("1", "B", "Bmom", "B-full + momentum vs B-full"),
    ("1-ref", "gate", "mom", "M_mom vs gate (base + L1; does momentum add to the current state?)"),
    ("1-ref", "gate", "B", "B-full vs gate (reference)"),
    ("1-sens", "mom", "Bnest", "B-full (nested tau_w 5 / 10 min) vs M_mom"),
    ("1-sens", "momlit", "B", "B-full vs M_mom_lit (one ln(1 + dur prev2))"),
    ("2", "B", "BS", "B-full + S (nested grid) vs B-full"),
]


def skey(r_h: float, d_h: float) -> str:
    return f"S_r{r_h:g}_d{d_h:g}"


# ================================================================== features (pure; selftested)
def momentum_starts(state: np.ndarray) -> dict[int, np.ndarray]:
    """NREM bout start -> vector over MOM_ALL (see the module docstring)."""
    bl = bouts(state)
    ix = {c: j for j, c in enumerate(MOM_ALL)}
    out = {}
    for i, (s, a, b) in enumerate(bl):
        if s != N:
            continue
        f = np.zeros(len(MOM_ALL))
        if i >= 1:
            s1, a1, b1 = bl[i - 1]
            if s1 == R:
                f[ix["l1_R"]] = np.log1p(b1 - a1)
            elif s1 == 0:
                f[ix["l1_U"]] = np.log1p(b1 - a1)
        if i >= 2:
            s2, a2, b2 = bl[i - 2]
            t2 = TYPE[s2]
            if t2 != "N":
                f[ix[f"m2_{t2}"]] = 1.0
            f[ix[f"l2_{t2}"]] = np.log1p(b2 - a2)
            f[ix["l2_any"]] = np.log1p(b2 - a2)
        else:
            f[ix["m2_none"]] = 1.0
        out[a] = f
    return out


def s_pass(state: np.ndarray, tau_r: float, tau_d: float, s0: float) -> tuple[dict[int, float], float, int]:
    """S (value at the start of the second) at every NREM bout start of one record, the sum of S over its recorded
    (non-unknown) seconds and their number. tau_r, tau_d in s. Exact per-second exponential updates, summed per bout in
    closed form: over a WAKE run of n s from S0 the values are 1 - (1 - S0) q_r^k, k = 0..n-1, over a sleep run S0 q_d^k."""
    qr, qd = np.exp(-1.0 / tau_r), np.exp(-1.0 / tau_d)
    S, out, tot, cnt = float(s0), {}, 0.0, 0
    for s, a, b in bouts(state):
        n = b - a
        if s == 0:
            continue
        if s == N:
            out[a] = S
        if s == W:
            tot += n - (1.0 - S) * (1.0 - qr ** n) / (1.0 - qr)
            S = 1.0 - (1.0 - S) * qr ** n
        else:
            tot += S * (1.0 - qd ** n) / (1.0 - qd)
            S *= qd ** n
        cnt += n
    return out, tot, cnt


def s_starts(recs: list[dict], grid) -> tuple[dict[str, dict[int, dict[int, float]]], pd.DataFrame]:
    """Two passes per grid point: pass 1 from S_INIT -> each animal's mean S over its recorded seconds; pass 2 starts every
    record at that mean. Returns {skey: {record_id: {bout_start: S}}} and the per-animal start values."""
    out, rows = {}, []
    animals = sorted({rc["animal"] for rc in recs})
    for r_h, d_h in grid:
        tr, td = 3600.0 * r_h, 3600.0 * d_h
        acc = {a: [0.0, 0] for a in animals}
        for rc in recs:
            _, tot, cnt = s_pass(rc["state"], tr, td, S_INIT)
            acc[rc["animal"]][0] += tot
            acc[rc["animal"]][1] += cnt
        mean = {a: (v[0] / v[1] if v[1] else S_INIT) for a, v in acc.items()}
        k = skey(r_h, d_h)
        out[k] = {rc["record_id"]: s_pass(rc["state"], tr, td, mean[rc["animal"]])[0] for rc in recs}
        rows += [{"grid": k, "tau_r_h": r_h, "tau_d_h": d_h, "animal": a, "S_start": m} for a, m in mean.items()]
    return out, pd.DataFrame(rows)


def prep_recs(recs: list[dict], grid) -> tuple[dict, dict]:
    """Step B's data (counter keys KEY, KEY_ALT) + momentum, S columns, since_rem_class and the prev1 type."""
    allv = variant_specs()
    steps = build_data(recs, {k: allv[k] for k in (KEY, KEY_ALT)})
    D = to_arrays(steps)
    n = len(steps)
    byrid = {rc["record_id"]: rc for rc in recs}
    S0, SA = s_starts(recs, grid)
    cls = np.zeros(n, np.int8)
    M = np.zeros((n, len(MOM_ALL)))
    Sc = {skey(*g): np.zeros(n) for g in grid}
    for rid, g in steps.groupby("record_id"):
        st = byrid[rid]["state"]
        pos = steps.index.get_indexer(g.index)
        bs = g.bout_start.to_numpy()
        el = g.elapsed.to_numpy().astype(float)
        c = since_rem_class(st)
        cls[pos] = [c[b] for b in bs]
        mm = momentum_starts(st)
        M[pos] = np.array([mm[b] for b in bs])
        for r_h, d_h in grid:
            k = skey(r_h, d_h)
            ss = S0[k][rid]
            Sc[k][pos] = np.array([ss[b] for b in bs]) * np.exp(-el / (3600.0 * d_h))
    for j, cname in enumerate(MOM_ALL):
        D[cname] = M[:, j]
    D.update(Sc)
    D["cls"] = cls
    D["prev1"] = np.where(steps.d_prev.to_numpy() > 0, 0, np.where(steps.prev_rem.to_numpy() > 0, 1, 2)).astype(np.int8)
    info = {"steps": n, "rem": int((D["y"] == 1).sum()), "wake": int((D["y"] == 2).sum()), "records": len(recs),
            "animals": sorted(set(D["animal"])), "S_start": SA,
            "cls_counts": {lab: int((cls == c).sum()) for c, lab in enumerate(("after_short", "after_medium", "after_long"))}}
    return D, info


def masks(D: dict) -> dict[str, np.ndarray | None]:
    m = {"all": None, "after_short": D["cls"] == 0, "after_medium": D["cls"] == 1, "after_long": D["cls"] == 2,
         "after_wake": D["cls"] >= 1}
    m.update({lab: D["prev1"] == j for j, lab in enumerate(PREV1)})
    return m


def specs_for(grid) -> dict[str, dict]:
    sp = {"B": {"L1": True, "hist": KEY}, "B300": {"L1": True, "hist": KEY_ALT}, "gate": {"L1": True, "hist": None},
          "mom": {"L1": True, "hist": None, "extra": MOM}, "momlit": {"L1": True, "hist": None, "extra": MOM_LIT},
          "Bmom": {"L1": True, "hist": KEY, "extra": MOM}}
    for g in grid:
        sp[f"BS:{skey(*g)}"] = {"L1": True, "hist": KEY, "extra": (skey(*g),)}
    return sp


# ================================================================== held out
def ho_job(k: int, tr: np.ndarray, te: np.ndarray, D: dict, name: str, spec: dict) -> dict:
    warnings.filterwarnings("ignore")
    t0 = time.time()
    te = te[np.isin(D["animal"][te], np.unique(D["animal"][tr]))]
    ll = fit_eval(D, tr, te, spec)
    return {"k": k, "name": name, "te": te, "ll": np.asarray(ll, np.float64), "secs": time.time() - t0}


def run_heldout(D: dict, specs: dict[str, dict], folds, workers: int, label: str = "") -> list[dict]:
    """Every (fold, spec) is one job (largest training sets first). Per fold: test indices, per-step held-out log loss of
    every spec ('arr'), their means ('ll') and per-animal (mean, n) ('lla') in Step B's layout (for `nested`)."""
    from joblib import Parallel, delayed
    jobs = [(k, tr, te, nm, sp) for k, (tr, te) in enumerate(folds) for nm, sp in specs.items()]
    jobs.sort(key=lambda j: -len(j[1]))
    t0 = time.time()
    out = Parallel(n_jobs=workers, backend="loky", verbose=0)(delayed(ho_job)(k, tr, te, D, nm, sp) for k, tr, te, nm, sp in jobs)
    print(f"[{label}] {len(jobs)} held-out fits in {time.time() - t0:.0f} s (sum of fit times {sum(o['secs'] for o in out) / 60:.1f} min)", flush=True)
    res = []
    for k in range(len(folds)):
        rr = [o for o in out if o["k"] == k]
        te = rr[0]["te"]
        an = D["animal"][te]
        ua = np.unique(an)
        arr = {o["name"]: o["ll"] for o in rr}
        res.append({"k": k, "te": te, "n": len(te), "n_rem": int((D["y"][te] == 1).sum()), "arr": arr,
                    "ll": {nm: float(v.mean()) for nm, v in arr.items()},
                    "lla": {nm: {a: (float(v[an == a].mean()), int((an == a).sum())) for a in ua} for nm, v in arr.items()}})
    return res


def sub_tables(res: list[dict], D: dict, cols: dict[str, tuple], mask: np.ndarray | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """cols: name -> ('fixed', spec) or ('chosen', per-fold spec list). Folds 1.. only; per fold the mean held-out log loss
    over the test steps in `mask` (all if None), per fold and per (fold, animal)."""
    F, FA = [], []
    for i, r in enumerate(res):
        if i == 0:
            continue
        te = r["te"]
        sel = np.ones(len(te), bool) if mask is None else mask[te]
        if not sel.any():
            continue
        row = {"fold": r["k"], "n": int(sel.sum()), "n_rem": int((D["y"][te][sel] == 1).sum())}
        an = D["animal"][te][sel]
        vals = {}
        for c, (kind, v) in cols.items():
            nm = v if kind == "fixed" else v[i]
            vals[c] = r["arr"][nm][sel]
            row[f"ll_{c}"] = float(vals[c].mean())
        F.append(row)
        for a in np.unique(an):
            m = an == a
            FA.append({"fold": r["k"], "animal": a, "n": int(m.sum()), **{f"ll_{c}": float(v[m].mean()) for c, v in vals.items()}})
    return pd.DataFrame(F), pd.DataFrame(FA)


def analyse(res: list[dict], D: dict, grid, label: str) -> dict:
    """Nested choices, the comparisons by subset, the S profile."""
    sfam = [f"BS:{skey(*g)}" for g in grid]
    chS, _, _ = nested(res, sfam)
    chB, _, _ = nested(res, ["B", "B300"])
    cols = {c: ("fixed", c) for c in ("B", "gate", "mom", "momlit", "Bmom")}
    cols["BS"] = ("chosen", chS)
    cols["Bnest"] = ("chosen", chB)
    for g in grid:
        cols[f"BS:{skey(*g)}"] = ("fixed", f"BS:{skey(*g)}")
    rows, folds_rows = [], []
    for sub, m in masks(D).items():
        F, FA = sub_tables(res, D, cols, m)
        if not len(F):
            continue
        folds_rows.append(F.assign(scores=label, subset=sub))
        comps = COMPS if sub in SUBSETS else [c for c in COMPS if c[0] in ("1", "2")]
        for part, lo, hi, lab in comps:
            r = cmp(F, FA, lo, hi, sub)
            rows.append({"scores": label, "part": part, "label": lab, **r})
    C = pd.DataFrame(rows)
    F, FA = sub_tables(res, D, cols, None)
    prof = []
    for (r_h, d_h), k in zip(grid, sfam):
        r = cmp(F, FA, "B", k, "all")
        prof.append({"scores": label, "grid": k[3:], "tau_r_h": r_h, "tau_d_h": d_h, **{c: r.get(c) for c in
                     ("delta_pct", "ci_lo_pct", "ci_hi_pct", "folds_better", "folds", "animals_better", "holds")}})
    PR = pd.DataFrame(prof)
    CH = pd.DataFrame({"scores": label, "fold": [r["k"] for r in res], "n_test": [r["n"] for r in res],
                       "chosen_S": [c[3:] if isinstance(c, str) else "" for c in chS],
                       "chosen_B_nested": [c if isinstance(c, str) else "" for c in chB]})
    return {"C": C, "PR": PR, "CH": CH, "folds": pd.concat(folds_rows, ignore_index=True), "chS": chS}


# ================================================================== full-data fits (descriptive; cluster-robust CI by block)
def design_names(spec: dict, st: dict, levels: list[str]) -> list[str]:
    """Column names in the order of sleep_model.design (spline blocks, sin1 cos1 sin2 cos2, linear, animal dummies)."""
    spl = ["l_elapsed"]
    lin = ["T_day", "has_anchor"] + (["dark"] if spec.get("dark", True) else [])
    if spec.get("L1"):
        lin += ["l_dprev", "prev_rem", "prev_unk", "fW10"]
    h = spec.get("hist")
    if h == "M2t":
        spl.append("l_nsince_t")
        lin += ["l_wsince", "l_rem_pre"]
    elif h:
        spl.append(f"lP_{h}")
    for e in spec.get("extra", ()):
        (spl if e == "l_tsince_t" else lin).append(e)
    names = []
    for c in spl:
        kk = st[f"spl_{c}"].transform(np.zeros((1, 1))).shape[1]
        names += [f"spl({c})_{j}" for j in range(kk)]
    return names + ["sin1", "cos1", "sin2", "cos2"] + lin + [f"animal_{lv}" for lv in levels[1:]]


def full_fit(D: dict, spec: dict, idx: np.ndarray | None = None) -> tuple[dict, list[str], dict]:
    from sleep_explore_c import mnl_fit
    idx = np.arange(len(D["y"])) if idx is None else idx
    levels = sorted(set(D["animal"][idx]))
    X, st = design(D, idx, spec, None, levels)
    names = design_names(spec, st, levels)
    assert len(names) == X.shape[1], (len(names), X.shape)
    f = mnl_fit(X, D["y"][idx].astype(int), D["block"][idx])
    return f, names, st


def fit_job(tag: str, D: dict, spec: dict, terms: tuple, idx: np.ndarray | None = None) -> list[dict]:
    from sleep_explore_c import coef
    warnings.filterwarnings("ignore")
    try:
        f, names, st = full_fit(D, spec, idx)
    except np.linalg.LinAlgError as e:
        return [{"fit": tag, "term": t, "why": f"singular: {e}"} for t in terms]
    rows = []
    for t in terms:
        for eq, eqn in ((0, "REM vs stay"), (1, "WAKE vs stay")):
            c = coef(f, names, t, eq)
            rows.append({"fit": tag, "term": t, "equation": eqn, **c, "sd_term": st["sd"].get(t, np.nan), "n": f["n"],
                         "clusters": f["clusters"], "converged": f["conv"]})
    return rows


def coef_tables(D: dict, label: str, s_modal: str, grid, workers: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    from joblib import Parallel, delayed
    jobs = [(f"{label}|B+S {skey(*g)}|pooled", D, {"L1": True, "hist": KEY, "extra": (skey(*g),)}, (skey(*g),), None) for g in grid]
    for a in sorted(set(D["animal"])):
        jobs.append((f"{label}|B+S {s_modal}|{a}", D, {"L1": True, "hist": KEY, "extra": (s_modal,)}, (s_modal,), np.flatnonzero(D["animal"] == a)))
    jobs.append((f"{label}|B+mom|pooled", D, {"L1": True, "hist": KEY, "extra": MOM}, MOM, None))
    jobs.append((f"{label}|M_mom|pooled", D, {"L1": True, "hist": None, "extra": MOM}, MOM, None))
    out = Parallel(n_jobs=workers, backend="loky", verbose=0)(delayed(fit_job)(*j) for j in jobs)
    T = pd.DataFrame([r for rr in out for r in rr])
    sp = T.fit.str.split("|", expand=True)
    T.insert(0, "scores", sp[0])
    T.insert(1, "model", sp[1])
    T.insert(2, "animal", sp[2])
    T = T.drop(columns="fit")
    S = T[T.model.str.startswith("B+S")].reset_index(drop=True)
    Mo = T[~T.model.str.startswith("B+S")].reset_index(drop=True)
    return S, Mo


# ================================================================== one scoring
def run_scoring(label: str, states: Path | None, workers: int, out: Path, smoke: bool = False, recs: list[dict] | None = None) -> dict:
    t0 = time.time()
    grid = GRID[::4] if smoke else GRID
    recs = records_for(states) if recs is None else recs
    D, info = prep_recs(recs, grid)
    folds = folds_of(D)
    if smoke:
        folds = folds[:4]
    print(f"[{label}] {info['steps']} NREM steps, {info['rem']} REM ends, {info['wake']} WAKE ends, {len(folds)} folds; "
          f"data {time.time() - t0:.0f} s", flush=True)
    res = run_heldout(D, specs_for(grid), folds, workers, label)
    A = analyse(res, D, grid, label)
    # per-step held-out log losses (bulk; reusable)
    np.savez_compressed(out / f"heldout_steps_{label}.npz", **{f"te_{r['k']}": r["te"] for r in res},
                        **{f"ll_{r['k']}__{nm}": v.astype(np.float32) for r in res for nm, v in r["arr"].items()})
    A["folds"].to_csv(out / f"folds_by_subset_{label}.csv", index=False)
    # modal nested choice over folds 1..; ties -> the tied grid point with the lowest non-nested profile Delta
    vc = pd.Series([c[3:] for c in A["chS"] if isinstance(c, str)]).value_counts()
    tied = list(vc.index[vc == vc.max()]) if len(vc) else [skey(*grid[0])]
    prof = A["PR"].set_index("grid").delta_pct
    s_modal = min(tied, key=lambda g: prof.get(g, np.inf))
    CS, CM = coef_tables(D, label, s_modal, grid, workers)
    print(f"[{label}] done {time.time() - t0:.0f} s", flush=True)
    return {"label": label, "info": info, "s_modal": s_modal, "CS": CS, "CM": CM, "n_folds_used": len(folds) - 1,
            "secs": time.time() - t0, **A}


# ================================================================== report
def fci(d, lo, hi, nd: int = 3) -> str:
    return f"{d:+.{nd}f} % [{lo:+.{nd}f}, {hi:+.{nd}f}]"


def held(r: dict | None) -> bool:
    """True only for a comparison that holds (Python or numpy bool; NaN / missing -> False)."""
    v = None if r is None else r.get("holds")
    return bool(v) if isinstance(v, (bool, np.bool_)) else False


def frac(a, b) -> str:
    return "n/a" if pd.isna(a) or pd.isna(b) else f"{int(a)}/{int(b)}"


def row_of(C: pd.DataFrame, scores: str, label: str, subset: str) -> dict | None:
    q = C[(C.scores == scores) & (C.label == label) & (C.subset == subset)]
    return q.iloc[0].to_dict() if len(q) else None


def short(r: dict | None) -> str:
    if r is None or pd.isna(r.get("delta_pct", np.nan)):
        return "n/a"
    return (f"Δ {fci(r['delta_pct'], r['ci_lo_pct'], r['ci_hi_pct'])}, folds {frac(r.get('folds_better'), r.get('folds'))}, "
            f"rats {frac(r.get('animals_better'), r.get('animals'))}" + (" — holds" if held(r) else ""))


def comp_table(C: pd.DataFrame, labels: list[str], subsets) -> pd.DataFrame:
    q = C[C.label.isin(labels) & C.subset.isin(subsets)].copy()
    q["order"] = q.label.map({lab: i for i, lab in enumerate(labels)}) * 100 + q.subset.map({s: i for i, s in enumerate(subsets)})
    q = q.sort_values(["order", "scores"])
    return pd.DataFrame({"comparison": q.label, "subset": q.subset, "scores": q.scores, "steps": q.n_steps, "REM ends": q.n_rem,
                         "Δ % [95 % CI]": [fci(a, b, c) for a, b, c in zip(q.delta_pct, q.ci_lo_pct, q.ci_hi_pct)],
                         "folds better": [frac(a, b) for a, b in zip(q.folds_better, q.folds)],
                         "rats better": [frac(a, b) for a, b in zip(q.animals_better, q.animals)],
                         "holds": q.holds.map({True: "yes", False: "no"})})


def figures(runs: dict, C: pd.DataFrame, PR: pd.DataFrame, fd: Path, gc: str) -> tuple[Path, Path]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    from sleep_quant import save_fig
    labs = list(runs)
    subs = list(SUBSETS)

    def forest(ax, label, title):
        for j, sc in enumerate(labs):
            for i, sub in enumerate(subs):
                r = row_of(C, sc, label, sub)
                if r is None:
                    continue
                y = i + (j - (len(labs) - 1) / 2) * 0.22
                ax.plot([r["ci_lo_pct"], r["ci_hi_pct"]], [y, y], color=COL[sc], lw=2, solid_capstyle="round")
                ax.plot(r["delta_pct"], y, "o", ms=8, color=COL[sc], mfc=COL[sc] if held(r) else "white", mew=2)
        ax.axvline(0, color=COL["grey"], lw=1)
        ax.set_yticks(range(len(subs)), subs)
        ax.invert_yaxis()
        ax.set_xlabel("held-out log-loss change Δ (%), < 0 = the first model is better")
        ax.set_title(title, fontsize=9)
        ax.grid(axis="x", color="#e6e5e1", lw=0.6)
        from matplotlib.lines import Line2D
        hs = [Line2D([], [], color=COL[sc], marker="o", ms=7, lw=2, label=sc) for sc in labs]
        hs += [Line2D([], [], color=COL["ink"], marker="o", ms=7, lw=0, label="holds"),
               Line2D([], [], color=COL["ink"], marker="o", ms=7, lw=0, mfc="white", mew=2, label="does not hold")]
        ax.legend(handles=hs, fontsize=7, frameon=False, loc="best")

    fig, axs = plt.subplots(1, 3, figsize=(16, 4.8), sharey=True)
    forest(axs[0], "B-full (counter) vs M_mom (momentum)", "counter (B-full) vs momentum (M_mom)")
    forest(axs[1], "B-full + momentum vs B-full", "does momentum add to the counter?")
    forest(axs[2], "M_mom vs gate (base + L1; does momentum add to the current state?)", "momentum vs current state only (reference)")
    fig.suptitle(f"Step E (held out): the REM-entry counter vs a 2nd-order momentum model, by what happened since the last REM  {gc}", fontsize=9)
    fig.tight_layout()
    p1 = save_fig(fig, fd / f"{TAG}_momentum_2026c.png")
    plt.close(fig)
    fig, axs = plt.subplots(1, len(labs) + 1, figsize=(5.2 * (len(labs) + 1), 4.6), gridspec_kw={"width_ratios": [1] * len(labs) + [1.5]})
    vmax = max(0.05, float(np.nanmax(np.abs(PR[["delta_pct"]].to_numpy(float)))))
    for ax, sc in zip(axs, labs):
        q = PR[PR.scores == sc]
        Z = np.full((len(TAU_R_H), len(TAU_D_H)), np.nan)
        for r in q.itertuples():
            Z[TAU_R_H.index(r.tau_r_h), TAU_D_H.index(r.tau_d_h)] = r.delta_pct
        im = ax.imshow(Z, cmap="RdBu_r", norm=TwoSlopeNorm(0, -vmax, vmax), aspect="auto")
        for i in range(Z.shape[0]):
            for j in range(Z.shape[1]):
                if np.isfinite(Z[i, j]):
                    ax.text(j, i, f"{Z[i, j]:+.3f}", ha="center", va="center", fontsize=8,
                            color="white" if abs(Z[i, j]) > 0.6 * vmax else "#1f1e1c")
        ax.set_xticks(range(len(TAU_D_H)), [f"{x:g} h" for x in TAU_D_H])
        ax.set_yticks(range(len(TAU_R_H)), [f"{x:g} h" for x in TAU_R_H])
        ax.set_xlabel("tau_d (decay in sleep)")
        ax.set_ylabel("tau_r (rise in wake)")
        ax.set_title(f"{sc}: B-full + S vs B-full, Δ % (folds 1.., fixed grid point)", fontsize=8)
        fig.colorbar(im, ax=ax, shrink=0.8)
    forest(axs[-1], "B-full + S (nested grid) vs B-full", "B-full + S (nested grid) vs B-full, by subset")
    fig.suptitle(f"Step E (held out): does an NREM homeostat S add to the counter model?  {gc}", fontsize=9)
    fig.tight_layout()
    p2 = save_fig(fig, fd / f"{TAG}_S_2026c.png")
    plt.close(fig)
    return p1, p2


def heldout(a) -> None:
    from _common import git_commit, write_json
    from output_paths import figure_dir, report_dir, run_dir
    from sleep_quant import md_table
    t0 = time.time()
    out = run_dir(NAME + ("_smoke" if a.smoke else ""), "2026c")
    rd, fd = (out, out / "figures") if a.smoke else (report_dir("2026c", "ephys_spikes"), figure_dir("2026c", "ephys_spikes"))
    gc = git_commit()
    runs = {}
    for lab in a.scorings:
        runs[lab] = run_scoring(lab, STATES if lab == "final" else PASS2MED, a.workers, out, smoke=a.smoke)
    C = pd.concat([r["C"] for r in runs.values()], ignore_index=True)
    PR = pd.concat([r["PR"] for r in runs.values()], ignore_index=True)
    CH = pd.concat([r["CH"] for r in runs.values()], ignore_index=True)
    CS = pd.concat([r["CS"] for r in runs.values()], ignore_index=True)
    CM = pd.concat([r["CM"] for r in runs.values()], ignore_index=True)
    SA = pd.concat([r["info"]["S_start"].assign(scores=k) for k, r in runs.items()], ignore_index=True)

    def save(df: pd.DataFrame, name: str) -> Path:
        p = rd / f"{TAG}_{name}_2026c.csv"
        df.to_csv(p, index=False)
        return p
    save(C, "comparisons")
    save(PR, "S_profile")
    save(CH, "chosen")
    save(CS, "S_coef")
    save(CM, "momentum_coef")
    save(SA, "S_start")
    p1, p2 = figures(runs, C, PR, fd, gc)
    # ---------------- verdicts
    L1lab, L2lab, Slab = COMPS[0][3], COMPS[1][3], COMPS[6][3]
    V = []
    for sc in runs:
        ra, rw = row_of(C, sc, L1lab, "all"), row_of(C, sc, L1lab, "after_wake")
        ok = bool(ra and ra.get("holds") and rw and rw.get("holds"))
        V.append({"part": "1", "scores": sc, "rule": "B-full beats M_mom held out (holds) on all NREM steps AND after wakes (after_long ∪ after_medium)",
                  "verdict": "PASS" if ok else "FAIL", "all steps": short(ra), "after wakes": short(rw),
                  "after_long": short(row_of(C, sc, L1lab, "after_long")), "after_medium": short(row_of(C, sc, L1lab, "after_medium")),
                  "after_short": short(row_of(C, sc, L1lab, "after_short"))})
        rb = row_of(C, sc, L2lab, "all")
        V.append({"part": "1b", "scores": sc, "rule": "momentum adds to the counter: B-full + momentum beats B-full (holds)",
                  "verdict": "momentum ADDS" if (rb and rb.get("holds")) else "momentum adds nothing that holds", "all steps": short(rb),
                  "after wakes": short(row_of(C, sc, L2lab, "after_wake")), "after_long": short(row_of(C, sc, L2lab, "after_long")),
                  "after_medium": short(row_of(C, sc, L2lab, "after_medium")), "after_short": short(row_of(C, sc, L2lab, "after_short"))})
        rs = row_of(C, sc, Slab, "all")
        V.append({"part": "2", "scores": sc, "rule": "S adds to the counter model: B-full + S (nested grid) beats B-full (holds)",
                  "verdict": "PASS (S in the generative model)" if (rs and rs.get("holds")) else "FAIL (S left out of the generative model)",
                  "all steps": short(rs), "after wakes": short(row_of(C, sc, Slab, "after_wake")),
                  "after_long": short(row_of(C, sc, Slab, "after_long")), "after_medium": short(row_of(C, sc, Slab, "after_medium")),
                  "after_short": short(row_of(C, sc, Slab, "after_short"))})
    V = pd.DataFrame(V)
    save(V, "verdicts")
    # ---------------- report
    first = list(runs)[0]
    L = [f"# Sleep behaviour explore — Step E (held-out part): the counter vs momentum, and an NREM homeostat S (cohort 2026c)", "",
         f"Plan: [{PLAN}](../../../../{PLAN}) (sections 1, 3, 4 and 5 Steps B and E; the pass rules are the plan's, unchanged). "
         "Builds on Step B ([ephys_spikes_sleep_explore_B_2026c.md](ephys_spikes_sleep_explore_B_2026c.md)) and its post-hoc "
         "split ([ephys_spikes_sleep_explore_B_diag_2026c.md](ephys_spikes_sleep_explore_B_diag_2026c.md)). "
         f"Driver `ephys/sleep_model_e.py heldout` (commit {gc}; file uncommitted at run time); bulk `{out}`; scorings "
         f"{', '.join(runs)}; runtime {(time.time() - t0) / 60:.1f} min ({', '.join(f'{k} {r['secs'] / 60:.1f} min' for k, r in runs.items())}).", "",
         "**Status: exploration step; claim statuses are changed in the claim audit, not here.** Only the held-out comparisons "
         "of Step E are here; the generative simulation checks (i)–(vi) are a separate part. Inputs: the scored 1-s states "
         "(FINAL = primary, pass2med_remclean = the check). No LFP features. Everything from 2026-09-11 19:40 is cut. The "
         "sleep states come from the scorer, whose EMG is the head IMU; no claim here links movement to state.", "",
         "## Verdicts", "",
         *md_table(V[["part", "scores", "rule", "verdict", "all steps", "after wakes"]]), "", "Per since-REM class:", "",
         *md_table(V[["part", "scores", "after_long", "after_medium", "after_short"]]), "",
         "## Data", ""]
    for k, r in runs.items():
        i = r["info"]
        L.append(f"- {k}: {i['steps']} NREM steps, {i['rem']} REM ends, {i['wake']} WAKE ends; {i['records']} records; animals "
                 f"{', '.join(i['animals'])}; since-REM classes (steps): " + ", ".join(f"{a} {b}" for a, b in i["cls_counts"].items())
                 + f"; {r['n_folds_used']} test folds (fold 0 only starts the nested choices).")
    L += ["", f"- Counter P = `{KEY}` (τ_w = 600 s, κ = 0) for both scorings: the grid point chosen most often by Step B's nested "
          "forward chaining on FINAL (folds 7–15; 300 s in folds 2–6, 600 s with κ = 60 s in fold 1). **Noted:** fixing it "
          "uses a choice made with all of Step B's folds, i.e. partly with later test blocks; the same base enters every "
          "comparison except B-full vs M_mom, where it could favour the counter, so that comparison is repeated with the "
          "per-fold nested choice τ_w ∈ {300, 600} s, κ = 0 (row 'B-full (nested tau_w 5 / 10 min) vs M_mom'). pass2med "
          "uses FINAL's key, as in Steps B-diag and C.", "",
          "## Definitions", "",
          "Time is field-PC local time. States per second $s_t \\in \\{0\\ \\text{unknown}, 1\\ \\text{WAKE}, 3\\ \\text{NREM}, "
          "5\\ \\text{REM}\\}$. A **bout** is a maximal run of one state (unknown runs included). Records, scorings, the cut, "
          "light (NOAA sunrise–sunset) and the day-half blocks are those of Steps A–C.", "",
          "### The step model (Step B's, imported unchanged)", "",
          "- **NREM step.** Every 10 s of every NREM bout; outcome $y \\in \\{$stay, REM, WAKE$\\}$ = the state that follows the "
          "bout if the bout ends inside the step. History is taken at the bout start; elapsed $e$ = s since the bout start.",
          "- **Multinomial hazard.** $\\Pr(y = j \\mid x) = e^{\\eta_j} / (1 + e^{\\eta_R} + e^{\\eta_W})$, $\\eta_{stay} = 0$, "
          "$\\eta_j = \\alpha_j + x^\\top \\beta_j$; sklearn multinomial logistic regression, $C = 10^4$ (`sleep_model.fit_eval`). "
          "A coefficient on REM vs stay is the log-odds ratio of entering REM rather than staying in NREM in the next 10 s.",
          "- **base** = cubic B-spline of $\\ln(e + 5)$ (4 knots) + $(\\sin, \\cos)(2\\pi k h / 24)$, $k = 1, 2$ ($h$ = clock hour) "
          "+ experiment day + has_anchor (a REM earlier in the record) + dark (NOAA sunset → sunrise) + animal intercepts; "
          "linear terms z-scored on the training steps.",
          "- **L1** (current state) = $\\ln(1 + d)$ ($d$ = length in s of the WAKE bout just before the NREM bout, 0 otherwise), "
          "previous bout REM, previous bout unknown (or record start), wake share of the last 10 min.",
          "- **Counter P** (min). $P$ rises by $1/60$ per NREM second, is multiplied by $e^{-d/\\tau_w}$ over a wake of length "
          "$d$ and set to 0 by a REM bout ($\\kappa = 0$); unknown epochs freeze it; at a step $P_t = P_{start} + e/60$ "
          "(`sleep_model.counter_starts`). Enters as a cubic B-spline of $\\ln(1 + P_t)$ (4 knots).",
          "- **B-full** = base + L1 + spline $\\ln(1 + P_t)$ (Step B's model; $\\tau_w = 600$ s). **gate** = base + L1 (no history).", "",
          "### Part 1: momentum (a 2nd-order semi-Markov alternative; Stephenson 2025)", "",
          "For NREM bout $i$: prev1 = bout $i-1$ (WAKE, REM or unknown; never NREM, since bouts are maximal; 'none' at the "
          "record start), prev2 = bout $i-2$ (NREM, WAKE, REM, unknown, or none if $i < 2$); $\\delta_1, \\delta_2$ = their lengths (s).",
          "- **momentum terms** $m$: $\\mathbb 1[\\text{prev2} = c]$ for $c \\in$ {WAKE, REM, unknown, none} (reference NREM); "
          "$\\ln(1 + \\delta_2)\\,\\mathbb 1[\\text{prev2} = c]$ for $c \\in$ {NREM, WAKE, REM, unknown}; "
          "$\\ln(1 + \\delta_1)\\,\\mathbb 1[\\text{prev1} = c]$ for $c \\in$ {REM, unknown} (for a WAKE prev1 this is L1's "
          "$\\ln(1 + d)$; L1 also holds the prev1 type dummies). All z-scored, linear, in both equations.",
          "- **M_mom** = base + L1 + $m$ — the current-state terms extended to two bouts back, with no counter. "
          "**B-full + momentum** = B-full + $m$. **M_mom_lit** (sensitivity, the task's literal list) = base + L1 + prev2 "
          "dummies + one $\\ln(1 + \\delta_2)$ for every prev2 type + the two prev1 terms. *Choice stated here:* the main $m$ "
          "lets the prev2 log duration have a slope per prev2 type, so an NREM and a wake duration are not forced to share one "
          "(this gives momentum more room, never less).", "",
          "### Part 2: the NREM homeostat S (plan section 4)", "",
          "- **S** (0–1, dimensionless), per second, exact exponential updates: WAKE $S_{t+1} = 1 - (1 - S_t)\\,e^{-1/\\tau_r}$ "
          "(rises towards 1 with time constant $\\tau_r$); NREM or REM $S_{t+1} = S_t\\,e^{-1/\\tau_d}$ (decays towards 0 "
          "with $\\tau_d$); unknown $S_{t+1} = S_t$ (frozen).",
          "- **Start.** Each record starts at its animal's mean $\\bar S_a$ = the mean of S over all recorded (non-unknown) "
          "seconds of the animal's records in a first pass started at 0.5 (two passes). *Noted:* $\\bar S_a$ uses all of the "
          "animal's records (test blocks included); it is one number per animal and grid point.",
          "- **At an NREM step** $S_t = S_{start}\\,e^{-e/\\tau_d}$ ($S_{start}$ = S at the bout start), entered as one z-scored "
          "linear term; a coefficient is per SD of $S_t$ on the training steps (SD in the coefficient table).",
          "- **Grid** $\\tau_r \\in$ {1, 4, 16} h × $\\tau_d \\in$ {0.5, 2, 6} h. **B-full + S** = B-full + $S_t$; the grid "
          "point is chosen per test fold by nested forward chaining (the lowest step-weighted held-out log loss over the "
          "earlier folds, as Step B; fold 0 only starts the choice). The **profile** = each grid point fixed over folds 1.., "
          "Δ vs B-full.",
          "- **Coefficients** (description): full-data fit of B-full + S at the modal chosen grid point (the grid point chosen "
          "in most test folds; a tie goes to the tied point with the lowest profile Δ) and pooled at every "
          "grid point), multinomial logit by Newton–Raphson with the same L2 penalty ($10^{-4}\\lVert\\beta\\rVert^2/2$; "
          "`sleep_explore_c.mnl_fit`), reference-coded (REM vs stay, WAKE vs stay); cluster-robust 95 % CI "
          "$\\hat\\beta \\pm 1.96\\,\\widehat{se}$, $\\hat V = H^{-1}(\\sum_g U_g U_g^\\top) H^{-1} G/(G-1)$ over the day-half "
          "blocks $g$; per animal: the same model fitted to the animal alone (signs).", "",
          "### Held out, subsets and verdict rules", "",
          "- **Δ.** Forward chaining over the day-half blocks (train on all earlier blocks, test the next; the first 6 blocks "
          "only train); per-step log loss $\\ell = -\\ln \\hat p(y)$; per fold the mean over the test steps of the subset; "
          "$\\Delta = 100\\,(\\bar\\ell_{hi} - \\bar\\ell_{lo}) / \\bar\\ell_{lo}$ (step-weighted over folds 1..), < 0 = the first-"
          "named model is better; 95 % CI by bootstrap over folds (2000); rats better = per-animal pooled Δ < 0; **holds** = CI "
          "< 0 and ≥ 5/6 rats (`sleep_schedule_phase2.compare`).",
          "- **since-REM class** at the NREM bout start (`sleep_model_diag.since_rem_class`): after_long = a wake ≥ 420 s "
          "occurred since the last REM (or the record start if no REM yet); after_medium = a 120–419-s wake, none longer; "
          "after_short = only wakes < 120 s or none; **after_wake** = after_long ∪ after_medium. Supplementary split by the "
          "prev1 type (WAKE / REM / unknown or none). The nested S choice is made on all steps and applied in every subset.",
          "- **Part 1 rule** (plan Step E: 'the model must beat momentum held out, especially on bouts after wakes'), "
          "operationalised here before the run: PASS = B-full vs M_mom holds on all NREM steps **and** on the after_wake "
          "steps (FINAL; pass2med as the check). Whether momentum adds anything beyond the counter is read from B-full + "
          "momentum vs B-full (holds = it adds).",
          "- **Part 2 rule** (the task): PASS = B-full + S vs B-full holds on all NREM steps; otherwise S is left out of the "
          "generative model.", "",
          "## Part 1 — the counter vs momentum (held out)", "",
          f"![]({'../figures/' if not a.smoke else 'figures/'}{p1.name})", "",
          "### Main comparisons by since-REM class", "",
          *md_table(comp_table(C, [COMPS[0][3], COMPS[1][3]], SUBSETS)), "",
          "### References and sensitivities", "",
          *md_table(comp_table(C, [COMPS[2][3], COMPS[3][3], COMPS[4][3], COMPS[5][3]], SUBSETS)), "",
          "### Supplementary: by the type of the bout just before (prev1)", "",
          *md_table(comp_table(C, [COMPS[0][3], COMPS[1][3], COMPS[6][3]], PREV1)), "",
          "### Momentum coefficients (full-data fits; description; per SD; cluster-robust 95 % CI by block)", ""]
    for k in runs:
        q = CM[(CM.scores == k)]
        if not len(q):
            continue
        tb = q.assign(**{"coef [95 % CI]": [f"{c:+.3f} [{lo:+.3f}, {hi:+.3f}]" for c, lo, hi in zip(q["coef"], q.ci_lo, q.ci_hi)]})
        L += [f"**{k}**", "", *md_table(tb[["model", "term", "equation", "coef [95 % CI]", "p"]].round(4)), ""]
    L += ["## Part 2 — does an NREM homeostat S add to the counter model? (held out)", "",
          f"![]({'../figures/' if not a.smoke else 'figures/'}{p2.name})", "",
          "### B-full + S (nested grid) vs B-full by since-REM class", "",
          *md_table(comp_table(C, [COMPS[6][3]], SUBSETS)), "",
          "### Profile over the grid (each grid point fixed, folds 1..; Δ vs B-full)", "",
          *md_table(PR.assign(**{"Δ % [95 % CI]": [fci(a_, b_, c_) for a_, b_, c_ in zip(PR.delta_pct, PR.ci_lo_pct, PR.ci_hi_pct)],
                                 "folds better": [frac(x, y) for x, y in zip(PR.folds_better, PR.folds)],
                                 "rats better": [frac(x, 6) for x in PR.animals_better],
                                 "holds": PR.holds.map({True: "yes", False: "no"})})[
              ["scores", "tau_r_h", "tau_d_h", "Δ % [95 % CI]", "folds better", "rats better", "holds"]]), "",
          "### Grid point chosen per fold (nested forward chaining) and the B-full nested τ_w", "",
          *md_table(CH), "",
          "### S coefficients (full-data fits; per SD of S_t; cluster-robust 95 % CI by block)", ""]
    for k, r in runs.items():
        q = CS[(CS.scores == k) & (CS.animal == "pooled")]
        tb = q.assign(**{"coef [95 % CI]": [f"{c:+.3f} [{lo:+.3f}, {hi:+.3f}]" for c, lo, hi in zip(q["coef"], q.ci_lo, q.ci_hi)]})
        L += [f"**{k}** — pooled at every grid point; modal chosen grid point `{r['s_modal']}`", "",
              *md_table(tb[["term", "equation", "coef [95 % CI]", "p", "sd_term"]].round(4)), ""]
        pa = CS[(CS.scores == k) & (CS.animal != "pooled")]
        if len(pa):
            sg = pa.groupby("equation")["coef"].agg(lambda s: f"{int((s < 0).sum())}/{len(s)} < 0, {int((s > 0).sum())}/{len(s)} > 0")
            L += [f"Per animal at `{r['s_modal']}` (the same model fitted to each animal alone): "
                  + "; ".join(f"{e}: {v}" for e, v in sg.items()), "",
                  *md_table(pa[["animal", "equation", "coef", "ci_lo", "ci_hi"]].round(3)), ""]
    L += ["### Start values of S per animal (two-pass mean)", "",
          *md_table(SA.pivot_table(index=["scores", "grid"], columns="animal", values="S_start").round(3).reset_index()), "",
          "## Deviations from the plan and notes", "",
          "- Only the held-out part of Step E is here (task scope); the simulation checks (i)–(vi) are not run in this module.",
          f"- B-full's counter is fixed at `{KEY}` (see Data); the momentum comparison is repeated with a per-fold nested τ_w.",
          "- The task listed the prev2 types as WAKE / REM / unknown / none; prev2 is most often NREM (prev1 never is), so NREM "
          "is the reference level, and ln(1 + dur prev2) is entered per prev2 type (the literal single-slope version is the "
          "sensitivity M_mom_lit).",
          "- The 'especially after wakes' clause of the plan's Step-E rule has no number in the plan; it is read as 'holds on "
          "the after_wake steps' (written in Definitions before the run).",
          "- Held out on all NREM steps, no post-round exclusion (as Step B; plan section 3 restricts that exclusion to day / "
          "night contrasts).",
          "- S's start value per animal uses all of the animal's records (one number per animal and grid point), stated in "
          "Definitions.",
          "- Bulk: per-step held-out log losses `heldout_steps_<scores>.npz` (keys `te_<fold>`, `ll_<fold>__<spec>`) and "
          "per-fold tables `folds_by_subset_<scores>.csv` in the run folder.", ""]
    rp = rd / f"{TAG}_2026c.md"
    rp.write_text("\n".join(L) + "\n", encoding="utf-8")
    write_json(rd / f"run_manifest_{NAME}_2026c.json",
               {"run_dir": str(out), "git_commit": gc, "scorings": list(runs), "p_key": KEY, "p_key_alt": KEY_ALT,
                "grid_tau_r_h": list(TAU_R_H), "grid_tau_d_h": list(TAU_D_H), "s_modal": {k: r["s_modal"] for k, r in runs.items()},
                "runtime_min": round((time.time() - t0) / 60, 2), "workers": a.workers, "smoke": bool(a.smoke),
                "report": str(rp), "figures": [str(p1), str(p2)]})
    print(V[["part", "scores", "verdict", "all steps", "after wakes"]].to_string(index=False), flush=True)
    print("written", rp, flush=True)


# ================================================================== selftest
def simulate_e(world: str, n_animals: int = 3, n_days: int = 7, hours: float = 8.0, seed: int = 0) -> list[dict]:
    """Synthetic records, one per day-half (06:00 and 18:00 starts). Per 10-s NREM step: REM and WAKE hazards by world;
    REM bouts 40-120 s, then NREM (or WAKE with p_rw); wakes 5-40 s (55 %), 60-419 s (30 %), 600-3600 s (15 %).
      'counter'  logit REM = -6 + 1.8 ln(1 + P) (P: tau_w 600 s, kappa 0); logit WAKE = -4.2; no momentum, no S effect.
      'momentum' logit REM = -5 + 2.2 [prev2 = REM] - 0.8 [prev2 = NREM] (ln(1 + dur prev2) - 5); logit WAKE = -4.2; no counter.
      'S'        REM as 'counter'; logit WAKE = -2.0 - 4.0 S, S per second with tau_r 4 h, tau_d 2 h (start 0.4)."""
    rng = np.random.default_rng(seed)
    L = int(hours * 3600)
    qr, qd = np.exp(-1 / (4 * 3600.0)), np.exp(-1 / (2 * 3600.0))
    p_rw = 0.4 if world == "momentum" else 0.2
    recs, rid = [], 0
    for an in range(n_animals):
        for d in range(n_days):
            for half in ("D", "N"):
                start = pd.Timestamp("2026-09-01") + pd.Timedelta(days=d, hours=6 if half == "D" else 18)
                st = np.zeros(L, np.int8)
                t, s, P, S = 0, N, 0.0, 0.4
                hist: list[tuple[int, int]] = []          # completed bouts (type, length)
                nb_start, prev1, prev2 = 0, None, None
                while t < L:
                    if s == N:
                        if t == nb_start:                 # new NREM bout: the two bouts before it
                            prev1 = hist[-1] if len(hist) >= 1 else None
                            prev2 = hist[-2] if len(hist) >= 2 else None
                        if world == "momentum":
                            er = -5.0 + (2.2 if prev2 is not None and prev2[0] == R else 0.0)
                            if prev2 is not None and prev2[0] == N:
                                er -= 0.8 * (np.log1p(prev2[1]) - 5.0)
                        else:
                            er = -6.0 + 1.8 * np.log1p(P)
                        ew = -2.0 - 4.0 * S if world == "S" else -4.2
                        den = 1 + np.exp(er) + np.exp(ew)
                        pr, pw = np.exp(er) / den, np.exp(ew) / den
                        n = min(10, L - t)
                        st[t:t + n] = N
                        P += n / 60
                        S *= qd ** n
                        t += n
                        u = rng.random()
                        nxt = R if u < pr else (W if u < pr + pw else N)
                        if nxt != N:
                            hist.append((N, t - nb_start))
                            s = nxt
                    elif s == R:
                        r = int(rng.integers(40, 121))
                        st[t:t + r] = R
                        P, S = 0.0, S * qd ** r
                        t += r
                        hist.append((R, r))
                        s = W if rng.random() < p_rw else N
                        nb_start = t
                    else:
                        u = rng.random()
                        dd = int(rng.integers(5, 41)) if u < 0.55 else (int(rng.integers(60, 420)) if u < 0.85 else int(rng.integers(600, 3601)))
                        st[t:t + dd] = W
                        P *= np.exp(-dd / 600.0)
                        S = 1 - (1 - S) * qr ** dd
                        t += dd
                        hist.append((W, dd))
                        s, nb_start = N, t
                recs.append({"animal": f"S{an}", "start": start, "end": start + pd.Timedelta(seconds=L), "state": st[:L],
                             "record_id": rid, "block": f"{start:%Y-%m-%d}{half}", "sessions": []})
                rid += 1
    return recs


def selftest(workers: int = 6) -> None:
    t0 = time.time()
    # 1. momentum features by hand
    seq = [(W, 10), (N, 20), (R, 10), (N, 30), (W, 20), (N, 40), (R, 15), (W, 8), (N, 10), (W, 5), (0, 4), (N, 10), (0, 3), (W, 7), (N, 12)]
    st = np.concatenate([np.full(n, s, np.int8) for s, n in seq])
    mm = momentum_starts(st)
    ix = {c: j for j, c in enumerate(MOM_ALL)}

    def chk(a, **kv):
        exp = np.zeros(len(MOM_ALL))
        for k_, v_ in kv.items():
            exp[ix[k_]] = v_
        assert np.allclose(mm[a], exp), (a, dict(zip(MOM_ALL, mm[a])), kv)
    starts = np.cumsum([0] + [n for _, n in seq])
    sa = {i: int(starts[i]) for i in range(len(seq))}
    chk(sa[1], m2_none=1)                                                             # prev1 WAKE, no prev2
    chk(sa[3], l1_R=np.log1p(10), l2_N=np.log1p(20), l2_any=np.log1p(20))             # prev1 REM, prev2 NREM
    chk(sa[5], l2_N=np.log1p(30), l2_any=np.log1p(30))                                # prev1 WAKE, prev2 NREM
    chk(sa[8], m2_R=1, l2_R=np.log1p(15), l2_any=np.log1p(15))                        # R W N
    chk(sa[11], l1_U=np.log1p(4), m2_W=1, l2_W=np.log1p(5), l2_any=np.log1p(5))       # W U N
    chk(sa[14], m2_U=1, l2_U=np.log1p(3), l2_any=np.log1p(3))                         # U W N
    # 2. S closed form vs a per-second loop
    rng = np.random.default_rng(1)
    st2 = np.concatenate([np.full(int(rng.integers(1, 900)), rng.choice([0, W, N, R]), np.int8) for _ in range(300)])
    for tr, td, s0 in ((3600.0, 1800.0, 0.3), (57600.0, 21600.0, 0.8)):
        out, tot, cnt = s_pass(st2, tr, td, s0)
        S, vals, Ss = s0, [], np.zeros(len(st2))
        for i, x in enumerate(st2):
            Ss[i] = S
            if x == 0:
                continue
            vals.append(S)
            S = 1 - (1 - S) * np.exp(-1 / tr) if x == W else S * np.exp(-1 / td)
        assert cnt == len(vals) and abs(tot - sum(vals)) < 1e-6 * len(vals), (tot, sum(vals))
        assert all(abs(out[a] - Ss[a]) < 1e-9 for a in out)
        a0 = next(a for s_, a, b in bouts(st2) if s_ == N and b - a > 50)
        assert abs(Ss[a0 + 37] - out[a0] * np.exp(-37 / td)) < 1e-9                 # S_t inside an NREM bout
    print(f"selftest: feature arithmetic OK ({time.time() - t0:.0f} s)", flush=True)
    # 3. synthetic worlds: the comparisons must pick the right model
    grid = [(1.0, 0.5), (4.0, 2.0), (16.0, 6.0)]
    got = {}
    for world in ("counter", "momentum", "S"):
        recs = simulate_e(world, seed={"counter": 11, "momentum": 12, "S": 13}[world])
        D, info = prep_recs(recs, grid)
        folds = folds_of(D)
        allsp = specs_for(grid)
        keep = {"counter": ("B", "B300", "gate", "mom", "Bmom", *(f"BS:{skey(*g)}" for g in grid)),
                "momentum": ("B", "B300", "gate", "mom", "Bmom"),
                "S": ("B", "B300", *(f"BS:{skey(*g)}" for g in grid))}[world]
        res = run_heldout(D, {k: allsp[k] for k in keep}, folds, workers, world)
        cols = {c: ("fixed", c) for c in keep}
        if world != "momentum":
            chS, _, _ = nested(res, [f"BS:{skey(*g)}" for g in grid])
            cols["BS"] = ("chosen", chS)
        F, FA = sub_tables(res, D, cols, None)
        r = {}
        if "mom" in cols:
            r["B_vs_mom"] = cmp(F, FA, "mom", "B")
            r["Bmom_vs_B"] = cmp(F, FA, "B", "Bmom")
        if "BS" in cols:
            r["BS_vs_B"] = cmp(F, FA, "B", "BS")
            mode = pd.Series([c for c in chS if isinstance(c, str)]).mode().iloc[0][3:]
            rows = fit_job("x", D, {"L1": True, "hist": KEY, "extra": (mode,)}, (mode,))
            r["S_coef"] = {x["equation"]: (x["coef"], x["ci_lo"], x["ci_hi"]) for x in rows}
            r["S_mode"] = mode
        got[world] = r
        print(f"selftest [{world}] {info['steps']} steps, {info['rem']} REM, {info['wake']} WAKE: "
              + "; ".join(f"{k}: {v['delta_pct']:+.3f} % [{v['ci_lo_pct']:+.3f}, {v['ci_hi_pct']:+.3f}] folds {v['folds_better']}/{v['folds']}"
                          for k, v in r.items() if isinstance(v, dict) and "delta_pct" in v)
              + (f"; S mode {r['S_mode']}, coef {r['S_coef']}" if "S_coef" in r else ""), flush=True)
    c, m, s = got["counter"], got["momentum"], got["S"]
    assert c["B_vs_mom"]["delta_pct"] < 0 and c["B_vs_mom"]["ci_hi_pct"] < 0, "counter world: B-full must beat M_mom"
    assert c["Bmom_vs_B"]["ci_lo_pct"] > -0.3, "counter world: momentum must not add much"
    assert m["B_vs_mom"]["delta_pct"] > 0 and m["B_vs_mom"]["ci_lo_pct"] > 0, "momentum world: M_mom must beat B-full"
    assert m["Bmom_vs_B"]["delta_pct"] < 0 and m["Bmom_vs_B"]["ci_hi_pct"] < 0, "momentum world: momentum must add to B-full"
    assert s["BS_vs_B"]["delta_pct"] < 0 and s["BS_vs_B"]["ci_hi_pct"] < 0, "S world: B-full + S must beat B-full"
    assert s["S_coef"]["WAKE vs stay"][2] < 0, "S world: S must lower the WAKE hazard (CI < 0)"
    assert s["BS_vs_B"]["delta_pct"] < c["BS_vs_B"]["delta_pct"] - 0.3, "S world gain must exceed the no-S world's"
    print(f"selftest PASS ({time.time() - t0:.0f} s): momentum / S arithmetic; counter world -> counter beats momentum; "
          "momentum world -> momentum beats the counter and adds to it; S world -> S adds, lowers waking", flush=True)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["heldout"])
    ap.add_argument("--scorings", nargs="+", default=["final", "pass2med"], choices=["final", "pass2med"])
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--smoke", action="store_true", help="4 folds, 3 grid points, outputs only in the run folder")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest(min(a.workers, 8))
    elif a.cmd == "heldout":
        if a.workers > 8:
            raise SystemExit("at most 8 workers on this shared PC")
        heldout(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
