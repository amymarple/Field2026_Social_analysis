r"""Default WISER smoother for cohort 2026c, chosen by a pre-registered rule (the step after the failure audit).

Plan: implementation_plan/2026-10-02-wiser-default-smoother.md (approved by the user 2026-10-02, "do 1st first").
Report (full Definitions section): results/<cohort>/wiser_baseline/reports/wiser_baseline_default_smoother_<cohort>.md

Candidates (WISER inches, fix times aligned on the IMU clock by the animal's tau*; tuned values of the smoothing pilot):
  B1      library centred 7-sample coordinate-wise median
  B2      robust constant-velocity Kalman + RTS, per-fix noise from anchors_used
  B2p     B2' = B2 + AR(1) measurement drift; delivered track = the drift-free position p
  V1      B2' + zero-velocity pseudo-measurement in IMU-still seconds
  V2      B2' with the process noise switched by the IMU state
  V2b     NEW: V2's state switching and multipliers on the B2 base, no drift state, no retuning
  V2b_rt  NEW, secondary (not eligible): V2b with the multipliers retuned on the pilot's tuning night only
Every IMU-dependent method falls back to B2 at fixes whose aligned second fails the IMU QC.

Still metrics on the failure audit's certified >= 30-s segments (truth = median raw fix); safety S1 held-out error on
moving fixes vs B2 (schemes (a) runs of 4-8, (s) every 5th fix), S2 1-s speed p50/p95 within +-10 % of B2 on
IMU-locomoting and WISER-fast seconds, S3 rain >= 12-in excursions <= raw, S4 zero jumps, S5 onset/offset lag (reported).
Rule: eliminate S1-S4 failures, lowest calm-dry fake path, ties within 5 % -> the simpler method.

Inputs (all read-only): the failure audit's bulk run (tracks/, imu_seconds/, speeds/, tables/), the WISER fix caches
(library speed), and - only for the +1 h IMU QC mask of the V2b_rt tuning objective - the make_imu npz through the
audit's own loaders. Existing scripts are imported, never modified.

Usage:
  python wiser/scripts/analyze_wiser_default_smoother.py --cohort 2026c [--workers 5]
  python wiser/scripts/analyze_wiser_default_smoother.py --report-only <run_dir>   # re-aggregate / re-render
  python wiser/scripts/analyze_wiser_default_smoother.py --selftest                # synthetic data, no field data
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "wiser" / "src"))
sys.path.insert(0, str(REPO / "wiser" / "scripts"))
sys.path.append(str(REPO / "ephys"))
import output_paths  # noqa: E402  (wiser shim -> common/output_paths.py)
import analyze_imu_wiser_calibration as C  # noqa: E402  (helpers; unmodified)
import analyze_wiser_imu_smoothing as P  # noqa: E402  (B1/B2/B2'/V1/V2 Kalman core, schemes, bootstrap; unmodified)
import analyze_wiser_failure_audit as FA  # noqa: E402  (segment scoring, block bootstrap, loaders; unmodified)

DIRECTION = "wiser_baseline"
NAME = "wiser_default_smoother"
STEM = f"{DIRECTION}_default_smoother"
PLAN = "implementation_plan/2026-10-02-wiser-default-smoother.md"
SAVED = ["raw", "B1", "B2", "B2p", "B2pb", "V1", "V2"]        # audit tracks as saved (V1/V2 = in-filter B2' fallback)
NEW = ["V1", "V2", "V2b", "V2b_rt"]                           # deployable forms built here (B2 fallback)
CANDS = ["B1", "B2", "B2p", "V1", "V2", "V2b"]
SECONDARY = ["V2b_rt"]
SCORED = CANDS + SECONDARY
SPEED_METHODS = ["raw", "B1", "B2", "B2p", "V1", "V2", "V2b", "V2b_rt", "V1_audit", "V2_audit", "V2b_infilter", "V2b_rt_infilter"]
INFILTER = {"V2b": "V2b_infilter", "V2b_rt": "V2b_rt_infilter"}     # amendment 1: in-filter forms (sensitivity only)
STILL_METHODS = ["raw", "B1", "B2", "B2p", "V1", "V2", "V2b", "V2b_rt", "V1_audit", "V2_audit"]
S1_KF = ["B2", "B2p", "V1", "V2", "V2b", "V2b_rt"]
S1_METHODS = ["B1", "B2", "B2p", "V1", "V2", "V2b", "V2b_rt", "B2pb", "V1pb", "V2pb"]
LABEL = {"raw": "raw fixes", "B1": "B1 median-7", "B2": "B2 robust CV", "B2p": "B2′ (+drift, p)", "B2pb": "B2′ p+b",
         "V1": "V1 ZUPT", "V2": "V2 IMU-q (B2′ base)", "V2b": "V2b IMU-q (B2 base)", "V2b_rt": "V2b_rt (retuned)",
         "V1_audit": "V1, audit form", "V2_audit": "V2, audit form", "V1pb": "V1 p+b", "V2pb": "V2 p+b",
         "V2b_infilter": "V2b in-filter (no splice)", "V2b_rt_infilter": "V2b_rt in-filter (no splice)"}
COL = {"raw": "#7f7f7f", "B1": "#1f77b4", "B2": "#2ca02c", "B2p": "#d62728", "V1": "#9467bd", "V2": "#8c564b",
       "V2b": "#e377c2", "V2b_rt": "#17becf", "V1_audit": "#c5b0d5", "V2_audit": "#c49c94", "V2b_infilter": "#f7b6d2",
       "V2b_rt_infilter": "#9edae5"}
S1_EDGES = np.arange(0.0, 20.0 + 1e-9, 0.005)     # held-out error histogram (in); larger values fall into the last bin (medians ~4 in unaffected)


def log_to(fh, msg: str) -> None:
    print(msg, flush=True)
    if fh is not None:
        fh.write(msg + "\n")
        fh.flush()


# ====================================================================================================== config / context
def load_cfg(cohort: str, path: str | None = None) -> dict:
    cp = Path(path) if path else REPO / "wiser" / "configs" / f"wiser_default_smoother_{cohort}.json"
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    cfg["_path"] = str(cp)
    cfg["_cohort"] = cohort
    return cfg


def load_acfg(cfg: dict) -> dict:
    return FA.load_cfg(cfg["_cohort"], str(REPO / cfg["audit_config"]))


_CTX: dict = {}


def _ctx(acfg: dict) -> dict:
    if acfg["_path"] not in _CTX:
        _CTX[acfg["_path"]] = FA.context(acfg)
    return _CTX[acfg["_path"]]


def kf_specs(tuned: dict, mult_rt) -> dict:
    """Kalman configurations (kf_run dicts) of every Kalman method from the pilot's tuned block."""
    b2, b2p = tuned["B2"], tuned["B2p"]
    base_b2 = {"q": float(b2["q"]), "mrej": float(b2["mrej"])}
    base_p = {"q": float(b2p["q"]), "tb": float(b2p["tb"]), "sb": float(b2p["sb"]), "mrej": float(b2["mrej"])}
    mult = tuple(float(x) for x in tuned["V2"]["mult"])
    spec = {"B2": dict(base_b2), "B2p": dict(base_p), "V1": {**base_p, "sv": float(tuned["V1"]["sv"])},
            "V2": {**base_p, "mult": mult}, "V2b": {**base_b2, "mult": mult}}
    spec["V2b_rt"] = {**base_b2, "mult": tuple(float(x) for x in (mult_rt if mult_rt is not None else mult))}
    return spec


# ====================================================================================================== small helpers
def lookup(secs: np.ndarray, vals: np.ndarray, q: np.ndarray, fill):
    """vals at the integer seconds q for a contiguous second axis secs; fill outside."""
    q = np.asarray(q, np.int64)
    out = np.full(len(q), fill, dtype=np.asarray(vals).dtype)
    if not len(secs):
        return out
    i = q - int(secs[0])
    inb = (i >= 0) & (i < len(secs))
    out[inb] = np.asarray(vals)[i[inb]]
    return out


def second_speeds(t_s: np.ndarray, p: np.ndarray, secs: np.ndarray, max_gap: float) -> np.ndarray:
    """1-s centred speed at the centre of each second s: |p~(s + 1) - p~(s)| / 1 s (in/s); p~ = linear interpolation,
    defined only inside inter-fix gaps <= max_gap. t_s and secs on the same absolute clock (s)."""
    g = np.r_[secs, secs[-1] + 1].astype(np.float64) if len(secs) else np.zeros(0)
    q = FA.interp_track(t_s, p, g, max_gap)
    return np.hypot(*(q[1:] - q[:-1]).T)


def hidden_masks(n: int, seed_a: int, seed_s: int, s_every: int) -> dict:
    """(a): the pilot's runs of 4-8 hidden fixes separated by 1-47 visible ones; (s): every s_every-th fix hidden alone,
    random phase (V5's scheme (s))."""
    r = int(np.random.default_rng(seed_s).integers(s_every))
    return {"a": P.hide_runs(n, np.random.default_rng(seed_a)), "s": (np.arange(n) % s_every) == r}


def transition_events(state: np.ndarray, secs: np.ndarray, lo: float, hi: float, s5: dict) -> list:
    """The audit's onset/offset events (FA.onset_offset event selection) from per-second IMU states (0 unusable,
    1 still, 2 active, 3 locomoting): a still run [a, b) of >= still_run_min_s seconds followed (onset) / preceded
    (offset) within loco_search_s by a locomoting second, no still-run or unusable second in between, and the run
    >= edge_s from the window edges. Times relative to lo (s): ra = run start, rb = run end, rl = loco second."""
    stt = np.asarray(state, int)
    minr, look, edge = int(s5["still_run_min_s"]), int(s5["loco_search_s"]), float(s5["edge_s"])
    hi_s = (hi - lo) / 1000.0
    rel = lambda i: (secs[i] * 1000.0 - lo) / 1000.0  # noqa: E731
    long_runs = [(a, b) for a, b in C.true_runs(stt == 1) if b - a >= minr]
    in_long = np.zeros(len(stt), bool)
    for a, b in long_runs:
        in_long[a:b] = True
    ev = []
    for a, b in long_runs:
        sl = None
        for j in range(b, min(b + look, len(stt))):
            if stt[j] == 0 or in_long[j]:
                break
            if stt[j] == 3:
                sl = j
                break
        sl2 = None
        for j in range(a - 1, max(a - look, 0) - 1, -1):
            if stt[j] == 0 or in_long[j]:
                break
            if stt[j] == 3:
                sl2 = j
                break
        for kind, s_loco in (("onset", sl), ("offset", sl2)):
            if s_loco is None:
                continue
            ra = rel(a)
            rb = rel(b) if b < len(secs) else rel(b - 1) + 1.0
            if not (edge <= ra and rb <= hi_s - edge):
                continue
            ev.append({"kind": kind, "ra": ra, "rb": rb, "rl": rel(s_loco), "still_run_s": int(b - a)})
    return ev


def event_lag(t: np.ndarray, p: np.ndarray, ev: dict, s5: dict) -> tuple[float, float]:
    """S5 lag of one track at one event (s). Onset: first 0.25-s grid time g in [rb - pre, rl + post] with the 1-s centred
    speed >= thr, minus rb; offset: last such g in [rl - pre, ra + post] plus one grid step, minus ra. Second value = the
    same time relative to the locomoting second (onset: - rl; offset: - (rl + 1)). NaN when the speed never reaches thr."""
    thr, step, mg = float(s5["speed_thr_inps"]), float(s5["grid_s"]), float(s5["max_gap_s"])
    if ev["kind"] == "onset":
        g = np.arange(ev["rb"] - s5["onset_pre_s"], ev["rl"] + s5["onset_post_s"] + 1e-9, step)
    else:
        g = np.arange(ev["rl"] - s5["offset_pre_s"], ev["ra"] + s5["offset_post_s"] + 1e-9, step)
    i0, i1 = np.searchsorted(t, [g[0] - 2.0, g[-1] + 2.0])
    tt, pp = t[i0:i1], p[i0:i1]
    v = np.hypot(*(FA.interp_track(tt, pp, g + 0.5, mg) - FA.interp_track(tt, pp, g - 0.5, mg)).T)
    j = np.flatnonzero(np.nan_to_num(v, nan=-1.0) >= thr)
    if not len(j):
        return np.nan, np.nan
    if ev["kind"] == "onset":
        return float(g[j[0]] - ev["rb"]), float(g[j[0]] - ev["rl"])
    te = float(g[j[-1]] + step)
    return te - ev["ra"], te - (ev["rl"] + 1.0)


def hist_boot_q(vals: np.ndarray, blk: np.ndarray, cnt: np.ndarray, edges: np.ndarray, qs) -> np.ndarray:
    """Block-bootstrap quantiles from per-block histograms: rows = cnt rows (row 0 = point estimate on the histogram),
    columns = qs (fractions). vals (n,), blk (n,) block codes 0..K-1, cnt (B, K) resampling counts."""
    from scipy import sparse
    nb = len(edges) - 1
    K = cnt.shape[1]
    j = np.clip(np.searchsorted(edges, vals, side="right") - 1, 0, nb - 1)
    H = sparse.csr_matrix((np.ones(len(vals)), (blk.astype(np.int64), j)), shape=(K, nb))   # duplicate entries are summed
    W = np.asarray((H.T @ cnt.T).T)          # (B, nb): sparse product, cost = non-empty (block, bin) cells x B
    return np.column_stack([FA.hist_q(W, edges, q) for q in qs])


def block_codes(*cols) -> tuple[np.ndarray, int]:
    """Integer code 0..K-1 per row for the unique combinations of the given columns (e.g. animal, period, block)."""
    df = pd.DataFrame({f"c{i}": np.asarray(c) for i, c in enumerate(cols)})
    codes = df.groupby(list(df.columns), sort=True).ngroup().to_numpy(np.int64)
    return codes, (int(codes.max()) + 1 if len(codes) else 0)


def wmedian_boot(x: np.ndarray, blk: np.ndarray, cnt: np.ndarray) -> np.ndarray:
    """Weighted median of x under each row of block counts (exact; for small n)."""
    o = np.argsort(x, kind="stable")
    xs, bs = x[o], blk[o]
    W = cnt[:, bs]
    cw = np.cumsum(W, axis=1)
    half = cw[:, -1:] / 2.0
    j = (cw < half).sum(axis=1)
    out = xs[np.minimum(j, len(xs) - 1)]
    out[cw[:, -1] <= 0] = np.nan
    return out


# ====================================================================================================== decision rule
def simplicity_key(m: str, cplx: dict) -> tuple:
    c = cplx[m]
    return (bool(c["drift"]), int(c["n_params"]), bool(c["imu"]))


def choose(cands: list, fake: dict, cplx: dict, tie_tol: float) -> tuple[str, list]:
    """Lowest fake path; every candidate within (1 + tie_tol) of it is tied; the simplest of the tied set wins."""
    fmin = min(fake[m] for m in cands)
    tied = [m for m in cands if fake[m] <= (1.0 + tie_tol) * fmin]
    return sorted(tied, key=lambda m: (simplicity_key(m, cplx), fake[m]))[0], tied


def decide(tab: dict, eligible: list, cplx: dict, tie_tol: float) -> dict:
    """tab[m] = {"S1": bool, "S2": bool, "S3": bool, "S4": bool, "fake_calm": float, "fake_rain": float} (True = pass).
    Pre-registered rule: eliminate failures of S1-S4; lowest calm-dry fake path; ties within tie_tol -> simpler. No
    survivor -> the eligible method(s) with the fewest failed criteria, then the same choice."""
    crit = ["S1", "S2", "S3", "S4"]
    nfail = {m: sum(not tab[m][c] for c in crit) for m in tab}
    surv = [m for m in eligible if nfail[m] == 0]
    out = {"n_failed": nfail, "survivors": surv, "eliminated": {m: [c for c in crit if not tab[m][c]] for m in tab}}
    if surv:
        pool, out["no_survivor_fallback"] = surv, False
    else:
        k = min(nfail[m] for m in eligible)
        pool, out["no_survivor_fallback"] = [m for m in eligible if nfail[m] == k], True
    out["pool"] = pool
    out["default"], out["tied_calm"] = choose(pool, {m: tab[m]["fake_calm"] for m in pool}, cplx, tie_tol)
    out["rain_choice"], out["tied_rain"] = choose(pool, {m: tab[m]["fake_rain"] for m in pool}, cplx, tie_tol)
    out["secondary_would_win"] = {}
    for m in [x for x in tab if x not in eligible]:          # the same rule with the secondary method made eligible
        out["secondary_would_win"][m] = bool(decide(tab, list(eligible) + [m], cplx, tie_tol)["default"] == m)
    return out


