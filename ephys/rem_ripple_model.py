r"""Do NREM ripples carry REM-entry information beyond the NREM counter? (cohort 2026c)
Plan, pre-registered before any fit: implementation_plan/2026-10-09-rem-ripple-model.md (Amendment 1 = the model owner's
reply). The REM-entry model is reused unchanged from ephys/sleep_model.py (Step B's B-full, counter P_tw600_k0).

Usage:  python ephys/rem_ripple_model.py run [--scorings final pass2med] [--workers 6] [--smoke]
        python ephys/rem_ripple_model.py report --run <run dir>      (re-render the report from the saved tables)
        python ephys/rem_ripple_model.py --selftest

Definitions (1-s states 0 unknown, 1 WAKE, 3 NREM, 5 REM; records and 10-s NREM steps exactly as sleep_model.py; a step
starts at t_off = bout_start + elapsed s into its record, its outcome y is the transition at the step's end):
  covered second   its session has SWR tier validated / good, it is before use_until and outside the probe-advance
                   settle windows (09-11 19:40 is already cut by records_for).
  events           ALL (primary) = every detected event whose peak second is NREM in the scoring being modelled and
                   covered, all flags ignored; KEPT (sensitivity) = the same with excluded == False.
  window rate      for lag L (0 / 60 / 120 s): seconds [t_off - L - 600, t_off - L) of the record;
                   rr_L = ln((k + 0.5) / (m / 60 * rbar_b(t - L))), k = events, m = NREM seconds in the window,
                   rbar_b(tau) = events / NREM minutes over the covered NREM seconds of the animal x probe block before tau
                   (causal, primary; >= 30 min needed) or over the whole block (sensitivity 'w').
  ripple counter   C = E / rbar_b(t), E kept with P_tw600_k0's bookkeeping: NREM adds its events (up to the step start),
                   a wake of d s multiplies by exp(-d / 600), REM empties it, unknown freezes it. lC = ln(1 + C);
                   rho = ln((C + 0.5) / (P + 0.5)) = the discounted relative ripple rate since the last REM.
  depth            depth_L = mean over the window's NREM seconds of the raw spectral slope (imu_fixch SleepScoreRaw 'sw')
                   z-scored within animal x block.
  subsets          S1: step second covered, every NREM second of [t_off - 720, t_off) covered, m >= 180 s in all three
                   windows, every rr finite; S2 = S1 and every NREM second since the last REM (or the record start)
                   covered.
  rule             Delta = held-out log-loss change in % of the smaller model (sleep_model.cmp, 15 folds); holds = CI
                   upper < 0 and >= n - 1 of the n animals with test steps better; required on BOTH scorings.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _common import figure_dir, git_commit, report_dir, write_json  # noqa: E402

COHORT = "2026c"
W, N, R = 1, 3, 5
WIN_S = 600
LAGS = (0, 60, 120)
MIN_M_S = 180
MIN_NORM_S = 1800
K0 = 0.5
TAU_W = 600.0
REF = "P_tw600_k0"
B = {"L1": True, "hist": REF}
HELDOUT = Path("D:/Field2026_analysis_out/2026c/sleep_heldout_steps")
SWR_ROOT = "Q:/hc997/SocialFieldRat2026/3rd_rat/analysis/swr"
SLEEP_ROOT = "Q:/hc997/SocialFieldRat2026/3rd_rat/analysis/sleep/imu_fixch"


# ------------------------------------------------------------------ pure pieces (selftested)
def bouts(state: np.ndarray) -> list[tuple[int, int, int]]:
    from sleep_cycles import bouts as _b
    return _b(state)


def ripple_counter(state: np.ndarray, ev: np.ndarray, tau: float = TAU_W) -> dict[int, tuple[float, int]]:
    """Discounted event sum E and the reset index (end of the last REM, else 0) at the start of every NREM bout: the
    bookkeeping of sleep_model.counter_starts(mode='disc', tau, kappa=0) with events in place of minutes."""
    ce = np.r_[0, np.cumsum(ev)]
    E, reset, out = 0.0, 0, {}
    for s, a, b in bouts(state):
        if s == N:
            out[a] = (E, reset)
            E += float(ce[b] - ce[a])
        elif s == W:
            E = 0.0 if tau == 0 else E * np.exp(-(b - a) / tau)
        elif s == R:
            E, reset = 0.0, b
    return out


def window(t_off: np.ndarray, lag: int) -> tuple[np.ndarray, np.ndarray]:
    x1 = np.maximum(t_off - lag, 0)
    return np.maximum(x1 - WIN_S, 0), x1


def block_rate(T: np.ndarray, cE: np.ndarray, tau: np.ndarray, causal: bool = True) -> np.ndarray:
    """Events per NREM minute of one block over its covered NREM seconds before tau (causal) or all of them."""
    j = np.searchsorted(T, tau, side="left") if causal else np.full(len(tau), len(T))
    e = cE[j]
    with np.errstate(divide="ignore", invalid="ignore"):
        r = e / (j / 60.0)
    return np.where((j >= MIN_NORM_S) & (e > 0), r, np.nan)


# ------------------------------------------------------------------ inputs
def load_cache(Q: dict, swr_root: Path, sleep_root: Path, cache_file: Path) -> dict:
    """Per session: event peak seconds + excluded flag, and the imu_fixch raw slope. Read once from storage, then local."""
    if cache_file.exists():
        return pd.read_pickle(cache_file)
    out = {}
    for (an, s) in Q:
        f = swr_root / an / s / f"{s}.swr_events.npz"
        if not f.exists():
            out[(an, s)] = None
            continue
        with np.load(f, allow_pickle=True) as z:
            d = {"peak_s": z["peak_s"].astype(float), "excluded": z["excluded"].astype(bool)}
        rf = sleep_root / an / s / f"{s}.SleepScoreRaw.npz"
        if rf.exists():
            with np.load(rf) as r_:
                d["t_clus"], d["sw"] = r_["t_clus"].astype(np.int64), r_["sw"].astype(np.float32)
        out[(an, s)] = d
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    pd.to_pickle(out, cache_file)
    return out


def record_arrays(rc: dict, starts: dict, Q: dict, settle: list, cache: dict, codes: dict) -> dict:
    st = rc["state"]
    n = len(st)
    cov, blk = np.zeros(n, bool), np.full(n, -1, np.int32)
    ea, ek, sw = np.zeros(n, np.int32), np.zeros(n, np.int32), np.full(n, np.nan, np.float32)
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
        sec = o + np.floor(z["peak_s"]).astype(np.int64)
        ok = (sec >= max(o, 0)) & (sec < min(e, n))
        sec, exc = sec[ok], z["excluded"][ok]
        good = cov[sec] & (st[sec] == N)
        np.add.at(ea, sec[good], 1)
        np.add.at(ek, sec[good & ~exc], 1)
        if "sw" in z:
            ts = o + z["t_clus"]
            okd = (ts >= max(o, 0)) & (ts < min(e, n))
            sw[ts[okd]] = z["sw"][okd]
    sw[~(cov & (st == N))] = np.nan
    return {"cov": cov, "blk": blk, "ea": ea, "ek": ek, "sw": sw}


def block_tables(recs: list[dict], arrs: dict) -> dict:
    acc = {}
    for rc in sorted(recs, key=lambda r: r["start"]):
        A = arrs[rc["record_id"]]
        idx = np.flatnonzero(A["cov"] & (rc["state"] == N))
        t0 = rc["start"].value / 1e9
        for b in np.unique(A["blk"][idx]):
            j = idx[A["blk"][idx] == b]
            acc.setdefault(int(b), []).append((t0 + j, A["ea"][j], A["ek"][j], A["sw"][j]))
    out = {}
    for b, parts in acc.items():
        T = np.concatenate([p[0] for p in parts])
        o = np.argsort(T, kind="stable")
        ea, ek, sw = (np.concatenate([p[i] for p in parts])[o] for i in (1, 2, 3))
        f = np.isfinite(sw)
        out[b] = {"T": T[o], "ca": np.r_[0, np.cumsum(ea)], "ck": np.r_[0, np.cumsum(ek)],
                  "sw_mu": float(sw[f].mean()) if f.any() else np.nan, "sw_sd": float(sw[f].std()) if f.sum() > 1 else np.nan}
    return out


def rates_for(blocks: np.ndarray, tau: np.ndarray, BT: dict, ver: str, causal: bool) -> np.ndarray:
    out = np.full(len(tau), np.nan)
    for b in np.unique(blocks):
        if b < 0 or b not in BT:
            continue
        m = blocks == b
        out[m] = block_rate(BT[b]["T"], BT[b]["c" + ver], tau[m], causal)
    return out


def record_features(g: pd.DataFrame, rc: dict, A: dict, BT: dict) -> pd.DataFrame:
    st = rc["state"]
    isN = st == N
    t_off = (g.bout_start.to_numpy() + g.elapsed.to_numpy()).astype(np.int64)
    bs = g.bout_start.to_numpy().astype(np.int64)
    cN, cU = np.r_[0, np.cumsum(isN)], np.r_[0, np.cumsum(isN & ~A["cov"])]
    cE = {"a": np.r_[0, np.cumsum(A["ea"])], "k": np.r_[0, np.cumsum(A["ek"])]}
    blk = A["blk"][t_off]
    dz = depth_z(A, BT)
    fin = np.isfinite(dz)
    cS, cSn = np.r_[0, np.cumsum(np.where(fin, dz, 0.0))], np.r_[0, np.cumsum(fin)]
    t0 = rc["start"].value / 1e9
    F = {"win_cov": A["cov"][t_off] & (cU[t_off] - cU[np.maximum(t_off - WIN_S - max(LAGS), 0)] == 0) & (blk >= 0)}
    with np.errstate(divide="ignore", invalid="ignore"):
        for L in LAGS:
            x0, x1 = window(t_off, L)
            m = cN[x1] - cN[x0]
            F[f"m{L}"] = m
            for ver in ("a", "k"):
                k = cE[ver][x1] - cE[ver][x0]
                F[f"k{ver}{L}"] = k
                F[f"rr{ver}{L}"] = np.log((k + K0) / (m / 60.0 * rates_for(blk, t0 + x1, BT, ver, True)))
                if ver == "a":
                    F[f"rrw{L}"] = np.log((k + K0) / (m / 60.0 * rates_for(blk, t0 + x1, BT, "a", False)))
            dn = cSn[x1] - cSn[x0]
            F[f"dep{L}"] = np.where(dn >= 60, (cS[x1] - cS[x0]) / np.maximum(dn, 1), np.nan)
        for ver in ("a", "k"):
            ev = A["e" + ver]
            cs = ripple_counter(st, ev)
            E = np.array([cs[b][0] for b in bs]) + (cE[ver][t_off] - cE[ver][bs])
            if ver == "a":
                reset = np.array([cs[b][1] for b in bs])
                F["cnt_cov"] = cU[t_off] - cU[reset] == 0
            F[f"C{ver}"] = E / rates_for(blk, t0 + t_off, BT, ver, True)
    return pd.DataFrame(F, index=g.index)


def build_features(steps: pd.DataFrame, recs: list[dict], arrs: dict, BT: dict) -> pd.DataFrame:
    byrid = {rc["record_id"]: rc for rc in recs}
    parts = [record_features(g, byrid[rid], arrs[rid], BT) for rid, g in steps.groupby("record_id")]
    F = pd.concat(parts).reindex(steps.index)
    P = np.expm1(steps[f"lP_{REF}"].to_numpy().astype(float))
    for v in ("a", "k"):
        F[f"lC{v}"] = np.log1p(F[f"C{v}"])
    F["rho"] = np.log((F.Ca + 0.5) / (P + 0.5))
    rr_cols = [f"rr{v}{L}" for v in ("a", "k") for L in LAGS] + [f"rrw{L}" for L in LAGS]
    ok_rr = np.isfinite(F[rr_cols].to_numpy()).all(1)
    ok_m = np.all([F[f"m{L}"].to_numpy() >= MIN_M_S for L in LAGS], axis=0)
    F["S1"] = F.win_cov.to_numpy() & ok_m & ok_rr
    F["S2"] = F.S1 & F.cnt_cov & np.isfinite(F.Ca) & np.isfinite(F.Ck)
    return F


# ------------------------------------------------------------------ Amendment 2 check features (K2-K5)
SHIFTS = (0.3, 0.5, 0.7)
KLAGS = (0, 60, 120)


def circular_shift(ev: np.ndarray, mask: np.ndarray, frac: float) -> np.ndarray:
    """Event counts of the masked seconds rolled by frac of their number (the K3 control); zero elsewhere."""
    idx = np.flatnonzero(mask)
    out = np.zeros_like(ev)
    if len(idx):
        out[idx] = np.roll(ev[idx], int(round(frac * len(idx))))
    return out


def counter_at_steps(st: np.ndarray, ev: np.ndarray, bs: np.ndarray, upto: np.ndarray) -> np.ndarray:
    """P_tw600_k0 bookkeeping of ev, read at each step: the bout-start value + ev of the current bout before `upto`."""
    cs = ripple_counter(st, ev)
    ce = np.r_[0, np.cumsum(ev)]
    return np.array([cs[b][0] for b in bs]) + (ce[upto] - ce[bs])


def check_features(g: pd.DataFrame, rc: dict, A: dict, BT: dict, P: np.ndarray) -> pd.DataFrame:
    st = rc["state"]
    bs = g.bout_start.to_numpy().astype(np.int64)
    el = g.elapsed.to_numpy().astype(np.int64)
    t_off = bs + el
    blk = A["blk"][t_off]
    t0 = rc["start"].value / 1e9
    P0 = P - el / 60.0                                                     # P at the bout start
    covN = A["cov"] & (st == N)
    F = {}
    with np.errstate(divide="ignore", invalid="ignore"):
        for L in KLAGS:                                                    # K2: lagged counter and lagged P
            upto = np.maximum(bs, t_off - L)
            C = counter_at_steps(st, A["ea"], bs, upto) / rates_for(blk, t0 + t_off - L, BT, "a", True)
            PL = P0 + np.maximum(0, el - L) / 60.0
            F[f"rho{L}"] = np.log((C + 0.5) / (PL + 0.5))
        rate = rates_for(blk, t0 + t_off, BT, "a", True)
        for i, fr in enumerate(SHIFTS):                                    # K3: shifted events, true normaliser
            C = counter_at_steps(st, circular_shift(A["ea"], covN, fr), bs, t_off) / rate
            F[f"rhos{i + 1}"] = np.log((C + 0.5) / (P + 0.5))
        C = counter_at_steps(st, A["ea"], bs, t_off) / rates_for(blk, t0 + t_off, BT, "a", False)
        F["rhow"] = np.log((C + 0.5) / (P + 0.5))                          # K5: whole-block normaliser
        ce = np.r_[0, np.cumsum(A["ea"])]
        F["kbout"] = ce[t_off] - ce[bs]                                    # K8: the current bout's events before the step
        dz = depth_z(A, BT)                                                # K4: discounted mean depth since REM
        fin = np.isfinite(dz) & (st == N)
        Sd = counter_at_steps(st, np.where(fin, dz, 0.0), bs, t_off)
        Sn = counter_at_steps(st, fin.astype(float), bs, t_off)
        F["dbar"] = np.where(Sn >= 60, Sd / np.maximum(Sn, 1e-9), np.nan)
    return pd.DataFrame(F, index=g.index)


def depth_z(A: dict, BT: dict) -> np.ndarray:
    dz = A["sw"].astype(float).copy()
    for b in np.unique(A["blk"][A["blk"] >= 0]):
        m = A["blk"] == b
        dz[m] = (dz[m] - BT[b]["sw_mu"]) / BT[b]["sw_sd"] if b in BT else np.nan
    return dz


# ------------------------------------------------------------------ fitting
def holds(r: dict) -> bool:
    return bool(r.get("ci_hi_pct", 1) < 0 and r.get("animals", 0) > 0 and r.get("animals_better", 0) >= r["animals"] - 1)


def run_family(D: dict, specs: dict, pairs: list[tuple[str, str, str]], workers: int, folds=None) -> tuple[list[dict], pd.DataFrame, pd.DataFrame]:
    from sleep_model import cmp, run_folds, tables
    res = run_folds(D, specs, workers, folds)
    F, FA = tables(res, {k: ("fixed", k) for k in specs})
    rows = []
    for test, lo, hi in pairs:
        r = cmp(F, FA, lo, hi)
        r["test"], r["holds_rule"] = test, holds(r)
        rows.append(r)
    return rows, F, FA


def subset_arrays(steps: pd.DataFrame, F: pd.DataFrame, mask: np.ndarray) -> dict:
    from sleep_model import to_arrays
    s = steps[mask].reset_index(drop=True)
    f = F[mask].reset_index(drop=True)
    D = to_arrays(s)
    for c in f.columns:
        if f[c].dtype.kind in "fi":
            D[c] = f[c].to_numpy().astype(float)
    D["lP_ripcount"], D["lP_ripcountk"] = f.lCa.to_numpy().astype(float), f.lCk.to_numpy().astype(float)
    return D


def t3_coefs(D: dict, col: str) -> pd.DataFrame:
    """Full-subset fit: B + the ripple term, pooled and interacted with animal; log-odds vs stay per +1 SD."""
    from sklearn.linear_model import LogisticRegression
    from sleep_model import design
    idx = np.arange(len(D["y"]))
    levels = sorted(set(D["animal"]))
    X, _ = design(D, idx, B, None, levels)
    x = D[col]
    z = (x - x.mean()) / x.std()
    rows = []
    for kind in ("pooled", "per_animal"):
        if kind == "pooled":
            Xe, names = np.column_stack([X, z]), ["all"]
        else:
            names = levels
            Xe = np.column_stack([X] + [z * (D["animal"] == a) for a in levels])
        m = LogisticRegression(C=1e4, max_iter=3000).fit(Xe, D["y"])
        cl = list(m.classes_)
        for j, nm in enumerate(names):
            c = m.coef_[:, X.shape[1] + j]
            rows.append({"term": col, "fit": kind, "animal": nm, "sd": float(x.std()),
                         "b_rem": float(c[cl.index(1)] - c[cl.index(0)]), "b_wake": float(c[cl.index(2)] - c[cl.index(0)]),
                         "n": int((D["animal"] == nm).sum()) if kind == "per_animal" else len(z),
                         "n_rem": int(((D["animal"] == nm) & (D["y"] == 1)).sum()) if kind == "per_animal" else int((D["y"] == 1).sum())})
    return pd.DataFrame(rows)


def alignment(steps: pd.DataFrame, sc: str) -> dict:
    f = HELDOUT / f"heldout_steps_{sc}.csv.gz"
    if not f.exists():
        return {"file": str(f), "missing": True}
    H = pd.read_csv(f, usecols=["animal", "record_id", "bout_start", "elapsed", "y"])
    j = H.merge(steps[["animal", "record_id", "bout_start", "elapsed", "y"]], on=["record_id", "bout_start", "elapsed"],
                how="left", suffixes=("_h", ""))
    return {"file": str(f), "heldout_rows": len(H), "matched": int(j.y.notna().sum()), "y_equal": int((j.y == j.y_h).sum()),
            "animal_equal": int((j.animal == j.animal_h).sum())}


# ------------------------------------------------------------------ shared data preparation
def prepare(a) -> dict:
    import swr_temperature as stp
    from output_paths import out_root
    from sleep_model import PASS2MED
    from sleep_schedule import STATES
    q = stp.sessions(Path(a.quality), Path(a.review), ["validated", "good"])
    Q = {(r.animal, r.session): {"use_until_t": r.use_until_t, "block_from": r.block_from} for r in q.itertuples()}
    codes = {k: i for i, k in enumerate(sorted({(r.animal, r.block_from) for r in q.itertuples()}))}
    cache = load_cache(Q, Path(a.swr_root), Path(a.sleep_root), out_root() / COHORT / "rem_ripple_inputs" / "swr_events_and_slope.pkl")
    return {"Q": Q, "codes": codes, "settle": stp.settle_windows(Path(a.cohort_yaml)), "cache": cache,
            "roots": {"final": STATES, "pass2med": PASS2MED}}


def scoring_data(sc: str, ctx: dict) -> dict:
    from sleep_model import build_data, records_for, variant_specs
    from sleep_schedule import REVIEW, included_sessions
    recs = records_for(ctx["roots"][sc])
    starts = {(r.animal, r.session): r.start for r in included_sessions(REVIEW, ctx["roots"][sc]).itertuples()}
    steps = build_data(recs, {REF: variant_specs()[REF]})
    arrs = {rc["record_id"]: record_arrays(rc, starts, ctx["Q"], ctx["settle"], ctx["cache"], ctx["codes"]) for rc in recs}
    BT = block_tables(recs, arrs)
    return {"recs": recs, "steps": steps, "arrs": arrs, "BT": BT, "F": build_features(steps, recs, arrs, BT)}


def pred_job(k: int, tr: np.ndarray, te: np.ndarray, D: dict, specs: dict) -> dict:
    """Held-out class probabilities of each spec in one forward-chaining fold (same design / logit as sleep_model)."""
    from sklearn.linear_model import LogisticRegression
    from sleep_model import design
    te = te[np.isin(D["animal"][te], np.unique(D["animal"][tr]))]
    levels = sorted(set(D["animal"][tr]))
    out = {"k": k, "te": te}
    for name, sp in specs.items():
        Xtr, st = design(D, tr, sp, None, levels)
        m = LogisticRegression(C=1e4, max_iter=3000).fit(Xtr, D["y"][tr])
        Xte, _ = design(D, te, sp, st, levels)
        p = np.full((len(te), 3), 1e-12)
        p[:, m.classes_] = m.predict_proba(Xte)
        out[name] = p / p.sum(1, keepdims=True)
    return out


def outcome_split(D: dict, res: list[dict], lo: str, hi: str) -> list[dict]:
    """K1: the held-out change split into the total, the binary REM and the binary WAKE log-loss (folds 1.., as tables)."""
    from sleep_cycles import boot_ci
    eps = 1e-12
    y = D["y"]
    rows = []
    for metric in ("total", "rem", "wake"):
        per, pa = [], {}
        for r in res[1:]:
            te = r["te"]
            yy = y[te]

            def ll(p):
                if metric == "total":
                    return -np.log(np.clip(p[np.arange(len(yy)), yy], eps, 1))
                c = 1 if metric == "rem" else 2
                pc, yc = np.clip(p[:, c], eps, 1 - eps), (yy == c)
                return -(yc * np.log(pc) + (~yc) * np.log(1 - pc))
            a_, b_ = ll(r[lo]), ll(r[hi])
            per.append({"fold": r["k"], "n": len(te), "d": float(b_.mean() - a_.mean()), "base": float(a_.mean())})
            an = D["animal"][te]
            for x in np.unique(an):
                m = an == x
                s = pa.setdefault(x, [0.0, 0])
                s[0] += float((b_[m] - a_[m]).sum())
                s[1] += int(m.sum())
        Pf = pd.DataFrame(per)
        est, l_, h_ = boot_ci(Pf, "d")
        base = float(np.sum(Pf.base * Pf.n) / Pf.n.sum())
        better = sum(v[0] < 0 for v in pa.values())
        rows.append({"comparison": f"{hi} vs {lo}", "metric": metric, "delta_pct": 100 * est / base, "ci_lo_pct": 100 * l_ / base,
                     "ci_hi_pct": 100 * h_ / base, "animals_better": better, "animals": len(pa), "n_steps": int(Pf.n.sum())})
    return rows


def checks(a):
    """Amendment 2: artifact checks K1-K6 of the ripple-counter gain (ALL events), both scorings, subset S2."""
    from joblib import Parallel, delayed
    from output_paths import run_dir
    from sleep_model import folds_of
    t_start = time.time()
    out = Path(a.run) if a.run else run_dir("rem_ripple_checks", COHORT)
    ctx = prepare(a)
    comp, split, k6 = [], [], []
    for sc in a.scorings:
        S = scoring_data(sc, ctx)
        steps, F = S["steps"], S["F"]
        byrid = {rc["record_id"]: rc for rc in S["recs"]}
        P = np.expm1(steps[f"lP_{REF}"].to_numpy().astype(float))
        K = pd.concat([check_features(g, byrid[rid], S["arrs"][rid], S["BT"], P[steps.index.get_indexer(g.index)])
                       for rid, g in steps.groupby("record_id")]).reindex(steps.index)
        FK = pd.concat([F, K], axis=1)
        s2 = F.S2.to_numpy()
        kfin = np.isfinite(K[[c for c in K.columns if c != "dbar"]].to_numpy()).all(1)
        print(f"[{sc}] S2 {s2.sum()} steps, K features finite on {(s2 & kfin).sum()}", flush=True)
        D = subset_arrays(steps, FK, s2 & kfin)

        def fam(name, D_, specs, pairs):
            t1 = time.time()
            rows, Ft, FAt = run_family(D_, specs, pairs, a.workers)
            for r in rows:
                r.update(scoring=sc, family=name)
            Ft.to_csv(out / f"folds_{name}_{sc}.csv", index=False)
            FAt.to_csv(out / f"folds_animal_{name}_{sc}.csv", index=False)
            print(f"[{sc}] {name}: {len(D_['y'])} steps, {time.time() - t1:.0f} s", flush=True)
            for r in rows:
                print(f"   {r['test']:<34} {r.get('delta_pct', np.nan):+.3f} % [{r.get('ci_lo_pct', np.nan):+.3f}, "
                      f"{r.get('ci_hi_pct', np.nan):+.3f}] {r.get('animals_better')}/{r.get('animals')}  holds={r['holds_rule']}", flush=True)
            comp.extend(rows)
            pd.DataFrame(comp).to_csv(out / "comparisons_checks.csv", index=False)

        specs = {"B": B, **{f"B+rho{L}": {**B, "extra": (f"rho{L}",)} for L in KLAGS},
                 **{f"B+rhos{i}": {**B, "extra": (f"rhos{i}",)} for i in (1, 2, 3)}, "B+rhow": {**B, "extra": ("rhow",)}}
        pairs = [("K2 rho L0 (= T2 rho)", "B", "B+rho0"), ("K2 rho L60 (lagged)", "B", "B+rho60"), ("K2 rho L120 (lagged)", "B", "B+rho120"),
                 ("K3 shift 0.3", "B", "B+rhos1"), ("K3 shift 0.5", "B", "B+rhos2"), ("K3 shift 0.7", "B", "B+rhos3"),
                 ("K5 rho whole-block normaliser", "B", "B+rhow")]
        fam("K235", D, specs, pairs)
        # K1: outcome split of the held-out change
        t1 = time.time()
        kspecs = {"B": B, "B+rho0": specs["B+rho0"], "B+rho60": specs["B+rho60"]}
        res = Parallel(n_jobs=a.workers, backend="loky")(delayed(pred_job)(k, tr, te, D, kspecs) for k, (tr, te) in enumerate(folds_of(D)))
        res = sorted(res, key=lambda r: r["k"])
        for hi in ("B+rho0", "B+rho60"):
            for r in outcome_split(D, res, "B", hi):
                r.update(scoring=sc)
                split.append(r)
                print(f"   K1 {r['comparison']:<18} {r['metric']:<5} {r['delta_pct']:+.3f} % [{r['ci_lo_pct']:+.3f}, {r['ci_hi_pct']:+.3f}] "
                      f"{r['animals_better']}/{r['animals']}", flush=True)
        pd.DataFrame(split).to_csv(out / "k1_outcome_split.csv", index=False)
        print(f"[{sc}] K1: {time.time() - t1:.0f} s", flush=True)
        del res
        # K4: depth since the last REM
        md = np.isfinite(D["dbar"])
        Dd = {k: (v[md] if isinstance(v, np.ndarray) and len(v) == len(md) else v) for k, v in D.items()}
        fam("K4", Dd, {"B+dbar": {**B, "extra": ("dbar",)}, "B+dbar+rho0": {**B, "extra": ("dbar", "rho0")},
                       "B+dbar+rho60": {**B, "extra": ("dbar", "rho60")}},
            [("K4 rho L0 beyond depth", "B+dbar", "B+dbar+rho0"), ("K4 rho L60 beyond depth", "B+dbar", "B+dbar+rho60")])
        del Dd
        # K6: direction
        for col in ("rho0", "rho60", "lCa"):
            k6.append(t3_coefs(D, col).assign(scoring=sc))
        pd.concat(k6).to_csv(out / "k6_coefs.csv", index=False)
        del D
    write_json(out / "meta.json", dict(git=git_commit(), scorings=a.scorings, workers=a.workers, shifts=SHIFTS, lags=KLAGS,
                                      minutes=(time.time() - t_start) / 60))
    print(f"checks dir {out}  ({(time.time() - t_start) / 60:.1f} min)", flush=True)
    rd = report_dir(COHORT)
    man = json.loads((rd / f"run_manifest_rem_ripple_model_{COHORT}.json").read_text())
    report(Path(man["run_dir"]), out)


def followup(a):
    """Amendment 3 (after the Fable audit, before running): K7 the lag test on steps >= 60 / 120 s into a bout, K4b the
    depth control with a same-subset baseline, K8 a description of the REM- / WAKE-ending bouts by length."""
    man = json.loads((report_dir(COHORT) / f"run_manifest_rem_ripple_model_{COHORT}.json").read_text())
    out = Path(man["checks_dir"])
    ctx = prepare(a)
    comp, k8 = [], []

    def sub(D, m):
        return {k: (v[m] if isinstance(v, np.ndarray) and len(v) == len(m) else v) for k, v in D.items()}
    for sc in a.scorings:
        S = scoring_data(sc, ctx)
        steps, F = S["steps"], S["F"]
        byrid = {rc["record_id"]: rc for rc in S["recs"]}
        P = np.expm1(steps[f"lP_{REF}"].to_numpy().astype(float))
        K = pd.concat([check_features(g, byrid[rid], S["arrs"][rid], S["BT"], P[steps.index.get_indexer(g.index)])
                       for rid, g in steps.groupby("record_id")]).reindex(steps.index)
        m = F.S2.to_numpy() & np.isfinite(K.drop(columns="dbar").to_numpy()).all(1)
        D = subset_arrays(steps, pd.concat([F, K], axis=1), m)
        st = pd.concat([steps, K, F[["Ca"]]], axis=1)[m].reset_index(drop=True)
        el = st.elapsed.to_numpy()

        def fam(name, D_, specs, pairs):
            t1 = time.time()
            rows, Ft, FAt = run_family(D_, specs, pairs, a.workers)
            for r in rows:
                r.update(scoring=sc, family=name)
            Ft.to_csv(out / f"folds_{name}_{sc}.csv", index=False)
            FAt.to_csv(out / f"folds_animal_{name}_{sc}.csv", index=False)
            print(f"[{sc}] {name}: {len(D_['y'])} steps, {int((D_['y'] == 1).sum())} REM, {time.time() - t1:.0f} s", flush=True)
            for r in rows:
                print(f"   {r['test']:<40} {r.get('delta_pct', np.nan):+.3f} % [{r.get('ci_lo_pct', np.nan):+.3f}, "
                      f"{r.get('ci_hi_pct', np.nan):+.3f}] {r.get('animals_better')}/{r.get('animals')}  holds={r['holds_rule']}", flush=True)
            comp.extend(rows)
            pd.DataFrame(comp).to_csv(out / "comparisons_followup.csv", index=False)
        sp = {"B": B, "B+rho0": {**B, "extra": ("rho0",)}, "B+rho60": {**B, "extra": ("rho60",)}}
        for E in (60, 120):                                                # K7
            fam(f"K7_{E}", sub(D, el >= E), sp, [(f"K7 elapsed>={E}: rho0", "B", "B+rho0"), (f"K7 elapsed>={E}: rho60", "B", "B+rho60")])
        md = np.isfinite(D["dbar"])                                        # K4b
        fam("K4b", sub(D, md), {"B": B, "B+rho0": sp["B+rho0"], "B+dbar": {**B, "extra": ("dbar",)},
                                "B+dbar+rho0": {**B, "extra": ("dbar", "rho0")}},
            [("K4b depth subset: rho0 (baseline)", "B", "B+rho0"), ("K4b depth subset: dbar", "B", "B+dbar"),
             ("K4b depth subset: rho0 beyond dbar", "B+dbar", "B+dbar+rho0")])
        # K8: bouts by length and end (the last step of each bout in the subset)
        gb = st.groupby(["record_id", "bout_start"])
        last = st[st.elapsed == gb.elapsed.transform("max")]
        last = last[last.y.isin([1, 2])].copy()
        last["end"] = last.y.map({1: "REM", 2: "WAKE"})
        last["len"] = pd.cut(last.bout_len, [0, 60, 120, 300, 1e9], labels=["<= 60 s", "60-120 s", "2-5 min", "> 5 min"])
        last["prev"] = np.select([last.prev_rem == 1, last.d_prev > 0], ["REM", "WAKE"], "unknown / start")
        for (e, ln), g in last.groupby(["end", "len"], observed=True):
            k8.append({"scoring": sc, "end": e, "bout_len": ln, "n": len(g), "share_of_end": len(g) / int((last.end == e).sum()),
                       "after_REM": float((g.prev == "REM").mean()), "after_WAKE": float((g.prev == "WAKE").mean()),
                       "bout_ripples_median": float(g.kbout.median()), "bout_zero_ripples": float((g.kbout == 0).mean()),
                       "bout_rate_per_min_median": float((g.kbout / np.maximum(g.elapsed, 10) * 60).median()),
                       "C_median": float(g.Ca.median())})
        pd.DataFrame(k8).to_csv(out / "k8_bouts.csv", index=False)
        print(pd.DataFrame(k8)[lambda d: d.scoring == sc].round(3).to_string(index=False), flush=True)
    report(Path(man["run_dir"]), out)


def posthoc(a):
    """POST HOC (after Amendment 2, not pre-registered): where in time the unlagged rho gain sits. Held-out per-step
    log-loss change of B + rho0 vs B, by how the bout ends and by the seconds from the step's end to the bout's end."""
    from joblib import Parallel, delayed
    from sleep_model import folds_of
    man = json.loads((report_dir(COHORT) / f"run_manifest_rem_ripple_model_{COHORT}.json").read_text())
    out = Path(man["checks_dir"])
    ctx = prepare(a)
    rows = []
    for sc in a.scorings:
        S = scoring_data(sc, ctx)
        steps, F = S["steps"], S["F"]
        byrid = {rc["record_id"]: rc for rc in S["recs"]}
        P = np.expm1(steps[f"lP_{REF}"].to_numpy().astype(float))
        K = pd.concat([check_features(g, byrid[rid], S["arrs"][rid], S["BT"], P[steps.index.get_indexer(g.index)])
                       for rid, g in steps.groupby("record_id")]).reindex(steps.index)
        m = F.S2.to_numpy() & np.isfinite(K.drop(columns="dbar").to_numpy()).all(1)
        D = subset_arrays(steps, pd.concat([F, K], axis=1), m)
        st = steps[m].reset_index(drop=True)
        gb = st.groupby(["record_id", "bout_start"])
        last = gb.elapsed.transform("max")
        st["bout_end"] = gb.y.transform("max")                             # only a bout's last step can be != 0
        st["to_end_s"] = last - st.elapsed                                 # 0 = the step whose end is the transition
        specs = {"B": B, "B+rho0": {**B, "extra": ("rho0",)}}
        res = Parallel(n_jobs=a.workers, backend="loky")(delayed(pred_job)(k, tr, te, D, specs) for k, (tr, te) in enumerate(folds_of(D)))
        for r in sorted(res, key=lambda r: r["k"])[1:]:
            te, yy = r["te"], D["y"][r["te"]]
            d = (-np.log(np.clip(r["B+rho0"][np.arange(len(te)), yy], 1e-12, 1))) - (-np.log(np.clip(r["B"][np.arange(len(te)), yy], 1e-12, 1)))
            rows.append(pd.DataFrame({"scoring": sc, "fold": r["k"], "animal": D["animal"][te], "d_ll": d,
                                      "bout_end": st.bout_end.to_numpy()[te], "to_end_s": st.to_end_s.to_numpy()[te],
                                      "elapsed": st.elapsed.to_numpy()[te], "rho0": D["rho0"][te], "rho60": D["rho60"][te]}))
    X = pd.concat(rows, ignore_index=True)
    X["end"] = X.bout_end.map({0: "no transition (censored)", 1: "ends in REM", 2: "ends in WAKE"})
    X["to_end"] = pd.cut(X.to_end_s, [-1, 0, 50, 110, 290, 1e9], labels=["last step", "10-50 s before", "60-110 s before",
                                                                           "2-5 min before", "> 5 min before"])
    X["el"] = pd.cut(X.elapsed, [-1, 50, 290, 1e9], labels=["first minute of the bout", "1-5 min", "> 5 min"])
    tabs = []
    for by in (["end", "to_end"], ["end", "el"]):
        g = X.groupby(["scoring"] + by, observed=True)
        t = g.agg(steps=("d_ll", "size"), mean_d_ll=("d_ll", "mean"), sum_d_ll=("d_ll", "sum"),
                  rho0=("rho0", "mean"), rho60=("rho60", "mean")).reset_index()
        t["share_of_gain"] = t.sum_d_ll / t.groupby("scoring").sum_d_ll.transform("sum")
        t["split"] = "+".join(by)
        tabs.append(t)
    T = pd.concat(tabs, ignore_index=True)
    T.to_csv(out / "posthoc_gain_by_time.csv", index=False)
    print(T.round(4).to_string(index=False), flush=True)
    report(Path(man["run_dir"]), out)


# ------------------------------------------------------------------ run
def run(a):
    from output_paths import run_dir
    t_start = time.time()
    out = Path(a.run) if a.run else run_dir("rem_ripple_model" + ("_smoke" if a.smoke else ""), COHORT)
    ctx = prepare(a)
    print(f"sessions covered {sum(v is not None for v in ctx['cache'].values())} / {len(ctx['Q'])}  ({time.time() - t_start:.0f} s)", flush=True)
    comp, counts, t3s, meta = [], [], [], {"alignment": {}, "codes": {f"{k[0]}|{k[1]}": v for k, v in ctx["codes"].items()}}
    for sc in a.scorings:
        S = scoring_data(sc, ctx)
        steps, F = S["steps"], S["F"]
        meta["alignment"][sc] = alignment(steps, sc)
        print(sc, "alignment", meta["alignment"][sc], flush=True)
        keys = steps[["animal", "record_id", "block", "bout_start", "elapsed", "t", "y"]]
        pd.concat([keys, F], axis=1)[F.S1].to_csv(out / f"features_S1_{sc}.csv.gz", index=False)
        # subset counts, before any fit
        for nm, msk in (("all", np.ones(len(F), bool)), ("S1", F.S1.to_numpy()), ("S2", F.S2.to_numpy())):
            g = steps[msk].groupby("animal")
            for an, gg in g:
                counts.append({"scoring": sc, "subset": nm, "animal": an, "steps": len(gg), "rem": int((gg.y == 1).sum()),
                               "wake": int((gg.y == 2).sum()), "blocks": gg.block.nunique(), "first": str(gg.t.min()), "last": str(gg.t.max())})
        C = pd.DataFrame(counts)
        print(C[C.scoring == sc].to_string(index=False), flush=True)
        if a.features_only:
            continue
        folds_n = 4 if a.smoke else None

        def fam(name, D, specs, pairs):
            from sleep_model import folds_of
            fo = folds_of(D)[:folds_n] if folds_n else None
            t1 = time.time()
            rows, Ft, FAt = run_family(D, specs, pairs, a.workers, fo)
            for r in rows:
                r.update(scoring=sc, family=name)
            Ft.to_csv(out / f"folds_{name}_{sc}.csv", index=False)
            FAt.to_csv(out / f"folds_animal_{name}_{sc}.csv", index=False)
            print(f"[{sc}] {name}: {len(D['y'])} steps, {time.time() - t1:.0f} s", flush=True)
            for r in rows:
                print(f"   {r['test']:<28} {r['comparison']:<28} {r.get('delta_pct', np.nan):+.3f} % "
                      f"[{r.get('ci_lo_pct', np.nan):+.3f}, {r.get('ci_hi_pct', np.nan):+.3f}] "
                      f"{r.get('animals_better')}/{r.get('animals')}  holds={r['holds_rule']}", flush=True)
            comp.extend(rows)
            pd.DataFrame(comp).to_csv(out / "comparisons.csv", index=False)
            return rows

        if not a.smoke:                                                    # reproduction of Step B on all steps
            Dall = subset_arrays(steps, F, np.ones(len(F), bool))
            fam("repro", Dall, {"gate": {"L1": True, "hist": None}, "B": B}, [("repro: B-full vs gate", "gate", "B")])
            del Dall
        D1 = subset_arrays(steps, F, F.S1.to_numpy())
        specsA = {"B": B, **{f"B+rra{L}": {**B, "extra": (f"rra{L}",)} for L in LAGS},
                  **{f"B+rrk{L}": {**B, "extra": (f"rrk{L}",)} for L in (0, 60)},
                  **{f"B+rrw{L}": {**B, "extra": (f"rrw{L}",)} for L in (0, 60)}}
        pairsA = [("T1 L0 ALL (precursor)", "B", "B+rra0"), ("T1 L60 ALL (readiness, primary)", "B", "B+rra60"),
                  ("T1 L120 ALL (sens.)", "B", "B+rra120"), ("T1 L0 KEPT (sens.)", "B", "B+rrk0"),
                  ("T1 L60 KEPT (sens.)", "B", "B+rrk60"), ("T1 L0 whole-block (sens.)", "B", "B+rrw0"),
                  ("T1 L60 whole-block (sens.)", "B", "B+rrw60")]
        if a.smoke:
            specsA = {k: specsA[k] for k in ("B", "B+rra60")}
            pairsA = pairsA[1:2]
        fam("T1", D1, specsA, pairsA)
        for L in (0, 60):
            t3s.append(t3_coefs(D1, f"rra{L}").assign(scoring=sc))
        pd.concat(t3s).to_csv(out / "t3_coefs.csv", index=False)
        if a.smoke:
            continue
        D2 = subset_arrays(steps, F, F.S2.to_numpy())
        specsB = {"B": B, "Bc": {"L1": True, "hist": "ripcount"}, "Bck": {"L1": True, "hist": "ripcountk"},
                  "B+lCa": {**B, "extra": ("lCa",)}, "B+lCk": {**B, "extra": ("lCk",)}, "B+rho": {**B, "extra": ("rho",)}}
        pairsB = [("T2 ripple counter replaces P (ALL)", "B", "Bc"), ("T2 ripple counter replaces P (KEPT)", "B", "Bck"),
                  ("T2 + ln(1+C) on B (ALL)", "B", "B+lCa"), ("T2 + ln(1+C) on B (KEPT)", "B", "B+lCk"),
                  ("T2 + rate since REM rho (ALL)", "B", "B+rho")]
        fam("T2", D2, specsB, pairsB)
        del D2
        # depth control for every lag whose ALL term holds on this scoring (applied as the rule on both scorings later)
        held = [L for L in LAGS if any(r["holds_rule"] for r in comp if r["scoring"] == sc and r["test"].startswith(f"T1 L{L} ALL"))]
        for L in held:
            m = F.S1.to_numpy() & np.isfinite(F[f"dep{L}"].to_numpy())
            Dd = subset_arrays(steps, F, m)
            fam(f"D{L}", Dd, {f"B+dep{L}": {**B, "extra": (f"dep{L}",)}, f"B+dep{L}+rra{L}": {**B, "extra": (f"dep{L}", f"rra{L}")}},
                [(f"D L{L}: rr beyond depth", f"B+dep{L}", f"B+dep{L}+rra{L}")])
        del D1
    pd.DataFrame(counts).to_csv(out / "subset_counts.csv", index=False)
    meta.update(git=git_commit(), scorings=a.scorings, workers=a.workers, smoke=a.smoke, minutes=(time.time() - t_start) / 60,
                params=dict(WIN_S=WIN_S, LAGS=LAGS, MIN_M_S=MIN_M_S, MIN_NORM_S=MIN_NORM_S, K0=K0, TAU_W=TAU_W, REF=REF))
    write_json(out / "meta.json", meta)
    print(f"run dir {out}  ({(time.time() - t_start) / 60:.1f} min)", flush=True)
    if not a.smoke and not a.features_only:
        report(out)


# ------------------------------------------------------------------ report
def _f(x, nd=2):
    return "–" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:+.{nd}f}"


def figure(Cm: pd.DataFrame, out: Path, Kc: pd.DataFrame | None = None) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    d = Cm[Cm.family.isin(["T1", "T2"]) | Cm.family.str.startswith("D")].copy()
    if Kc is not None:
        d = pd.concat([d, Kc[Kc.test != "K2 rho L0 (= T2 rho)"]], ignore_index=True)
    tests = list(dict.fromkeys(d.test))
    fig, ax = plt.subplots(figsize=(8.5, 0.42 * len(tests) + 1.6))
    for j, (sc, col) in enumerate((("final", "#1f77b4"), ("pass2med", "#d62728"))):
        g = d[d.scoring == sc].set_index("test")
        y = np.arange(len(tests)) + (j - 0.5) * 0.28
        for i, t in enumerate(tests):
            if t not in g.index:
                continue
            r = g.loc[t]
            ax.errorbar(r.delta_pct, y[i], xerr=[[r.delta_pct - r.ci_lo_pct], [r.ci_hi_pct - r.delta_pct]], fmt="o",
                        mfc=col if r.holds_rule else "white", color=col, ms=5, capsize=2, label=sc if i == 0 else None)
    ax.axvline(0, color="k", lw=0.8)
    ax.set_yticks(np.arange(len(tests)), tests, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("held-out log-loss change vs the smaller model (%)   (< 0 = the ripple term predicts better)")
    ax.set_title("Ripples in the REM-entry model (B-full, P_tw600_k0); filled = holds (CI < 0, >= n-1 animals)", fontsize=9)
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    p = figure_dir(COHORT) / f"ephys_spikes_rem_ripple_model_{COHORT}.png"
    fig.savefig(p, dpi=150)
    fig.savefig(out / "figures" / p.name, dpi=150)
    plt.close(fig)
    return p


def checks_verdict(K: pd.DataFrame, S: pd.DataFrame) -> tuple[str, dict]:
    """Amendment 2 reading of rho (ALL): (i) lagged rho_60 holds, (ii) true gain beyond every shift and no shift holds,
    (iii) beyond depth, (iv) binary REM log-loss improves; each on both scorings."""
    sc = sorted(K.scoring.unique())

    def hold(test):
        g = K[K.test == test]
        return len(g) == len(sc) and bool(g.holds_rule.all())
    ok = {"i": hold("K2 rho L60 (lagged)")}
    ii = True
    for s in sc:
        g = K[K.scoring == s].set_index("test")
        true = g.loc["K2 rho L0 (= T2 rho)", "delta_pct"]
        sh = g.loc[[t for t in g.index if t.startswith("K3")]]
        ii &= bool((sh.delta_pct > true).all() and not sh.holds_rule.any())
    ok["ii"] = ii
    ok["iii"] = hold("K4 rho L0 beyond depth")
    r = S[(S.comparison == "B+rho0 vs B") & (S.metric == "rem")]
    ok["iv"] = len(r) == len(sc) and bool((r.ci_hi_pct < 0).all())
    why = {"i": "the gain is a precursor of the transition (it vanishes when the last minute is left out)",
           "ii": "the gain is the record-level ripple rate (which records are ripple-rich), not ripple timing in the REM cycle",
           "iii": "beyond NREM depth the gain is not stable across the two scorings", "iv": "the gain is not in REM entry (it predicts waking)"}
    if all(ok.values()):
        txt = ("**The ripples accumulated since the last REM carry REM-entry information beyond NREM time, the clock and the "
               "wake history — all four artifact checks pass on both scorings.** Candidate (one cohort, five test animals, a "
               "few tenths of a percent).")
    else:
        failed = [k for k in ("i", "ii", "iii", "iv") if not ok[k]]
        test_of = {"i": "K2 rho L60 (lagged)", "iii": "K4 rho L0 beyond depth"}

        def where(k):
            if k not in test_of:
                return ""
            g = K[K.test == test_of[k]]
            bad = [f"{r.scoring} {r.delta_pct:+.3f} % [{r.ci_lo_pct:+.3f}, {r.ci_hi_pct:+.3f}]" for r in g.itertuples() if not r.holds_rule]
            return f" ({'; '.join(bad)})" if bad else ""
        txt = ("**The ripple-counter gain does not survive the pre-registered artifact checks:** "
               + "; ".join(f"({k}) failed{where(k)} — {why[k]}" for k in failed) + ".")
    return txt, ok


def followup_text(Fu: pd.DataFrame, K8: pd.DataFrame) -> tuple[str, str]:
    """Amendment 3 reading from the follow-up tables: (lag + depth text, short-bout description)."""
    def hold(test):
        g = Fu[Fu.test == test]
        return len(g) == 2 and bool(g.holds_rule.all())

    def num(test):
        g = Fu[Fu.test == test]
        return "; ".join(f"{r.scoring} {r.delta_pct:+.3f} % [{r.ci_lo_pct:+.3f}, {r.ci_hi_pct:+.3f}], {r.animals_better}/{r.animals}"
                         + ("" if r.holds_rule else " (does not hold)") for r in g.itertuples())
    r0, r60 = hold("K7 elapsed>=60: rho0"), hold("K7 elapsed>=60: rho60")
    r0_120 = hold("K7 elapsed>=120: rho0")
    lag = ("**Where the lag can see (steps >= 60 s into a NREM bout):** the unlagged rho gives " + num("K7 elapsed>=60: rho0")
           + "; the lagged rho gives " + num("K7 elapsed>=60: rho60") + ". **Steps >= 120 s into a bout:** unlagged "
           + num("K7 elapsed>=120: rho0") + ". ")
    if r0 and not r60:
        lag += "Pre-registered reading: information in the last 60 s before the step, within longer bouts."
    elif not r0 and not r0_120:
        lag += ("Pre-registered reading: the unlagged rho does not hold on both scorings even 60 s into a bout, and on neither "
                "from 120 s. **The counter's gain comes from the first one to two minutes of NREM bouts,** not from steps >= 120 s "
                "into a bout (K7); a last-minute dip within long bouts (naps R3, a within-run description) was not tested as a "
                "predictor.")
    else:
        lag += "Mixed: see the table."
    g = Fu[Fu.test.str.startswith("K4b")].set_index(["scoring", "test"])
    parts = []
    for sc in sorted(Fu.scoring.unique()):
        base = g.loc[(sc, "K4b depth subset: rho0 (baseline)")]
        beyond = g.loc[(sc, "K4b depth subset: rho0 beyond dbar")]
        parts.append(f"{sc}: rho alone {base.delta_pct:+.3f} % ({'holds' if base.holds_rule else 'does not hold'}), beyond depth "
                     f"{beyond.delta_pct:+.3f} % ({'holds' if beyond.holds_rule else 'does not hold'})")
    depth = ("**Depth with its own baseline (K4b; the subset drops the first NREM minute after a REM):** " + "; ".join(parts)
             + ". The two scorings disagree, so the depth control is **inconclusive**.")
    k = K8[(K8.end == "REM") & (K8.bout_len == "<= 60 s")]
    w = K8[(K8.end == "WAKE") & (K8.bout_len == "<= 60 s")].set_index("scoring")
    lng = K8[K8.bout_len == "> 5 min"].set_index(["scoring", "end"])
    short = ("**The short bouts (K8):** " + "; ".join(
        f"{r.scoring}: {100 * r.share_of_end:.0f} % of REM entries come from NREM bouts <= 60 s, {100 * r.after_REM:.0f} % of "
        f"them directly after REM, ripple rate {r.bout_rate_per_min_median:.0f} /min (short bouts ending in WAKE: "
        f"{w.loc[r.scoring, 'bout_rate_per_min_median']:.0f} /min), {100 * r.bout_zero_ripples:.0f} % with no ripple"
        for r in k.itertuples()) + ". In bouts > 5 min the whole-bout rate before REM equals the whole-bout rate before WAKE ("
        + "; ".join(f"{sc} {lng.loc[(sc, 'REM'), 'bout_rate_per_min_median']:.0f} vs {lng.loc[(sc, 'WAKE'), 'bout_rate_per_min_median']:.0f} /min"
                    for sc in sorted(K8.scoring.unique())) + "). So the REM-predictive ripple signal is the ripple poverty "
        "of short NREM stretches that return to REM, often inside a REM episode. The scorer's NREM / REM call and the ripple "
        "detector read the same LFP, so this cannot be separated from how the scorer cuts REM episodes.") if len(k) else ""
    return lag + " " + depth, short


def report(out: Path, chk: Path | None = None) -> Path:
    out = Path(out)
    Cm = pd.read_csv(out / "comparisons.csv")
    SC = pd.read_csv(out / "subset_counts.csv")
    T3 = pd.read_csv(out / "t3_coefs.csv") if (out / "t3_coefs.csv").exists() else pd.DataFrame()
    meta = json.loads((out / "meta.json").read_text())
    rd = report_dir(COHORT)
    Cm.to_csv(rd / f"ephys_spikes_rem_ripple_model_comparisons_{COHORT}.csv", index=False)

    def both(prefix):
        g = Cm[Cm.test.str.startswith(prefix)]
        return len(g) == 2 and bool(g.holds_rule.all()), g

    v60, _ = both("T1 L60 ALL")
    v0, _ = both("T1 L0 ALL")
    vk60, _ = both("T1 L60 KEPT")
    vd = {L: both(f"D L{L}")[0] for L in LAGS}
    if v60:
        verdict = ("**The lagged ripple rate (window ending 60 s before the step) improves held-out REM-entry prediction beyond "
                   "the NREM counter, the clock and the wake history on both scorings** — REM readiness carries ripple "
                   "information. " + ("It survives the depth control." if vd[60] else "It does **not** survive the depth control: "
                                       "it is carried by NREM depth."))
    elif v0:
        verdict = ("**Only the unlagged rate helps** (window ending at the step start); the lagged one does not. The gain is a "
                   "precursor of the transition already under way (the pre-REM ripple drop), not a slower REM-readiness signal.")
    else:
        verdict = ("**The recent ripple rate (10-min window, any lag) does not improve held-out REM-entry prediction on both "
                   "scorings.** Beyond the NREM counter, the clock and the wake history, the ripple rate of the last 10 min of "
                   "NREM adds no predictive information.")
    t2 = Cm[Cm.family == "T2"]
    t2_both = {t: (len(g) == 2 and bool(g.holds_rule.all())) for t, g in t2.groupby("test")}
    t2_txt = ("**The ripples accumulated since the last REM (T2) pass the numeric rule on both scorings** "
              f"({', '.join(t for t, v in t2_both.items() if v)}). By the plan's rule this is description, because T1 failed "
              "at L = 60 s; Amendment 2 tests it for artifacts.") if any(t2_both.values()) else \
        "The ripple counter since the last REM (T2) does not hold on both scorings either."
    Kc = pd.read_csv(Path(chk) / "comparisons_checks.csv") if chk else None
    Ks = pd.read_csv(Path(chk) / "k1_outcome_split.csv") if chk else None
    K6 = pd.read_csv(Path(chk) / "k6_coefs.csv") if chk else None
    k_txt, k_ok = checks_verdict(Kc, Ks) if chk else ("Amendment 2 checks not run yet.", {})
    fig = figure(Cm, out, Kc)
    ph = Path(chk) / "posthoc_gain_by_time.csv" if chk else None
    fu = Path(chk) / "comparisons_followup.csv" if chk else None
    Fu = pd.read_csv(fu) if fu is not None and fu.exists() else None
    K8 = pd.read_csv(Path(chk) / "k8_bouts.csv") if Fu is not None else None
    a3_txt, short_txt = followup_text(Fu, K8) if Fu is not None else ("", "")
    overall = ""
    if Fu is not None:
        overall = ("4. **After the Fable audit (Amendment 3).** The lag check of Amendment 2 cannot see the first minute of a "
                   "bout, where 70-80 % of the counter's gain sits (post hoc). " + a3_txt + "\n\n   " + short_txt + "\n\n"
                   "5. **Overall.** Beyond the NREM counter, the clock and the wake history, the preceding NREM ripples carry "
                   "no REM-timing information at the scale of the REM cycle: no held-out gain larger than about 0.05 % from a "
                   "10-min window rate at lags 0-120 s, and no gain from ripples older than the current bout. The ripple "
                   "information about REM entry is the ripple poverty of short NREM bouts that end in REM (see 4). The macro-scale reciprocity "
                   "(ripple-rich naps, REM-poor nights) is therefore accounted for by drivers the model already has. Limits: 5 "
                   "test animals (SF11 only in training), one cohort; sleep-onset NREM after long wakes is not in S1; ripple "
                   "counts are not replay content.")
    L = []
    L += [f"# Ripples in the REM-entry model (cohort {COHORT})", "",
          f"Plan, pre-registered before any fit: [2026-10-09-rem-ripple-model.md](../../../../implementation_plan/2026-10-09-rem-ripple-model.md) "
          "(Amendment 1 = the model owner's reply; Amendment 2 = the artifact checks; Amendment 3 = after a read-only Fable "
          "audit; each written before it ran). Driver "
          f"`ephys/rem_ripple_model.py`; run `{out}`" + (f", checks `{chk}`" if chk else "") + f"; git `{meta.get('git')}`.", "",
          "## Answer", "", "1. **Recent rate (T1).** " + verdict, "", "2. **Accumulated count (T2).** " + t2_txt, "",
          "3. **Artifact checks (Amendment 2).** " + k_txt + (" *Two of these readings were revised after the audit: (i) is "
          "uninformative for steps in a bout's first minute, and (iii) ran without a same-subset baseline; see 4.*"
          if Fu is not None else ""), ""] + ([overall, ""] if overall else [])
    L += ["## The question", "",
          "- Naps and the early main sleep are ripple-rich and REM-poor. Across sleep periods REM and ripple rate are "
          "reciprocal (ρ −0.54, 6/6). In NREM runs >= 5 min the last-minute ripple rate, relative to the run's own earlier "
          "rate, is lower before REM than before waking (naps R3, 6/6; a description within the run, not a predictor).",
          "- Is that a link, or two outputs of the same drivers?",
          "- The test: does the ripple rate of the preceding NREM improve **held-out** prediction of the next REM entry?",
          "  - The reference model is the sleep model's best: Step B's B-full, i.e. the NREM counter P_tw600_k0 + clock + "
          "experiment day + wake history (L1) + animal.",
          "  - Only information from before each 10-s step is used.",
          "- Ripples stay a candidate predictor: they never define naps or REM, and the staging is unchanged.", ""]
    L += ["## Definitions", "",
          "Steps, outcome and model: `ephys/sleep_model.py` Step B. A step = 10 s of NREM, starting at $t$; outcome = stay / "
          "REM / WAKE at its end; multinomial logit, C = 1e4.", "",
          "- **Covered second:** session tier validated / good (SWR quality guide), before `use_until`, outside the probe-advance "
          "settle windows. SF11 is covered only to 09-02 ~17:04.",
          "- **ALL events (primary):** every detected event whose peak second is NREM in the scoring being modelled, flags ignored. "
          "**KEPT (sensitivity):** the same with `excluded == False`.",
          "- **Window rate**, for lag $L$ ∈ {0, 60, 120 s}, over the record seconds $[t-L-600,\\,t-L)$:",
          "  $$rr_L = \\ln\\frac{k + 0.5}{(m/60)\\,\\bar r_b(t-L)}$$",
          "  where $k$ = events in the window, $m$ = its NREM seconds, and $\\bar r_b(\\tau)$ = events per NREM minute of the "
          "animal × probe block over its covered NREM seconds before $\\tau$.",
          "  - It needs ≥ 30 min, which makes the normaliser causal. **Text:** the recent ripple rate relative to the block's "
          "running average; 0 = typical, +0.69 = twice the usual rate.",
          "  - Sensitivity 'whole-block': $\\bar r_b$ over the whole block.",
          "- **Ripple counter:** $C = E/\\bar r_b(t)$, with $E$ kept exactly like P_tw600_k0:",
          "  - NREM adds its events up to $t$;",
          "  - a wake of $d$ s multiplies by $e^{-d/600}$;",
          "  - REM empties it;",
          "  - unknown freezes it.",
          "  - **Text:** the ripples accumulated since the last REM, in 'expected NREM minutes', so $C$ and $P$ read in the "
          "same units.",
          "  - Enters as $\\ln(1+C)$ (spline in the history slot, replacing $P$; or linear on top of B).",
          "- **Rate since REM:** $\\rho = \\ln\\frac{C+0.5}{P+0.5}$, the discounted relative ripple rate since the last REM.",
          "- **Depth:** $\\text{depth}_L$ = mean raw spectral slope (imu_fixch, z within animal × block) over the window's NREM "
          "seconds (>= 60 s with a slope). $\\bar d$ = the discount-weighted mean depth z since the last REM with P's "
          "bookkeeping, defined when >= 60 discounted NREM-s carry a slope (so it drops the steps right after a REM).",
          "- **Subsets:**",
          "  - S1: the step and every NREM second of $[t-720, t)$ covered; $m$ ≥ 180 s in all three windows; all rates finite.",
          "  - S2: S1 + every NREM second since the last REM covered.",
          "  - All models of one comparison are fitted on the same subset.",
          "- **Rule:** $\\Delta$ = held-out log-loss change in % of the smaller model, forward chaining over day-half blocks "
          "(fold 0 dropped), 95 % CI by bootstrap over folds.",
          "  - **holds** = CI upper < 0 **and** ≥ n − 1 of the n animals with test steps better.",
          "  - A term counts only if it holds on **both** FINAL and pass2med.", ""]
    L += ["## Data", ""]
    al = meta.get("alignment", {})
    for sc, d in al.items():
        L.append(f"- Alignment with the owner's cached held-out steps ({sc}): {d.get('matched')} / {d.get('heldout_rows')} rows "
                 f"matched, y equal on {d.get('y_equal')}.")
    rp = Cm[Cm.family == "repro"]
    for r in rp.itertuples():
        L.append(f"- Reproduction of Step B, B-full vs gate-only on all steps ({r.scoring}): {_f(r.delta_pct)} % "
                 f"[{_f(r.ci_lo_pct)}, {_f(r.ci_hi_pct)}], {r.animals_better}/{r.animals} animals, {r.n_steps} test steps / "
                 f"{r.n_rem} REM. Step B: " + ("−2.17 % (122,735 / 2,544)" if r.scoring == "final" else "−1.97 % (123,304 / 2,666)")
                 + ", there with the counter's grid point chosen per fold (nested: P_tw600_k60 in fold 1, P_tw300_k0 in "
                 "folds 2-6, then P_tw600_k0); here it is fixed at the full-run optimum P_tw600_k0, mildly optimistic for B.")
    L.append("")
    pv = SC.pivot_table(index=["scoring", "animal"], columns="subset", values="steps", aggfunc="sum").reset_index()
    pr = SC.pivot_table(index=["scoring", "animal"], columns="subset", values="rem", aggfunc="sum").reset_index()
    L += ["Steps per subset (REM entries in brackets):", "", "| scoring | animal | all | S1 | S2 |", "|---|---|---:|---:|---:|"]
    for (r, rr) in zip(pv.itertuples(index=False), pr.itertuples(index=False)):
        d, e = r._asdict(), rr._asdict()
        L.append(f"| {d['scoring']} | {d['animal']} | " + " | ".join(
            f"{int(d[c]) if pd.notna(d.get(c)) else 0} ({int(e[c]) if pd.notna(e.get(c)) else 0})" for c in ("all", "S1", "S2")) + " |")
    L += ["", "S1 keeps the steps whose preceding 12 min are ripple-covered. Steps after an uncovered stretch (another tier, a "
          "settle window, SF11 after 09-02) or early in a block (no causal normaliser yet) are lost.", ""]
    L += ["## Results", "", f"![comparisons](../figures/{fig.name})", "",
          "| test | scoring | comparison | Δ % | 95 % CI | animals better | holds |", "|---|---|---|---:|---|---:|:---:|"]
    for r in Cm[Cm.family != "repro"].itertuples():
        L.append(f"| {r.test} | {r.scoring} | {r.comparison} | {_f(r.delta_pct, 3)} | [{_f(r.ci_lo_pct, 3)}, {_f(r.ci_hi_pct, 3)}] | "
                 f"{r.animals_better}/{r.animals} | {'yes' if r.holds_rule else 'no'} |")
    L.append("")
    if len(T3):
        L += ["### Direction (T3, description)", "",
              "Full-subset fit of B + the ripple term, z-scored. Coefficient = log-odds change per +1 SD vs staying in NREM.",
              "Negative on REM = more recent ripples, later REM.", "",
              "| scoring | term | fit | animal | b REM | b WAKE | steps | REM |", "|---|---|---|---|---:|---:|---:|---:|"]
        for r in T3.itertuples():
            L.append(f"| {r.scoring} | {r.term} | {r.fit} | {r.animal} | {_f(r.b_rem, 3)} | {_f(r.b_wake, 3)} | {r.n} | {r.n_rem} |")
        L.append("")
    if chk:
        L += ["## Artifact checks of the counter gain (Amendment 2)", "",
              "All on S2, ALL events, ρ = ln((C + 0.5) / (P + 0.5)). Pre-registered reading: ρ counts as REM-readiness information "
              "only if (i)–(iv) all pass on both scorings.", "",
              "- (i) **K2 lagged:** events of the current bout counted only to t − L, and P lagged alike.",
              "- (ii) **K3 shifts:** each record's per-NREM-second event counts rolled by 0.3 / 0.5 / 0.7 of its length. This keeps "
              "the record's mean rate and breaks the timing.",
              "- (iii) **K4 depth:** d̄ = discount-weighted mean NREM depth z since the last REM, with P's bookkeeping.",
              "- (iv) **K1:** the held-out change split into binary REM and binary WAKE log-loss.",
              "- **K5:** ρ with the whole-block normaliser.", "",
              "| check | scoring | Δ % | 95 % CI | animals better | holds |", "|---|---|---:|---|---:|:---:|"]
        for r in Kc.itertuples():
            L.append(f"| {r.test} | {r.scoring} | {_f(r.delta_pct, 3)} | [{_f(r.ci_lo_pct, 3)}, {_f(r.ci_hi_pct, 3)}] | "
                     f"{r.animals_better}/{r.animals} | {'yes' if r.holds_rule else 'no'} |")
        L += ["", "K1 — where the held-out change sits (binary log-losses, % of B's):", "",
              "| comparison | scoring | outcome | Δ % | 95 % CI | animals better |", "|---|---|---|---:|---|---:|"]
        for r in Ks.itertuples():
            L.append(f"| {r.comparison} | {r.scoring} | {r.metric} | {_f(r.delta_pct, 3)} | [{_f(r.ci_lo_pct, 3)}, {_f(r.ci_hi_pct, 3)}] | "
                     f"{r.animals_better}/{r.animals} |")
        L += ["", "Conditions: " + ", ".join(f"({k}) {'pass' if v else 'FAIL'}" for k, v in k_ok.items()), "",
              "K6 — direction (full-subset fit, log-odds vs staying in NREM per +1 SD). Negative on REM = more ripples since the "
              "last REM than its NREM time predicts, so a later REM:", "",
              "| scoring | term | fit | animal | b REM | b WAKE |", "|---|---|---|---|---:|---:|"]
        for r in K6.itertuples():
            L.append(f"| {r.scoring} | {r.term} | {r.fit} | {r.animal} | {_f(r.b_rem, 3)} | {_f(r.b_wake, 3)} |")
        L.append("")
    if Fu is not None:
        L += ["## Amendment 3: the lag where it can see, depth with a baseline, the short bouts", "",
              "- **K7:** the same comparisons on steps at least 60 s (120 s) into their NREM bout, where the 60-s lag can see "
              "the last minute.",
              "- **K4b:** the depth control with its own baseline on the same subset.",
              "- **K8:** REM- and WAKE-ending bouts by length.", "",
              "| test | scoring | Δ % | 95 % CI | animals better | holds |", "|---|---|---:|---|---:|:---:|"]
        for r in Fu.itertuples():
            L.append(f"| {r.test} | {r.scoring} | {_f(r.delta_pct, 3)} | [{_f(r.ci_lo_pct, 3)}, {_f(r.ci_hi_pct, 3)}] | "
                     f"{r.animals_better}/{r.animals} | {'yes' if r.holds_rule else 'no'} |")
        L += ["", "K8, bouts ending in REM or WAKE (the last step of each bout in S2). Ripples = the bout's events before its "
              "last step:", "",
              "| scoring | ends in | bout length | n | share of that end | after REM | after WAKE | ripples, median | no ripple "
              "| rate /min, median | C median |",
              "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for r in K8.itertuples():
            L.append(f"| {r.scoring} | {r.end} | {r.bout_len} | {r.n} | {100 * r.share_of_end:.0f} % | {100 * r.after_REM:.0f} % | "
                     f"{100 * r.after_WAKE:.0f} % | {r.bout_ripples_median:.0f} | {100 * r.bout_zero_ripples:.0f} % | "
                     f"{r.bout_rate_per_min_median:.1f} | {r.C_median:.2f} |")
        L.append("")
    ph = Path(chk) / "posthoc_gain_by_time.csv" if chk else None
    if ph is not None and ph.exists():
        T = pd.read_csv(ph)
        L += ["## Post hoc: where the unlagged gain sits (not pre-registered)", "",
              "Held-out per-step log-loss change of B + ρ (unlagged) vs B, from the same forward chaining (folds 1..). Negative = "
              "ρ helps; *share* = that cell's part of the total change.", "",
              "| scoring | bout | position | steps | mean Δll × 10³ | share of gain | mean ρ0 | mean ρ60 |",
              "|---|---|---|---:|---:|---:|---:|---:|"]
        for r in T.itertuples():
            pos = r.to_end if isinstance(getattr(r, "to_end", None), str) else r.el
            L.append(f"| {r.scoring} | {r.end} | {pos} | {r.steps} | {1e3 * r.mean_d_ll:+.2f} | {r.share_of_gain:.2f} | "
                     f"{r.rho0:+.3f} | {r.rho60:+.3f} |")
        L.append("")
    L += ["## Reading and limits", "",
          "- A held-out gain is predictive information, not a mechanism. Ripples and REM may both follow an unmeasured state, "
          "such as cortical slow-wave dynamics or temperature.",
          "- Ripple counts are not memory processing: replay content can fall while ripples rise (sleep deprivation; Giri et al. "
          "2024, https://pubmed.ncbi.nlm.nih.gov/38867049/).",
          "- **L = 0 vs L = 60 s:**",
          "  - A gain only at L = 0 may be the transition already under way: the last minute before REM is intermediate "
          "sleep, and naps R3 reports a lower relative last-minute rate. It is not read as readiness.",
          "  - Whether a last-minute term carries held-out information within long bouts was not tested here: T1 is a "
          "10-min window and K7's rho is cumulative since the last REM.",
          "  - Only L = 60 s speaks to slower REM readiness.",
          "- **ALL vs KEPT:** the kept events drop theta- and REM-flagged events, which shares information with the scorer's REM "
          "call. So the ALL version decides.",
          "- **Animals:** SF11 has no test steps, because its ripples end on 09-02, inside the six train-only blocks. The rule is "
          "therefore n − 1 of 5.",
          "- **T2 was pre-registered as description unless T1 held at L = 60 s.** Its gain is therefore read only through the "
          "Amendment-2 checks; C is strongly collinear with P.", ""]
    p = rd / f"ephys_spikes_rem_ripple_model_{COHORT}.md"
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    write_json(rd / f"run_manifest_rem_ripple_model_{COHORT}.json", dict(name="rem_ripple_model", run_dir=str(out), git=meta.get("git"),
                                                                         checks_dir=str(chk) if chk else None, report=str(p),
                                                                         figure=str(fig)))
    print(f"report {p}")
    return p


# ------------------------------------------------------------------ selftest
def selftest():
    from sleep_model import counter_starts
    ok = True
    rng = np.random.default_rng(0)
    st = np.array([W] * 50 + [N] * 400 + [W] * 30 + [N] * 200 + [R] * 60 + [N] * 300 + [0] * 40 + [N] * 120 + [W] * 900 + [N] * 1000, np.int8)
    # (1) unit events (one per NREM second, rbar = 60 / min) reproduce P_tw600_k0 at every bout start
    ev = (st == N).astype(int)
    cs = ripple_counter(st, ev)
    ps = counter_starts(st, "disc", 600.0, 0.0)
    e1 = max(abs(cs[a][0] / 60.0 - ps[a]) for a in ps)
    print(f"{'PASS' if e1 < 1e-9 else 'FAIL'} ripple counter with unit events == P_tw600_k0 (max diff {e1:.2e})")
    ok &= e1 < 1e-9
    # (2) reset index = end of the last REM
    r_ok = cs[740][1] == 740 and cs[50][1] == 0 and cs[480][1] == 0 and cs[1080][1] == 740
    print(f"{'PASS' if r_ok else 'FAIL'} reset index {[(a, cs[a][1]) for a in sorted(cs)]}")
    ok &= r_ok
    # (3) windows exclude the step itself and everything after t - L
    t_off = np.array([400, 1000])
    x0, x1 = window(t_off, 60)
    w_ok = list(x1) == [340, 940] and list(x0) == [0, 340]
    print(f"{'PASS' if w_ok else 'FAIL'} window [x0, x1) = {list(zip(x0, x1))}")
    ok &= w_ok
    # (4) causal block rate uses only seconds before tau and needs MIN_NORM_S
    T = np.arange(4000, dtype=float)
    e = rng.poisson(1.0, 4000)
    cE = np.r_[0, np.cumsum(e)]
    rt = block_rate(T, cE, np.array([100.0, 2500.0, 1e9]))
    exp = [np.nan, cE[2500] / (2500 / 60), cE[4000] / (4000 / 60)]
    b_ok = np.isnan(rt[0]) and np.allclose(rt[1:], exp[1:])
    print(f"{'PASS' if b_ok else 'FAIL'} causal block rate {rt}")
    ok &= b_ok
    # (5) a planted ripple-rate effect is recovered in the features: a step after a ripple-rich window gets the higher rr
    cov = np.ones(len(st), bool)
    ea = np.zeros(len(st), int)
    ea[50:250] = (rng.random(200) < 0.5)                     # ripple-rich start of the first bout
    A = {"cov": cov, "blk": np.zeros(len(st), np.int32), "ea": ea, "ek": ea, "sw": np.where(st == N, 1.0, np.nan).astype(np.float32)}
    rc = {"state": st, "start": pd.Timestamp("2026-09-05 00:00:00"), "record_id": 0}
    BT = block_tables([rc], {0: A})
    BT[0]["T"] = BT[0]["T"] - 1e7                             # pretend the block has a long past (causal normaliser available)
    g = pd.DataFrame({"bout_start": [740, 740], "elapsed": [0, 290]})
    Fe = record_features(g, rc, A, BT)
    f_ok = Fe.ka0.iloc[0] > 0 and Fe.ka0.iloc[1] == 0 and Fe.rra0.iloc[0] > Fe.rra0.iloc[1] and np.isfinite(Fe.Ca).all()
    print(f"{'PASS' if f_ok else 'FAIL'} features (k, rr at L = 0): {Fe[['ka0', 'rra0', 'Ca']].round(3).to_dict('list')}")
    ok &= f_ok
    # (6) Amendment-2 pieces: a shift keeps the total and the masked support; lag 0 equals the T2 counter; dbar of a constant
    msk = st == N
    sh = circular_shift(ea, msk, 0.5)
    s_ok = sh.sum() == ea[msk].sum() and not sh[~msk].any() and not np.array_equal(sh[msk], ea[msk])
    P_ = np.expm1(np.zeros(2)) + np.array([0.0, 290 / 60])          # P at the two steps (bout after a REM: P0 = 0)
    Kf = check_features(g, rc, A, BT, P_)
    l_ok = np.allclose(np.exp(Kf.rho0) * (P_ + 0.5) - 0.5, Fe.Ca.to_numpy()) and np.allclose(Kf.dbar.dropna(), 0.0, atol=1e-9)
    print(f"{'PASS' if s_ok and l_ok else 'FAIL'} shift keeps total ({sh.sum()} = {ea[msk].sum()}); rho0 <-> T2 counter; "
          f"dbar {Kf.dbar.round(3).tolist()}")
    ok &= s_ok and l_ok
    print("SELFTEST " + ("PASS" if ok else "FAIL"))
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["run", "checks", "posthoc", "followup", "report"])
    ap.add_argument("--scorings", nargs="+", default=["final", "pass2med"], choices=["final", "pass2med"])
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--smoke", action="store_true", help="FINAL only, B vs B+rra60 on 4 folds (timing / plumbing)")
    ap.add_argument("--features-only", action="store_true", help="build features and subset counts, no fit")
    ap.add_argument("--run", default=None, help="run dir (report: required; run / checks: reuse a folder)")
    ap.add_argument("--checks", default=None, help="report: the Amendment-2 checks run dir")
    ap.add_argument("--swr-root", default=SWR_ROOT)
    ap.add_argument("--sleep-root", default=SLEEP_ROOT)
    ap.add_argument("--quality", default=str(report_dir(COHORT) / f"ephys_spikes_swr_quality_{COHORT}.csv"))
    ap.add_argument("--review", default=str(report_dir(COHORT) / f"ephys_spikes_sleep_review_{COHORT}.csv"))
    ap.add_argument("--cohort-yaml", default=str(REPO / f"cohorts/{COHORT}.yaml"))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    if a.cmd == "run":
        run(a)
    elif a.cmd == "checks":
        checks(a)
    elif a.cmd == "posthoc":
        posthoc(a)
    elif a.cmd == "followup":
        followup(a)
    elif a.cmd == "report":
        report(Path(a.run), Path(a.checks) if a.checks else None)


if __name__ == "__main__":
    main()
