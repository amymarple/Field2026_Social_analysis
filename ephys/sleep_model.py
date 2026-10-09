r"""Step B of the sleep-behaviour explore (plan implementation_plan/2026-10-08-sleep-behaviour-explore.md §4-§5, written
before results): the minimal scheduler model — one REM-entry counter P with a wake discount, read through a day/night
gate — held out by forward chaining against the feature model M2t, a hard reset, a pause and a gate-only model.

Usage:  python ephys/sleep_model.py stepB [--scorings final pass2med] [--workers 15] [--smoke]
        python ephys/sleep_model.py --selftest

Definitions (1-s scored states: 0 unknown, 1 WAKE, 3 NREM, 5 REM; records = sessions joined across splits <= 60 s;
everything from 2026-09-11 19:40 excluded; 10-s NREM steps as Phases 1-3):
  counter P (minutes), per record, from its bouts in order, starting at 0 at the record start:
      NREM bout of length n s      P <- P + n / 60   (within the bout, at a step with `elapsed` s: P_t = P_start + elapsed / 60)
      WAKE bout of length d s      P <- P * exp(-d / tau_w)        (any wake, microarousals included)
      REM bout of length r s       P <- P * exp(-r / kappa)        (discharge phi(r) = 1 - exp(-r / kappa); kappa = 0: P <- 0)
      unknown run                  P unchanged (frozen)
    variants: tau_w in {0, 15 s, 30 s, 1, 2, 5, 10, 30 min, inf} (0 = every wake erases P; inf = a wake pauses P);
              kappa in {0 (full discharge), 20, 60, 180 s};
              reset    = P <- 0 after a wake >= 420 s, unchanged after shorter wakes (the hard-reset hypothesis);
              pause    = tau_w = inf;
              const    = discharge by a constant fraction phi0 in {0.5, 0.8, 0.95, 1} independent of the REM length (H6).
  hazard per 10-s NREM step: multinomial logit over stay / REM / WAKE (sklearn LogisticRegression, C = 1e4) with
      base     B-spline of ln(elapsed + 5) (4 knots), sin / cos (2 pi k h / 24) for k = 1, 2, linear experiment day,
               dark (NOAA sunset-to-sunrise at the step), has_anchor (a REM seen earlier in the record), animal intercepts;
      L1       ln(1 + preceding wake), previous bout REM, previous bout unknown, wake share of the last 10 min (as M2t);
      history  'P'   = B-spline of ln(1 + P_t);
               'M2t' = B-spline of ln(1 + n_since + elapsed) + ln(1 + wake since the last REM) + ln REM_pre (Phase 2 C2);
               none  = gate-only.
      B-full = base + L1 + P;  B-mech = base + P (no L1);  M2t here = base + L1 + 'M2t' (Phase 2's M2t + dark).
  validation: forward chaining over the day-half blocks (train on all earlier blocks, test the next; the first 6 blocks
      only train). Grid parameters are chosen by NESTED forward chaining: for test fold k the grid point with the lowest
      step-weighted held-out log-loss over folds 1..k-1 is used; fold 0 therefore has no choice and is dropped from every
      comparison. Delta = held-out log-loss change in % of the smaller model, 95 % CI by bootstrap over folds;
      holds = CI < 0 and >= 5 / 6 animals better (Phase 1-3 rule).
  pass rules (plan §5 Step B): B-full not worse than M2t by more than 0.1 %; B-full beats reset and pause (holds);
      B-full beats gate-only by at least 0.5 %; the tau_w profile minimum is interior (30 s - 10 min) and stable when one
      animal is left out (refit without it). Inside step B: H6 (kappa vs a constant discharge fraction), H19 (a wall-clock
      time-since-REM spline on top of B-full), H24 (fragmentation frag60 on top of B-full + w60).
  frag60 = number of wake bouts >= 40 s ending in the 60 min before the bout start; w60 = wake share of recorded seconds
      in the same 60 min; t_since = wall seconds since the end of the last REM (bout start) + elapsed.
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
from sleep_cycles import boot_ci, bouts, loglosses  # noqa: E402
from sleep_schedule import N, R, REVIEW, ROOT, STATES, W, included_sessions  # noqa: E402

TAUS = [0.0, 15.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1800.0, np.inf]
KAPPAS = [0.0, 20.0, 60.0, 180.0]
PHIS = [0.5, 0.8, 0.95, 1.0]
RESET_S = 420
PASS2MED = Path("D:/3rd_rat_spikes/analysis/sleep_server/states_1s_pass2med")
FIRST = 6


def tlab(x: float) -> str:
    return "inf" if np.isinf(x) else f"{int(x)}"


def pkey(tau: float, kappa: float) -> str:
    return f"P_tw{tlab(tau)}_k{tlab(kappa)}"


# ------------------------------------------------------------------ the counter (pure; selftested)
def counter_starts(state: np.ndarray, mode: str, tau: float = np.inf, kappa: float = 0.0, phi: float = 1.0) -> dict[int, float]:
    """P (minutes) at the start of every NREM bout of one record. mode: 'disc' (exponential wake discount tau, REM
    discharge kappa), 'reset' (P <- 0 after a wake >= RESET_S, else unchanged; REM discharge kappa), 'const' (wake
    discount tau, REM discharge by the constant fraction phi)."""
    P, out = 0.0, {}
    for s, a, b in bouts(state):
        n = b - a
        if s == N:
            out[a] = P
            P += n / 60.0
        elif s == W:
            if mode == "reset":
                if n >= RESET_S:
                    P = 0.0
            elif tau == 0:
                P = 0.0
            elif np.isfinite(tau):
                P *= np.exp(-n / tau)
        elif s == R:
            if mode == "const":
                P *= (1.0 - phi)
            elif kappa == 0:
                P = 0.0
            else:
                P *= np.exp(-n / kappa)
    return out


def variant_specs() -> dict[str, dict]:
    v = {}
    for t in TAUS:
        for k in KAPPAS:
            v[pkey(t, k)] = {"mode": "disc", "tau": t, "kappa": k}
    for k in KAPPAS:
        v[f"R7_k{tlab(k)}"] = {"mode": "reset", "kappa": k}
    for t in TAUS:
        for f in PHIS:
            v[f"Pc_tw{tlab(t)}_f{int(round(100 * f))}"] = {"mode": "const", "tau": t, "phi": f}
    return v


# ------------------------------------------------------------------ data
def frag_terms(state: np.ndarray, starts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    bl = bouts(state)
    wake_ends = np.array([b for s, a, b in bl if s == W and (b - a) >= 40])
    cw = np.r_[0, np.cumsum(state == W)]
    ck = np.r_[0, np.cumsum(state != 0)]
    lo = np.maximum(starts - 3600, 0)
    frag = np.searchsorted(wake_ends, starts, side="right") - np.searchsorted(wake_ends, lo, side="right") if len(wake_ends) else np.zeros(len(starts))
    rec = ck[starts] - ck[lo]
    w60 = np.where(rec > 0, (cw[starts] - cw[lo]) / np.maximum(rec, 1), 0.0)
    return frag.astype(float), w60


def build_data(recs: list[dict], variants: dict[str, dict]) -> pd.DataFrame:
    from sleep_schedule_phase2 import build_steps
    from sleep_schedule_phase3 import light_flags
    steps = build_steps(recs)
    steps["dark"] = (~light_flags(steps.t)).astype(float)
    byrid = {rc["record_id"]: rc for rc in recs}
    cols = {k: np.zeros(len(steps)) for k in variants}
    frag, w60 = np.zeros(len(steps)), np.zeros(len(steps))
    for rid, g in steps.groupby("record_id"):
        st = byrid[rid]["state"]
        pos = steps.index.get_indexer(g.index)
        bs = g.bout_start.to_numpy()
        el = g.elapsed.to_numpy() / 60.0
        for k, sp in variants.items():
            ps = counter_starts(st, sp["mode"], sp.get("tau", np.inf), sp.get("kappa", 0.0), sp.get("phi", 1.0))
            cols[k][pos] = np.array([ps[b] for b in bs]) + el
        ub, inv = np.unique(bs, return_inverse=True)
        f_, w_ = frag_terms(st, ub)
        frag[pos], w60[pos] = f_[inv], w_[inv]
    for k in variants:
        steps[f"lP_{k}"] = np.log1p(cols[k]).astype(np.float32)
    steps["frag60"], steps["w60"] = frag, w60
    steps["l_tsince_t"] = np.log1p(steps.t_since.astype(float) + steps.elapsed.astype(float)) * steps.has_anchor
    return steps


def to_arrays(steps: pd.DataFrame) -> dict[str, np.ndarray]:
    D = {"y": steps.y.to_numpy().astype(np.int8), "animal": steps.animal.to_numpy().astype(str), "block": steps.block.to_numpy().astype(str)}
    hour = steps.hour.to_numpy()
    for k in (1, 2):
        D[f"sin{k}"], D[f"cos{k}"] = np.sin(2 * np.pi * k * hour / 24), np.cos(2 * np.pi * k * hour / 24)
    D["l_elapsed"] = np.log(steps.elapsed.to_numpy() + 5.0)
    D["T_day"] = steps.T_day.to_numpy().astype(float)
    D["dark"] = steps.dark.to_numpy().astype(float)
    D["has_anchor"] = steps.has_anchor.to_numpy().astype(float)
    D["l_dprev"] = np.log1p(steps.d_prev.to_numpy().astype(float))
    D["prev_rem"], D["prev_unk"], D["fW10"] = (steps[c].to_numpy().astype(float) for c in ("prev_rem", "prev_unk", "fW10"))
    D["l_nsince_t"] = np.log1p(steps.n_since.to_numpy().astype(float) + steps.elapsed.to_numpy().astype(float))
    D["l_wsince"] = np.log1p(steps.w_since.to_numpy().astype(float))
    D["l_rem_pre"] = np.log(steps.rem_pre.to_numpy().astype(float)) * D["has_anchor"]
    D["l_tsince_t"] = steps.l_tsince_t.to_numpy().astype(float)
    D["frag60"], D["w60"] = steps.frag60.to_numpy().astype(float), steps.w60.to_numpy().astype(float)
    for c in steps.columns:
        if c.startswith("lP_"):
            D[c] = steps[c].to_numpy()
    return D


# ------------------------------------------------------------------ design / fit
def design(D: dict, idx: np.ndarray, spec: dict, st: dict | None, levels: list[str]) -> tuple[np.ndarray, dict]:
    from sklearn.preprocessing import SplineTransformer
    fit = st is None
    st = st or {}
    spl_cols = ["l_elapsed"]
    lin = ["T_day", "has_anchor"] + (["dark"] if spec.get("dark", True) else [])
    if spec.get("L1"):
        lin += ["l_dprev", "prev_rem", "prev_unk", "fW10"]
    h = spec.get("hist")
    if h == "M2t":
        spl_cols.append("l_nsince_t")
        lin += ["l_wsince", "l_rem_pre"]
    elif h:
        spl_cols.append(f"lP_{h}")
    for e in spec.get("extra", ()):
        (spl_cols if e == "l_tsince_t" else lin).append(e)
    if fit:
        for c in spl_cols:
            st[f"spl_{c}"] = SplineTransformer(n_knots=4, degree=3, include_bias=False).fit(D[c][idx, None].astype(float))
        st["mu"] = {c: float(D[c][idx].mean()) for c in lin}
        st["sd"] = {c: float(D[c][idx].std()) or 1.0 for c in lin}
    parts = [st[f"spl_{c}"].transform(D[c][idx, None].astype(float)) for c in spl_cols]
    parts.append(np.column_stack([D[f"{f}{k}"][idx] for k in (1, 2) for f in ("sin", "cos")]))
    parts.append(np.column_stack([(D[c][idx] - st["mu"][c]) / st["sd"][c] for c in lin]))
    an = D["animal"][idx]
    parts.append(np.column_stack([(an == lv).astype(float) for lv in levels[1:]]) if len(levels) > 1 else np.zeros((len(idx), 0)))
    return np.column_stack(parts), st


def fit_eval(D: dict, tr: np.ndarray, te: np.ndarray, spec: dict) -> np.ndarray:
    from sklearn.linear_model import LogisticRegression
    levels = sorted(set(D["animal"][tr]))
    Xtr, st = design(D, tr, spec, None, levels)
    m = LogisticRegression(C=1e4, max_iter=3000).fit(Xtr, D["y"][tr])
    Xte, _ = design(D, te, spec, st, levels)
    p = np.full((len(te), 3), 1e-12)
    p[:, m.classes_] = m.predict_proba(Xte)
    p /= p.sum(1, keepdims=True)
    return loglosses(p, D["y"][te].astype(int))["ll"]


def fold_job(k: int, tr: np.ndarray, te: np.ndarray, D: dict, specs: dict[str, dict]) -> dict:
    te = te[np.isin(D["animal"][te], np.unique(D["animal"][tr]))]
    out = {"k": k, "n": len(te), "n_rem": int((D["y"][te] == 1).sum()), "ll": {}, "lla": {}}
    an = D["animal"][te]
    ua = np.unique(an)
    for name, sp in specs.items():
        ll = fit_eval(D, tr, te, sp)
        out["ll"][name] = float(ll.mean())
        out["lla"][name] = {a: (float(ll[an == a].mean()), int((an == a).sum())) for a in ua}
    return out


def folds_of(D: dict) -> list[tuple[np.ndarray, np.ndarray]]:
    blocks = sorted(set(D["block"]))
    return [(np.flatnonzero(np.isin(D["block"], blocks[:k])), np.flatnonzero(D["block"] == blocks[k])) for k in range(FIRST, len(blocks))]


def run_folds(D: dict, specs: dict, workers: int, folds=None) -> list[dict]:
    from joblib import Parallel, delayed
    folds = folds or folds_of(D)
    res = Parallel(n_jobs=workers, backend="loky", verbose=0)(delayed(fold_job)(k, tr, te, D, specs) for k, (tr, te) in enumerate(folds))
    return sorted(res, key=lambda r: r["k"])


# ------------------------------------------------------------------ nested selection + comparison tables
def nested(res: list[dict], family: list[str]) -> tuple[list[str | None], np.ndarray, list[dict]]:
    """Per fold, the family member with the lowest step-weighted held-out loss over the earlier folds (None for fold 0)."""
    chosen, ll, lla = [], [], []
    for i, r in enumerate(res):
        if i == 0:
            chosen.append(None)
            ll.append(np.nan)
            lla.append({})
            continue
        prev = res[:i]
        w = np.array([p["n"] for p in prev], float)
        tot = {f: float(np.sum([p["ll"][f] for p in prev] * w) / w.sum()) for f in family}
        best = min(tot, key=tot.get)
        chosen.append(best)
        ll.append(r["ll"][best])
        lla.append(r["lla"][best])
    return chosen, np.array(ll), lla


def tables(res: list[dict], cols: dict[str, tuple]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """cols: name -> ('fixed', spec_name) or ('nested', (ll array, lla list)). Folds 1.. only."""
    F, FA = [], []
    for i, r in enumerate(res):
        if i == 0:
            continue
        row = {"fold": r["k"], "n": r["n"], "n_rem": r["n_rem"]}
        arows = {}
        for name, (kind, v) in cols.items():
            if kind == "fixed":
                row[f"ll_{name}"] = r["ll"][v]
                src = r["lla"][v]
            else:
                row[f"ll_{name}"] = v[0][i]
                src = v[1][i]
            for a, (m, n) in src.items():
                arows.setdefault(a, {"fold": r["k"], "animal": a, "n": n})[f"ll_{name}"] = m
        F.append(row)
        FA += list(arows.values())
    return pd.DataFrame(F), pd.DataFrame(FA)


def cmp(F: pd.DataFrame, FA: pd.DataFrame, lo: str, hi: str, label: str = "") -> dict:
    from sleep_schedule_phase2 import compare
    return compare(F, FA, lo, hi, label)


# ------------------------------------------------------------------ step B
def records_for(states: Path) -> list[dict]:
    from sleep_cycles_v2 import build_records
    return build_records(included_sessions(REVIEW, states), states)


def specs_pass1(variants: dict, mech: bool = True) -> dict[str, dict]:
    sp = {"M2t": {"L1": True, "hist": "M2t"}, "gate": {"L1": True, "hist": None}}
    for k in variants:
        sp[f"B:{k}"] = {"L1": True, "hist": k}
    if mech:
        sp["gate_mech"] = {"L1": False, "hist": None}
        for k in variants:
            if k.startswith(("P_", "R7_")):
                sp[f"Bm:{k}"] = {"L1": False, "hist": k}
    return sp


def families(variants: dict, pre: str) -> dict[str, list[str]]:
    P = [f"{pre}{k}" for k in variants if k.startswith("P_")]
    return {"B": P, "reset": [f"{pre}{k}" for k in variants if k.startswith("R7_")],
            "pause": [f"{pre}{k}" for k in variants if k.startswith("P_twinf")],
            "everywake": [f"{pre}{k}" for k in variants if k.startswith("P_tw0_")],
            "const": [f"{pre}{k}" for k in variants if k.startswith("Pc_")]}


def run_scoring(label: str, states: Path, workers: int, out: Path, full: bool) -> dict:
    t0 = time.time()
    variants = variant_specs()
    if not full:                                   # robustness scoring: the main grid only
        variants = {k: v for k, v in variants.items() if not k.startswith("Pc_")}
    recs = records_for(states)
    steps = build_data(recs, variants)
    D = to_arrays(steps)
    folds = folds_of(D)
    print(f"[{label}] steps {len(steps)}, REM ends {int((steps.y == 1).sum())}, WAKE ends {int((steps.y == 2).sum())}, "
          f"folds {len(folds)}, variants {len(variants)}; data {time.time() - t0:.0f} s", flush=True)
    specs = specs_pass1(variants, mech=full)
    res = run_folds(D, specs, workers, folds)
    print(f"[{label}] pass 1 done {time.time() - t0:.0f} s", flush=True)
    fam = families(variants, "B:")
    ch, ll, lla = {}, {}, {}
    for f, members in fam.items():
        if members:
            ch[f], ll[f], lla[f] = nested(res, members)
    cols = {"M2t": ("fixed", "M2t"), "gate": ("fixed", "gate"), **{f"{f}": ("nested", (ll[f], lla[f])) for f in ch}}
    if full:
        fm = families(variants, "Bm:")
        for f in ("B", "reset", "pause"):
            c_, l_, a_ = nested(res, fm[f])
            cols[f"mech_{f}"] = ("nested", (l_, a_))
            ch[f"mech_{f}"] = c_
        cols["gate_mech"] = ("fixed", "gate_mech")
    # pass 2: at the fold's chosen B-full point: no dark step, + wall-clock since REM (H19), + w60 (+ frag60) (H24)
    p2 = []
    if full:
        from joblib import Parallel, delayed
        jobs = []
        for i, (tr, te) in enumerate(folds):
            if i == 0:
                continue
            k = ch["B"][i][2:]
            jobs.append((i, tr, te, {"nodark": {"L1": True, "hist": k, "dark": False},
                                     "H19": {"L1": True, "hist": k, "extra": ("l_tsince_t",)},
                                     "H24base": {"L1": True, "hist": k, "extra": ("w60",)},
                                     "H24": {"L1": True, "hist": k, "extra": ("w60", "frag60")}}))
        p2 = Parallel(n_jobs=workers, backend="loky")(delayed(fold_job)(i, tr, te, D, sp) for i, tr, te, sp in jobs)
        p2 = {r["k"]: r for r in p2}
        for name in ("nodark", "H19", "H24base", "H24"):
            llv = np.array([np.nan] + [p2[i]["ll"][name] for i in range(1, len(folds))])
            lav = [{}] + [p2[i]["lla"][name] for i in range(1, len(folds))]
            cols[name] = ("nested", (llv, lav))
        print(f"[{label}] pass 2 done {time.time() - t0:.0f} s", flush=True)
    F, FA = tables(res, cols)
    F.to_csv(out / f"folds_{label}.csv", index=False)
    FA.to_csv(out / f"folds_by_animal_{label}.csv", index=False)
    rows = [cmp(F, FA, "M2t", "B", "B-full vs M2t (pass: delta <= +0.1 %)"),
            cmp(F, FA, "reset", "B", "B-full vs hard reset at wakes >= 7 min"),
            cmp(F, FA, "pause", "B", "B-full vs pause (tau_w = inf)"),
            cmp(F, FA, "everywake", "B", "B-full vs reset at every wake (tau_w = 0)"),
            cmp(F, FA, "gate", "B", "B-full vs gate-only (pass: <= -0.5 %)"),
            cmp(F, FA, "gate", "M2t", "M2t vs gate-only (reference)")]
    if full:
        rows += [cmp(F, FA, "nodark", "B", "dark step needed once P is in (B-full vs no dark)"),
                 cmp(F, FA, "const", "B", "H6: REM discharge grows with REM length (kappa) vs constant fraction"),
                 cmp(F, FA, "B", "H19", "H19: + wall-clock time since REM on top of B-full"),
                 cmp(F, FA, "H24base", "H24", "H24: + frag60 on top of B-full + w60"),
                 cmp(F, FA, "mech_reset", "mech_B", "B-mech vs reset (no L1)"),
                 cmp(F, FA, "mech_pause", "mech_B", "B-mech vs pause (no L1)"),
                 cmp(F, FA, "gate_mech", "mech_B", "B-mech vs gate-only (no L1)"),
                 cmp(F, FA, "M2t", "mech_B", "B-mech (one counter, no L1) vs M2t")]
    C = pd.DataFrame(rows)
    C.insert(0, "scores", label)
    # profile over the grid (non-nested, folds 1..): step-weighted mean held-out log-loss, % vs M2t
    w = np.array([r["n"] for r in res[1:]], float)
    m2t = float(np.sum([r["ll"]["M2t"] for r in res[1:]] * w) / w.sum())
    prof = []
    for k, sp in variants.items():
        if not k.startswith(("P_", "R7_")):
            continue
        for pre, fam_ in (("B:", "B-full"), ("Bm:", "B-mech")):
            if f"{pre}{k}" not in res[1]["ll"]:
                continue
            v = float(np.sum([r["ll"][f"{pre}{k}"] for r in res[1:]] * w) / w.sum())
            prof.append({"scores": label, "model": fam_, "variant": k, "mode": sp["mode"], "tau_w_s": sp.get("tau", np.nan),
                         "kappa_s": sp.get("kappa", np.nan), "ll": v, "delta_vs_M2t_pct": 100 * (v - m2t) / m2t})
    PR = pd.DataFrame(prof)
    chosen = pd.DataFrame({"fold": [r["k"] for r in res], **{f"chosen_{f}": v for f, v in ch.items()}})
    return {"label": label, "C": C, "PR": PR, "chosen": chosen, "D": D, "folds": folds, "steps": len(steps),
            "rem": int((steps.y == 1).sum()), "wake": int((steps.y == 2).sum()), "n_folds_used": len(folds) - 1}


def loao_profile(D: dict, folds, kappa: float, workers: int) -> pd.DataFrame:
    """Refit without each animal: the tau_w profile (B-full, fixed kappa); argmin per left-out animal."""
    from joblib import Parallel, delayed
    animals = sorted(set(D["animal"]))
    specs = {pkey(t, kappa): {"L1": True, "hist": pkey(t, kappa)} for t in TAUS}
    jobs = []
    for a in animals:
        for i, (tr, te) in enumerate(folds):
            if i == 0:
                continue
            jobs.append((a, i, tr[D["animal"][tr] != a], te[D["animal"][te] != a]))
    res = Parallel(n_jobs=workers, backend="loky")(delayed(fold_job)(i, tr, te, D, specs) for a, i, tr, te in jobs)
    rows = []
    for (a, i, _, _), r in zip(jobs, res):
        for k, v in r["ll"].items():
            rows.append({"left_out": a, "fold": i, "n": r["n"], "variant": k, "ll": v})
    T = pd.DataFrame(rows)
    T["tau_w_s"] = T.variant.map({pkey(t, kappa): t for t in TAUS})
    P = T.groupby(["left_out", "tau_w_s"]).apply(lambda g: np.sum(g.ll * g.n) / g.n.sum(), include_groups=False).rename("ll").reset_index()
    return P


def partial_curve(D: dict, key: str) -> pd.DataFrame:
    """Full-data fit of B-full at `key`; predicted per-10-s REM and WAKE probability against P at fixed covariates
    (elapsed 60 s, has_anchor 1, L1 terms and day at their means, first animal), light (13:00) vs dark (01:00)."""
    from sklearn.linear_model import LogisticRegression
    idx = np.arange(len(D["y"]))
    levels = sorted(set(D["animal"]))
    spec = {"L1": True, "hist": key}
    X, st = design(D, idx, spec, None, levels)
    m = LogisticRegression(C=1e4, max_iter=3000).fit(X, D["y"])
    Pm = np.r_[0, np.geomspace(0.1, 120, 60)]
    rows = []
    for lab, hour, dark in (("light 13:00", 13.0, 0.0), ("dark 01:00", 1.0, 1.0)):
        G = {"y": np.zeros(len(Pm), np.int8), "animal": np.array([levels[0]] * len(Pm))}
        for k in (1, 2):
            G[f"sin{k}"], G[f"cos{k}"] = np.full(len(Pm), np.sin(2 * np.pi * k * hour / 24)), np.full(len(Pm), np.cos(2 * np.pi * k * hour / 24))
        G["l_elapsed"] = np.full(len(Pm), np.log(65.0))
        for c in ("T_day", "l_dprev", "prev_rem", "prev_unk", "fW10"):
            G[c] = np.full(len(Pm), st["mu"][c])
        G["has_anchor"], G["dark"] = np.ones(len(Pm)), np.full(len(Pm), dark)
        G[f"lP_{key}"] = np.log1p(Pm)
        Xg, _ = design(G, np.arange(len(Pm)), spec, st, levels)
        p = np.zeros((len(Pm), 3))
        p[:, m.classes_] = m.predict_proba(Xg)
        rows += [{"phase": lab, "P_min": pm, "p_rem_10s": pr, "p_wake_10s": pw} for pm, pr, pw in zip(Pm, p[:, 1], p[:, 2])]
    return pd.DataFrame(rows)


def stepB(a) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from _common import git_commit, write_json
    from output_paths import figure_dir, report_dir, run_dir
    from sleep_quant import md_table, save_fig
    out = run_dir("sleep_explore_B" + ("_smoke" if a.smoke else ""), "2026c")
    rd, fd = (out, out) if a.smoke else (report_dir("2026c", "ephys_spikes"), figure_dir("2026c", "ephys_spikes"))
    gc = git_commit()
    t0 = time.time()
    runs = {}
    for lab in a.scorings:
        states = STATES if lab == "final" else PASS2MED
        runs[lab] = run_scoring(lab, states, a.workers, out, full=(lab == "final"))
    R0 = runs[a.scorings[0]]
    C = pd.concat([r["C"] for r in runs.values()], ignore_index=True)
    PR = pd.concat([r["PR"] for r in runs.values()], ignore_index=True)
    CH = R0["chosen"]
    C.to_csv(rd / "ephys_spikes_sleep_explore_B_comparisons_2026c.csv", index=False)
    PR.to_csv(rd / "ephys_spikes_sleep_explore_B_profile_2026c.csv", index=False)
    CH.to_csv(rd / "ephys_spikes_sleep_explore_B_chosen_2026c.csv", index=False)
    # the most frequently chosen kappa, then the LOAO tau_w profile at it
    ck = pd.Series([c for c in CH.chosen_B if isinstance(c, str)]).str.extract(r"_k(\w+)$")[0]
    kappa = float(ck.mode().iloc[0]) if len(ck) else 60.0
    print(f"LOAO profile at kappa {kappa}", flush=True)
    LO = loao_profile(R0["D"], R0["folds"], kappa, a.workers)
    LO.to_csv(rd / "ephys_spikes_sleep_explore_B_loao_2026c.csv", index=False)
    am = LO.loc[LO.groupby("left_out").ll.idxmin()][["left_out", "tau_w_s"]].rename(columns={"tau_w_s": "argmin_tau_w_s"})
    # overall best (non-nested) B-full point for the descriptive curve
    pf = PR[(PR.scores == R0["label"]) & (PR.model == "B-full") & (PR["mode"] == "disc")]
    best = pf.loc[pf.ll.idxmin()]
    PC = partial_curve(R0["D"], best.variant)
    PC.to_csv(rd / "ephys_spikes_sleep_explore_B_partial_2026c.csv", index=False)
    # ---- figures
    fig, axs = plt.subplots(1, 2, figsize=(13, 4.6))
    xt = {t: i for i, t in enumerate(TAUS)}
    for ax, model in zip(axs, ("B-full", "B-mech")):
        q = PR[(PR.scores == R0["label"]) & (PR.model == model)]
        for k_ in KAPPAS:
            g = q[(q["mode"] == "disc") & (q.kappa_s == k_)].sort_values("tau_w_s")
            ax.plot([xt[t] for t in g.tau_w_s], g.delta_vs_M2t_pct, "o-", label=f"kappa {tlab(k_)} s")
        r7 = q[q["mode"] == "reset"]
        if len(r7):
            ax.axhline(r7.delta_vs_M2t_pct.min(), color="k", ls="--", lw=0.8, label="hard reset >= 7 min (best kappa)")
        ax.axhline(0, color="grey", lw=0.6)
        ax.set_xticks(range(len(TAUS)), ["0", "15 s", "30 s", "1 m", "2 m", "5 m", "10 m", "30 m", "inf"])
        ax.set_xlabel("wake discount time constant tau_w")
        ax.set_ylabel("held-out log-loss vs M2t (%), lower = better")
        ax.set_title(f"{model}: profile over tau_w (folds 1.., non-nested)", fontsize=9)
        ax.legend(fontsize=7)
    fig.suptitle(f"Step B: one REM-entry counter discounted by wakes  {gc}", fontsize=9)
    save_fig(fig, fd / "ephys_spikes_sleep_explore_B_profile_2026c.png")
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.2))
    for ph, g in PC.groupby("phase"):
        axs[0].plot(g.P_min, g.p_rem_10s, label=ph)
        axs[1].plot(g.P_min, g.p_wake_10s, label=ph)
    for ax, t in zip(axs, ("P(REM in the next 10 s)", "P(WAKE in the next 10 s)")):
        ax.set_xscale("symlog", linthresh=1)
        ax.set_xlabel("counter P (min of NREM, discounted)")
        ax.set_ylabel(t)
        ax.legend(fontsize=8)
    fig.suptitle(f"Step B: fitted read-out at {best.variant} (full-data fit; other covariates fixed)  {gc}", fontsize=9)
    save_fig(fig, fd / "ephys_spikes_sleep_explore_B_readout_2026c.png")
    # ---- verdicts
    Cf = C[C.scores == R0["label"]].set_index("subset")

    def g(sub, col):
        return float(Cf.loc[sub, col]) if sub in Cf.index and col in Cf.columns else np.nan
    v = []
    d_m2t = g("B-full vs M2t (pass: delta <= +0.1 %)", "delta_pct")
    v.append(("B-full not worse than M2t by > 0.1 %", d_m2t <= 0.1, f"delta {d_m2t:+.3f} %"))
    for sub, lab in (("B-full vs hard reset at wakes >= 7 min", "beats hard reset"), ("B-full vs pause (tau_w = inf)", "beats pause")):
        v.append((f"B-full {lab} (holds)", bool(Cf.loc[sub, "holds"]) if sub in Cf.index else False,
                  f"delta {g(sub, 'delta_pct'):+.3f} % [{g(sub, 'ci_lo_pct'):+.3f}, {g(sub, 'ci_hi_pct'):+.3f}], animals {g(sub, 'animals_better'):.0f}/6"))
    d_gate = g("B-full vs gate-only (pass: <= -0.5 %)", "delta_pct")
    v.append(("B-full beats gate-only by >= 0.5 %", d_gate <= -0.5, f"delta {d_gate:+.3f} %"))
    tau_ch = pd.Series([float(c.split("_tw")[1].split("_")[0]) if isinstance(c, str) else np.nan for c in CH.chosen_B]).dropna()
    tmode = float(tau_ch.mode().iloc[0]) if len(tau_ch) else np.nan
    interior = 30 <= tmode <= 600
    loao_ok = bool(am.argmin_tau_w_s.between(30, 600).all())
    v.append(("tau_w profile minimum interior (30 s - 10 min) and LOAO-stable", interior and loao_ok,
              f"chosen tau_w (mode over folds) {tlab(tmode)} s; LOAO argmins {', '.join(f'{r.left_out} {tlab(r.argmin_tau_w_s)}' for r in am.itertuples())}"))
    V = pd.DataFrame(v, columns=["criterion", "pass", "numbers"])
    V.to_csv(rd / "ephys_spikes_sleep_explore_B_verdicts_2026c.csv", index=False)
    L = ["# Sleep-behaviour explore — Step B: the minimal scheduler model (one REM-entry counter + a day/night gate), cohort 2026c", "",
         "Plan [implementation_plan/2026-10-08-sleep-behaviour-explore.md](../../../../implementation_plan/2026-10-08-sleep-behaviour-explore.md) "
         f"§4-§5 (pass rules written before results). Driver `ephys/sleep_model.py stepB` (commit {gc}); bulk `{out}`. "
         f"Runtime {(time.time() - t0) / 60:.0f} min. **Technical ledger.**", "",
         "## Definitions", "", "```", (__doc__ or "").strip(), "```", "",
         "## Data", ""]
    for r in runs.values():
        L.append(f"- {r['label']}: {r['steps']} NREM steps, {r['rem']} REM ends, {r['wake']} WAKE ends; {r['n_folds_used']} test folds "
                 "(fold 0 is used only to start the nested choice).")
    L += ["", "## Verdicts against the plan's pass rules (FINAL scores)", "", *md_table(V), "",
          "## Held-out comparisons", "", *md_table(C.round(4)), "",
          "![](../figures/ephys_spikes_sleep_explore_B_profile_2026c.png)", "",
          "## Chosen grid point per fold (nested forward chaining)", "", *md_table(CH), "",
          f"## Leave-one-animal-out tau_w profile (refit without the animal; B-full, kappa {tlab(kappa)} s)", "",
          *md_table(LO.pivot(index="tau_w_s", columns="left_out", values="ll").round(5).reset_index()), "",
          *md_table(am), "",
          f"## Read-out of the counter (full-data fit at {best.variant}; description)", "",
          "![](../figures/ephys_spikes_sleep_explore_B_readout_2026c.png)", "",
          "## Profile table (non-nested, folds 1..)", "", *md_table(PR.round(4)), ""]
    (rd / "ephys_spikes_sleep_explore_B_2026c.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    write_json(rd / "run_manifest_sleep_explore_B_2026c.json", {"run_dir": str(out), "git_commit": gc, "scorings": a.scorings})
    print(V.to_string(index=False), flush=True)
    print("written", rd / "ephys_spikes_sleep_explore_B_2026c.md", flush=True)


# ------------------------------------------------------------------ selftest
def simulate(n_animals: int, n_days: int, tau: float, kappa: float, seed: int = 0) -> list[dict]:
    """Synthetic records (one per day-half) generated by the counter model itself: REM entry logit -6 + 1.8 ln(1+P)
    - 1.2 dark per 10-s NREM step, constant WAKE hazard; wakes short / medium / long (long ones more at night)."""
    from sleep_quant import sun_times
    rng = np.random.default_rng(seed)
    recs, rid = [], 0
    for an in range(n_animals):
        for d in range(n_days):
            for half in ("D", "N"):
                start = pd.Timestamp("2026-09-01") + pd.Timedelta(days=d, hours=6 if half == "D" else 18)
                L = 43200
                st = np.zeros(L, np.int8)
                t, s, P = 0, N, 0.0
                while t < L:
                    now = start + pd.Timedelta(seconds=t)
                    sr, ss = sun_times(now.date())
                    dark = float(not (sr <= now.to_pydatetime() < ss))
                    if s == N:
                        pr = 1 / (1 + np.exp(-(-6.0 + 1.8 * np.log1p(P) - 1.2 * dark)))
                        pw = 1 / (1 + np.exp(-(-4.2)))
                        st[t:t + 10] = N
                        P += 10 / 60
                        t += 10
                        u = rng.random()
                        s = R if u < pr else (W if u < pr + pw else N)
                    elif s == R:
                        r = int(rng.integers(40, 120))
                        st[t:t + r] = R
                        P = 0.0 if kappa == 0 else P * np.exp(-r / kappa)
                        t += r
                        s = N if rng.random() < 0.8 else W
                    else:
                        u = rng.random()
                        long_p = 0.25 if dark else 0.08
                        dd = int(rng.integers(5, 40)) if u < 0.6 else (int(rng.integers(60, 420)) if u < 1 - long_p else int(rng.integers(600, 3600)))
                        st[t:t + dd] = W
                        P = 0.0 if tau == 0 else (P * np.exp(-dd / tau) if np.isfinite(tau) else P)
                        t += dd
                        s = N
                recs.append({"animal": f"S{an}", "start": start, "end": start + pd.Timedelta(seconds=L), "state": st[:L],
                             "record_id": rid, "block": f"{start:%Y-%m-%d}{half}", "sessions": []})
                rid += 1
    return recs


def selftest() -> None:
    # 1. the counter by hand
    st = np.array([N] * 120 + [W] * 60 + [N] * 60 + [R] * 30 + [N] * 30 + [W] * 500 + [N] * 10, np.int8)
    c = counter_starts(st, "disc", tau=60.0, kappa=30.0)
    exp1 = 2.0 * np.exp(-1.0)
    exp2 = (exp1 + 1.0) * np.exp(-1.0)
    exp3 = (exp2 + 0.5) * np.exp(-500 / 60)
    assert abs(c[0]) < 1e-12 and abs(c[180] - exp1) < 1e-9 and abs(c[270] - exp2) < 1e-9 and abs(c[800] - exp3) < 1e-9, c
    r = counter_starts(st, "reset", kappa=30.0)
    assert abs(r[180] - 2.0) < 1e-9 and abs(r[800]) < 1e-12, r                      # 60-s wake pauses; 500-s wake resets
    p = counter_starts(st, "disc", tau=np.inf, kappa=0.0)
    assert abs(p[270]) < 1e-12 and abs(p[800] - 0.5) < 1e-9, p                      # full discharge at REM; pause over the wake
    q = counter_starts(st, "const", tau=np.inf, phi=0.5)
    assert abs(q[270] - 1.5) < 1e-9, q
    # 2. recovery of tau_w from data generated with tau_w = 120 s, kappa = 30 s
    global TAUS, KAPPAS
    keep = (TAUS, KAPPAS)
    TAUS, KAPPAS = [0.0, 30.0, 120.0, 600.0, np.inf], [30.0]
    try:
        recs = simulate(3, 6, tau=120.0, kappa=30.0, seed=3)
        variants = {pkey(t, 30.0): {"mode": "disc", "tau": t, "kappa": 30.0} for t in TAUS}
        steps = build_data(recs, variants)
        D = to_arrays(steps)
        specs = {f"B:{k}": {"L1": False, "hist": k} for k in variants}
        res = run_folds(D, specs, workers=4)
        w = np.array([r["n"] for r in res], float)
        tot = {k: float(np.sum([r["ll"][k] for r in res] * w) / w.sum()) for k in specs}
        best = min(tot, key=tot.get)
        print("selftest tau profile (mean held-out log-loss):", {k: round(v, 5) for k, v in tot.items()}, "best", best, flush=True)
        assert best in ("B:" + pkey(30.0, 30.0), "B:" + pkey(120.0, 30.0), "B:" + pkey(600.0, 30.0)), best
        assert tot["B:" + pkey(0.0, 30.0)] > tot[best] and tot["B:" + pkey(np.inf, 30.0)] > tot[best]
    finally:
        TAUS, KAPPAS = keep
    print("selftest PASS: counter arithmetic (discount / reset / pause / constant discharge); tau_w recovered from synthetic data", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["stepB"])
    ap.add_argument("--scorings", nargs="+", default=["final", "pass2med"], choices=["final", "pass2med"])
    ap.add_argument("--workers", type=int, default=15)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    elif a.cmd == "stepB":
        stepB(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