# ====================================================================================================== V2b_rt retuning
def retune(cfg: dict, acfg: dict, ctx: dict, fh=None) -> dict:
    """V2b multipliers retuned with the smoothing pilot's own objective on its tuning night; also reproduces the pilot's
    tuning-night B2 median and V2 optimum as a check of the reconstruction."""
    rc = cfg["retune"]
    tz = ctx["tz"]
    pk = rc["period"]
    pp = acfg["periods"][pk]
    lo, hi = C.to_ms(pp["start"], tz), C.to_ms(pp["end"], tz)
    run = Path(cfg["audit_run"])
    tr = []
    info = []
    for i, a in enumerate(acfg["animals"]):
        with np.load(run / "tracks" / f"{a}_{pk}.npz") as z:
            sel = (z["t_ms"] >= lo) & (z["t_ms"] < hi)
            t_al = z["t_al_ms"][sel].astype(np.float64)
            zz = z["raw"][sel].astype(np.float64)
            A = z["anchors"][sel].astype(np.float64)
        ps = pd.read_csv(run / "imu_seconds" / f"{a}_{pk}.csv.gz")
        secs = ps["sec"].to_numpy(np.int64)
        st_mid, st_at = P.step_states(t_al, secs, ps["state"].to_numpy(np.int8))
        fsec = np.floor(t_al / 1000.0).astype(np.int64)
        ok_true = lookup(secs, ps["ok"].to_numpy(bool), fsec, False)
        sid = C.resolve_tag(ctx["ids"], a, lo, hi)
        vf, vu = C.tag_window(ctx["ids"], sid, a, (lo + hi) / 2)
        sess = FA.sessions_for(acfg, ctx, a, lo + 3.6e6 - 60_000, hi + 3.6e6 + 60_000)
        imu = FA.load_imu(sess, lo + 3.6e6, hi + 3.6e6, tz)
        pss = FA.per_second_states(imu, ctx, a, lo + 3.6e6, hi + 3.6e6, vf, vu)
        ok_shift = lookup(pss["sec"].to_numpy(np.int64) - 3600, pss["ok"].to_numpy(bool), fsec, False)
        h = P.hide_runs(len(t_al), np.random.default_rng(int(rc["pilot_seed"]) + i))
        sc = h & (A >= 7) & ok_true & ok_shift
        tr.append({"t": (t_al - lo) / 1000.0, "z": zz, "A": A, "st_mid": st_mid, "st_at": st_at, "h": h, "sc": sc})
        info.append({"animal": a, "n_fix": int(len(t_al)), "n_scored": int(sc.sum()), "ok_true_s": int(ps["ok"].sum()),
                     "ok_shift_s": int(pss["ok"].sum()), "shift_sessions": ";".join(s["session"] for s in sess)})
        log_to(fh, f"retune {a}: {len(t_al):,} fixes, scored {int(sc.sum()):,}, shifted-IMU ok {int(pss['ok'].sum())} s")

    def evaluate(cfgs: list) -> list:
        errs = [[] for _ in cfgs]
        for d in tr:
            r2 = P.r2_from_anchors(d["A"], ctx["table"])
            Pk, Bk, _ = P.kf_run(d["t"], d["z"], r2, [~d["h"]], [d["st_mid"]], [d["st_at"]], [{**c, "vis": 0} for c in cfgs])
            for k in range(len(cfgs)):
                errs[k].append(np.hypot(*(d["z"][d["sc"]] - (Pk[k] + Bk[k])[d["sc"]]).T))
        out = []
        for c, e in zip(cfgs, errs):
            e = np.concatenate(e)
            out.append({"med": float(np.median(e)), "rmse": float(np.sqrt(np.mean(e ** 2))), "n": int(len(e))})
        return out

    spec = kf_specs(ctx["tuned"], None)
    g = rc["grid"]
    mults = [(1.0, ms, ma, ml) for ms in g["m_still"] for ma in g["m_active"] for ml in g["m_loco"]]
    cfgs = [("B2", None, spec["B2"])]
    cfgs += [("V2_on_B2p", m, {**spec["B2p"], "mult": m}) for m in mults]
    cfgs += [("V2b_on_B2", m, {**spec["B2"], "mult": m}) for m in mults]
    res = evaluate([c[2] for c in cfgs])
    rows = [{"family": f, "m_still": (m[1] if m else np.nan), "m_active": (m[2] if m else np.nan),
             "m_loco": (m[3] if m else np.nan), **r} for (f, m, _), r in zip(cfgs, res)]
    G = pd.DataFrame(rows)

    def best(fam):
        d = G[G.family == fam].copy()
        d["_k"] = d["med"].round(4)
        return d.sort_values(["_k", "rmse"]).iloc[0]
    b2 = G[G.family == "B2"].iloc[0]
    bv2 = best("V2_on_B2p")
    bv2b = best("V2b_on_B2")
    mult_rt = [1.0, float(bv2b.m_still), float(bv2b.m_active), float(bv2b.m_loco)]
    edge = {"m_still": float(bv2b.m_still) in (min(g["m_still"]), max(g["m_still"])),
            "m_active": float(bv2b.m_active) in (min(g["m_active"]), max(g["m_active"])),
            "m_loco": float(bv2b.m_loco) in (min(g["m_loco"]), max(g["m_loco"]))}
    tol = float(rc["repro_tol_in"])
    repro = {"B2_med": float(b2.med), "B2_med_pilot": float(rc["pilot_B2_med"]),
             "V2_best_mult": [1.0, float(bv2.m_still), float(bv2.m_active), float(bv2.m_loco)], "V2_best_med": float(bv2.med),
             "V2_mult_pilot": rc["pilot_V2_mult"], "V2_med_pilot": float(rc["pilot_V2_med"])}
    repro["ok"] = bool(abs(repro["B2_med"] - repro["B2_med_pilot"]) <= tol and abs(repro["V2_best_med"] - repro["V2_med_pilot"]) <= tol
                       and np.allclose(repro["V2_best_mult"], repro["V2_mult_pilot"]))
    out = {"mult_rt": mult_rt, "med_rt": float(bv2b.med), "rmse_rt": float(bv2b.rmse), "med_B2": float(b2.med),
           "gain_vs_B2": float(1.0 - bv2b.med / b2.med), "edge": edge, "repro": repro, "info": info, "grid": G}
    log_to(fh, f"retune: V2b_rt multipliers {mult_rt} (med {bv2b.med:.4f} vs B2 {b2.med:.4f} in); edges {edge}; pilot reproduction "
               f"B2 {repro['B2_med']:.4f} (pilot {repro['B2_med_pilot']:.4f}), V2 {repro['V2_best_mult']} {repro['V2_best_med']:.4f} "
               f"(pilot {repro['V2_mult_pilot']} {repro['V2_med_pilot']:.4f}) -> {'OK' if repro['ok'] else 'MISMATCH'}")
    return out


# ====================================================================================================== one animal-period
_SEG: dict = {}


def _segments(run: Path) -> pd.DataFrame:
    k = str(run)
    if k not in _SEG:
        S = pd.read_csv(run / "tables" / "segments.csv")
        for c in ("primary", "scored", "ge30"):
            S[c] = S[c].astype(bool)
        _SEG[k] = S[S.primary & S.scored].reset_index(drop=True)
    return _SEG[k]


def process(job: dict) -> dict:
    """Everything for one animal and one period; big arrays are written into the run dir."""
    t_job = time.time()
    cfg, acfg, animal, pkey, out = job["cfg"], job["acfg"], job["animal"], job["pkey"], Path(job["out"])
    if P.HAVE_NUMBA:
        P.set_num_threads(int(job["threads"]))
    ctx = _ctx(acfg)
    tz = ctx["tz"]
    pp = acfg["periods"][pkey]
    lo, hi = C.to_ms(pp["start"], tz), C.to_ms(pp["end"], tz)
    hi_s = (hi - lo) / 1000.0
    run = Path(cfg["audit_run"])
    mc, trim = acfg["metrics"], float(acfg["still"]["trim_s"])
    s2, s4, s5 = cfg["s2"], cfg["s4"], cfg["s5"]
    blk_s = float(cfg["bootstrap"]["block_s"])
    base = {"animal": animal, "period": pkey, "set": pp["set"], "kind": pp["kind"]}
    # ---- saved audit tracks + IMU seconds
    with np.load(run / "tracks" / f"{animal}_{pkey}.npz") as z:
        t_ms = z["t_ms"].astype(np.int64)
        t_al = z["t_al_ms"].astype(np.float64)
        A = z["anchors"].astype(np.float64)
        trk = {m: z[m].astype(np.float64) for m in SAVED}
    trk["V1_audit"], trk["V2_audit"] = trk.pop("V1"), trk.pop("V2")
    n = len(t_al)
    t = (t_al - lo) / 1000.0
    t_abs = t_al / 1000.0
    zraw = trk["raw"]
    ps = pd.read_csv(run / "imu_seconds" / f"{animal}_{pkey}.csv.gz")
    secs = ps["sec"].to_numpy(np.int64)
    assert np.all(np.diff(secs) == 1), "imu_seconds not contiguous"
    state = ps["state"].to_numpy(np.int8)
    ok_s = ps["ok"].to_numpy(bool)
    still_s = ps["still"].to_numpy(bool) & ok_s
    fsec = np.floor(t_al / 1000.0).astype(np.int64)
    ok_f = lookup(secs, ok_s, fsec, False)
    still_f = lookup(secs, still_s, fsec, False)
    st_f = lookup(secs, state, fsec, np.int8(0))
    st_mid, st_at = P.step_states(t_al, secs, state)
    r2 = P.r2_from_anchors(A, ctx["table"])
    spec = kf_specs(ctx["tuned"], job["mult_rt"])
    inwin = (t >= 0) & (t < hi_s)
    # ---- full-data tracks of the new methods (+ V1/V2 rebuilt from the saved in-window states as a check)
    keys = ["V2b", "V2b_rt", "V1", "V2"]
    Pk, _, _ = P.kf_run(t, zraw, r2, [np.ones(n, bool)], [st_mid], [st_at], [spec[k] for k in keys])
    trk["V2b"], trk["V2b_rt"] = Pk[0], Pk[1]
    trk["V2b_infilter"], trk["V2b_rt_infilter"] = Pk[0], Pk[1]
    core = (t >= 60.0) & (t < hi_s - 60.0)
    rep = {**base}
    for k, chk in (("V1", Pk[2]), ("V2", Pk[3])):
        d = np.hypot(*(chk - trk[f"{k}_audit"]).T)
        rep[f"{k}_maxdiff_core_in"] = float(np.max(d[core])) if core.any() else np.nan
        rep[f"{k}_p999diff_win_in"] = float(np.percentile(d[inwin], 99.9)) if inwin.any() else np.nan
        rep[f"{k}_maxdiff_win_in"] = float(np.max(d[inwin])) if inwin.any() else np.nan
    # ---- deployable forms: the method at IMU-QC-ok fixes, B2 elsewhere
    for m, src in (("V1", "V1_audit"), ("V2", "V2_audit"), ("V2b", "V2b"), ("V2b_rt", "V2b_rt")):
        trk[m] = np.where(ok_f[:, None], trk[src], trk["B2"])
    (out / "tracks").mkdir(exist_ok=True)
    np.savez_compressed(out / "tracks" / f"{animal}_{pkey}.npz", t_ms=t_ms, t_al_ms=t_al, imu_ok=ok_f,
                        **{m: trk[m].astype(np.float32) for m in NEW}, V2b_infilter=Pk[0].astype(np.float32),
                        V2b_rt_infilter=Pk[1].astype(np.float32))
    # amendment 1: size of the splice (deployable vs in-filter at IMU-failed fixes) and of the steps it creates
    for m in ("V2b", "V2b_rt", "V1", "V2"):
        src = trk[INFILTER.get(m, f"{m}_audit")]
        dd = np.hypot(*(trk[m] - src).T)
        sel = inwin & ~ok_f
        rep[f"{m}_splice_diff_max_in"] = float(dd[sel].max()) if sel.any() else 0.0
        rep[f"{m}_splice_diff_p99_in"] = float(np.percentile(dd[sel], 99)) if sel.any() else 0.0
        bnd = np.flatnonzero((ok_f[1:] != ok_f[:-1]) & inwin[1:] & inwin[:-1])
        st_dep = np.hypot(*(trk[m][bnd + 1] - trk[m][bnd]).T)
        st_src = np.hypot(*(src[bnd + 1] - src[bnd]).T)
        rep[f"{m}_splice_n_boundaries"] = int(len(bnd))
        rep[f"{m}_splice_extra_step_gt5in"] = int(((st_dep - st_src) > 5.0).sum())
        rep[f"{m}_splice_extra_step_max_in"] = float((st_dep - st_src).max()) if len(bnd) else 0.0
    fb = {**base, "n_fix_win": int(inwin.sum()), "n_fix_win_imu_fail": int((inwin & ~ok_f).sum())}
    # ---- still segments: score the new methods with the audit's own scorer
    Sj = _segments(run)
    Sj = Sj[(Sj.animal == animal) & (Sj.period == pkey)]
    mrows, frows, evrows, jrows, reprows = [], [], [], [], []
    spd = {m: [] for m in NEW}
    spd_idx = {m: [] for m in NEW}
    seg_ids = []
    n_bad = 0
    for k, r in enumerate(Sj.itertuples()):
        ts, te = (r.t0_ms - lo) / 1000.0 + trim, (r.t1_ms - lo) / 1000.0 - trim
        i0, i1 = np.searchsorted(t, [ts, te])
        n_bad += int((i1 - i0) != r.n_fix)
        truth = np.array([r.truth_x, r.truth_y])
        meths = list(NEW) + (["raw", "B2", "B2p", "V2_audit"] if k % 20 == 0 else [])
        sub = {m: trk[m][i0:i1] for m in meths}
        res, evs, jps, speeds = FA.score_segment(t[i0:i1], sub, truth, ts, te, mc, meths)
        for m in meths:
            row = {"seg_id": r.seg_id, "method": m, **{kk: v for kk, v in res[m].items() if not kk.startswith("_")}}
            (mrows if m in NEW else reprows).append(row)
        fr = {"seg_id": np.repeat(r.seg_id, i1 - i0), "t_al_ms": (lo + t[i0:i1] * 1000).round(1),
              "imu_ok": ok_f[i0:i1]}
        for m in NEW:
            fr[f"r_{m}"] = np.hypot(*(sub[m] - truth).T).round(3)
        frows.append(pd.DataFrame(fr))
        for e in evs:
            if e["method"] in NEW:
                evrows.append({"seg_id": r.seg_id, **base, "ge30": bool(r.ge30), "method": e["method"],
                               "start_ms": lo + (e["c0"] - mc["roll_short_s"] / 2) * 1000, "end_ms": lo + (e["c1"] + mc["roll_short_s"] / 2) * 1000,
                               "dur_s": e["dur_s"], "size_in": e["size_in"], "zone": r.zone, "anchors_med": r.anchors_med})
        for m, kk in jps:
            if m in NEW:
                jrows.append({"seg_id": r.seg_id, **base, "ge30": bool(r.ge30), "method": m, "t_ms": lo + 0.5 * (t[i0 + kk] + t[i0 + kk + 1]) * 1000,
                              "size_in": float(np.hypot(*(sub[m][kk + 1] - sub[m][kk])))})
        seg_ids.append(r.seg_id)
        for m in NEW:
            spd[m].append(speeds[m])
            spd_idx[m].append(np.full(len(speeds[m]), len(seg_ids) - 1, np.int32))
    if seg_ids:
        (out / "speeds").mkdir(exist_ok=True)
        np.savez_compressed(out / "speeds" / f"{animal}_{pkey}.npz", seg_ids=np.array(seg_ids),
                            **{m: np.concatenate(spd[m]) for m in NEW}, **{f"idx_{m}": np.concatenate(spd_idx[m]) for m in NEW})
    rep["n_seg"] = int(len(Sj))
    rep["n_seg_fixcount_mismatch"] = n_bad
    # ---- S2 per-second speeds + analysis mask + WISER library speed
    sid = C.resolve_tag(ctx["ids"], animal, lo, hi)
    vf, vu = C.tag_window(ctx["ids"], sid, animal, (lo + hi) / 2)
    mid = (secs + 0.5) * 1000.0
    amask = ((mid >= lo) & (mid < hi) & ~C.in_any(mid, ctx["handling"]) & ~C.in_any(mid, ctx["silences"])
             & (mid >= vf) & (mid < vu))
    fc = pd.read_csv(Path(cfg["fix_cache_root"]) / pkey / f"{animal}.csv.gz", usecols=["t_ms", "valid", "speed_inps_smooth"])
    marg = float(acfg["fix_cache"]["margin_s"]) * 1000
    fc = fc[(fc.t_ms >= lo - marg) & (fc.t_ms < hi + marg)]
    rep["cache_rows_match"] = bool(len(fc) == n and np.array_equal(np.sort(fc.t_ms.to_numpy(np.int64)), t_ms))
    fv = fc[fc["valid"].astype(bool)]
    tau = float(ctx["taus"][animal])
    s_fix = np.floor((fv["t_ms"].to_numpy(np.float64) - tau * 1000.0) / 1000.0).astype(np.int64)
    u = pd.Series(fv["speed_inps_smooth"].to_numpy(float)).groupby(s_fix).median().reindex(secs).to_numpy(float)
    vsec = {m: second_speeds(t_abs, trk[m], secs, float(s2["max_gap_s"])).astype(np.float32) for m in SPEED_METHODS}
    (out / "seconds").mkdir(exist_ok=True)
    np.savez_compressed(out / "seconds" / f"{animal}_{pkey}.npz", sec=secs, state=state, ok=ok_s, mask=amask, u=u.astype(np.float32),
                        **{f"v_{m}": v for m, v in vsec.items()})
    fast = amask & (np.nan_to_num(u) >= float(s2["wiser_speed_thr_inps"]))
    fb.update({"n_sec_mask": int(amask.sum()), "n_sec_mask_imu_fail": int((amask & ~ok_s).sum()),
               "n_sec_fast": int(fast.sum()), "n_sec_fast_imu_fail": int((fast & ~ok_s).sum()),
               "n_sec_loco": int((state == 3).sum())})
    # ---- S4 motion-side jumps (whole window)
    j4 = []
    for m in SPEED_METHODS:
        jk = FA.find_jumps(t, trk[m], float(s4["jump_in"]), float(s4["jump_dt_s"]))
        jk = jk[inwin[jk] & inwin[np.minimum(jk + 1, n - 1)]]
        tm = 0.5 * (t[jk] + t[jk + 1])
        sj = np.floor((tm * 1000.0 + lo) / 1000.0).astype(np.int64)
        j4.append({**base, "method": m, "jumps_win": int(len(jk)), "jumps_mask": int(lookup(secs, amask, sj, False).sum()),
                   "jumps_imu_ok": int(lookup(secs, ok_s, sj, False).sum()),
                   "jumps_mask_imu_fail": int((lookup(secs, amask, sj, False) & ~lookup(secs, ok_s, sj, False)).sum())})
    # ---- S5 onset / offset lags
    erows = []
    for e in transition_events(state, secs, lo, hi, s5):
        anchor = e["rb"] if e["kind"] == "onset" else e["ra"]
        row = {**base, **e, "block": int(anchor // blk_s)}
        for m in SPEED_METHODS:
            row[f"lag_{m}"], row[f"lagloco_{m}"] = event_lag(t, trk[m], e, s5)
        erows.append(row)
    # ---- S1 held-out (schemes (a), (s))
    pi, ai = int(job["pi"]), int(job["ai"])
    s1 = cfg["s1"]
    seed = int(s1["seed"])
    hid = hidden_masks(n, seed + 100 * pi + ai, seed + 50_000 + 100 * pi + ai, int(s1["s_every"]))
    cfgs = [{**spec[k], "vis": vi} for vi in (0, 1) for k in S1_KF]
    Ph, Bh, _ = P.kf_run(t, zraw, r2, [~hid["a"], ~hid["s"]], [st_mid], [st_at], cfgs)
    s1out = {}
    for vi, sch in enumerate(("a", "s")):
        h = hid[sch]
        sc = h & inwin & (A >= float(s1["min_anchors"])) & ok_f
        idx = np.flatnonzero(sc)
        pred = {}
        for jj, k in enumerate(S1_KF):
            c = vi * len(S1_KF) + jj
            pred[k] = Ph[c][sc]
            if k in ("B2p", "V1", "V2"):
                pred[{"B2p": "B2pb", "V1": "V1pb", "V2": "V2pb"}[k]] = (Ph[c] + Bh[c])[sc]
        pred["B1"] = P.b1_predict(t[~h], zraw[~h], t[sc])
        d = {"i": idx.astype(np.int32), "block": np.floor(t[sc] / blk_s).astype(np.int32), "still": still_f[sc],
             "moving": ok_f[sc] & ~still_f[sc], "loco": st_f[sc] == 3, "anchors": A[sc].astype(np.int8)}
        for m in S1_METHODS:
            d[f"e_{m}"] = np.hypot(*(zraw[sc] - pred[m]).T).astype(np.float32)
        s1out[sch] = d
    (out / "s1").mkdir(exist_ok=True)
    np.savez_compressed(out / "s1" / f"{animal}_{pkey}.npz", **{f"{s}__{k}": v for s, d in s1out.items() for k, v in d.items()})
    rep["runtime_s"] = round(time.time() - t_job, 1)
    return {"rep": rep, "fb": fb, "metrics": pd.DataFrame(mrows), "fixes": pd.concat(frows, ignore_index=True) if frows else pd.DataFrame(),
            "events": pd.DataFrame(evrows), "jumps": pd.DataFrame(jrows), "repro_still": pd.DataFrame(reprows), "s4": pd.DataFrame(j4),
            "s5": pd.DataFrame(erows)}


def _process_safe(job: dict) -> dict:
    try:
        return process(job)
    except Exception as e:  # noqa: BLE001
        import traceback
        return {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc(), "animal": job["animal"], "pkey": job["pkey"]}


# ====================================================================================================== compute run
def run_compute(cfg: dict, workers: int) -> Path:
    t0 = time.time()
    acfg = load_acfg(cfg)
    out = output_paths.run_dir(NAME, cfg["_cohort"])
    (out / "tables").mkdir(exist_ok=True)
    fh = open(out / "log.txt", "w", encoding="utf-8")
    log_to(fh, f"run dir {out}; git {C.git_commit()}; config {cfg['_path']}; audit run {cfg['audit_run']}")
    ctx = _ctx(acfg)
    if P.HAVE_NUMBA:
        P.set_num_threads(16)
    rt = retune(cfg, acfg, ctx, fh)
    rt["grid"].to_csv(out / "tables" / "v2b_rt_tuning_grid.csv", index=False)
    pd.DataFrame(rt["info"]).to_csv(out / "tables" / "v2b_rt_tuning_tracks.csv", index=False)
    rtj = {k: v for k, v in rt.items() if k not in ("grid", "info")}
    (out / "tables" / "v2b_rt_tuning.json").write_text(json.dumps(rtj, indent=2, default=float), encoding="utf-8")
    log_to(fh, f"retune done ({time.time() - t0:.0f} s)")
    threads = max(1, 24 // max(1, workers))
    jobs = [{"cfg": cfg, "acfg": acfg, "animal": a, "pkey": pk, "out": str(out), "mult_rt": rt["mult_rt"], "pi": pi, "ai": ai,
             "threads": threads} for pi, pk in enumerate(acfg["periods"]) for ai, a in enumerate(acfg["animals"])]
    res = []
    with ProcessPoolExecutor(max_workers=max(1, workers)) as ex:
        for r in ex.map(_process_safe, jobs):
            if "error" in r:
                log_to(fh, f"ERROR {r['animal']} {r['pkey']}: {r['error']}\n{r['trace']}")
                continue
            rp = r["rep"]
            log_to(fh, f"{rp['animal']} {rp['period']}: {rp['n_seg']} segments, V2 rebuild max diff (core) {rp['V2_maxdiff_core_in']:.4f} in, "
                       f"cache rows match {rp['cache_rows_match']}, {rp['runtime_s']} s")
            res.append(r)
    tb = out / "tables"
    pd.DataFrame([r["rep"] for r in res]).to_csv(tb / "reproduction_tracks.csv", index=False)
    pd.DataFrame([r["fb"] for r in res]).to_csv(tb / "fallback_share.csv", index=False)
    for key, f in (("metrics", "still_metrics_new.csv.gz"), ("fixes", "still_fixes_new.csv.gz"), ("events", "still_events_new.csv"),
                   ("jumps", "still_jumps_new.csv"), ("repro_still", "reproduction_still_sample.csv"), ("s4", "s4_motion_jumps.csv"),
                   ("s5", "s5_events.csv.gz")):
        parts = [r[key] for r in res if r[key] is not None and len(r[key])]
        (pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()).to_csv(tb / f, index=False)
    prov = {"config": Path(cfg["_path"]).relative_to(REPO).as_posix(), "audit_config": cfg["audit_config"], "audit_run": cfg["audit_run"],
            "smoothing_config": cfg["smoothing_config"], "fix_cache_root": cfg["fix_cache_root"], "git_commit": C.git_commit(),
            "audit_run_manifest": json.loads((Path(cfg["audit_run"]) / "run_manifest.json").read_text(encoding="utf-8")),
            "tuned_used": {k: ctx["tuned"][k] for k in ("B2", "B2p", "V1", "V2", "huber_k", "gate2", "n_irls")},
            "v2b_rt_mult": rt["mult_rt"], "runtime_compute_s": round(time.time() - t0, 1)}
    (out / "input_provenance.json").write_text(json.dumps(prov, indent=2, default=str), encoding="utf-8")
    log_to(fh, f"compute done ({time.time() - t0:.0f} s)")
    fh.close()
    return out


# ====================================================================================================== aggregation
def load_speeds_multi(d: Path, S: pd.DataFrame, methods: list, rename: dict | None = None) -> dict:
    """method -> (row index into S, speed) from <d>/*.npz (the audit's speeds format)."""
    rename = rename or {}
    pos = pd.Series(np.arange(len(S)), index=S["seg_id"])
    acc = {}
    for f in sorted(d.glob("*.npz")):
        with np.load(f) as z:
            ids = pos.reindex(z["seg_ids"]).to_numpy()
            for m in methods:
                if m in z.files:
                    mm = rename.get(m, m)
                    a, v = acc.setdefault(mm, ([], []))
                    a.append(ids[z[f"idx_{m}"]].astype(np.int64))
                    v.append(z[m].astype(np.float32))
    return {m: (np.concatenate(a), np.concatenate(v)) for m, (a, v) in acc.items()}


def aggregate(out: Path, cfg: dict, fh=None) -> dict:
    t0 = time.time()
    acfg = load_acfg(cfg)
    run = Path(cfg["audit_run"])
    tb = out / "tables"
    bc = cfg["bootstrap"]
    nb = int(bc["n_boot"])
    rng = np.random.default_rng(int(bc["seed"]))          # still bootstrap; S1 / S2 / S5 get their own streams below
    rng_s1, rng_s2, rng_s5 = (np.random.default_rng(int(bc["seed"]) + k) for k in (1, 2, 3))
    sets = ["calm", "rain"]
    A: dict = {"cfg": cfg}
    # ---------------- still tables (audit rows for the saved methods + the new methods)
    T = FA.load_tables(run)
    S = T["S"]
    for c in ("primary", "scored", "ge30"):
        S[c] = S[c].astype(bool)
    Mo = T["M"].copy()
    Mo["method"] = Mo["method"].replace({"V1": "V1_audit", "V2": "V2_audit"})
    Fo = T["F"].rename(columns={"r_V1": "r_V1_audit", "r_V2": "r_V2_audit"})
    Mn = pd.read_csv(tb / "still_metrics_new.csv.gz")
    Fn = pd.read_csv(tb / "still_fixes_new.csv.gz")
    Fo["_k"] = Fo.groupby("seg_id").cumcount()
    Fn["_k"] = Fn.groupby("seg_id").cumcount()
    F = Fo.merge(Fn, on=["seg_id", "_k"], how="left", suffixes=("", "_new"))
    chk = {"F_rows": int(len(F)), "F_new_rows": int(len(Fn)), "F_unmatched": int(F["r_V2b"].isna().sum()),
           "F_t_maxdiff_ms": float((F["t_al_ms"] - F["t_al_ms_new"]).abs().max())}
    M = pd.concat([Mo, Mn], ignore_index=True)
    SP = load_speeds_multi(run / "speeds", S, ["raw", "B1", "B2", "B2p", "B2pb", "V1", "V2"], {"V1": "V1_audit", "V2": "V2_audit"})
    SP.update(load_speeds_multi(out / "speeds", S, NEW))
    Sp30 = S[S.primary & S.scored & S.ge30]
    A["checks"] = chk
    # still-segment reproduction sample (re-derived raw / B2 / B2' / V2_audit vs the saved audit rows)
    R = pd.read_csv(tb / "reproduction_still_sample.csv")
    Rm = R.merge(Mo, on=["seg_id", "method"], suffixes=("", "_saved"))
    rep_still = {}
    for col in ("rms_in", "drift10_in", "path_in_per_min", "crazy_n", "jumps", "speed_p95"):
        rep_still[col] = float(np.nanmax(np.abs(Rm[col] - Rm[f"{col}_saved"]))) if len(Rm) else np.nan
    rep_still["n_rows"] = int(len(Rm))
    A["repro_still"] = rep_still
    # pooled / set x kind summaries (Sall = the full S table: the speed index refers to its rows)
    pooled = pd.DataFrame([{"set": s, **FA.still_summary(Sp30[Sp30.set == s], M, F, SP, m, S)} for s in sets for m in STILL_METHODS])
    setkind = pd.DataFrame([{"set": s, "kind": k, **FA.still_summary(Sp30[(Sp30.set == s) & (Sp30.kind == k)], M, F, SP, m, S)}
                            for s in sets for k in ("day", "night") for m in STILL_METHODS])
    pooled.to_csv(tb / "still_pooled.csv", index=False)
    setkind.to_csv(tb / "still_setkind.csv", index=False)
    # audit group_table speed quantiles used positions relative to the grouped frame (finding; pooled table unaffected)
    g = Sp30[Sp30.set == "calm"]
    A["audit_speed_index_check"] = {"pooled_correct": FA.still_summary(g, M, F, SP, "raw", S)["speed_p95"],
                                    "group_table_style": FA.still_summary(g, M, F, SP, "raw", Sp30)["speed_p95"]}
    # block bootstrap of the still metrics (paired draws per set); reused from an earlier aggregation of the same run when
    # complete (deterministic: its own random stream, seed = bootstrap.seed)
    bsp = tb / "still_bootstrap.csv"
    brow = []
    if bsp.exists():
        BS0 = pd.read_csv(bsp)
        if set(BS0.method) == set(STILL_METHODS) and set(BS0.set) == set(sets):
            log_to(fh, f"still bootstrap reused from {bsp.name}")
            sets_todo = []
        else:
            sets_todo = sets
    else:
        sets_todo = sets
    for s in sets_todo:
        gs = Sp30[Sp30.set == s]
        st = {}
        cnt = None
        for m in STILL_METHODS:
            Ab = FA.block_arrays(gs, M, F, SP, m, S)
            if cnt is None:
                cnt = FA.boot_counts(Ab["K"], nb, rng)
                K = Ab["K"]
            x = FA.set_stats(Ab, cnt)
            st[m] = {k: x[k] for k in ("path_rate", "rms", "drift_med", "crazy_rate", "jump_rate", "speed_p95")}
            del Ab
        for m in STILL_METHODS:
            for k in st[m]:
                e, lo_, hi_ = FA.ci(st[m][k])
                with np.errstate(divide="ignore", invalid="ignore"):
                    r_, rlo, rhi = FA.ci(st[m][k] / st["B2"][k])
                    d_, dlo, dhi = FA.ci(st[m][k] - st["raw"][k])
                brow.append({"set": s, "method": m, "metric": k, "value": e, "lo": lo_, "hi": hi_, "ratio_vs_B2": r_, "ratio_lo": rlo,
                             "ratio_hi": rhi, "diff_vs_raw": d_, "diff_lo": dlo, "diff_hi": dhi, "n_blocks": K})
    if sets_todo:
        BS = pd.DataFrame(brow)
        BS.to_csv(bsp, index=False)
    else:
        BS = BS0
    log_to(fh, f"still tables done ({time.time() - t0:.0f} s)")
    # ---------------- S1
    rows = []
    E = []
    for f in sorted((out / "s1").glob("*.npz")):
        a, pk = f.stem.split("_", 1)
        with np.load(f) as z:
            for sch in ("a", "s"):
                d = {k.split("__", 1)[1]: z[k] for k in z.files if k.startswith(sch + "__")}
                dd = pd.DataFrame(d)
                dd.insert(0, "scheme", sch)
                dd.insert(0, "period", pk)
                dd.insert(0, "animal", a)
                E.append(dd)
    E = pd.concat(E, ignore_index=True)
    E["set"] = E["period"].map({k: v["set"] for k, v in acfg["periods"].items()})
    E["kind"] = E["period"].map({k: v["kind"] for k, v in acfg["periods"].items()})
    for s in sets:
        for sch in ("a", "s"):
            d0 = E[(E.set == s) & (E.scheme == sch)]
            for sub in ("moving", "all", "still", "loco"):
                d = d0 if sub == "all" else d0[d0[sub].astype(bool)]
                if not len(d):
                    continue
                med_ref = float(np.median(d["e_B2"]))
                if sub == "moving":
                    blk, K = block_codes(d["animal"], d["period"], d["block"])
                    cnt = FA.boot_counts(K, nb, rng_s1)
                    qref = hist_boot_q(d["e_B2"].to_numpy(float), blk, cnt, S1_EDGES, [0.5])[:, 0]
                for m in S1_METHODS:
                    med = float(np.median(d[f"e_{m}"]))
                    row = {"set": s, "scheme": sch, "subset": sub, "method": m, "n": int(len(d)), "med": med, "med_B2": med_ref,
                           "D": 1.0 - med / med_ref, "rmse": float(np.sqrt(np.mean(d[f"e_{m}"].astype(float) ** 2))),
                           "rmse_B2": float(np.sqrt(np.mean(d["e_B2"].astype(float) ** 2)))}
                    if sub == "moving":
                        qm = hist_boot_q(d[f"e_{m}"].to_numpy(float), blk, cnt, S1_EDGES, [0.5])[:, 0]
                        b = 1.0 - qm[1:] / qref[1:]
                        row.update({"D_lo": float(np.nanpercentile(b, 2.5)), "D_hi": float(np.nanpercentile(b, 97.5)), "n_blocks": K})
                    rows.append(row)
    S1 = pd.DataFrame(rows)
    S1.to_csv(tb / "s1_heldout.csv", index=False)
    A["s1_n"] = E.groupby(["set", "scheme"]).size().to_dict()
    del E
    log_to(fh, f"S1 done ({time.time() - t0:.0f} s)")
    # ---------------- S2
    secs = []
    for f in sorted((out / "seconds").glob("*.npz")):
        a, pk = f.stem.split("_", 1)
        with np.load(f) as z:
            d = pd.DataFrame({k: z[k] for k in z.files})
        d.insert(0, "period", pk)
        d.insert(0, "animal", a)
        secs.append(d)
    SE = pd.concat(secs, ignore_index=True)
    SE["set"] = SE["period"].map({k: v["set"] for k, v in acfg["periods"].items()})
    SE["kind"] = SE["period"].map({k: v["kind"] for k, v in acfg["periods"].items()})
    lo_map = {k: C.to_ms(v["start"], acfg["tz"]) for k, v in acfg["periods"].items()}
    SE["block"] = ((SE["sec"] * 1000.0 - SE["period"].map(lo_map)) // (float(bc["block_s"]) * 1000.0)).astype(np.int64)
    s2 = cfg["s2"]
    thr = float(s2["wiser_speed_thr_inps"])
    vcols = [f"v_{m}" for m in SPEED_METHODS]
    SE["paired"] = np.isfinite(SE[vcols].to_numpy(float)).all(axis=1)
    subsets = {"loco": SE["state"] == 3, "wfast": SE["mask"].astype(bool) & (SE["u"].fillna(-1) >= thr)}
    rows = []
    cdf = {}
    for s in sets:
        for subn, cond in subsets.items():
            d = SE[(SE.set == s) & cond & SE["paired"]]
            blk, K = block_codes(d["animal"], d["period"], d["block"])
            cnt = FA.boot_counts(K, nb, rng_s2)
            qb = {m: hist_boot_q(d[f"v_{m}"].to_numpy(float), blk, cnt, FA.SPEED_EDGES, [0.5, 0.95]) for m in SPEED_METHODS}
            ex = {m: np.percentile(d[f"v_{m}"].to_numpy(float), [50, 95]) for m in SPEED_METHODS}
            imu_fail = float((~d["ok"].astype(bool)).mean())
            for m in SPEED_METHODS:
                row = {"set": s, "subset": subn, "method": m, "n_sec": int(len(d)), "n_blocks": K, "imu_fail_share": imu_fail,
                       "p50": float(ex[m][0]), "p95": float(ex[m][1]), "p50_B2": float(ex["B2"][0]), "p95_B2": float(ex["B2"][1])}
                for qi, qn in enumerate(("p50", "p95")):
                    row[f"d_{qn}"] = float(ex[m][qi] / ex["B2"][qi] - 1.0)
                    b = qb[m][1:, qi] / qb["B2"][1:, qi] - 1.0
                    row[f"d_{qn}_lo"] = float(np.nanpercentile(b, 2.5))
                    row[f"d_{qn}_hi"] = float(np.nanpercentile(b, 97.5))
                rows.append(row)
            if subn == "loco":
                cdf[s] = {m: np.sort(d[f"v_{m}"].to_numpy(float))[:: max(1, len(d) // 4000)] for m in SPEED_METHODS}
    S2 = pd.DataFrame(rows)
    S2.to_csv(tb / "s2_speed.csv", index=False)
    A["s2_cdf"] = cdf
    del SE
    log_to(fh, f"S2 done ({time.time() - t0:.0f} s)")
    # ---------------- S3 / S4
    S3 = pooled[["set", "method", "crazy_n", "crazy_per_h", "still_h"]].copy()
    raw_n = S3.set_index(["set", "method"])["crazy_n"]
    S3["raw_n"] = [raw_n[(s, "raw")] for s in S3["set"]]
    b3 = BS[BS.metric == "crazy_rate"][["set", "method", "diff_vs_raw", "diff_lo", "diff_hi"]]
    S3 = S3.merge(b3, on=["set", "method"], how="left")
    S3.to_csv(tb / "s3_excursions.csv", index=False)
    J4 = pd.read_csv(tb / "s4_motion_jumps.csv")
    S4m = J4.groupby(["set", "kind", "method"])[["jumps_win", "jumps_mask", "jumps_imu_ok", "jumps_mask_imu_fail"]].sum().reset_index()
    S4m.to_csv(tb / "s4_motion_jumps_by_set.csv", index=False)
    # night motion-side reproduction vs the audit's motion_jumps (IMU-ok seconds)
    MJ = T["MJ"]
    rep_mj = {}
    if len(MJ):
        aud = MJ[MJ.sec_ok.astype(bool)].groupby("method").size()
        mine = J4[J4.kind == "night"].groupby("method")["jumps_imu_ok"].sum()
        for m in ("raw", "B1", "B2p"):
            rep_mj[m] = {"audit": int(aud.get(m, 0)), "here": int(mine.get(m, 0))}
    A["repro_motion_jumps"] = rep_mj
    # ---------------- S5
    EV = pd.read_csv(tb / "s5_events.csv.gz")
    rows = []
    for s in sets:
        for kind in ("onset", "offset"):
            for pk_kind in ("all", "night", "day"):
                d = EV[(EV.set == s) & (EV.kind == kind)]
                if pk_kind != "all":
                    d = d[d["period"].str.startswith(pk_kind)]
                if not len(d):
                    continue
                blk, K = block_codes(d["animal"], d["period"], d["block"])
                cnt = FA.boot_counts(K, nb, rng_s5)
                for m in SPEED_METHODS:
                    lag = d[f"lag_{m}"].to_numpy(float)
                    row = {"set": s, "kind": kind, "periods": pk_kind, "method": m, "n_events": int(len(d)),
                           "n_defined": int(np.isfinite(lag).sum()), "lag_med": float(np.nanmedian(lag)) if np.isfinite(lag).any() else np.nan,
                           "lagloco_med": float(np.nanmedian(d[f"lagloco_{m}"])) if d[f"lagloco_{m}"].notna().any() else np.nan}
                    dl = lag - d["lag_B2"].to_numpy(float)
                    ok = np.isfinite(dl)
                    row["n_paired"] = int(ok.sum())
                    if ok.sum() >= 5:
                        wb = wmedian_boot(dl[ok], blk[ok], cnt)
                        row.update({"dlag_med": float(np.median(dl[ok])), "dlag_lo": float(np.nanpercentile(wb[1:], 2.5)),
                                    "dlag_hi": float(np.nanpercentile(wb[1:], 97.5))})
                    rows.append(row)
    S5 = pd.DataFrame(rows)
    S5.to_csv(tb / "s5_lags.csv", index=False)
    # event-count reproduction vs the audit's nights
    ON = T["ON"]
    rep_ev = {}
    if len(ON):
        aud = ON[ON.method == "raw"].groupby(["kind"]).size()
        mine = EV[EV.period.str.startswith("night")].groupby("kind").size()
        rep_ev = {k: {"audit": int(aud.get(k, 0)), "here": int(mine.get(k, 0))} for k in ("onset", "offset")}
    A["repro_events"] = rep_ev
    # ---------------- decision
    s1c, s2c = cfg["s1"], cfg["s2"]
    tab = {}
    detail = {}
    for m in SCORED:
        d1 = S1[(S1.subset == "moving") & (S1.method == m)]
        s1_worst = d1.loc[d1.D.idxmin()] if len(d1) else None
        s1_pass = bool(len(d1) == 4 and (d1.D >= -float(s1c["max_loss"])).all()) if m != "B2" else True
        d2 = S2[S2.method == m]
        dd = pd.concat([d2[["set", "subset", "d_p50"]].rename(columns={"d_p50": "d"}).assign(q="p50"),
                        d2[["set", "subset", "d_p95"]].rename(columns={"d_p95": "d"}).assign(q="p95")], ignore_index=True)
        s2_worst = dd.loc[dd.d.abs().idxmax()] if len(dd) else None
        s2_pass = bool(len(dd) == 8 and (dd.d.abs() <= float(s2c["max_rel"])).all()) if m != "B2" else True
        r3 = S3[(S3.set == "rain") & (S3.method == m)].iloc[0]
        s3_pass = bool(r3.crazy_n <= r3.raw_n)
        s3_ci_pass = bool(not (r3.diff_lo > 0))
        still_j = int(pooled[(pooled.method == m)]["jumps_n"].sum())
        mot_j = int(J4[J4.method == m]["jumps_mask"].sum())
        s4_pass = bool(still_j == 0 and mot_j == 0)
        fc = float(pooled[(pooled.set == "calm") & (pooled.method == m)].path_in_per_min.iloc[0])
        fr = float(pooled[(pooled.set == "rain") & (pooled.method == m)].path_in_per_min.iloc[0])
        tab[m] = {"S1": s1_pass, "S2": s2_pass, "S3": s3_pass, "S4": s4_pass, "fake_calm": fc, "fake_rain": fr}
        d1pb = S1[(S1.subset == "moving") & (S1.method == {"B2p": "B2pb", "V1": "V1pb", "V2": "V2pb"}.get(m, m))]
        detail[m] = {"S1_worst": (None if s1_worst is None else {"set": s1_worst.set, "scheme": s1_worst.scheme, "D": float(s1_worst.D),
                                                                   "D_lo": float(s1_worst.get("D_lo", np.nan)), "D_hi": float(s1_worst.get("D_hi", np.nan))}),
                     "S1_pb_pass": bool(len(d1pb) == 4 and (d1pb.D >= -float(s1c["max_loss"])).all()) if m != "B2" else True,
                     "S2_worst": (None if s2_worst is None else {"set": s2_worst.set, "subset": s2_worst.subset, "q": s2_worst.q, "d": float(s2_worst.d)}),
                     "S3_rain_n": int(r3.crazy_n), "S3_raw_n": int(r3.raw_n), "S3_ci_pass": s3_ci_pass,
                     "S3_diff_ci": [float(r3.diff_vs_raw), float(r3.diff_lo), float(r3.diff_hi)],
                     "S4_still_jumps": still_j, "S4_motion_jumps": mot_j}
    cplx = {k: v for k, v in cfg["complexity"].items() if not k.startswith("_")}
    dec = decide(tab, list(cfg["candidates"]), cplx, float(cfg["tie_tol"]))
    # sensitivities (never the decision)
    tab_s3 = {m: {**tab[m], "S3": detail[m]["S3_ci_pass"]} for m in tab}
    tab_pb = {m: {**tab[m], "S1": detail[m]["S1_pb_pass"]} for m in tab}
    tab_inf = {m: dict(tab[m]) for m in tab}           # amendment 1: V2b / V2b_rt without the B2 splice
    for m, mi in INFILTER.items():
        d2 = S2[S2.method == mi]
        tab_inf[m]["S2"] = bool(len(d2) == 4 and (d2[["d_p50", "d_p95"]].abs() <= float(s2c["max_rel"])).all().all())
        tab_inf[m]["S4"] = bool(detail[m]["S4_still_jumps"] == 0 and int(J4[J4.method == mi]["jumps_mask"].sum()) == 0)
        detail[m]["infilter"] = {"S2": tab_inf[m]["S2"], "S4": tab_inf[m]["S4"], "motion_jumps": int(J4[J4.method == mi]["jumps_mask"].sum()),
                                 "S2_worst": float(pd.concat([d2.d_p50, d2.d_p95]).abs().max()) if len(d2) else np.nan}
    sens = {"S3_by_CI": decide(tab_s3, list(cfg["candidates"]), cplx, float(cfg["tie_tol"])),
            "S1_with_p_plus_b": decide(tab_pb, list(cfg["candidates"]), cplx, float(cfg["tie_tol"])),
            "V2b_in_filter": decide(tab_inf, list(cfg["candidates"]), cplx, float(cfg["tie_tol"]))}
    fbs = pd.read_csv(tb / "fallback_share.csv")
    fb = {}
    for s in sets:
        g2 = fbs[fbs.set == s]
        fb[s] = {"fix_share": float(g2.n_fix_win_imu_fail.sum() / g2.n_fix_win.sum()),
                 "mask_sec_share": float(g2.n_sec_mask_imu_fail.sum() / g2.n_sec_mask.sum()),
                 "fast_sec_share": float(g2.n_sec_fast_imu_fail.sum() / max(g2.n_sec_fast.sum(), 1))}
    rt = json.loads((tb / "v2b_rt_tuning.json").read_text(encoding="utf-8"))
    rep_tr = pd.read_csv(tb / "reproduction_tracks.csv")
    A.update({"S": S, "Sp30": Sp30, "M": M, "F": F, "SP": SP, "pooled": pooled, "setkind": setkind, "BS": BS, "S1": S1, "S2": S2,
              "S3": S3, "S4m": S4m, "J4": J4, "S5": S5, "EV": EV, "tab": tab, "detail": detail, "dec": dec, "sens": sens, "fb": fb,
              "rt": rt, "rep_tr": rep_tr, "acfg": acfg, "events_new": pd.read_csv(tb / "still_events_new.csv") if (tb / "still_events_new.csv").stat().st_size > 5 else pd.DataFrame(),
              "E_audit": T["E"]})
    summ = {"decision": {k: v for k, v in dec.items()}, "table": tab, "detail": detail, "sensitivity": sens, "fallback_share": fb,
            "checks": chk, "repro_still": rep_still, "repro_motion_jumps": rep_mj, "repro_events": rep_ev,
            "audit_speed_index_check": A["audit_speed_index_check"], "retune": rt, "runtime_aggregate_s": round(time.time() - t0, 1)}
    (out / "summary.json").write_text(json.dumps(summ, indent=2, default=_jd), encoding="utf-8")
    A["summary"] = summ
    log_to(fh, f"aggregation done ({time.time() - t0:.0f} s); default = {dec['default']} "
               f"({'NO-SURVIVOR FALLBACK' if dec['no_survivor_fallback'] else 'survivor'}); survivors {dec['survivors']}; "
               f"rain choice {dec['rain_choice']}")
    return A


def _jd(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


# ====================================================================================================== figures
def make_figures(A: dict, fdir: Path) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figs = {}
    cohort = A["cfg"]["_cohort"]
    ms = SCORED
    # ---- 1. decision overview
    fig, ax = plt.subplots(1, 3, figsize=(16, 5.2))
    pooled = A["pooled"]
    x = np.arange(len(ms))
    for k, (s, off) in enumerate((("calm", -0.2), ("rain", 0.2))):
        v = [float(pooled[(pooled.set == s) & (pooled.method == m)].path_in_per_min.iloc[0]) for m in ms]
        ax[0].bar(x + off, v, 0.38, color=[COL[m] for m in ms], alpha=1.0 if s == "calm" else 0.5, edgecolor="k", lw=0.5,
                  label=f"{s}{' (light)' if s == 'rain' else ''}")
    ax[0].set_yscale("log")
    ax[0].set_xticks(x)
    ax[0].set_xticklabels(ms, rotation=30)
    ax[0].set_ylabel("fake path during certified stillness (in/min, log)")
    ax[0].set_title("Still: fake path (calm dark, rain light)")
    S1 = A["S1"]
    mm = [m for m in ms if m != "B2"]
    for j, (s, sch, mk) in enumerate((("calm", "a", "o"), ("calm", "s", "s"), ("rain", "a", "^"), ("rain", "s", "D"))):
        for i, m in enumerate(mm):
            r = S1[(S1.subset == "moving") & (S1.method == m) & (S1.set == s) & (S1.scheme == sch)]
            if not len(r):
                continue
            r = r.iloc[0]
            ax[1].errorbar(i + (j - 1.5) * 0.15, 100 * r.D, yerr=[[100 * (r.D - r.D_lo)], [100 * (r.D_hi - r.D)]], fmt=mk, color=COL[m],
                           ms=5, capsize=2, label=f"{s} ({sch})" if i == 0 else None)
    ax[1].axhline(-2, color="r", ls="--", lw=1)
    ax[1].axhline(0, color="k", lw=0.5)
    ax[1].set_xticks(np.arange(len(mm)))
    ax[1].set_xticklabels(mm, rotation=30)
    ax[1].set_ylabel("S1: Δ median held-out error vs B2 on moving fixes (%)")
    ax[1].set_title("S1 (fail below −2 %)")
    ax[1].legend(fontsize=7)
    S2 = A["S2"]
    for j, (s, sub, q, mk) in enumerate((("calm", "loco", "p50", "o"), ("calm", "loco", "p95", "s"), ("rain", "loco", "p50", "^"),
                                         ("rain", "loco", "p95", "D"), ("calm", "wfast", "p50", "<"), ("calm", "wfast", "p95", ">"),
                                         ("rain", "wfast", "p50", "v"), ("rain", "wfast", "p95", "P"))):
        for i, m in enumerate(mm):
            r = S2[(S2.method == m) & (S2.set == s) & (S2.subset == sub)]
            if not len(r):
                continue
            r = r.iloc[0]
            ax[2].errorbar(i + (j - 3.5) * 0.09, 100 * r[f"d_{q}"], yerr=[[100 * (r[f"d_{q}"] - r[f"d_{q}_lo"])], [100 * (r[f"d_{q}_hi"] - r[f"d_{q}"])]],
                           fmt=mk, color=COL[m], ms=4, capsize=1.5, label=f"{s} {sub} {q}" if i == 0 else None)
    ax[2].axhspan(-10, 10, color="g", alpha=0.08)
    ax[2].axhline(0, color="k", lw=0.5)
    ax[2].set_xticks(np.arange(len(mm)))
    ax[2].set_xticklabels(mm, rotation=30)
    ax[2].set_ylabel("S2: Δ 1-s speed quantile vs B2 (%)")
    ax[2].set_title("S2 (pass inside ±10 %)")
    ax[2].legend(fontsize=6, ncol=2)
    fig.suptitle(f"Default WISER smoother {cohort}: still benefit vs motion safety (95 % CIs: 10-min block bootstrap)")
    fig.tight_layout()
    f = f"{STEM}_decision_{cohort}.png"
    fig.savefig(fdir / f, dpi=130)
    plt.close(fig)
    figs["decision"] = f
    # ---- 2. speed CDFs on IMU-locomoting seconds
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.6), sharey=True)
    for k, s in enumerate(("calm", "rain")):
        cd = A["s2_cdf"].get(s, {})
        for m in ["raw", "B1", "B2", "B2p", "V1", "V2", "V2b", "V2b_rt"]:
            if m not in cd:
                continue
            v = cd[m]
            ax[k].plot(v, np.linspace(0, 1, len(v)), color=COL[m], lw=1.6 if m in ("B2", "V2b") else 1.0, label=LABEL[m])
        ax[k].set_xlim(0, 40)
        ax[k].set_xlabel("1-s centred speed on IMU-locomoting seconds (in/s)")
        ax[k].set_title(f"{s}")
        ax[k].grid(alpha=0.3)
    ax[0].set_ylabel("cumulative fraction")
    ax[1].legend(fontsize=8)
    fig.suptitle("S2: speed distributions while the IMU says the rat is locomoting")
    fig.tight_layout()
    f = f"{STEM}_speed_{cohort}.png"
    fig.savefig(fdir / f, dpi=130)
    plt.close(fig)
    figs["speed"] = f
    # ---- 3. S5 lags
    EV = A["EV"]
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))
    meths = ["B2", "B2p", "V1", "V2", "V2b", "V2b_rt"]
    for k, kind in enumerate(("onset", "offset")):
        d = EV[EV.kind == kind]
        data = [d[f"lag_{m}"].dropna().to_numpy() for m in meths]
        bp = ax[k].boxplot(data, showfliers=False, patch_artist=True)
        for patch, m in zip(bp["boxes"], meths):
            patch.set_facecolor(COL[m])
            patch.set_alpha(0.6)
        ax[k].set_xticks(np.arange(1, len(meths) + 1))
        ax[k].set_xticklabels(meths, rotation=30)
        ax[k].axhline(0, color="k", lw=0.5)
        ax[k].set_ylabel("lag (s)" + (": first speed ≥ 3 in/s − first non-still second" if kind == "onset" else ": last speed ≥ 3 in/s − first still second"))
        ax[k].set_title(f"S5 {kind} (all periods, n = {len(d)})")
    fig.tight_layout()
    f = f"{STEM}_lags_{cohort}.png"
    fig.savefig(fdir / f, dpi=130)
    plt.close(fig)
    figs["lags"] = f
    return figs


# ====================================================================================================== report
def _f(x, nd: int = 1) -> str:
    try:
        if x is None or not np.isfinite(float(x)):
            return "–"
    except (TypeError, ValueError):
        return str(x)
    return f"{float(x):,.{nd}f}"


def _p(x, nd: int = 1, sign: bool = True) -> str:
    try:
        if x is None or not np.isfinite(float(x)):
            return "–"
    except (TypeError, ValueError):
        return "–"
    return f"{100 * float(x):{'+' if sign else ''}.{nd}f} %"


def _pf(b: bool) -> str:
    return "pass" if b else "**FAIL**"


DEFINITIONS = r"""
## Definitions

All positions are WISER **inches in the unverified offset frame**; only distances and speeds (frame-invariant) are used.
Times are field-PC local (EDT). $k$ indexes the fixes of one tag; $\mathbf z_k$ = raw fix (in); $\hat{\mathbf p}^{(m)}_k$ =
method $m$'s position at fix $k$; $t_k=t_k^{\text{WISER}}-\tau^*$ = fix time aligned on the IMU clock ($\tau^*$ =
0.20 / 0.15 / 0.10 / 0.20 / 0.15 s for SF07 / 08 / 09 / 10 / 12); $s$ = an integer field-PC second.

### Candidate smoothers
B1: $\hat{\mathbf p}_k=\operatorname{med}_{j=k-3}^{k+3}\mathbf z_j$ (coordinate-wise). B2: per axis a constant-velocity state
$(p,v)$, $\mathbf x_k=F_k\mathbf x_{k-1}+\boldsymbol\eta_k$, $\mathrm{Cov}(\boldsymbol\eta_k)=q\begin{pmatrix}\Delta t^3/3&\Delta t^2/2\\\Delta t^2/2&\Delta t\end{pmatrix}$,
$z_k=p_k+\varepsilon_k$, $\varepsilon_k\sim\mathcal N(0,\sigma^2_{\mathrm{ax}}(A_k)/w_k)$ ($A_k$ = `anchors_used`, robust per-anchor SD of the pilot;
$w_k$ = χ² gate then two Huber IRLS passes, $k_H$ = 2.5), forward Kalman filter + RTS smoother; $q$ = 3 in²/s³.
B2′: adds $b_k=e^{-\Delta t/T_b}b_{k-1}+\xi_k$, $z_k=p_k+b_k+\varepsilon_k$ ($q$ = 1, $T_b$ = 15 s, $\sigma_b$ = 2.5 in); the delivered track is $p$.
V1: B2′ plus the pseudo-measurement $0=v_k+\epsilon$, $\epsilon\sim\mathcal N(0,0.25^2)$ (in/s)² at fixes in IMU-still seconds.
V2: B2′ with $q_k=m_{c(k)}\,q$, $c(k)$ = IMU class of the second containing $(t_{k-1}+t_k)/2$, $(m_0,m_{\text{still}},m_{\text{active}},m_{\text{loco}})$ = (1, 0.01, 0.3, 10).
**V2b:** the same switching and multipliers on B2 ($q_k=m_{c(k)}\cdot 3$ in²/s³, no $b$). **V2b_rt:** V2b with
$(m_{\text{still}},m_{\text{active}},m_{\text{loco}})$ chosen on the pilot's tuning night (below). **Text:** B1 is the library
median; B2/B2′ are position-only state-space smoothers; V1/V2/V2b use the head IMU's per-second state.

### IMU fallback and its share
$$ \hat{\mathbf p}^{(m),\text{dep}}_k=\begin{cases}\hat{\mathbf p}^{(m)}_k & \text{ok}(\lfloor t_k\rfloor)\\ \hat{\mathbf p}^{(B2)}_k & \text{otherwise}\end{cases},\qquad
\text{share}=\frac{\#\{k\in\text{window}:\neg\text{ok}(\lfloor t_k\rfloor)\}}{\#\{k\in\text{window}\}} $$
ok($s$) = the audit's per-second IMU QC (no missing samples, saturation, frozen chip, invalid, Fusion recovery, handling ± 5 min,
all-tag silence ± 120 s, own ADC lane, tag limits). **Text:** where the IMU cannot be trusted, an IMU method outputs B2.

### IMU per-second classes
still($s$) = ok ∧ $\overline{\text{VeDBA}}_{1s}<\theta_a$ (per animal 0.31–0.39 m/s²) ∧ $\overline{|\boldsymbol\omega|}_{1s}<10$ °/s;
locomoting($s$) = ok ∧ ¬still ∧ $\overline{\text{VeDBA}}_{1s}\ge3.93$ m/s² ∧ SBF($s$) ≥ 0.10 (4–7 Hz share of the vertical
linear acceleration, 2-s window); active = ok ∧ neither. Locomotion detector TPR 0.75 / FPR 0.15 vs WISER speed (pilot).

### Certified still segment and truth (from the audit, unchanged)
IMU-certified head stillness ≥ 30 s (gate-v2 strict windows on 09-08, S50 elsewhere), 1 s trimmed at both ends;
truth $\mathbf c_\sigma=\operatorname{med}_{k\in\sigma}\mathbf z_k$ (coordinate-wise). **Text:** the tag cannot move, so every
displacement of a track inside $\sigma$ is error; drift is a lower bound because the truth is itself WISER.

### Still metrics
Per-fix distance $r_k=\lVert\hat{\mathbf p}_k-\mathbf c_\sigma\rVert$; RMS $=(\frac1N\sum r_k^2)^{1/2}$, p99 = 99th percentile of $r_k$ (in).
Rolling-median drift $d^{(L)}_\sigma=\max_c\lVert\operatorname{med}_{t_k\in[c-L/2,c+L/2)}\hat{\mathbf p}_k-\mathbf c_\sigma\rVert$, $L$ = 10 s
(≥ 10 fixes) or 60 s (≥ 60 fixes, segments ≥ 120 s); reported as the median and p90 over segments (in).
≥ 12-in excursion (crazy-drift event): ≥ 10 consecutive 1-s centres with $\lVert\mathbf m^{(10)}(c)-\mathbf c_\sigma\rVert\ge12$ in; count and per still-hour.
Jump: consecutive fixes with $\lVert\hat{\mathbf p}_{k+1}-\hat{\mathbf p}_k\rVert>30$ in and $t_{k+1}-t_k\le0.35$ s.
Fake path $\Pi=\sum_s\lVert\tilde{\mathbf p}(s+1)-\tilde{\mathbf p}(s)\rVert/(N_s/60)$ (in/min) with $\tilde{\mathbf p}$ the linear
interpolation of the track inside inter-fix gaps ≤ 1 s, $N_s$ the valid 1-s steps, pooled over segments (sum of path / sum of time).
**Text:** inside certified stillness the true path, speed and displacement are zero; every number is invented by the tracker.

### S1 — held-out error on moving fixes
Schemes: (a) runs of $L\sim\mathcal U\{4..8\}$ hidden fixes separated by $G\sim\mathcal U\{1..47\}$ visible ones; (s) every 5th fix
hidden alone (random phase). Each method is rerun with the hidden fixes invisible; B1 predicts by the median of the 7 nearest visible fixes.
$$ e_k=\lVert\mathbf z_k-\hat{\mathbf p}^{(m)}_{-}(t_k)\rVert,\qquad D_m=1-\frac{\operatorname{med}_{k\in\mathcal K}e^{(m)}_k}{\operatorname{med}_{k\in\mathcal K}e^{(B2)}_k} $$
$\mathcal K$ = hidden fixes in the period window with $A_k\ge7$, ok($\lfloor t_k\rfloor$) and not IMU-still (moving). The prediction
is the delivered track ($p$ for drift methods; $p+b$ as a sensitivity). **Text:** + = the method predicts unseen moving fixes
better than B2; the hidden fix contains WISER noise and drift, so this is a floor-dominated safety check, not accuracy.
**Rule:** fail if $D_m<-0.02$ in calm or rain, in (a) or (s).

### S2 — speed preservation
$$ v_m(s)=\lVert\tilde{\mathbf p}^{(m)}(s+1)-\tilde{\mathbf p}^{(m)}(s)\rVert/1\,\text{s},\qquad \Delta_{q,m}=\frac{Q_q[v_m]}{Q_q[v_{B2}]}-1,\quad q\in\{0.5,0.95\} $$
over (i) IMU-locomoting seconds and (ii) seconds with the WISER library speed $u(s)=\operatorname{med}\{\text{speed\_inps\_smooth}_k:\lfloor t_k\rfloor=s,\ \text{valid}_k\}\ge10$ in/s
inside the analysis mask (window, no handling ± 5 min, no silence ± 120 s, tag valid; IMU not required). Seconds where any track is
undefined are dropped for all. **Text:** how much a method slows down (−) or speeds up (+) real movement relative to B2.
**Rule:** fail if $|\Delta_{q,m}|>0.10$ for any quantile, subset or set.

### S3 — rain excursions
$n^{(m)}_{\text{rain}}$ = ≥ 12-in excursion events of method $m$ in the rain primary ≥ 30-s segments. **Rule:** fail if
$n^{(m)}_{\text{rain}}>n^{(\text{raw})}_{\text{rain}}$ (point counts). **Text:** a smoother must not invent ≥ 1-ft displacements
of a still rat that raw WISER (judged by its own 10-s median) does not show.

### S4 — residual jumps
Fail unless the method has 0 jumps in the primary ≥ 30-s still segments (calm and rain) **and** 0 jumps over the analysis mask of every
period (pair midpoint second in the mask). **Text:** a > 30-in step within ≤ 0.35 s (> 86 in/s) is never a real head movement here.

### S5 — onset / offset lag (reported only)
Events: an IMU still run $[a,b)$ ≥ 10 s followed (onset) / preceded (offset) within 60 s by a locomoting second $s_L$ with no
still-run or unusable second in between, ≥ 10 s from the window edges. With $v_m(g)$ the 1-s centred speed on a 0.25-s grid:
$$ \lambda^{\text{on}}_m=\min\{g\in[b-5,\,s_L+20]:v_m(g)\ge3\}-b,\qquad \lambda^{\text{off}}_m=\max\{g\in[s_L-20,\,a+10]:v_m(g)\ge3\}+0.25-a $$
(s); $\Delta\lambda_m=\lambda_m-\lambda_{B2}$ per event. **Text:** how long after the head starts moving the track starts moving
(onset) and how long after the head stops the track stops (offset); + = later than the IMU.

### V2b_rt retuning objective
$\arg\min_{(m_s,m_a,m_l)\in\mathcal G}\operatorname{med}_{k\in\mathcal K_a}\lVert\mathbf z_k-\hat{\mathbf p}_{-}(t_k)\rVert$ (ties: RMSE)
over $\mathcal G=\{0.01,0.03,0.1,0.3,1\}\times\{0.3,1,3\}\times\{1,3,10\}$ on the tuning night 2026-09-08 21:00 → 09-09 04:20,
$\mathcal K_a$ = scheme-(a) hidden fixes (pilot seeds) with $A_k\ge7$, IMU and +1 h IMU QC-ok. **Text:** the pilot's own tuning objective,
now for the B2 base.

### Block bootstrap
$$ \theta^{*(b)}=\theta\big(\{\text{10-min animal-period blocks drawn with replacement within the set}\}\big),\ b=1..1000 $$
CI = 2.5–97.5 % of $\theta^*$; paired comparisons use the same draw for both methods. Quantiles inside the bootstrap use
histograms (0.005 in for held-out errors, 0.05 in/s for speeds, 0.1 in for drift); point estimates are exact.

### Decision rule (pre-registered)
Eliminate an eligible method failing S1, S2, S3 or S4; choose the lowest calm-dry fake path $\Pi$; candidates with
$\Pi\le1.05\,\Pi_{\min}$ are tied and the simplest wins (no drift state, then fewer tuned parameters, then no IMU:
B1 < B2 < V2b < B2′ < V1 < V2). No survivor: the eligible method(s) with the fewest failed criteria, then the same choice.
V2b_rt is scored but not eligible.
"""


def render_report(A: dict, out: Path, figs: dict, meta: dict) -> str:
    cfg, acfg = A["cfg"], A["acfg"]
    cohort = cfg["_cohort"]
    dec, tab, det, sens, fb = A["dec"], A["tab"], A["detail"], A["sens"], A["fb"]
    pooled, setkind, BS, S1, S2, S3, S4m, S5 = (A[k] for k in ("pooled", "setkind", "BS", "S1", "S2", "S3", "S4m", "S5"))
    rt = A["rt"]
    d0 = dec["default"]

    def pv(s, m, col):
        r = pooled[(pooled.set == s) & (pooled.method == m)]
        return float(r[col].iloc[0]) if len(r) else np.nan

    def bsv(s, m, metric):
        r = BS[(BS.set == s) & (BS.method == m) & (BS.metric == metric)]
        return r.iloc[0] if len(r) else None

    def s1v(m, s, sch, sub="moving"):
        r = S1[(S1.method == m) & (S1.set == s) & (S1.scheme == sch) & (S1.subset == sub)]
        return r.iloc[0] if len(r) else None

    def s2v(m, s, sub):
        r = S2[(S2.method == m) & (S2.set == s) & (S2.subset == sub)]
        return r.iloc[0] if len(r) else None

    def s5v(m, s, kind, per="all"):
        r = S5[(S5.method == m) & (S5.set == s) & (S5.kind == kind) & (S5.periods == per)]
        return r.iloc[0] if len(r) else None

    L = []
    L.append(f"# Default WISER smoother for cohort {cohort}, chosen by a pre-registered rule\n")
    L.append(f"**Step after the failure audit** — approved by the user 2026-10-02 (\"do 1st first\"). Plan [`{PLAN}`](../../../../{PLAN}) "
             f"(written before any result; operational choices marked [op] there); driver `wiser/scripts/analyze_wiser_default_smoother.py` "
             f"(`--selftest` ALL PASS); config `wiser/configs/wiser_default_smoother_{cohort}.json` (decision written into its `decision` block); "
             f"bulk `{out}`; inputs = the failure audit run `{cfg['audit_run']}` (reused, not recomputed); git `{meta['git_commit']}`. "
             f"Measurement report: no behavioural claim; WISER inch frame unverified (only distances and speeds used).\n")
    # ---------------- executive summary
    L.append("## Executive summary\n")
    nf = dec["no_survivor_fallback"]
    fbm = {"B1": "itself", "B2": "itself", "B2p": "itself"}.get(d0, "B2")
    E_ = []
    NM = {"B2p": "B2′"}
    r3 = S3[(S3.set == "rain") & (S3.method == d0)].iloc[0]
    why = (f"no eligible method passed all of S1–S4; {d0} fails only {', '.join(dec['eliminated'][d0]) or 'none'}"
           + (f" — by {int(r3.crazy_n - r3.raw_n)} event ({int(r3.crazy_n)} vs raw's {int(r3.raw_n)} rain ≥ 12-in excursions; rate difference "
              f"{_f(r3.diff_vs_raw, 2)}/still-h [{_f(r3.diff_lo, 2)}, {_f(r3.diff_hi, 2)}])" if dec["eliminated"][d0] == ["S3"] else ""))
    E_.append(f"**Default: {d0} ({LABEL[d0]})** — chosen by the pre-registered **no-survivor fallback** ({why}). "
              if nf else f"**Default: {d0} ({LABEL[d0]})** — lowest calm-dry fake path among the survivors {', '.join(dec['survivors'])}. ")
    E_[-1] += (f"Fallback where the IMU QC fails: {fbm}" + (f" ({_p(fb['calm']['fix_share'], 1, False)} of calm / {_p(fb['rain']['fix_share'], 1, False)} of rain window fixes)." if fbm == "B2" else " (position-only, needs no IMU).")
               + (f" The same default results when S3 is judged by its CI ({d0} is then {'the only survivor' if sens['S3_by_CI']['survivors'] == [d0] else 'chosen'})." if sens["S3_by_CI"]["default"] == d0 else ""))
    E_.append(f"**Still benefit of {d0}:** calm-dry fake path {_f(pv('calm', d0, 'path_in_per_min'))} in/min (raw {_f(pv('calm', 'raw', 'path_in_per_min'), 0)}), "
              f"rain {_f(pv('rain', d0, 'path_in_per_min'))}; residual per-fix RMS {_f(pv('calm', d0, 'rms_in'), 2)} | {_f(pv('rain', d0, 'rms_in'), 2)} in (calm | rain); "
              f"jumps {det[d0]['S4_still_jumps']} still / {det[d0]['S4_motion_jumps']} motion.")
    imu = [m for m in ("V1", "V2", "V2b") if m != d0]
    E_.append("**What the IMU methods offer and why they fail:** calm fake path " + ", ".join(f"{m} {_f(tab[m]['fake_calm'])}" for m in imu)
              + f" in/min (circular: the IMU stillness also certifies the segments), but no candidate keeps the 1-s speed within ± 10 % of B2: "
              + "; ".join(f"{NM.get(m, m)} {_p(s2v(m, 'calm', 'loco').d_p50, 0)} / {_p(s2v(m, 'calm', 'loco').d_p95, 0)}" for m in ("B2p", "V1", "V2", "V2b"))
              + " (p50 / p95 on calm IMU-locomoting seconds; worst cases in the table).")
    E_.append("**S1 (held-out moving fixes, vs B2):** " + "; ".join(
        f"{NM.get(m, m)} {_p(min(s1v(m, s, sch).D for s in ('calm', 'rain') for sch in ('a', 's')))} to {_p(max(s1v(m, s, sch).D for s in ('calm', 'rain') for sch in ('a', 's')))}"
        for m in ("B1", "B2p", "V1", "V2", "V2b")) + " (B2′/V1 fail only on (s) with their delivered track p; with p + b they pass).")
    E_.append(f"**S3 / S4:** rain excursions raw {det['B2']['S3_raw_n']}: " + ", ".join(f"{NM.get(m, m)} {det[m]['S3_rain_n']}" for m in CANDS)
              + f"; jumps: B1 {det['B1']['S4_still_jumps']} still / {det['B1']['S4_motion_jumps']} motion, V2 {det['V2']['S4_motion_jumps']} and V2b "
              f"{det['V2b']['S4_motion_jumps']} motion jumps, all at B2-splice boundaries (in-filter forms: {det['V2b'].get('infilter', {}).get('motion_jumps', '–')}).")
    elim = "; ".join(f"{NM.get(m, m)} {', '.join(v) if v else 'none'}" for m, v in dec["eliminated"].items())
    E_.append(f"**Failed criteria:** {elim}. Rain-specific choice: {dec['rain_choice']}{' (same)' if dec['rain_choice'] == d0 else ' — differs'}.")
    sp = sens["S1_with_p_plus_b"]
    txt = (f"S3 by CI → {sens['S3_by_CI']['default']}; V2b without the B2 splice (amendment 1) → {sens['V2b_in_filter']['default']}; "
           f"S1 with the p + b predictor → {sp['default']}")
    if sp["default"] != d0 and sp["no_survivor_fallback"]:
        txt += (f" (the fallback then ties {', '.join(sp['pool'])} at {min(sp['n_failed'][m] for m in sp['pool'])} failure each and takes the lowest fake path — "
                f"trading {sp['default']}'s {', '.join(sp['eliminated'][sp['default']])} failure for {d0}'s {', '.join(dec['eliminated'][d0])} failure; a weakness of the "
                f"fewest-failures fallback, not support for {sp['default']})")
    E_.append(f"**Sensitivity (never the decision):** {txt}. V2b_rt retunes to V2b's own multipliers {tuple(rt['mult_rt'][1:])} (all at grid edges), so it is identical to V2b.")
    so, sf = s5v("V2b", "calm", "onset"), s5v("V2b", "calm", "offset")
    if so is not None and sf is not None:
        E_.append(f"**Transitions (S5, reported only):** B2 starts moving a median {_f(s5v('B2', 'calm', 'onset').lag_med, 2)} s after the first non-still IMU second "
                  f"(calm); V2b differs by {_f(so.get('dlag_med'), 2)} s at onsets and {_f(sf.get('dlag_med'), 2)} s at offsets, V2 by "
                  f"{_f(s5v('V2', 'calm', 'onset').get('dlag_med'), 2)} / {_f(s5v('V2', 'calm', 'offset').get('dlag_med'), 2)} s.")
    for i, e in enumerate(E_[:10], 1):
        L.append(f"{i}. {e}")
    L.append("")
    # ---------------- decision table
    L.append("## Decision table\n")
    L.append("Pooled primary ≥ 30-s certified segments for the still columns; S1/S2 worst case over calm/rain × schemes / subsets × quantiles. "
             "B2 is the S1/S2 reference (passes them by definition).\n")
    L.append("| method | eligible | calm fake path (in/min) [95 % CI] | rain fake path | S1 worst Δ moving | S1 | S2 worst speed Δ | S2 | S3 rain events (raw " +
             f"{det['B2']['S3_raw_n']}) | S3 | S4 jumps still / motion | S4 | S5 onset / offset Δ (s, calm) | outcome |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for m in SCORED:
        t_ = tab[m]
        b = bsv("calm", m, "path_rate")
        w1, w2 = det[m]["S1_worst"], det[m]["S2_worst"]
        so, sf = s5v(m, "calm", "onset"), s5v(m, "calm", "offset")
        if m == d0:
            oc = "**DEFAULT**"
        elif m in SECONDARY:
            oc = "secondary (not eligible)"
        elif m in dec["survivors"]:
            oc = "survivor"
        else:
            oc = "eliminated"
        s1txt = "ref" if m == "B2" else (f"{_p(w1['D'])} ({w1['set']}, ({w1['scheme']}))" if w1 else "–")
        s2txt = "ref" if m == "B2" else (f"{_p(w2['d'])} ({w2['set']} {w2['subset']} {w2['q']})" if w2 else "–")
        s5txt = "ref" if m == "B2" else (f"{_f(so.get('dlag_med') if so is not None else np.nan, 2)} / {_f(sf.get('dlag_med') if sf is not None else np.nan, 2)}")
        L.append(f"| {LABEL[m]} | {'no' if m in SECONDARY else 'yes'} | {_f(t_['fake_calm'])} [{_f(b.lo if b is not None else np.nan)}, {_f(b.hi if b is not None else np.nan)}] | "
                 f"{_f(t_['fake_rain'])} | {s1txt} | {_pf(t_['S1'])} | {s2txt} | {_pf(t_['S2'])} | {det[m]['S3_rain_n']} | {_pf(t_['S3'])} | "
                 f"{det[m]['S4_still_jumps']} / {det[m]['S4_motion_jumps']} | {_pf(t_['S4'])} | {s5txt} | {oc} |")
    L.append("")
    L.append(f"**Rule outcome.** Survivors of S1–S4: {', '.join(dec['survivors']) if dec['survivors'] else 'none'}. "
             + (f"No eligible method passed all four, so the pre-registered fallback took the eligible method(s) with the fewest failed criteria "
                f"({', '.join(dec['pool'])}, {min(dec['n_failed'][m] for m in dec['pool'])} failed each) and applied the fake-path choice. " if nf else "")
             + f"Calm-dry fake path among {', '.join(dec['pool'])}: " + ", ".join(f"{m} {_f(tab[m]['fake_calm'])}" for m in dec["pool"])
             + f" in/min; tied within 5 %: {', '.join(dec['tied_calm'])} → **{d0}**.\n")
    # ---------------- 1. inputs and checks
    rep = A["rep_tr"]
    L.append("## 1. Inputs, reproduction and fallback\n")
    L.append(f"Periods, animals, exclusions and certified segments are the audit's (calm-dry days 09-05/07/08 08:00–18:00, nights 09-05…09-08 "
             f"21:00–04:20; rain nights 09-03, 09-09 and day 09-10; SF07, SF08, SF09, SF10, SF12). The audit's saved tracks (every method at "
             f"every fix, ± 10 min margins) and per-second IMU states are reused; V2b and V2b_rt are new Kalman runs on the same fixes; V1/V2 "
             f"get the B2 fallback here (their audit form falls back to B2′ in-filter).\n")
    rs = A["repro_still"]
    rmj = A["repro_motion_jumps"]
    rev = A["repro_events"]
    rr = rt["repro"]
    L.append("| check | result |")
    L.append("|---|---|")
    L.append(f"| V2 rebuilt from the saved in-window IMU states vs the audit's V2 (≥ 60 s from the window edges) | max {_f(rep.V2_maxdiff_core_in.max(), 4)} in "
             f"(V1 {_f(rep.V1_maxdiff_core_in.max(), 4)} in); whole window p99.9 {_f(rep.V2_p999diff_win_in.max(), 4)} in (edges use margin states) |")
    L.append(f"| pilot tuning night reproduced (same code path as V2b_rt) | B2 median {_f(rr['B2_med'], 4)} in (pilot {_f(rr['B2_med_pilot'], 4)}); V2 optimum "
             f"{rr['V2_best_mult'][1:]} {_f(rr['V2_best_med'], 4)} in (pilot {rr['V2_mult_pilot'][1:]} {_f(rr['V2_med_pilot'], 4)}) → {'OK' if rr['ok'] else '**MISMATCH**'} |")
    L.append(f"| still metrics re-derived for a sample of {rs['n_rows']} segment × method rows (raw, B2, B2′, V2 audit form) vs the saved rows | max |Δ| RMS "
             f"{_f(rs['rms_in'], 4)} in, 10-s drift {_f(rs['drift10_in'], 4)} in, fake path {_f(rs['path_in_per_min'], 3)} in/min, events {_f(rs['crazy_n'], 0)}, jumps {_f(rs['jumps'], 0)} |")
    L.append(f"| segment fix counts / still-fix alignment | {int(rep.n_seg_fixcount_mismatch.sum())} mismatching segments; {A['checks']['F_unmatched']} unmatched "
             f"still fixes of {A['checks']['F_rows']:,}; max time offset {_f(A['checks']['F_t_maxdiff_ms'], 2)} ms |")
    if rmj:
        L.append("| night motion-side jumps in IMU-ok seconds vs the audit | " + "; ".join(f"{m} {v['here']} (audit {v['audit']})" for m, v in rmj.items()) + " |")
    if rev:
        L.append("| onset / offset events on the nights vs the audit | " + "; ".join(f"{k} {v['here']} (audit {v['audit']})" for k, v in rev.items()) + " |")
    L.append(f"| WISER fix caches = the tracks' fixes | {'all match' if bool(rep.cache_rows_match.all()) else 'MISMATCH in ' + str(int((~rep.cache_rows_match).sum()))} |")
    for m in ("V2b", "V2b_rt", "V1", "V2"):
        L.append(f"| B2 splice of {m} (amendment 1): deployable vs {'in-filter' if m in INFILTER else 'audit (B2′-fallback)'} form at IMU-failed window fixes | "
                 f"max {_f(rep[f'{m}_splice_diff_max_in'].max(), 1)} in (worst animal-period p99 {_f(rep[f'{m}_splice_diff_p99_in'].max(), 1)} in); "
                 f"{int(rep[f'{m}_splice_extra_step_gt5in'].sum())} of {int(rep[f'{m}_splice_n_boundaries'].sum()):,} ok↔failed boundaries add a step > 5 in "
                 f"(max extra step {_f(rep[f'{m}_splice_extra_step_max_in'].max(), 1)} in) |")
    L.append(f"| IMU fallback share (calm / rain) | window fixes {_p(fb['calm']['fix_share'], 2, False)} / {_p(fb['rain']['fix_share'], 2, False)}; analysis-mask seconds "
             f"{_p(fb['calm']['mask_sec_share'], 2, False)} / {_p(fb['rain']['mask_sec_share'], 2, False)}; WISER-fast seconds {_p(fb['calm']['fast_sec_share'], 2, False)} / "
             f"{_p(fb['rain']['fast_sec_share'], 2, False)} |")
    asi = A["audit_speed_index_check"]
    L.append(f"| audit finding (minor) | the audit's per-group still tables (`summary_still_{{period,setkind,set,...}}.csv`) take speed quantiles with row positions of the grouped frame instead of the full segment table: raw calm fake-speed p95 {_f(asi['group_table_style'], 2)} there vs {_f(asi['pooled_correct'], 2)} in/s correct (the audit report's pooled table is correct; path, RMS, drift, events and jumps are unaffected) |")
    L.append("")
    # ---------------- 2. still metrics
    L.append("## 2. Still metrics (primary; certified ≥ 30-s segments)\n")
    L.append("**Verdict:** IMU-switched process noise removes almost all fake motion during stillness on either base; on the B2 base (V2b) it does so without "
             "a drift state. These numbers are circular for V1/V2/V2b (the IMU stillness that drives them also certifies the segments): they show "
             "what the constraint removes, not independent evidence.\n")
    L.append("| set | method | still h | fake path in/min [CI] | fake speed p95 (in/s) | per-fix RMS (in) [CI] | p99 | 10-s drift med / p90 | 60-s drift med / p90 | ≥ 12-in events (/h) | jumps |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for s in ("calm", "rain"):
        for m in STILL_METHODS:
            r = pooled[(pooled.set == s) & (pooled.method == m)].iloc[0]
            bp_, br_ = bsv(s, m, "path_rate"), bsv(s, m, "rms")
            L.append(f"| {s} | {LABEL[m]} | {_f(r.still_h)} | {_f(r.path_in_per_min)} [{_f(bp_.lo)}, {_f(bp_.hi)}] | {_f(r.speed_p95, 2)} | "
                     f"{_f(r.rms_in, 2)} [{_f(br_.lo, 2)}, {_f(br_.hi, 2)}] | {_f(r.p99_in)} | {_f(r.drift10_med, 2)} / {_f(r.drift10_p90, 2)} | "
                     f"{_f(r.drift60_med, 2)} / {_f(r.drift60_p90, 2)} | {int(r.crazy_n)} ({_f(r.crazy_per_h, 3)}) | {int(r.jumps_n)} |")
    L.append("")
    L.append("Day vs night (fake path in/min · per-fix RMS in · ≥ 12-in events · jumps):\n")
    L.append("| method | calm day | calm night | rain day | rain night |")
    L.append("|---|---|---|---|---|")
    for m in STILL_METHODS:
        cells = []
        for s in ("calm", "rain"):
            for k in ("day", "night"):
                r = setkind[(setkind.set == s) & (setkind.kind == k) & (setkind.method == m)]
                if len(r):
                    r = r.iloc[0]
                    cells.append(f"{_f(r.path_in_per_min)} · {_f(r.rms_in, 2)} · {int(r.crazy_n)} · {int(r.jumps_n)} ({_f(r.still_h)} h)")
                else:
                    cells.append("–")
        L.append(f"| {LABEL[m]} | " + " | ".join(cells) + " |")
    L.append("")
    L.append(f"![decision](../figures/{figs['decision']})\n")
    # ---------------- 3. S1
    L.append("## 3. S1 — held-out error on moving fixes (vs B2)\n")
    L.append("Hidden fixes in the period window with ≥ 7 anchors whose aligned second is IMU-QC-ok and not IMU-still. Δ = 1 − med(method)/med(B2); "
             "+ = better than B2. 95 % CI: 10-min block bootstrap within the set. Fail below −2 %.\n")
    L.append("| method | calm (a) | calm (s) | rain (a) | rain (s) | S1 | p+b predictor (sensitivity) |")
    L.append("|---|---|---|---|---|---|---|")
    for m in [x for x in SCORED if x != "B2"]:
        cells = []
        for s in ("calm", "rain"):
            for sch in ("a", "s"):
                r = s1v(m, s, sch)
                cells.append(f"{_p(r.D)} [{_p(r.D_lo)}, {_p(r.D_hi)}]" if r is not None else "–")
        pbm = {"B2p": "B2pb", "V1": "V1pb", "V2": "V2pb"}.get(m)
        pbt = "–"
        if pbm:
            pbt = ", ".join(_p(s1v(pbm, s, sch).D) for s in ("calm", "rain") for sch in ("a", "s"))
        L.append(f"| {LABEL[m]} | " + " | ".join(cells) + f" | {_pf(tab[m]['S1'])} | {pbt} |")
    rb = s1v("B2", "calm", "a")
    rb2 = s1v("B2", "rain", "a")
    L.append(f"\nB2's median held-out error on moving fixes: calm (a) {_f(rb.med, 3)} in (n = {int(rb.n):,}), rain (a) {_f(rb2.med, 3)} in (n = {int(rb2.n):,}); "
             f"(s): calm {_f(s1v('B2', 'calm', 's').med, 3)}, rain {_f(s1v('B2', 'rain', 's').med, 3)} in. Other subsets (point Δ vs B2, scheme (a), calm | rain):\n")
    L.append("| method | all scored, calm | all scored, rain | IMU-still, calm | IMU-still, rain | IMU-locomoting, calm | IMU-locomoting, rain |")
    L.append("|---|---|---|---|---|---|---|")
    for m in [x for x in S1_METHODS if x != "B2"]:
        cells = []
        for sub in ("all", "still", "loco"):
            a_, b_ = s1v(m, "calm", "a", sub), s1v(m, "rain", "a", sub)
            cells.append(f"{_p(a_.D) if a_ is not None else '–'} | {_p(b_.D) if b_ is not None else '–'}")
        L.append(f"| {LABEL[m]} | " + " | ".join(cells) + " |")
    L.append("")
    # ---------------- 4. S2
    L.append("## 4. S2 — speed preservation (vs B2)\n")
    L.append("1-s centred speed at the centre of each second. (i) IMU-locomoting seconds; (ii) seconds whose WISER library 1-s median speed is ≥ 10 in/s "
             "(analysis mask, IMU not required). Δ = quantile(method)/quantile(B2) − 1. Fail outside ± 10 %.\n")
    L.append("| set | subset | n s | IMU-fail share | " + " | ".join(f"{m} p50 / p95 (Δ)" for m in ["B2"] + [x for x in SCORED if x != "B2"]) + " |")
    L.append("|---|---|---|---|" + "---|" * len(SCORED))
    for s in ("calm", "rain"):
        for sub in ("loco", "wfast"):
            r0 = s2v("B2", s, sub)
            cells = [f"{_f(r0.p50, 2)} / {_f(r0.p95, 2)}"]
            for m in [x for x in SCORED if x != "B2"]:
                r = s2v(m, s, sub)
                cells.append(f"{_f(r.p50, 2)} / {_f(r.p95, 2)} ({_p(r.d_p50, 0)} / {_p(r.d_p95, 0)})")
            L.append(f"| {s} | {'IMU-locomoting' if sub == 'loco' else 'WISER ≥ 10 in/s'} | {int(r0.n_sec):,} | {_p(r0.imu_fail_share, 1, False)} | " + " | ".join(cells) + " |")
    L.append("\nΔ with 95 % CIs (p50; p95):\n")
    L.append("| method | calm loco | rain loco | calm WISER-fast | rain WISER-fast | S2 |")
    L.append("|---|---|---|---|---|---|")
    for m in [x for x in SCORED if x != "B2"] + ["raw", "V1_audit", "V2_audit", "V2b_infilter", "V2b_rt_infilter"]:
        cells = []
        for s, sub in (("calm", "loco"), ("rain", "loco"), ("calm", "wfast"), ("rain", "wfast")):
            r = s2v(m, s, sub)
            cells.append(f"{_p(r.d_p50, 1)} [{_p(r.d_p50_lo, 1)}, {_p(r.d_p50_hi, 1)}]; {_p(r.d_p95, 1)} [{_p(r.d_p95_lo, 1)}, {_p(r.d_p95_hi, 1)}]")
        L.append(f"| {LABEL[m]} | " + " | ".join(cells) + f" | {_pf(tab[m]['S2']) if m in tab else 'n/a'} |")
    r0c, rvb, rv2 = s2v("B2", "calm", "loco"), s2v("V2b", "calm", "loco"), s2v("V2", "calm", "loco")
    L.append(f"\n**Reading.** On IMU-locomoting seconds B2's median 1-s speed is only {_f(r0c.p50, 1)} in/s (p95 {_f(r0c.p95, 1)}): half of the seconds the IMU calls "
             f"locomotion show almost no WISER displacement (in-place activity; the class has FPR 0.15). There a looser process noise passes more jitter, so "
             f"V2b's {_p(rvb.d_p50, 0)} at p50 is plausibly dominated by jitter rather than displacement; at p95 (real walking and running) V2b is {_p(rvb.d_p95, 0)} and V2 {_p(rv2.d_p95, 0)} relative to B2, "
             f"B2′/V1 about 10–12 % slower. Whether B2 under-follows fast runs (it lags V2b by up to "
             f"{_f(rep['V2b_splice_diff_max_in'].max(), 0)} in at IMU-failed fixes, which cluster in fast runs) or V2b over-follows cannot be decided "
             f"without an independent motion truth; S1 slightly favours V2b on moving fixes. The rule is two-sided, so both directions fail.\n")
    L.append(f"\n![speed](../figures/{figs['speed']})\n")
    # ---------------- 5. S3
    L.append("## 5. S3 — ≥ 12-in excursions in rain (vs raw)\n")
    L.append("Crazy-drift events (10-s median ≥ 12 in from the segment truth for ≥ 10 s) in the primary ≥ 30-s segments. Fail when the rain count exceeds raw's "
             "(point counts, as written); the CI of the rate difference (per still-hour) is the sensitivity.\n")
    L.append("| method | calm events (/h) | rain events (/h) | rain − raw rate [95 % CI] | S3 | S3 by CI |")
    L.append("|---|---|---|---|---|---|")
    for m in ["raw"] + SCORED + ["V1_audit", "V2_audit"]:
        rc_ = S3[(S3.set == "calm") & (S3.method == m)].iloc[0]
        rr_ = S3[(S3.set == "rain") & (S3.method == m)].iloc[0]
        L.append(f"| {LABEL[m]} | {int(rc_.crazy_n)} ({_f(rc_.crazy_per_h, 3)}) | {int(rr_.crazy_n)} ({_f(rr_.crazy_per_h, 3)}) | "
                 f"{_f(rr_.diff_vs_raw, 3)} [{_f(rr_.diff_lo, 3)}, {_f(rr_.diff_hi, 3)}] | {_pf(tab[m]['S3']) if m in tab else ('ref' if m == 'raw' else 'n/a')} | "
                 f"{('pass' if det[m]['S3_ci_pass'] else 'FAIL') if m in det else '–'} |")
    ev = A["events_new"]
    if len(ev):
        e0 = ev[(ev.method == d0) & (ev.set == "rain") & ev.ge30.astype(bool)] if d0 in NEW else pd.DataFrame()
        if len(e0):
            L.append(f"\nRain events of the default ({d0}): " + "; ".join(
                f"{r.animal} {FA.ms_local(r.start_ms)[5:]} {_f(r.size_in)} in × {int(r.dur_s)} s ({r.zone}, anchors {_f(r.anchors_med, 0)})" for r in e0.itertuples()) + ".")
    L.append("")
    # ---------------- 6. S4
    L.append("## 6. S4 — residual jumps\n")
    L.append("Jumps (> 30 in within ≤ 0.35 s) in the primary still segments and over the analysis mask of each period (days and nights). Fail unless both are 0.\n")
    L.append("| method | still jumps calm / rain | motion jumps calm day / calm night / rain day / rain night | of which IMU-QC-failed seconds | S4 |")
    L.append("|---|---|---|---|---|")
    for m in ["raw"] + SCORED + ["V1_audit", "V2_audit", "V2b_infilter", "V2b_rt_infilter"]:
        sj = ([int(pooled[(pooled.set == s) & (pooled.method == m)].jumps_n.iloc[0]) for s in ("calm", "rain")] if m in STILL_METHODS
              else ["–", "–"])
        mj = []
        for s in ("calm", "rain"):
            for k in ("day", "night"):
                r = S4m[(S4m.set == s) & (S4m.kind == k) & (S4m.method == m)]
                mj.append(int(r.jumps_mask.iloc[0]) if len(r) else 0)
        mf = int(S4m[S4m.method == m].jumps_mask_imu_fail.sum())
        L.append(f"| {LABEL[m]} | {sj[0]} / {sj[1]} | {' / '.join(map(str, mj))} | {mf} | {_pf(tab[m]['S4']) if m in tab else ('ref' if m == 'raw' else 'n/a')} |")
    L.append("")
    # ---------------- 7. S5
    L.append("## 7. S5 — onset / offset lag (reported, not in the rule)\n")
    L.append("Onset: first time the 1-s speed reaches 3 in/s minus the first non-still IMU second; offset: last such time minus the first still second. "
             "Δ vs B2 = median of the per-event difference [95 % CI]. All periods (days and nights).\n")
    L.append("| set | kind | events | " + " | ".join(f"{m} median lag (Δ vs B2)" for m in ["B2", "B2p", "V1", "V2", "V2b", "V2b_rt", "V2b_infilter"]) + " |")
    L.append("|---|---|---|" + "---|" * 7)
    for s in ("calm", "rain"):
        for kind in ("onset", "offset"):
            r0 = s5v("B2", s, kind)
            if r0 is None:
                continue
            cells = [f"{_f(r0.lag_med, 2)} s (n {int(r0.n_defined)})"]
            for m in ["B2p", "V1", "V2", "V2b", "V2b_rt", "V2b_infilter"]:
                r = s5v(m, s, kind)
                cells.append(f"{_f(r.lag_med, 2)} ({_f(r.get('dlag_med'), 2)} [{_f(r.get('dlag_lo'), 2)}, {_f(r.get('dlag_hi'), 2)}])")
            L.append(f"| {s} | {kind} | {int(r0.n_events)} | " + " | ".join(cells) + " |")
    L.append(f"\n![lags](../figures/{figs['lags']})\n")
    # ---------------- 8. V2b_rt
    L.append("## 8. V2b_rt — multipliers retuned on the pilot's tuning night (secondary)\n")
    L.append(f"Pilot objective on 2026-09-08/09 (scheme (a), pilot seeds, ≥ 7 anchors, IMU and +1 h IMU QC-ok), pre-registered V2 grid on the B2 base: "
             f"best (m_still, m_active, m_loco) = **{tuple(rt['mult_rt'][1:])}**, median {_f(rt['med_rt'], 4)} in vs B2 {_f(rt['med_B2'], 4)} in "
             f"({_p(rt['gain_vs_B2'], 2)}); grid edge: " + ", ".join(f"{k} {'yes' if v else 'no'}" for k, v in rt["edge"].items())
             + f". The same code reproduced the pilot's tuning night ({'OK' if rr['ok'] else 'MISMATCH'}, §1). V2b_rt is not eligible: it is tuned on "
             f"`night_20260908`, which is also one of the calm evaluation nights.\n")
    # ---------------- 9. decision + sensitivity
    L.append("## 9. Decision and sensitivity\n")
    L.append(f"- **Default WISER smoother for {cohort}: {d0} ({LABEL[d0]}).** Fallback where the IMU QC fails: {fbm}. "
             f"{'Chosen by the no-survivor fallback: ' + ', '.join(f'{m} fails ' + ', '.join(dec['eliminated'][m]) for m in dec['pool']) + '.' if nf else ''}")
    L.append(f"- Rain-specific choice: {dec['rain_choice']}.")
    L.append(f"- Sensitivity, S3 judged by its block-bootstrap CI instead of point counts: survivors {', '.join(sens['S3_by_CI']['survivors']) or 'none'} → {sens['S3_by_CI']['default']}.")
    L.append(f"- Sensitivity, S1 with the p + b predictor for the drift methods: survivors {', '.join(sens['S1_with_p_plus_b']['survivors']) or 'none'} → {sens['S1_with_p_plus_b']['default']}.")
    sp = sens["S1_with_p_plus_b"]
    if sp["default"] != d0:
        L.append(f"  This sensitivity changes the outcome only through the no-survivor fallback: with p + b, {sp['default']} fails {', '.join(sp['eliminated'][sp['default']])} "
                 f"alone and ties {d0} ({', '.join(dec['eliminated'][d0])} alone) at one failure, and the lower fake path wins. That trades a ≈ 15 % slower "
                 f"walking speed (S2) for one fewer rain excursion (S3, a difference inside its CI) — a weakness of counting failures equally, not evidence for {sp['default']}.")
    L.append(f"- Sensitivity, V2b / V2b_rt without the B2 splice (amendment 1): V2b passes S4 (0 jumps) but still fails S2 and S3 → {sens['V2b_in_filter']['default']}.")
    L.append(f"- Robustness: {d0} is the default under the literal rule (fallback) and under S3-by-CI (where it is the sole survivor); every IMU method fails S2 "
             f"in both readings, so the IMU does not enter the default track of {cohort} under this rule.")
    L.append("")
    # ---------------- do not do
    L.append("## Do not do\n")
    L.append(f"- Do not read the still-period gains of V1/V2/V2b as evidence that the IMU makes WISER more accurate: they use the IMU stillness that defines the test.")
    L.append(f"- Do not use B1 (library median-7) or raw WISER for speed, path length or rest detection: they keep jumps and tens to hundreds of inches per minute of fake path in stillness.")
    L.append(f"- Do not use B2′'s position (or V1, which inherits it) for speed or distance where the rule failed it: check S2 above before any kinematic claim.")
    L.append(f"- Do not run an IMU-dependent default without its fallback: where the IMU QC fails (handling, saturation, missing samples, ADC lane) the track must be B2.")
    L.append(f"- Do not treat the default as drift-free: no candidate removes the slow drift (10-s drift ≈ 1–2 in calm, more in rain), and ≥ 12-in excursions still occur in rain.")
    L.append(f"- Do not generalise the still numbers to the open field (≥ 95 % of certified stillness is inside the houses) or to other cohorts without re-running this rule.")
    L.append(f"- Do not compare speeds across smoothers as if one were the truth: S2 measures preservation relative to B2; there is no independent motion truth here.")
    L.append(f"- Do not place positions in the paddock: distances are in the unverified WISER inch frame.")
    L.append(f"- Do not switch the default to V1 or B2′ on the strength of the p + b sensitivity: their delivered position p is ≈ 15 % slower than B2 in locomotion (S2).")
    L.append(f"- Do not use V2 / V2b speeds or path lengths as if more correct than B2's: they are 8–28 % faster and the direction of the truth is unknown without video or another motion reference.")
    L.append(f"- Do not splice an IMU method with B2 sample-by-sample without checking the boundaries: the splice adds steps up to ≈ 24 in where the IMU fails during fast runs.")
    L.append("")
    L.append(DEFINITIONS)
    # ---------------- caveats
    L.append("## Caveats\n")
    L.append("- The smoothing pilot's parameters were tuned on 2026-09-08/09, one of the calm nights; V2b_rt is tuned on the same night.")
    L.append("- Still-segment truth is the segment's own WISER median (drift is a lower bound); certified stillness is ≥ 95 % inside the houses.")
    L.append("- S3 rests on a handful of events (6 raw events in 22.6 rain still-hours); a one-event difference decides it under the literal rule.")
    L.append("- S2 has no independent truth: the IMU locomotion class has TPR 0.75 / FPR 0.15, and the WISER-speed subset is selected by WISER itself.")
    L.append("- S1 scores against hidden WISER fixes (floor-dominated, blind to drift); it is a safety check only.")
    L.append("- The rain set is three weather episodes; block CIs treat 10-min blocks as independent within a set and ignore the shared weather.")
    L.append("- V2b/V2b_rt use in-window IMU states only (the ± 10-min margins count as unusable → B2 dynamics); the audit's V1/V2 used margin states, which "
             "changes nothing ≥ 60 s inside the window (§1).")
    L.append("")
    L.append("## Files\n")
    L.append(f"Bulk `{out}`: `tracks/<SFxx>_<period>.npz` (deployable V1, V2, V2b, V2b_rt at every fix + IMU-ok mask + in-filter V2b/V2b_rt), "
             f"`tables/` (still_metrics_new, still_fixes_new, still_pooled, still_setkind, still_bootstrap, s1_heldout, s2_speed, s3_excursions, "
             f"s4_motion_jumps(_by_set), s5_events, s5_lags, v2b_rt_tuning*, reproduction_*, fallback_share), `s1/` (per-fix held-out errors), "
             f"`seconds/` (per-second speeds), `speeds/` (still fake speeds), `summary.json`, `input_provenance.json`, logs. Re-aggregate without "
             f"recomputing: `python wiser/scripts/analyze_wiser_default_smoother.py --report-only <run_dir>`. Pointer: "
             f"`results/{cohort}/wiser_baseline/reports/run_manifest_default_smoother_{cohort}.json`.\n")
    return "\n".join(L)


def publish(A: dict, out: Path, fh=None) -> None:
    import shutil
    cfg = A["cfg"]
    cohort = cfg["_cohort"]
    fdir = output_paths.figure_dir(cohort, DIRECTION)
    figs = make_figures(A, fdir)
    (out / "figures").mkdir(exist_ok=True)
    for f in figs.values():
        shutil.copy2(fdir / f, out / "figures" / f)
    rdir = output_paths.report_dir(cohort, DIRECTION)
    rep = rdir / f"{STEM}_{cohort}.md"
    meta = {"cohort": cohort, "direction": DIRECTION, "analysis": NAME, "report": rep.name, "driver": "wiser/scripts/analyze_wiser_default_smoother.py",
            "config": Path(cfg["_path"]).relative_to(REPO).as_posix(), "plan": PLAN, "git_commit": C.git_commit(), "figures": sorted(figs.values()),
            "audit_run": cfg["audit_run"], "default": A["dec"]["default"]}
    rep.write_text(render_report(A, out, figs, meta), encoding="utf-8")
    output_paths.write_run_manifest(out, out, **meta)
    mp = rdir / f"run_manifest_default_smoother_{cohort}.json"
    mp.write_text(json.dumps({"run_dir": str(out.resolve()), **meta}, indent=2) + "\n", encoding="utf-8")
    # write the decision into the config's `decision` block
    cp = Path(cfg["_path"])
    cj = json.loads(cp.read_text(encoding="utf-8"))
    dec, det = A["dec"], A["detail"]
    d0 = dec["default"]
    cj["decision"] = {
        "default": d0, "label": LABEL[d0],
        "fallback_where_imu_qc_fails": {"B1": "itself", "B2": "itself", "B2p": "itself"}.get(d0, cfg["imu_fallback"]),
        "chosen_by": "no-survivor fallback (fewest failed criteria)" if dec["no_survivor_fallback"] else "survivor with the lowest calm-dry fake path",
        "survivors": dec["survivors"], "failed_criteria": dec["eliminated"], "tied_calm": dec["tied_calm"], "rain_choice": dec["rain_choice"],
        "calm_fake_path_in_per_min": {m: round(A["tab"][m]["fake_calm"], 3) for m in A["tab"]},
        "rain_fake_path_in_per_min": {m: round(A["tab"][m]["fake_rain"], 3) for m in A["tab"]},
        "S3_rain_events": {m: det[m]["S3_rain_n"] for m in det} | {"raw": det["B2"]["S3_raw_n"]},
        "v2b_rt_multipliers": A["rt"]["mult_rt"],
        "fallback_share_window_fixes": {s: round(A["fb"][s]["fix_share"], 5) for s in A["fb"]},
        "sensitivity": {"S3_by_CI": A["sens"]["S3_by_CI"]["default"], "S1_with_p_plus_b": A["sens"]["S1_with_p_plus_b"]["default"]},
        "run_dir": str(out), "report": f"results/{cohort}/wiser_baseline/reports/{rep.name}",
        "decided_local": pd.Timestamp.now(tz=cfg.get("tz", "America/New_York")).strftime("%Y-%m-%d %H:%M:%S")}
    cp.write_text(json.dumps(cj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log_to(fh, f"report {rep}\nmanifest {mp}\ndecision written into {cp.name}: {d0}")


# ====================================================================================================== selftest
def _synth(seed: int, dur_s: float = 3600.0) -> dict:
    """Synthetic head track: still bouts 60-200 s, walking bouts 15-45 s (OU velocity, tau 3 s, 8 in/s per axis),
    WISER-like bimodal fix intervals, anchors 6-9 with anchor-dependent white noise, slow AR(1) drift, rare outliers."""
    rng = np.random.default_rng(seed)
    m_ = int(dur_s / 0.18) + 20
    t = np.cumsum(rng.choice([0.134, 0.268], size=m_, p=[0.45, 0.55]) + rng.normal(0, 0.003, m_))
    t = t[t < dur_s]
    n = len(t)
    dg = 0.02
    g = np.arange(int(round((dur_s + 2) / dg))) * dg
    still = np.zeros(len(g), bool)
    pos = 0.0
    while pos < dur_s + 2:
        ls = rng.uniform(60, 200)
        still[(g >= pos) & (g < pos + ls)] = True
        pos += ls + rng.uniform(15, 45)
    vel = np.zeros((len(g), 2))
    vv = np.zeros(2)
    tau_v, sd_v = 3.0, 8.0
    for k in range(1, len(g)):
        if still[k]:
            vv = np.zeros(2)
        else:
            vv = vv - vv / tau_v * dg + rng.normal(0, sd_v * math.sqrt(2 * dg / tau_v), 2)
        vel[k] = vv
    pg = 300 + np.cumsum(vel, axis=0) * dg
    p = np.column_stack([np.interp(t, g, pg[:, a]) for a in range(2)])
    A = rng.choice([6, 7, 8, 9], size=n, p=[0.05, 0.1, 0.25, 0.6]).astype(float)
    sig = {6: (5.0, 4.5), 7: (2.8, 4.0), 8: (2.0, 3.2), 9: (1.5, 2.6)}
    sw = np.array([sig[int(a)] for a in A])
    b = np.zeros((n, 2))
    for k in range(1, n):
        ph = math.exp(-(t[k] - t[k - 1]) / 20.0)
        b[k] = ph * b[k - 1] + rng.normal(0, 0.8 * math.sqrt(1 - ph * ph), 2)
    z = p + b + rng.normal(0, 1, (n, 2)) * sw
    out_idx = rng.random(n) < 0.002
    z[out_idx] += rng.normal(0, 12, (int(out_idx.sum()), 2))
    secs = np.arange(0, int(dur_s) + 1)
    per = int(round(1.0 / dg))
    blk = still[:per * len(secs)].reshape(len(secs), per)
    st_full, mov_full = blk.all(axis=1), (~blk).all(axis=1)
    state = np.where(st_full, 1, np.where(mov_full, 3, 2)).astype(np.int8)
    return {"t": t, "z": z, "p": p, "A": A, "secs": secs, "state": state, "q_true": 2 * sd_v ** 2 / tau_v}


def selftest() -> int:
    ok_all = True

    def check(name, cond, info=""):
        nonlocal ok_all
        ok_all &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {info}", flush=True)

    t0 = time.time()
    cplx = {"B1": {"drift": False, "n_params": 1, "imu": False}, "B2": {"drift": False, "n_params": 2, "imu": False},
            "B2p": {"drift": True, "n_params": 4, "imu": False}, "V1": {"drift": True, "n_params": 5, "imu": True},
            "V2": {"drift": True, "n_params": 7, "imu": True}, "V2b": {"drift": False, "n_params": 5, "imu": True},
            "DAMP": {"drift": False, "n_params": 2, "imu": False}, "V2b_rt": {"drift": False, "n_params": 5, "imu": True}}
    # 1) rule branches
    tb = {"B2": {"S1": True, "S2": True, "S3": True, "S4": True, "fake_calm": 10.3, "fake_rain": 12.0},
          "V2": {"S1": True, "S2": True, "S3": True, "S4": True, "fake_calm": 10.0, "fake_rain": 11.0},
          "B1": {"S1": False, "S2": True, "S3": True, "S4": False, "fake_calm": 100.0, "fake_rain": 150.0}}
    d = decide(tb, ["B2", "V2", "B1"], cplx, 0.05)
    check("rule: tie within 5 % -> the simpler method", d["default"] == "B2" and not d["no_survivor_fallback"] and set(d["tied_calm"]) == {"B2", "V2"},
          f"default {d['default']}, tied {d['tied_calm']}")
    tb["B2"]["fake_calm"] = 11.0
    d = decide(tb, ["B2", "V2", "B1"], cplx, 0.05)
    check("rule: outside 5 % -> the lowest fake path", d["default"] == "V2")
    tb2 = {"B2": {**tb["B2"], "S3": False}, "V2": {**tb["V2"], "S2": False, "S3": False}, "B1": tb["B1"]}
    d = decide(tb2, ["B2", "V2", "B1"], cplx, 0.05)
    check("rule: no survivor -> fewest failed criteria", d["no_survivor_fallback"] and d["default"] == "B2" and d["pool"] == ["B2"],
          f"pool {d['pool']}, default {d['default']}")
    # 2) transition events + lags on a planted track
    secs = np.arange(0, 400)
    state = np.full(400, 2, np.int8)
    state[50:100] = 1          # still run 1
    state[103:110] = 3          # loco 3 s after the still run -> onset of run 1
    state[180:200] = 3          # loco ...
    state[205:260] = 1          # ... 5 s before still run 2 -> offset of run 2
    s5 = {"speed_thr_inps": 3.0, "onset_pre_s": 5.0, "onset_post_s": 20.0, "offset_pre_s": 20.0, "offset_post_s": 10.0, "grid_s": 0.25,
          "max_gap_s": 1.0, "still_run_min_s": 10, "loco_search_s": 60, "edge_s": 10.0}
    ev = transition_events(state, secs, 0.0, 400_000.0, s5)
    kinds = sorted((e["kind"], e["ra"]) for e in ev)
    check("events: one onset after run 1, one offset before run 2", kinds == [("offset", 205.0), ("onset", 50.0)], f"{kinds}")
    tt = np.arange(0, 400, 0.25)
    xx = np.where(tt < 103.0, 0.0, np.where(tt < 197.0, 10.0 * (tt - 103.0), 10.0 * (197.0 - 103.0)))
    pp = np.column_stack([xx, np.zeros_like(xx)])
    e_on = [e for e in ev if e["kind"] == "onset"][0]
    e_off = {"kind": "offset", "ra": 200.0, "rb": 260.0, "rl": 199.0}
    lag_on, _ = event_lag(tt, pp, e_on, s5)
    lag_off, _ = event_lag(tt, pp, e_off, s5)
    check("S5: planted 3-s onset delay recovered", abs(lag_on - 3.0) <= 0.25, f"lag {lag_on:.2f} s")
    check("S5: planted stop 3 s before the still run recovered", abs(lag_off + 2.75) <= 0.26, f"lag {lag_off:.2f} s")
    # 3) paired quantile bootstrap
    rng = np.random.default_rng(1)
    v = rng.gamma(3.0, 3.0, 20000)
    blk = np.repeat(np.arange(100), 200)
    cnt = FA.boot_counts(100, 300, rng)
    q0 = hist_boot_q(v, blk, cnt, FA.SPEED_EDGES, [0.5, 0.95])
    q1 = hist_boot_q(1.2 * v, blk, cnt, FA.SPEED_EDGES, [0.5, 0.95])
    r_id = q0[1:] / q0[1:] - 1
    r12 = q1[1:, 0] / q0[1:, 0] - 1
    check("S2 bootstrap: identical methods -> delta 0, CI [0, 0]", np.allclose(r_id, 0.0))
    check("S2 bootstrap: +20 % speeds -> delta 0.2 inside the CI", np.percentile(r12, 2.5) <= 0.2 <= np.percentile(r12, 97.5) + 0.01,
          f"[{np.percentile(r12, 2.5):.3f}, {np.percentile(r12, 97.5):.3f}]")
    # 4) synthetic tracks -> metrics -> rule
    mc = {"roll_short_s": 10.0, "roll_short_min_fix": 10, "roll_long_s": 60.0, "roll_long_min_fix": 60, "roll_long_min_seg_s": 120.0,
          "crazy_in": 12.0, "crazy_min_s": 10, "jump_in": 30.0, "jump_dt_s": 0.35, "speed_grid_s": 0.25, "speed_max_gap_s": 1.0}
    syn = [_synth(s) for s in (31, 32, 33)]
    devs = []
    for s_ in syn:
        for a_, b_ in C.true_runs(s_["state"] == 1):
            if b_ - a_ < 60:
                continue
            m = (s_["t"] >= a_ + 1) & (s_["t"] < b_ - 1)
            zz = s_["z"][m]
            devs.append(pd.DataFrame({"anchors_used": s_["A"][m], "dx": zz[:, 0] - np.median(zz[:, 0]), "dy": zz[:, 1] - np.median(zz[:, 1])}))
    table = P.anchor_sigma_table(pd.concat(devs))
    q = float(syn[0]["q_true"])
    specs = {"B2": {"q": q, "mrej": 1e9}, "DAMP": {"q": q * 0.01, "mrej": 1e9}, "V2b": {"q": q, "mrej": 1e9, "mult": (1.0, 1e-4, 1.0, 1.0)}}
    meths = ["raw", "B1", "B2", "DAMP", "V2b"]
    acc = {m: {"path": 0.0, "sec": 0.0, "crazy_calm": 0, "crazy_rain": 0, "still_jumps": 0, "mot_jumps": 0} for m in meths}
    s1e = {m: [] for m in meths}
    vloco = {m: [] for m in meths}
    vfast = {m: [] for m in meths}
    for si, s_ in enumerate(syn):
        t, z, A_ = s_["t"], s_["z"], s_["A"]
        n = len(t)
        r2 = P.r2_from_anchors(A_, table)
        st_mid, st_at = P.step_states(t * 1000.0, s_["secs"], s_["state"])
        Pk, _, _ = P.kf_run(t, z, r2, [np.ones(n, bool)], [st_mid], [st_at], [specs[k] for k in ("B2", "DAMP", "V2b")])
        trk = {"raw": z, "B1": P.b1_full(z), "B2": Pk[0], "DAMP": Pk[1], "V2b": Pk[2]}
        # still segments (true still runs >= 30 s; truth = median raw)
        for a_, b_ in C.true_runs(s_["state"] == 1):
            if b_ - a_ < 30:
                continue
            ts, te = a_ + 1.0, b_ - 1.0
            i0, i1 = np.searchsorted(t, [ts, te])
            truth = np.median(z[i0:i1], axis=0)
            res, _, _, _ = FA.score_segment(t[i0:i1], {m: trk[m][i0:i1] for m in meths}, truth, ts, te, mc, meths)
            for m in meths:
                acc[m]["path"] += res[m]["path_in"]
                acc[m]["sec"] += res[m]["path_s"]
                acc[m]["crazy_calm"] += res[m]["crazy_n"]
                acc[m]["still_jumps"] += res[m]["jumps"]
        for m in meths:
            acc[m]["mot_jumps"] += int(len(FA.find_jumps(t, trk[m], 30.0, 0.35)))
        # S1 held-out (a) on moving fixes
        hid = hidden_masks(n, 500 + si, 600 + si, 5)
        stf = lookup(s_["secs"], s_["state"], np.floor(t).astype(np.int64), np.int8(0))
        for sch in ("a", "s"):
            h = hid[sch]
            Ph, _, _ = P.kf_run(t, z, r2, [~h], [st_mid], [st_at], [specs[k] for k in ("B2", "DAMP", "V2b")])
            sc = h & (A_ >= 7) & (stf != 1)
            pred = {"B2": Ph[0][sc], "DAMP": Ph[1][sc], "V2b": Ph[2][sc], "B1": P.b1_predict(t[~h], z[~h], t[sc]), "raw": z[sc]}
            for m in meths:
                s1e[m].append(np.hypot(*(z[sc] - pred[m]).T))
        # S2 per-second speeds
        vs = {m: second_speeds(t, trk[m], s_["secs"][:-1], 1.0) for m in meths}
        loco = s_["state"][:-1] == 3
        fastm = np.nan_to_num(vs["B1"]) >= 10.0
        okv = np.isfinite(vs["B2"])
        for m in meths:
            vloco[m].append(vs[m][loco & okv])
            vfast[m].append(vs[m][fastm & okv])
    tabs = {}
    for m in ["B1", "B2", "DAMP", "V2b"]:
        e_m, e_r = np.concatenate(s1e[m]), np.concatenate(s1e["B2"])
        D = 1 - np.median(e_m) / np.median(e_r)
        dq = []
        for vv_ in (vloco, vfast):
            a_, b_ = np.concatenate(vv_[m]), np.concatenate(vv_["B2"])
            dq += [np.percentile(a_, 50) / np.percentile(b_, 50) - 1, np.percentile(a_, 95) / np.percentile(b_, 95) - 1]
        tabs[m] = {"S1": bool(D >= -0.02), "S2": bool(np.all(np.abs(dq) <= 0.10)), "S3": acc[m]["crazy_calm"] <= acc["raw"]["crazy_calm"],
                   "S4": acc[m]["still_jumps"] == 0 and acc[m]["mot_jumps"] == 0,
                   "fake_calm": acc[m]["path"] / (acc[m]["sec"] / 60.0), "fake_rain": acc[m]["path"] / (acc[m]["sec"] / 60.0), "_D": D, "_dq": dq}
        print(f"   {m}: fake path {tabs[m]['fake_calm']:.1f} in/min, S1 D {100 * D:+.1f} %, S2 dq " + ", ".join(f"{100 * x:+.1f} %" for x in dq)
              + f", events {acc[m]['crazy_calm']} (raw {acc['raw']['crazy_calm']}), jumps {acc[m]['still_jumps']}/{acc[m]['mot_jumps']}", flush=True)
    print(f"   raw: fake path {acc['raw']['path'] / (acc['raw']['sec'] / 60.0):.1f} in/min, jumps {acc['raw']['still_jumps']}/{acc['raw']['mot_jumps']}", flush=True)
    check("synthetic: the speed-damping smoother is slower than B2 by > 10 %", min(tabs["DAMP"]["_dq"]) < -0.10, f"min dq {100 * min(tabs['DAMP']['_dq']):+.1f} %")
    check("synthetic: the IMU-switched smoother preserves walking speed (|dq| <= 10 %)", tabs["V2b"]["S2"], f"{[round(100 * x, 1) for x in tabs['V2b']['_dq']]}")
    check("synthetic: the IMU-switched smoother has the lowest still fake path",
          tabs["V2b"]["fake_calm"] < min(tabs[m]["fake_calm"] for m in ("B1", "B2", "DAMP")),
          f"{tabs['V2b']['fake_calm']:.2f} vs B2 {tabs['B2']['fake_calm']:.2f}, DAMP {tabs['DAMP']['fake_calm']:.2f} in/min")
    tt_ = {m: {k: v for k, v in tabs[m].items() if not k.startswith("_")} for m in tabs}
    d = decide(tt_, ["B1", "B2", "DAMP", "V2b"], cplx, 0.05)
    check("synthetic rule: the damping smoother is eliminated by S2", "S2" in d["eliminated"]["DAMP"] and "DAMP" not in d["survivors"],
          f"DAMP fails {d['eliminated']['DAMP']}")
    check("synthetic rule: the IMU-switched smoother survives and is chosen", d["default"] == "V2b" and "V2b" in d["survivors"],
          f"survivors {d['survivors']}, default {d['default']}")
    print(f"numba: {P.HAVE_NUMBA}; selftest {time.time() - t0:.1f} s -> {'ALL PASS' if ok_all else 'FAILED'}", flush=True)
    return 0 if ok_all else 1


# ====================================================================================================== main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cohort", default="2026c")
    ap.add_argument("--config", default=None)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--report-only", default=None, help="existing run dir: re-aggregate and re-render from its saved tables")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    cfg = load_cfg(a.cohort, a.config)
    out = Path(a.report_only) if a.report_only else run_compute(cfg, a.workers or int(cfg.get("workers", 5)))
    fh = open(out / "log_report.txt", "a", encoding="utf-8")
    A = aggregate(out, cfg, fh)
    publish(A, out, fh)
    fh.close()


if __name__ == "__main__":
    main()
