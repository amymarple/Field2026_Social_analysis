r"""Sleep behaviour explore, Step C: day vs night, matched (cohort 2026c).

Plan: implementation_plan/2026-10-08-sleep-behaviour-explore.md (sections 1, 3, 4 and 5 Step C; the pass rules there are
fixed). Step C sits on Step B (`ephys/sleep_model.py`, imported, never edited): the REM-entry counter P with the grid point
chosen most often by Step B's nested forward chaining, read through the per-10-s NREM-step hazard.

Parts (definitions, formula + text, in the report's Definitions section):
  c1  gain vs prior wake. (a) the plan's literal form: no 2-harmonic clock; dark + ln(1+d) + dark x ln(1+d) + spline
      ln(1+P) + L1 (without its ln d) + animal; the dark coefficient on REM vs stay (cluster-robust CI by block) and per
      animal. (b) ADDED because Step B found the night effect carried by the smooth clock, not a step: B-full (2-harmonic
      clock + dark step + P + L1) + dark x ln(1+d); the model-implied night / day ratio of the per-step REM probability at
      each step's own P, d and L1 (clock standardised over the empirical night vs day clock), pooled and per animal.
  c2  light step vs circadian curve vs prior wake on the NREM steps within +-2 h of sunrise and of sunset (prior wake
      < 7 min, post-round 3 h excluded): forward-chained held-out log-loss of clock vs clock + light step vs clock + ln d.
  c3  where and with whom (WISER default tracks): house / field / unknown and co-located housemates per step; REM-entry
      and NREM -> WAKE coefficients of group size by phase (per-animal signs), held-out gain of location and group terms,
      and the c1 night / day effects recomputed within house-with-mates sleep only.
  c4  the 12-day drift: per animal-day night and day sleep share (and NREM min per recorded h) ~ experiment day +
      temperature + rain + WISER time outside the houses, animal fixed effects.

Usage: python ephys/sleep_explore_c.py stepC [--parts c1 c2 c3 c4] [--scorings FINAL pass2med] [--workers 8] [--p-key KEY]
       python ephys/sleep_explore_c.py --selftest
Written as a separate file (not a `stepC` command inside sleep_explore.py) so that stepA's file, CLI and selftest stay
untouched.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(ROOT / "common"))
sys.path.insert(0, str(ROOT / "wiser" / "src"))
from sleep_cycles import bouts, loglosses  # noqa: E402
from sleep_model import PASS2MED, build_data, folds_of, records_for, to_arrays, variant_specs  # noqa: E402
from sleep_schedule import N, R, REVIEW, STATES, W  # noqa: E402

SCORINGS = {"FINAL": STATES, "pass2med": PASS2MED}
PLAN = "implementation_plan/2026-10-08-sleep-behaviour-explore.md"
CHOSEN_CSV = ROOT / "results/2026c/ephys_spikes/reports/ephys_spikes_sleep_explore_B_chosen_2026c.csv"
P0_MANIFEST = ROOT / "results/2026c/ephys_spikes/reports/run_manifest_sleep_schedule_phase0_2026c.json"
OUT = Path("D:/Field2026_analysis_out/2026c")
ROUND_CAUSES = ("round_logged", "round_inferred")
POST_S = 3 * 3600
LN06 = float(np.log(0.6))
L2 = 1e-4                          # = sklearn C = 1e4 (Step B's engine), as an L2 penalty on the summed log-likelihood
G0 = pd.Timestamp("2026-08-30 12:00:00")       # the per-second WISER / state grid
G1 = pd.Timestamp("2026-09-12 00:00:00")
CUT = pd.Timestamp("2026-09-11 19:40:00")
RELEASE = pd.Timestamp("2026-08-30 19:00:00")
ANIMALS = ["SF07", "SF08", "SF09", "SF10", "SF11", "SF12"]
ZONES = {0: "unknown", 1: "house_1", 2: "house_2", 3: "field"}
K_CLOCK = 24                       # clock values per phase in the standardisation
TRANS_MIN = 120                    # c2: +- 2 h around sunrise / sunset
D_REF = {"d = 0 (after REM / unknown)": 0.0, "d = 20 s (MA)": 20.0, "d = 3 min": 180.0, "d = 15 min": 900.0, "d = 60 min": 3600.0}
COL = {"dark": "#2a78d6", "light": "#eb6834", "ink": "#52514e", "grey": "#9a9894", "FINAL": "#2a78d6", "pass2med": "#eb6834"}


# ================================================================== the multinomial engine (Newton, cluster sandwich)
def mnl_fit(X: np.ndarray, y: np.ndarray, groups=None, l2: float = L2, maxit: int = 60) -> dict:
    """Reference-coded multinomial logit stay (0) / REM (1) / WAKE (2) with an intercept, fitted by Newton-Raphson on the
    L2-penalised log-likelihood (penalty l2 / 2 * ||beta||^2, intercepts unpenalised; l2 = 1e-4 = sklearn's C = 1e4).
    Returns B (p + 1, 2): column 0 = REM vs stay, column 1 = WAKE vs stay; cov = cluster-robust sandwich over `groups`
    H^-1 (sum_g U_g U_g') H^-1 G / (G - 1) (U_g = summed scores of cluster g), cov_model = H^-1."""
    n, p = X.shape
    Xc = np.column_stack([np.ones(n), X])
    k = p + 1
    Y = np.column_stack([(y == 1), (y == 2)]).astype(float)
    pen = np.full(k, l2)
    pen[0] = 0.0
    B = np.zeros((k, 2))
    B[0] = np.log(np.maximum(Y.mean(0), 1e-6) / max(1e-6, 1 - Y.mean(0).sum()))
    prev = -np.inf
    H = None
    for it in range(maxit):
        P, ll = _probs(Xc, B, Y)
        ll -= 0.5 * float(np.sum(pen[:, None] * B ** 2))
        G = _xty(Xc, Y - P) - pen[:, None] * B
        H = _hess(Xc, P, pen)
        step = np.linalg.solve(H, G.ravel(order="F")).reshape((k, 2), order="F")
        # step halving if the penalised log-likelihood decreased
        t = 1.0
        for _ in range(20):
            Bn = B + t * step
            _, lln = _probs(Xc, Bn, Y)
            lln -= 0.5 * float(np.sum(pen[:, None] * Bn ** 2))
            if lln >= ll - 1e-9:
                break
            t /= 2
        B = Bn
        if abs(lln - ll) < 1e-9 * max(1.0, abs(ll)) and np.max(np.abs(t * step)) < 1e-6:
            break
        prev = lln
    P, ll = _probs(Xc, B, Y)
    H = _hess(Xc, P, pen)
    Hi = np.linalg.inv(H)
    out = {"B": B, "cov_model": Hi, "iters": it + 1, "ll": ll, "n": n, "conv": it + 1 < maxit}
    if groups is not None:
        gi = pd.factorize(np.asarray(groups))[0]
        Gn = int(gi.max()) + 1
        R = Y - P
        U = np.zeros((Gn, 2 * k))
        for g in range(Gn):                         # summed scores per cluster
            m = gi == g
            U[g] = np.r_[Xc[m].T @ R[m, 0], Xc[m].T @ R[m, 1]]
        out["cov"] = Hi @ (U.T @ U) @ Hi * Gn / max(Gn - 1, 1)
        out["clusters"] = Gn
    else:
        out["cov"] = Hi
        out["clusters"] = 0
    _ = prev
    return out


def _probs(Xc: np.ndarray, B: np.ndarray, Y: np.ndarray) -> tuple[np.ndarray, float]:
    E = Xc @ B
    m = np.maximum(E.max(1), 0.0)
    ex = np.exp(E - m[:, None])
    den = np.exp(-m) + ex.sum(1)
    P = ex / den[:, None]
    ll = float(np.sum(Y * E) - np.sum(m + np.log(den)))
    return P, ll


CHUNK = 4096                       # row chunks for X'WX: numpy's matmul here is unblocked (one 180k-row Gram ~8 s, chunked ~0.4 s)


def _hess(Xc: np.ndarray, P: np.ndarray, pen: np.ndarray) -> np.ndarray:
    n, k = Xc.shape
    H = np.zeros((2 * k, 2 * k))
    ws = {(0, 0): P[:, 0] * (1 - P[:, 0]), (1, 1): P[:, 1] * (1 - P[:, 1]), (0, 1): -P[:, 0] * P[:, 1]}
    blk = {ab: np.zeros((k, k)) for ab in ws}
    for i in range(0, n, CHUNK):
        Xi = Xc[i:i + CHUNK]
        for ab, w in ws.items():
            blk[ab] += (Xi * w[i:i + CHUNK, None]).T @ Xi
    H[:k, :k], H[k:, k:] = blk[(0, 0)], blk[(1, 1)]
    H[:k, k:] = blk[(0, 1)]
    H[k:, :k] = blk[(0, 1)].T
    H[np.diag_indices(2 * k)] += np.r_[pen, pen]
    return H


def _xty(Xc: np.ndarray, R: np.ndarray) -> np.ndarray:
    out = np.zeros((Xc.shape[1], R.shape[1]))
    for i in range(0, len(Xc), CHUNK):
        out += Xc[i:i + CHUNK].T @ R[i:i + CHUNK]
    return out


def mnl_predict(X: np.ndarray, B: np.ndarray) -> np.ndarray:
    E = np.column_stack([np.zeros(len(X)), np.column_stack([np.ones(len(X)), X]) @ B])
    E -= E.max(1, keepdims=True)
    P = np.exp(E)
    return P / P.sum(1, keepdims=True)


def coef(fit: dict, names: list[str], name: str, eq: int = 0) -> dict:
    """Coefficient of `name` in equation eq (0 = REM vs stay, 1 = WAKE vs stay) with its cluster-robust 95 % CI."""
    if name not in names:
        return {"coef": np.nan, "se": np.nan, "ci_lo": np.nan, "ci_hi": np.nan, "p": np.nan}
    return lincomb(fit, names, {name: 1.0}, eq)


def lincomb(fit: dict, names: list[str], w: dict, eq: int = 0) -> dict:
    from scipy.stats import norm
    k = len(names) + 1
    v = np.zeros(2 * k)
    for nm, c in w.items():
        if nm in names:
            v[eq * k + 1 + names.index(nm)] = c
    b = float(v[eq * k:(eq + 1) * k] @ fit["B"][:, eq])
    se = float(np.sqrt(max(v @ fit["cov"] @ v, 0.0)))
    return {"coef": b, "se": se, "ci_lo": b - 1.96 * se, "ci_hi": b + 1.96 * se, "p": float(2 * norm.sf(abs(b / se))) if se > 0 else np.nan}


# ================================================================== design (named columns; the clock block can be overridden)
def design_nc(D: dict, idx: np.ndarray, spec: dict, st: dict | None, levels: list[str]) -> tuple[np.ndarray, list[str], dict]:
    """Columns that do not depend on the clock. spec keys: hist (P variant key; spline of ln(1+P)), tday (bool, default True),
    L1 ('full' | 'noD' | None), lnd (ln(1+d) centred, unscaled), raw (columns centred, unscaled), lin (z-scored), animal."""
    from sklearn.preprocessing import SplineTransformer
    fit = st is None
    st = {} if st is None else st
    cols, names = [], []

    def spl(c: str) -> None:
        x = D[c][idx, None].astype(float)
        if fit:
            st[f"spl_{c}"] = SplineTransformer(n_knots=4, degree=3, include_bias=False).fit(x)
        m = st[f"spl_{c}"].transform(x)
        cols.append(m)
        names.extend(f"spl({c})_{j}" for j in range(m.shape[1]))

    def z(c: str, scale: bool = True, nm: str | None = None) -> None:
        x = D[c][idx].astype(float)
        if fit:
            st[f"mu_{c}"] = float(x.mean())
            st[f"sd_{c}"] = (float(x.std()) or 1.0) if scale else 1.0
        cols.append(((x - st[f"mu_{c}"]) / st[f"sd_{c}"])[:, None])
        names.append(nm or c)

    spl("l_elapsed")
    if spec.get("hist"):
        spl(f"lP_{spec['hist']}")
    if spec.get("tday", True):
        z("T_day")
    z("has_anchor")
    L1 = spec.get("L1", "noD")
    if L1:
        for c in (["l_dprev"] if L1 == "full" else []) + ["prev_rem", "prev_unk", "fW10"]:
            z(c)
    if spec.get("lnd"):
        z("l_dprev", scale=False, nm="lnd")
    for c in spec.get("lin", ()):
        z(c)
    for c in spec.get("raw", ()):
        z(c, scale=False)
    if spec.get("animal", True) and len(levels) > 1:
        an = D["animal"][idx]
        for lv in levels[1:]:
            cols.append((an == lv).astype(float)[:, None])
            names.append(f"animal_{lv}")
    if fit:
        st["c_lnd"] = float(spec["c_lnd"]) if "c_lnd" in spec else float(D["l_dprev"][idx].mean())
        st["c_T_day"] = float(D["T_day"][idx].mean())
        for c in spec.get("raw_x_dark", ()):
            st[f"c_{c}"] = float(D[c][idx].mean())
    return np.column_stack(cols) if cols else np.zeros((len(idx), 0)), names, st


def clock_block(D: dict, idx: np.ndarray, spec: dict, st: dict, hour=None, dark=None) -> tuple[np.ndarray, list[str]]:
    """Clock-dependent columns: harmonics (sin, cos)(2 pi k h / 24), k = 1, 2 ('harm'), the dark step ('dark'), and dark x
    centred ln(1+d) / experiment day / raw columns. hour / dark: scalars that replace every step's own clock."""
    n = len(idx)
    h = D["hour"][idx].astype(float) if hour is None else np.full(n, float(hour))
    dk = D["dark"][idx].astype(float) if dark is None else np.full(n, float(dark))
    cols, names = [], []
    if spec.get("harm", True):
        for k in (1, 2):
            cols += [np.sin(2 * np.pi * k * h / 24), np.cos(2 * np.pi * k * h / 24)]
            names += [f"sin{k}", f"cos{k}"]
    if spec.get("dark", True):
        cols.append(dk)
        names.append("dark")
    if spec.get("dark_x_lnd"):
        cols.append(dk * (D["l_dprev"][idx] - st["c_lnd"]))
        names.append("dark_x_lnd")
    if spec.get("dark_x_day"):
        cols.append(dk * (D["T_day"][idx] - st["c_T_day"]))
        names.append("dark_x_day")
    for c in spec.get("raw_x_dark", ()):
        cols.append(dk * (D[c][idx] - st[f"c_{c}"]))
        names.append(f"dark_x_{c}")
    return (np.column_stack(cols) if cols else np.zeros((n, 0))), names


def design(D: dict, idx: np.ndarray, spec: dict, st: dict | None, levels: list[str]):
    Xn, nn, st = design_nc(D, idx, spec, st, levels)
    Xk, nk = clock_block(D, idx, spec, st)
    return np.column_stack([Xn, Xk]), nn + nk, st


# ================================================================== the standardised night / day ratio
def clock_sets(D: dict, idx: np.ndarray, k: int = K_CLOCK) -> dict[str, list[tuple[float, float]]]:
    """K representative clocks per phase: the (j + 0.5) / K quantiles of the clock hour among the phase's steps (night:
    dark = 1; day: dark = 0); the night hours wrap at midnight, so they are taken from the sorted values directly."""
    out = {}
    for ph, dk in (("night", 1.0), ("day", 0.0)):
        h = np.sort(D["hour"][idx][D["dark"][idx] == dk].astype(float))
        if not len(h):
            out[ph] = []
            continue
        q = h[np.minimum(((np.arange(k) + 0.5) / k * len(h)).astype(int), len(h) - 1)]
        out[ph] = [(float(x), dk) for x in q]
    return out


def std_p(D: dict, idx: np.ndarray, spec: dict, st: dict, levels: list[str], B: np.ndarray,
          clocks: dict[str, list[tuple[float, float]]], Xn: np.ndarray | None = None, Xks: dict | None = None) -> dict[str, np.ndarray]:
    """Per step, the REM probability averaged over the night clocks and over the day clocks (each step keeps its own P, d,
    L1, elapsed, day and animal). Xks: precomputed clock blocks {(h, dark): X} (for repeated parameter draws)."""
    if Xn is None:
        Xn, _, _ = design_nc(D, idx, spec, st, levels)
    kn = Xn.shape[1]
    eta_nc = np.column_stack([np.ones(len(idx)), Xn]) @ B[:kn + 1]
    out = {}
    for ph, cl in clocks.items():
        acc = np.zeros(len(idx))
        for h, dk in cl:
            Xk = Xks[(h, dk)] if Xks is not None else clock_block(D, idx, spec, st, h, dk)[0]
            E = eta_nc + Xk @ B[kn + 1:]
            m = np.maximum(E.max(1), 0.0)
            ex = np.exp(E - m[:, None])
            acc += ex[:, 0] / (np.exp(-m) + ex.sum(1))
        out[ph] = acc / max(len(cl), 1)
    return out


def ratio_of(p: dict[str, np.ndarray], sel: np.ndarray | None = None) -> float:
    s = slice(None) if sel is None else sel
    return float(p["night"][s].sum() / p["day"][s].sum())


# ================================================================== jobs
def mn_job(name: str, D: dict, idx: np.ndarray, spec: dict, ratio: bool = False, draws: int = 0, clocks=None,
           subsets: dict | None = None, seed: int = 0) -> dict:
    """One full-data fit with cluster-robust SEs by block; optionally the standardised night / day ratio (point on all
    steps, CI from `draws` parameter vectors drawn from N(B, cov)), and the ratio within named step subsets."""
    t0 = time.time()
    levels = sorted(set(D["animal"][idx])) if spec.get("animal", True) else []
    X, names, st = design(D, idx, spec, None, levels)
    y = D["y"][idx].astype(int)
    if len(np.unique(y)) < 3:
        return {"name": name, "ok": False, "why": "fewer than 3 outcome classes"}
    try:
        f = mnl_fit(X, y, D["block"][idx])
    except np.linalg.LinAlgError as e:
        return {"name": name, "ok": False, "why": f"singular: {e}"}
    out = {"name": name, "ok": True, "names": names, "B": f["B"], "cov": f["cov"], "n": len(idx), "n_rem": int((y == 1).sum()),
           "n_wake": int((y == 2).sum()), "clusters": f["clusters"], "conv": f["conv"], "st_lnd": st["c_lnd"]}
    if ratio:
        clocks = clocks or clock_sets(D, idx)
        Xn, _, _ = design_nc(D, idx, spec, st, levels)
        p = std_p(D, idx, spec, st, levels, f["B"], clocks, Xn)
        out["ratio"] = ratio_of(p)
        out["p_night_mean"], out["p_day_mean"] = float(p["night"].mean()), float(p["day"].mean())
        out["ratio_subsets"] = {k: (ratio_of(p, m[idx]), int(np.sum(m[idx]))) for k, m in (subsets or {}).items()}  # m: full-length bool
        if draws:
            rng = np.random.default_rng(seed)
            k = f["B"].shape[0]
            mean = f["B"].ravel(order="F")
            try:
                # the cluster sandwich over ~22 blocks has rank <= G - 1 < the number of parameters: draw through its
                # eigen-decomposition (negative round-off eigenvalues set to 0), not a Cholesky factor
                ev, V = np.linalg.eigh((f["cov"] + f["cov"].T) / 2)
                L = V * np.sqrt(np.maximum(ev, 0.0))
                Xks = {c: clock_block(D, idx, spec, st, *c)[0] for cl in clocks.values() for c in cl}
                rs = []
                for _ in range(draws):
                    Bd = (mean + L @ rng.standard_normal(len(mean))).reshape((k, 2), order="F")
                    rs.append(ratio_of(std_p(D, idx, spec, st, levels, Bd, clocks, Xn, Xks)))
                lr = np.log(np.array(rs))
                out["ratio_ci"] = (float(np.exp(np.percentile(lr, 2.5))), float(np.exp(np.percentile(lr, 97.5))))
                out["lratio_se"] = float(lr.std(ddof=1))
            except np.linalg.LinAlgError:
                out["ratio_ci"] = (np.nan, np.nan)
                out["lratio_se"] = np.nan
    out["secs"] = time.time() - t0
    return out


def run_jobs(jobs: list[tuple], workers: int) -> dict[str, dict]:
    """jobs: (name, D, idx, spec[, kwargs]); the long parameter-draw jobs are dispatched first."""
    from joblib import Parallel, delayed
    jobs = sorted(jobs, key=lambda j: -(j[4].get("draws", 0) or 0) if len(j) > 4 else 0)
    res = Parallel(n_jobs=workers, backend="loky", verbose=0)(delayed(mn_job)(*j[:4], **(j[4] if len(j) > 4 else {})) for j in jobs)
    return {r["name"]: r for r in res}


def split_fits(allf: dict[str, dict], lab: str) -> dict[str, dict]:
    """Fits of one scoring from a pooled run (names '<label>|<name>')."""
    return {n.split("|", 1)[1]: f for n, f in allf.items() if n.split("|", 1)[0] == lab}


def heldout_job(k: int, tr: np.ndarray, te: np.ndarray, D: dict, specs: dict[str, dict]) -> dict:
    levels = sorted(set(D["animal"][tr]))
    te = te[np.isin(D["animal"][te], levels)]
    out = {"k": k, "te": te, "ll": {}}
    for name, sp in specs.items():
        X, _, st = design(D, tr, sp, None, levels)
        f = mnl_fit(X, D["y"][tr].astype(int))
        Xt, _, _ = design(D, te, sp, st, levels)
        out["ll"][name] = loglosses(mnl_predict(Xt, f["B"]), D["y"][te].astype(int))["ll"].astype(np.float64)
    return out


def run_heldout(D: dict, specs: dict[str, dict], folds: list[tuple[np.ndarray, np.ndarray]], workers: int) -> list[dict]:
    from joblib import Parallel, delayed
    res = Parallel(n_jobs=workers, backend="loky", verbose=0)(delayed(heldout_job)(k, tr, te, D, specs) for k, (tr, te) in enumerate(folds))
    return sorted(res, key=lambda r: r["k"])


def ho_tables(res: list[dict], D: dict, mask: np.ndarray | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-fold and per-(fold, animal) mean held-out log-loss of every spec, optionally over a subset of the test steps."""
    F, FA = [], []
    for r in res:
        te = r["te"]
        sel = np.ones(len(te), bool) if mask is None else mask[te]
        if sel.sum() == 0 or (D["y"][te][sel] == 1).sum() == 0:
            continue
        row = {"fold": r["k"], "n": int(sel.sum()), "n_rem": int((D["y"][te][sel] == 1).sum())}
        an = D["animal"][te][sel]
        for nm, ll in r["ll"].items():
            row[f"ll_{nm}"] = float(ll[sel].mean())
        F.append(row)
        for a in np.unique(an):
            m = an == a
            FA.append({"fold": r["k"], "animal": a, "n": int(m.sum()), **{f"ll_{nm}": float(ll[sel][m].mean()) for nm, ll in r["ll"].items()}})
    return pd.DataFrame(F), pd.DataFrame(FA)


def cmp(F: pd.DataFrame, FA: pd.DataFrame, lo: str, hi: str, label: str) -> dict:
    from sleep_schedule_phase2 import compare
    return compare(F, FA, lo, hi, label)


# ================================================================== data
def gaps_table() -> pd.DataFrame:
    return pd.read_csv(Path(json.load(open(P0_MANIFEST))["run_dir"]) / "gaps.csv", parse_dates=["gap_start", "gap_end"])


def post_round_mask(animal: np.ndarray, t: pd.Series, gaps: pd.DataFrame, seconds: int = POST_S) -> np.ndarray:
    """True where t lies in [gap end, gap end + 3 h) of a battery-round gap (cause round_logged / round_inferred) of the
    same animal (plan section 3)."""
    m = np.zeros(len(t), bool)
    tv = pd.to_datetime(t).to_numpy()
    for g in gaps[gaps.cause.isin(ROUND_CAUSES)].itertuples():
        ge = np.datetime64(pd.Timestamp(g.gap_end))
        m |= (animal == g.animal) & (tv >= ge) & (tv < ge + np.timedelta64(seconds, "s"))
    return m


def load_zone_c(an: str, dates, rois) -> pd.Series:
    """mic_wake_pilot.load_zone, with fixes flagged m_off_animal (SF11's tag on its dropped implant, 09-07 06:10:45 -> 08:20)
    removed: per second, the median default-track position (forward-filled over gaps <= 30 s) -> house_1 / house_2 (ROI +
    14 in) / field; unknown where no position."""
    import wiser_analysis_utils as Wu
    fs = [OUT / f"wiser_default_tracks/{an}/{d}.csv.gz" for d in dates]
    fs = [f for f in fs if f.exists()]
    if not fs:
        return pd.Series(dtype=object)
    tr = pd.concat([pd.read_csv(f, usecols=["t_ms", "x", "y", "m_off_animal"]) for f in fs])
    tr = tr[tr.m_off_animal.fillna(0).astype(int) == 0]
    tr["t"] = (pd.to_datetime(tr.t_ms, unit="ms") - pd.Timedelta(hours=4)).dt.floor("1s")
    pos = tr.groupby("t")[["x", "y"]].median()
    grid = pd.date_range(pos.index.min(), pos.index.max(), freq="1s")
    pos = pos.reindex(grid).ffill(limit=30)
    z = pd.Series("field", index=grid, dtype=object)
    fin = pos.x.notna().to_numpy()
    for h, roi in rois.items():
        _, inb = Wu._rect_membership(pos.x.fillna(0).to_numpy(), pos.y.fillna(0).to_numpy(), roi, 14.0)
        z[fin & inb] = h
    z[~fin] = "unknown"
    return z


def zone_arrays(cache: Path | None = None) -> dict[str, np.ndarray]:
    """Per animal, the zone code per second of the grid [G0, G1): 0 unknown, 1 house_1, 2 house_2, 3 field."""
    if cache is not None and cache.exists():
        with np.load(cache) as z:
            return {k: z[k] for k in z.files}
    rois = {r["name"]: r for r in json.load(open(ROOT / "wiser/configs/wiser_rois.json"))["rois"] if r["name"] in ("house_1", "house_2")}
    span = int((G1 - G0).total_seconds())
    dates = [d.strftime("%Y%m%d") for d in pd.date_range(G0.normalize(), G1.normalize())]
    out = {}
    for an in ANIMALS:
        z = load_zone_c(an, dates, rois)
        zc = np.zeros(span, np.int8)
        if len(z):
            zz = z.reindex(pd.date_range(G0, periods=span, freq="1s"))
            zc = np.select([zz.eq("house_1").to_numpy(), zz.eq("house_2").to_numpy(), zz.eq("field").to_numpy()], [1, 2, 3], 0).astype(np.int8)
        out[an] = zc
        print(f"  zone {an}: " + ", ".join(f"{ZONES[i]} {c}" for i, c in enumerate(np.bincount(zc, minlength=4))), flush=True)
    if cache is not None:
        np.savez_compressed(cache, **out)
    return out


def state_timelines(recs: list[dict]) -> dict[str, np.ndarray]:
    span = int((G1 - G0).total_seconds())
    arr = {an: np.zeros(span, np.int8) for an in ANIMALS}
    for rc in recs:
        o = int((rc["start"] - G0).total_seconds())
        s = rc["state"]
        lo, hi = max(o, 0), min(o + len(s), span)
        if hi > lo:
            arr[rc["animal"]][lo:hi] = s[lo - o:hi - o]
    return arr


def mates_arrays(zone: dict[str, np.ndarray], arr: dict[str, np.ndarray]) -> dict[str, tuple[np.ndarray, ...]]:
    """Per animal B and second: n_coloc = other tagged animals in the same house as B (WISER only); n_mates = those with a
    known scored state (Phase 5); n_asleep = those in NREM or REM."""
    out = {}
    for B in zone:
        zb = zone[B]
        inh = np.isin(zb, (1, 2))
        n_c = np.zeros(len(zb), np.int16)
        n_m = np.zeros(len(zb), np.int16)
        n_s = np.zeros(len(zb), np.int16)
        for A in zone:
            if A == B:
                continue
            co = inh & (zone[A] == zb)
            n_c += co
            sa = arr.get(A, np.zeros(len(zb), np.int8))
            n_m += co & (sa != 0)
            n_s += co & np.isin(sa, (N, R))
        out[B] = (n_c, n_m, n_s)
    return out


def sun_rel(t: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Minutes from the same date's NOAA sunrise and sunset (negative = before)."""
    from sleep_quant import sun_times
    t = pd.to_datetime(t)
    days = t.dt.normalize()
    mr, ms = np.zeros(len(t)), np.zeros(len(t))
    for d in days.unique():
        sr, ss = (pd.Timestamp(x) for x in sun_times(pd.Timestamp(d).date()))
        m = (days == d).to_numpy()
        mr[m] = ((t[m] - sr).dt.total_seconds() / 60).to_numpy()
        ms[m] = ((t[m] - ss).dt.total_seconds() / 60).to_numpy()
    return mr, ms


def prep(label: str, states: Path, keys: list[str], gaps: pd.DataFrame, zone: dict[str, np.ndarray] | None) -> dict:
    """Records -> 10-s NREM steps (sleep_model.build_data) with the P variants `keys`, + clock hour, post-round flag,
    sunrise / sunset offsets and (if zone) the WISER location / company columns. Returns D (arrays) + steps + recs."""
    t0 = time.time()
    recs = records_for(states)
    vs = variant_specs()
    steps = build_data(recs, {k: vs[k] for k in keys})
    D = to_arrays(steps)
    D["hour"] = steps.hour.to_numpy().astype(float)
    D["d_prev"] = steps.d_prev.to_numpy().astype(float)
    D["post_round"] = post_round_mask(steps.animal.to_numpy().astype(str), steps.t, gaps)
    mr, ms = sun_rel(steps.t)
    D["m_rise"], D["m_set"] = mr, ms
    D["trans"] = np.select([np.abs(mr) <= TRANS_MIN, np.abs(ms) <= TRANS_MIN], [1, 2], 0).astype(np.int8)
    D["t_s"] = ((steps.t - G0).dt.total_seconds()).to_numpy().astype(np.int64)
    if zone is not None:
        arr = state_timelines(recs)
        mates = mates_arrays(zone, arr)
        ti = np.clip(D["t_s"], 0, len(next(iter(zone.values()))) - 1)
        zc = np.zeros(len(ti), np.int8)
        nc, nm, ns = (np.zeros(len(ti)) for _ in range(3))
        for an in ANIMALS:
            sel = D["animal"] == an
            j = ti[sel]
            zc[sel] = zone[an][j]
            nc[sel], nm[sel], ns[sel] = mates[an][0][j], mates[an][1][j], mates[an][2][j]
        D["zone"] = zc
        D["in_house"] = np.isin(zc, (1, 2)).astype(float)
        D["loc_field"] = (zc == 3).astype(float)
        D["loc_unknown"] = (zc == 0).astype(float)
        D["n_coloc"] = nc
        D["n_mates"] = nm
        D["mates_asleep"] = np.where(nm > 0, ns / np.maximum(nm, 1), 0.0)
        D["with_mates"] = ((D["in_house"] == 1) & (nc >= 1)).astype(float)
    print(f"[{label}] steps {len(steps)} (post-round 3 h {int(D['post_round'].sum())}), REM ends {int((D['y'] == 1).sum())}, "
          f"WAKE ends {int((D['y'] == 2).sum())}; {time.time() - t0:.0f} s", flush=True)
    return {"D": D, "steps": steps, "recs": recs, "label": label}


def subset(D: dict, m: np.ndarray) -> dict:
    return {k: (v[m] if isinstance(v, np.ndarray) and len(v) == len(m) else v) for k, v in D.items()}


# ================================================================== model specs
def specs_c1(key: str) -> dict[str, dict]:
    a = {"harm": False, "dark": True, "L1": "noD", "lnd": True, "dark_x_lnd": True, "hist": key}
    b = {"harm": True, "dark": True, "L1": "noD", "lnd": True, "dark_x_lnd": True, "hist": key}
    return {"a": a, "a_nointer": {**a, "dark_x_lnd": False}, "a_darkxday": {**a, "dark_x_day": True},
            "b": b, "b_Bfull": {**b, "dark_x_lnd": False}, "b_darkxday": {**b, "dark_x_day": True}}


# ================================================================== C1
def c1_jobs(prepd: dict, key: str, sens_keys: dict[str, str], draws: int) -> list[tuple]:
    """The C1 full-data fits of one scoring, as jobs named '<label>|<name>'."""
    lab = prepd["label"]
    D = prepd["D"]
    keep = ~D["post_round"]
    idx = np.flatnonzero(keep)
    S = specs_c1(key)
    clocks = clock_sets(D, idx)
    d_mid = (D["d_prev"] >= 120) & (D["d_prev"] < 420)
    subsets = {"steps after a 2-7-min wake": d_mid, "steps after a wake < 40 s (MA)": (D["d_prev"] > 0) & (D["d_prev"] < 40),
               "steps after REM / unknown (d = 0)": D["d_prev"] == 0}
    jobs = []
    for nm, sp in S.items():
        rat = nm.startswith("b")
        jobs.append((f"pooled:{nm}", D, idx, {**sp}, {"ratio": rat, "draws": draws if nm in ("b", "b_Bfull") else 0,
                                                     "clocks": clocks, "subsets": subsets if nm == "b" else None}))
    for slab, k2 in sens_keys.items():
        for nm in ("a", "b"):
            jobs.append((f"pooled:{nm}@{slab}", D, idx, {**S[nm], "hist": k2}, {"ratio": nm == "b", "clocks": clocks}))
    for an in sorted(set(D["animal"][idx])):
        ia = idx[D["animal"][idx] == an]
        for nm in ("a", "b"):
            jobs.append((f"animal:{an}:{nm}", D, ia, {**S[nm], "animal": False}, {"ratio": nm == "b", "clocks": clocks}))
    return [(f"{lab}|{j[0]}", *j[1:]) for j in jobs]


def c1_tables(fits: dict, label: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows, ratio_rows, pa = [], [], []
    for nm, f in fits.items():
        if not f.get("ok") or not nm.startswith("pooled:"):
            continue
        model = nm.split(":", 1)[1]
        for eq, eqn in ((0, "REM vs stay"), (1, "WAKE vs stay")):
            for term in ("dark", "lnd", "dark_x_lnd", "dark_x_day"):
                c = coef(f, f["names"], term, eq)
                if np.isfinite(c["coef"]):
                    rows.append({"scores": label, "model": model, "equation": eqn, "term": term, **c, "n_steps": f["n"],
                                 "n_rem": f["n_rem"], "clusters": f["clusters"], "converged": f["conv"]})
            if "dark_x_lnd" in f["names"] and eq == 0:
                for dl, dv in D_REF.items():
                    c = lincomb(f, f["names"], {"dark": 1.0, "dark_x_lnd": float(np.log1p(dv) - f["st_lnd"])}, eq)
                    rows.append({"scores": label, "model": model, "equation": eqn, "term": f"dark at {dl}", **c, "n_steps": f["n"],
                                 "n_rem": f["n_rem"], "clusters": f["clusters"], "converged": f["conv"]})
        if "ratio" in f:
            ci = f.get("ratio_ci", (np.nan, np.nan))
            ratio_rows.append({"scores": label, "model": model, "subset": "all NREM steps (post-round 3 h excluded)", "ratio": f["ratio"],
                               "ci_lo": ci[0], "ci_hi": ci[1], "ln_ratio": np.log(f["ratio"]), "ln_ratio_se": f.get("lratio_se", np.nan),
                               "p_rem_night": f["p_night_mean"], "p_rem_day": f["p_day_mean"], "n_steps": f["n"]})
            for sub, (r, n) in f.get("ratio_subsets", {}).items():
                ratio_rows.append({"scores": label, "model": model, "subset": sub, "ratio": r, "ln_ratio": np.log(r), "n_steps": n})
    for nm, f in fits.items():
        if not nm.startswith("animal:"):
            continue
        _, an, model = nm.split(":")
        r = {"scores": label, "animal": an, "model": model, "ok": f.get("ok", False)}
        if f.get("ok"):
            c = coef(f, f["names"], "dark", 0)
            r.update(dark_coef=c["coef"], dark_ci_lo=c["ci_lo"], dark_ci_hi=c["ci_hi"], n_steps=f["n"], n_rem=f["n_rem"],
                     dark_x_lnd=coef(f, f["names"], "dark_x_lnd", 0)["coef"])
            if "ratio" in f:
                r["ratio"] = f["ratio"]
        pa.append(r)
    return pd.DataFrame(rows), pd.DataFrame(ratio_rows), pd.DataFrame(pa)


def c1_heldout(prepd: dict, key: str, workers: int) -> pd.DataFrame:
    D = subset(prepd["D"], ~prepd["D"]["post_round"])
    S = specs_c1(key)
    res = run_heldout(D, {"Bfull": S["b_Bfull"], "Bfull_dxl": S["b"], "a": S["a"]}, folds_of(D), workers)
    F, FA = ho_tables(res, D)
    lab = prepd["label"]
    rows = [cmp(F, FA, "Bfull", "Bfull_dxl", "B-full + dark x ln(1+d) vs B-full"),
            cmp(F, FA, "a", "Bfull_dxl", "(b) clock model vs (a) literal model (no 2-harmonic clock)")]
    T = pd.DataFrame(rows)
    T.insert(0, "scores", lab)
    return T


# ================================================================== C2
def c2_specs(key: str) -> dict[str, dict]:
    base = {"harm": True, "dark": False, "L1": "noD", "lnd": False, "hist": key}
    return {"clock": base, "step": {**base, "dark": True}, "lnd": {**base, "lnd": True}, "step_lnd": {**base, "dark": True, "lnd": True}}


def c2_run(prepd: dict, key: str, workers: int) -> dict:
    D0 = prepd["D"]
    m = (D0["trans"] > 0) & (D0["d_prev"] < 420) & ~D0["post_round"]
    D = subset(D0, m)
    S = c2_specs(key)
    res = run_heldout(D, S, folds_of(D), workers)
    out = {"n": int(m.sum()), "n_rem": int((D["y"] == 1).sum()), "rows": []}
    for sub, mask in (("both transitions", None), ("dawn (+-2 h of sunrise)", D["trans"] == 1), ("dusk (+-2 h of sunset)", D["trans"] == 2)):
        F, FA = ho_tables(res, D, mask)
        for lo, hi, lab in (("clock", "step", "+ light step vs 2-harmonic clock (pass rule)"), ("clock", "lnd", "+ ln(1+d) vs 2-harmonic clock"),
                            ("lnd", "step_lnd", "+ light step on top of clock + ln(1+d)")):
            r = cmp(F, FA, lo, hi, lab)
            r["steps_subset"] = sub
            r["train"] = "transition steps only"
            out["rows"].append(r)
    # sensitivity: train on all NREM steps of the earlier blocks (post-round excluded), test on the transition steps
    Dall = subset(D0, ~D0["post_round"])
    mt = (Dall["trans"] > 0) & (Dall["d_prev"] < 420)
    folds = [(tr, te[mt[te]]) for tr, te in folds_of(Dall)]
    folds = [(tr, te) for tr, te in folds if len(te)]
    res2 = run_heldout(Dall, S, folds, workers)
    F, FA = ho_tables(res2, Dall)
    for lo, hi, lab in (("clock", "step", "+ light step vs 2-harmonic clock (pass rule)"), ("clock", "lnd", "+ ln(1+d) vs 2-harmonic clock"),
                        ("lnd", "step_lnd", "+ light step on top of clock + ln(1+d)")):
        r = cmp(F, FA, lo, hi, lab)
        r["steps_subset"] = "both transitions"
        r["train"] = "all NREM steps (sensitivity)"
        out["rows"].append(r)
    # description: empirical REM hazard per 15-min bin around each transition; full-fit mean predictions (clock vs step)
    idx = np.arange(len(D["y"]))
    levels = sorted(set(D["animal"]))
    pred = {}
    for nm in ("clock", "step"):
        X, _, st = design(D, idx, S[nm], None, levels)
        f = mnl_fit(X, D["y"].astype(int))
        pred[nm] = mnl_predict(X, f["B"])[:, 1]
    hz = []
    for tr_, col, lab in ((1, "m_rise", "sunrise"), (2, "m_set", "sunset")):
        mm = D["trans"] == tr_
        b = np.floor(D[col][mm] / 15) * 15 + 7.5
        g = pd.DataFrame({"bin": b, "rem": (D["y"][mm] == 1).astype(float), "clock": pred["clock"][mm], "step": pred["step"][mm]})
        a = g.groupby("bin").agg(n=("rem", "size"), hazard=("rem", "mean"), pred_clock=("clock", "mean"), pred_step=("step", "mean")).reset_index()
        a["se"] = np.sqrt(a.hazard * (1 - a.hazard) / a.n)
        a.insert(0, "transition", lab)
        hz.append(a)
    out["hazard"] = pd.concat(hz, ignore_index=True)
    cnt = pd.DataFrame({"trans": D["trans"], "dark": D["dark"]}).value_counts().rename("steps").reset_index()
    cnt["transition"] = cnt.trans.map({1: "dawn", 2: "dusk"})
    cnt["side"] = np.where(cnt.dark == 1, "dark", "light")
    out["counts"] = cnt[["transition", "side", "steps"]].sort_values(["transition", "side"])
    return out


# ================================================================== C3
def c3_groupspec(key: str) -> dict:
    return {**specs_c1(key)["b_Bfull"], "raw": ("loc_field", "loc_unknown", "n_coloc", "mates_asleep"), "raw_x_dark": ("n_coloc",)}


def c3_jobs(prepd: dict, key: str, draws: int, c1_fit_b: dict, c1_fit_a: dict) -> list[tuple]:
    """The C3 full-data fits of one scoring, as jobs named '<label>|<name>'."""
    lab = prepd["label"]
    D0 = prepd["D"]
    keep = ~D0["post_round"]
    idx = np.flatnonzero(keep)
    S = specs_c1(key)
    clocks = clock_sets(D0, idx)
    wm = keep & (D0["with_mates"] == 1)
    iw = np.flatnonzero(wm)
    # sensitivity (stricter company restriction): house with mates, >= 1 of them with a known state, and all of those asleep
    ia_s = np.flatnonzero(wm & (D0["n_mates"] >= 1) & (D0["mates_asleep"] == 1))
    grp = c3_groupspec(key)
    c_all = {"c_lnd": c1_fit_a["st_lnd"]}           # the dark x ln d interaction centred where the all-step fit centred it
    jobs = [("restricted:a", D0, iw, {**S["a"], **c_all}, {}),
            ("restricted:b", D0, iw, {**S["b"], "c_lnd": c1_fit_b["st_lnd"]}, {"ratio": True, "draws": draws, "clocks": clocks}),
            ("strict:a", D0, ia_s, {**S["a"], **c_all}, {}),
            ("strict:b", D0, ia_s, {**S["b"], "c_lnd": c1_fit_b["st_lnd"]}, {"ratio": True, "draws": draws, "clocks": clocks}),
            ("all:group", D0, idx, grp, {"ratio": True, "clocks": clocks}),
            ("all:b_on_restricted_mix", D0, idx, S["b"], {"ratio": True, "clocks": clocks, "subsets": {"house-with-mates steps": wm}})]
    for an in sorted(set(D0["animal"][idx])):
        ia = idx[D0["animal"][idx] == an]
        jobs.append((f"animal:{an}:group", D0, ia, {**grp, "animal": False}, {}))
        iwa = iw[D0["animal"][iw] == an]
        if len(iwa) > 2000:
            jobs.append((f"animal:{an}:restricted_b", D0, iwa, {**S["b"], "animal": False}, {"ratio": True, "clocks": clocks}))
    return [(f"{lab}|{j[0]}", *j[1:]) for j in jobs]


def c3_run(prepd: dict, key: str, workers: int, fits: dict, c1_fit_b: dict, c1_fit_a: dict) -> dict:
    """Tables from the C3 fits of one scoring (`fits` = split_fits of the pooled run) + the held-out location / group test."""
    D0 = prepd["D"]
    keep = ~D0["post_round"]
    S = specs_c1(key)
    grp = c3_groupspec(key)
    lab = prepd["label"]
    # descriptive composition
    comp = []
    for ph, dk in (("night", 1.0), ("day", 0.0)):
        m = keep & (D0["dark"] == dk)
        tot = m.sum()
        for nm, mm in (("house, >= 1 co-located mate", m & (D0["with_mates"] == 1)), ("house, alone", m & (D0["in_house"] == 1) & (D0["n_coloc"] == 0)),
                       ("field", m & (D0["loc_field"] == 1)), ("WISER unknown", m & (D0["loc_unknown"] == 1))):
            comp.append({"scores": lab, "phase": ph, "where": nm, "steps": int(mm.sum()), "share": float(mm.sum() / max(tot, 1)),
                         "rem_per_1000_steps": float(1000 * (D0["y"][mm] == 1).mean()) if mm.sum() else np.nan,
                         "wake_per_1000_steps": float(1000 * (D0["y"][mm] == 2).mean()) if mm.sum() else np.nan,
                         "mean_n_coloc": float(D0["n_coloc"][mm].mean()) if mm.sum() else np.nan})
    COMP = pd.DataFrame(comp)
    # group coefficients
    g = fits["all:group"]
    coefs = []
    for eq, eqn in ((0, "REM vs stay"), (1, "WAKE vs stay")):
        for term, w in (("n_coloc, light", {"n_coloc": 1.0}), ("n_coloc, dark", {"n_coloc": 1.0, "dark_x_n_coloc": 1.0}),
                        ("n_coloc dark - light", {"dark_x_n_coloc": 1.0}), ("mates_asleep", {"mates_asleep": 1.0}),
                        ("location field (vs house)", {"loc_field": 1.0}), ("location unknown (vs house)", {"loc_unknown": 1.0}),
                        ("dark (at mean n_coloc)", {"dark": 1.0})):
            c = lincomb(g, g["names"], w, eq) if g.get("ok") else {"coef": np.nan}
            sg_pos, sg_n = 0, 0
            for an in ANIMALS:
                fa = fits.get(f"animal:{an}:group")
                if fa is None or not fa.get("ok"):
                    continue
                if not all(k in fa["names"] for k in w):
                    continue
                v = lincomb(fa, fa["names"], w, eq)["coef"]
                if np.isfinite(v):
                    sg_n += 1
                    sg_pos += int(v > 0)
            coefs.append({"scores": lab, "equation": eqn, "term": term, **c, "animals_positive": sg_pos, "animals": sg_n})
    CO = pd.DataFrame(coefs)
    # restriction comparison
    rb, ra = fits["restricted:b"], fits["restricted:a"]
    rmix = fits["all:b_on_restricted_mix"]
    d_all_a = coef(c1_fit_a, c1_fit_a["names"], "dark", 0)
    d_res_a = coef(ra, ra["names"], "dark", 0) if ra.get("ok") else {"coef": np.nan, "ci_lo": np.nan, "ci_hi": np.nan}
    res_rows = [{"scores": lab, "quantity": "(b) ln night/day ratio of p(REM per step)", "all_steps": np.log(c1_fit_b["ratio"]),
                 "all_ci": f"[{np.log(c1_fit_b['ratio_ci'][0]):+.3f}, {np.log(c1_fit_b['ratio_ci'][1]):+.3f}]",
                 "house_with_mates": np.log(rb["ratio"]) if rb.get("ok") else np.nan,
                 "house_with_mates_ci": (f"[{np.log(rb['ratio_ci'][0]):+.3f}, {np.log(rb['ratio_ci'][1]):+.3f}]" if rb.get("ok") else ""),
                 "change": (np.log(rb["ratio"]) - np.log(c1_fit_b["ratio"])) if rb.get("ok") else np.nan,
                 "n_all": c1_fit_b["n"], "n_house_with_mates": rb.get("n", 0)},
                {"scores": lab, "quantity": "(a) dark coefficient, REM vs stay", "all_steps": d_all_a["coef"],
                 "all_ci": f"[{d_all_a['ci_lo']:+.3f}, {d_all_a['ci_hi']:+.3f}]", "house_with_mates": d_res_a["coef"],
                 "house_with_mates_ci": f"[{d_res_a['ci_lo']:+.3f}, {d_res_a['ci_hi']:+.3f}]", "change": d_res_a["coef"] - d_all_a["coef"],
                 "n_all": c1_fit_a["n"], "n_house_with_mates": ra.get("n", 0)}]
    sb, sa = fits["strict:b"], fits["strict:a"]
    if sb.get("ok"):
        res_rows.append({"scores": lab, "quantity": "sensitivity: (b) ln ratio, house with mates, all known mates asleep",
                         "all_steps": np.log(c1_fit_b["ratio"]), "all_ci": res_rows[0]["all_ci"], "house_with_mates": np.log(sb["ratio"]),
                         "house_with_mates_ci": f"[{np.log(sb['ratio_ci'][0]):+.3f}, {np.log(sb['ratio_ci'][1]):+.3f}]",
                         "change": np.log(sb["ratio"]) - np.log(c1_fit_b["ratio"]), "n_all": c1_fit_b["n"], "n_house_with_mates": sb["n"]})
    if sa.get("ok"):
        c_ = coef(sa, sa["names"], "dark", 0)
        res_rows.append({"scores": lab, "quantity": "sensitivity: (a) dark coefficient, house with mates, all known mates asleep",
                         "all_steps": d_all_a["coef"], "all_ci": res_rows[1]["all_ci"], "house_with_mates": c_["coef"],
                         "house_with_mates_ci": f"[{c_['ci_lo']:+.3f}, {c_['ci_hi']:+.3f}]", "change": c_["coef"] - d_all_a["coef"],
                         "n_all": c1_fit_a["n"], "n_house_with_mates": sa["n"]})
    extra = [{"scores": lab, "quantity": "(b) ln ratio, all-step model, standardised over house-with-mates steps",
              "value": np.log(rmix["ratio_subsets"]["house-with-mates steps"][0]) if rmix.get("ok") else np.nan},
             {"scores": lab, "quantity": "(b) ln ratio, all steps, model + location + group terms", "value": np.log(g["ratio"]) if g.get("ok") else np.nan}]
    pa = []
    for an in ANIMALS:
        fa = fits.get(f"animal:{an}:restricted_b")
        if fa is not None and fa.get("ok"):
            pa.append({"scores": lab, "animal": an, "ratio_house_with_mates": fa["ratio"], "n_steps": fa["n"], "n_rem": fa["n_rem"]})
    # held out: location, group terms
    D = subset(D0, keep)
    loc = {**S["b_Bfull"], "raw": ("loc_field", "loc_unknown")}
    res = run_heldout(D, {"Bfull": S["b_Bfull"], "loc": loc, "group": grp}, folds_of(D), workers)
    F, FA = ho_tables(res, D)
    HO = pd.DataFrame([cmp(F, FA, "Bfull", "loc", "+ location (field / unknown vs house) on B-full"),
                       cmp(F, FA, "loc", "group", "+ group terms (n_coloc, n_coloc x dark, mates_asleep) on B-full + location")])
    HO.insert(0, "scores", lab)
    return {"COMP": COMP, "CO": CO, "RES": pd.DataFrame(res_rows), "EXTRA": pd.DataFrame(extra), "PA": pd.DataFrame(pa), "HO": HO}


# ================================================================== C4
def c4_table(recs: list[dict], zone: dict[str, np.ndarray], w: pd.DataFrame, label: str) -> pd.DataFrame:
    """Per animal and night_of date d: night = [sunset(d), sunrise(d+1)), day = [sunrise(d+1), sunset(d+1)) (as Phase 3b)."""
    from sleep_quant import sun_times
    arr = state_timelines(recs)
    rows = []
    con = w[w.source.astype(str).str.startswith("on-site")]
    for an in ANIMALS:
        s, zc = arr[an], zone.get(an)
        for d in pd.date_range("2026-08-30", "2026-09-11"):
            ss0 = pd.Timestamp(sun_times(d.date())[1])
            sr1, ss1 = (pd.Timestamp(x) for x in sun_times((d + pd.Timedelta(days=1)).date()))
            for per, (a, b) in (("night", (ss0, sr1)), ("day", (sr1, ss1))):
                ia, ib = int((a - G0).total_seconds()), int((b - G0).total_seconds())
                seg = s[ia:ib]
                rec = int((seg != 0).sum())
                L = ib - ia
                r = {"scores": label, "animal": an, "night_of": d, "period": per, "t0": a, "t1": b, "cover": rec / L,
                     "day": ((a + (b - a) / 2) - RELEASE).total_seconds() / 86400}
                r["sleep_share_pct"] = 100 * float(np.isin(seg, (N, R)).sum() / rec) if rec else np.nan
                r["nrem_min_per_h"] = 60 * float((seg == N).sum() / rec) if rec else np.nan
                r["rem_min_per_h"] = 60 * float((seg == R).sum() / rec) if rec else np.nan
                if zc is not None:
                    zz = zc[ia:ib]
                    kn = zz > 0
                    r["wiser_cover"] = float(kn.mean()) if len(kn) else np.nan
                    r["outside_pct"] = 100 * float((zz[kn] == 3).mean()) if kn.sum() > 0.5 * L else np.nan
                ww = w[(w.t >= a) & (w.t < b)]
                r["temp_C"] = float(ww.temp_C.mean()) if len(ww) >= 0.5 * L / 300 else np.nan
                cc = con[(con.t >= a) & (con.t < b)]
                r["rain_mm"] = float((cc.rain_rate_mmh.fillna(0) * 5 / 60).sum()) if len(cc) >= 0.5 * L / 300 else np.nan
                rows.append(r)
    return pd.DataFrame(rows)


def c4_models(T: pd.DataFrame) -> pd.DataFrame:
    import statsmodels.api as sm
    rows = []
    for (lab, per), g0 in T.groupby(["scores", "period"]):
        for y in ("sleep_share_pct", "nrem_min_per_h"):
            g = g0[(g0.cover >= 0.5)].dropna(subset=[y, "temp_C", "rain_mm", "outside_pct", "day"]).copy()
            if len(g) < 12:
                continue
            fe = pd.get_dummies(g.animal, prefix="an", drop_first=True, dtype=float)
            cl = pd.factorize(g.night_of)[0]

            def fit(xs):
                X = sm.add_constant(pd.concat([g[xs].astype(float), fe], axis=1) if xs else fe, has_constant="add")
                return sm.OLS(g[y].astype(float), X).fit(cov_type="cluster", cov_kwds={"groups": cl}, use_t=True)
            f0 = fit([])
            ssr0 = float(f0.ssr)
            sst = float(((g[y] - g[y].mean()) ** 2).sum())
            res = {"scores": lab, "period": per, "outcome": y, "n_animal_days": len(g), "dates": g.night_of.nunique(),
                   "animals": g.animal.nunique(), "R2_animal_FE": 1 - ssr0 / sst}
            for nm, xs in (("weather", ["temp_C", "rain_mm"]), ("weather_activity", ["temp_C", "rain_mm", "outside_pct"]),
                           ("day", ["day"]), ("full", ["temp_C", "rain_mm", "outside_pct", "day"])):
                f = fit(xs)
                res[f"R2_{nm}"] = float(f.rsquared)
                res[f"R2within_{nm}"] = 1 - float(f.ssr) / ssr0
                if nm == "full":
                    for x in xs:
                        ci = f.conf_int().loc[x]
                        res[f"{x}_coef"], res[f"{x}_lo"], res[f"{x}_hi"], res[f"{x}_p"] = float(f.params[x]), float(ci.iloc[0]), float(ci.iloc[1]), float(f.pvalues[x])
                if nm == "day":
                    res["day_alone_coef"], res["day_alone_p"] = float(f.params["day"]), float(f.pvalues["day"])
            # per-animal day slopes in the full model (signs)
            sg = []
            for an, ga in g.groupby("animal"):
                if len(ga) >= 7:
                    Xa = sm.add_constant(ga[["temp_C", "rain_mm", "outside_pct", "day"]].astype(float), has_constant="add")
                    sg.append(float(sm.OLS(ga[y].astype(float), Xa).fit().params["day"]))
            res["animals_day_coef_neg"], res["animals_fit"] = int(np.sum(np.array(sg) < 0)), len(sg)
            rows.append(res)
    return pd.DataFrame(rows)


# ================================================================== report helpers
def tbl(df: pd.DataFrame | None, nd: int = 3) -> list[str]:
    from sleep_quant import md_table
    if df is None or not len(df):
        return ["(no rows)"]
    d = df.copy()
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].round(nd)
    return md_table(d)


def fci(c: float, lo: float, hi: float, nd: int = 3) -> str:
    return f"{c:+.{nd}f} [{lo:+.{nd}f}, {hi:+.{nd}f}]" if np.isfinite(c) else "n/a"


def chosen_key(path: Path = CHOSEN_CSV, wait_s: int = 0) -> tuple[str, pd.DataFrame]:
    t0 = time.time()
    while not path.exists():
        if time.time() - t0 > wait_s:
            raise FileNotFoundError(path)
        print(f"waiting for {path.name} (Step B still running) ...", flush=True)
        time.sleep(180)
    CH = pd.read_csv(path)
    ks = CH.chosen_B.dropna().astype(str).str.replace("B:", "", regex=False)
    return ks.mode().iloc[0], CH


DEFINITIONS = [
    "## Definitions", "",
    r"Time is field-PC local time. States per second $s_t \in \{0\ \text{unknown}, 1\ \text{WAKE}, 3\ \text{NREM}, 5\ \text{REM}\}$. "
    r"Records, scorings, the cut at 2026-09-11 19:40, light (NOAA sunrise–sunset, `sleep_quant.sun_times`; never clock hours) "
    r"and the day-half blocks are those of Steps A and B.",
    "",
    "### The step model (shared by C1–C3; Step B's machinery)",
    r"- **NREM step.** Every 10 s of every NREM bout (`sleep_schedule.record_steps_s`); outcome $y \in \{$stay, REM, WAKE$\}$ = "
    r"what follows the bout if it ends inside the step. History is taken at the bout start; elapsed $e$ = s since the bout start.",
    r"- **Counter P** (min). Step B's REM-entry count at the step: $P_t = P_{\text{bout start}} + e/60$; NREM adds 1/60 per s, a "
    r"wake of length $d$ multiplies P by $e^{-d/\tau_w}$, a REM bout of length $r$ by $e^{-r/\kappa}$, unknown epochs freeze it "
    r"(`sleep_model.counter_starts`). $(\tau_w, \kappa)$ = the grid point chosen most often by Step B's nested forward chaining "
    r"(FINAL; stated in the Data section). Sensitivities: pause ($\tau_w = \infty$, same $\kappa$) and hard reset at wakes ≥ 7 min "
    r"(`R7`, same $\kappa$).",
    r"- **d** (s). Length of the WAKE bout that precedes the step's NREM bout (0 if the preceding bout is REM or unknown); "
    r"$\ln d$ in the text means $\ln(1 + d)$.",
    r"- **Multinomial hazard.** $\Pr(y = j \mid x) = e^{\eta_j} / (1 + e^{\eta_R} + e^{\eta_W})$, $\eta_{stay} = 0$; "
    r"$\eta_j = \alpha_j + x^\top\beta_j$; fitted by Newton–Raphson with an L2 penalty $10^{-4}\lVert\beta\rVert^2/2$ "
    r"(intercepts free; the same as Step B's sklearn $C = 10^4$). A coefficient on REM vs stay is a log-odds ratio of entering "
    r"REM in the next 10 s rather than staying in NREM; negative = REM less likely.",
    r"- **Terms.** elapsed = cubic B-spline of $\ln(e + 5)$ (4 knots); hist = cubic B-spline of $\ln(1 + P_t)$ (4 knots); "
    r"T_day = days since the release (2026-08-30 19:00), z-scored; has_anchor (a REM earlier in the record); L1 without its "
    r"ln d = previous bout REM, previous bout unknown, wake share of the last 10 min (z-scored); "
    r"$\ell = \ln(1+d) - \overline{\ln(1+d)}$ (centred on the fitted steps' mean, unscaled); dark ∈ {0, 1} at the step, "
    r"unscaled; clock = $(\sin, \cos)(2\pi k h/24)$, $k = 1, 2$, $h$ = clock hour of the step; animal intercepts.",
    r"- **Cluster-robust CI.** $\hat V = H^{-1}\big(\sum_g U_g U_g^\top\big)H^{-1}\,G/(G-1)$ over day-half blocks $g$ "
    r"($U_g$ = summed per-step scores of block $g$, $H$ = penalised information); 95 % CI $= \hat\beta \pm 1.96\,\widehat{se}$; "
    r"linear combinations $w^\top\hat\beta$ with $\widehat{se} = \sqrt{w^\top \hat V w}$.",
    r"- **Post-round exclusion.** Steps in $[g_{end}, g_{end} + 3\,\text{h})$ of a Phase-0 gap of the same animal with cause "
    r"`round_logged` / `round_inferred` are dropped from every fit (plan section 3); the counters still run through them.",
    r"- **Held out (Δ).** Forward chaining over the day-half blocks (train on all earlier blocks, test the next; the first 6 "
    r"blocks only train; `sleep_model.folds_of`); per-step log loss $-\ln \hat p(y)$; $\Delta = 100(\bar\ell_{hi} - \bar\ell_{lo})/\bar\ell_{lo}$ "
    r"(step-weighted over folds); 95 % CI by bootstrap over folds (2000); animals better = per-animal pooled Δ < 0; "
    r"**holds** = CI < 0 and ≥ 5/6 animals (`sleep_schedule_phase2.compare`).",
    "",
    "### C1",
    r"- **(a) literal model (plan).** $\eta_R = \alpha_a + \text{elapsed} + \text{hist} + \text{T\_day} + \text{has\_anchor} + "
    r"\text{L1}_{-d} + \beta_\ell \ell + \beta_{dark}\,\text{dark} + \beta_{d\ell}\,\text{dark}\cdot\ell$ (no 2-harmonic clock); "
    r"the same terms for $\eta_W$. $\beta_{dark}$ = the log-odds ratio of REM entry, dark vs light, at the mean $\ell$ and the "
    r"same P; $\beta_{d\ell}$ = the night ramp (how much more a longer prior wake lowers REM entry at night). Dark at a given "
    r"$d$: $\beta_{dark} + \beta_{d\ell}(\ln(1+d) - \overline{\ln(1+d)})$. Per animal: the same model fitted to the animal alone.",
    r"- **(b) clock model (added; Step B found the night effect in the smooth clock).** (a) + the 2-harmonic clock; with "
    r"$\beta_{d\ell} = 0$ it is Step B's B-full.",
    r"- **Standardised night / day ratio (b).** For each step $i$ (its own P, d, L1, elapsed, T_day, anchor, animal), "
    r"$\bar p_i^{night} = \frac1K\sum_k \hat p_{REM}(x_i; h = h_k^{night}, \text{dark} = 1)$ and $\bar p_i^{day}$ likewise with "
    r"the day clocks; $h_k^{\phi}$ = the $(k - \frac12)/K$ quantiles ($K = 24$) of the clock hour among the fitted steps of "
    r"phase $\phi$ (the empirical night / day clock). $\hat\rho = \sum_i \bar p_i^{night} / \sum_i \bar p_i^{day}$: < 1 = "
    r"fewer REM entries per NREM step at night at matched P and d. 95 % CI: 2.5–97.5 % of $\hat\rho$ over 300 parameter "
    r"vectors drawn from $N(\hat\beta, \hat V)$. Per animal: per-animal fits. Also standardised over sub-sets of steps "
    r"(after 2–7-min wakes, after MAs, after REM / unknown) with the same fit. For rare events $\ln\hat\rho$ is close to a log-odds.",
    "",
    "### C2",
    r"- **Transition steps.** NREM steps with $|t - \text{sunrise}| \le 120$ min (dawn) or $|t - \text{sunset}| \le 120$ min "
    r"(dusk) of the same date, $d < 420$ s, post-round 3 h excluded.",
    r"- **Models** (multinomial, same engine): clock = elapsed + hist + T_day + has_anchor + L1$_{-d}$ + 2-harmonic clock + "
    r"animal; step = clock + dark (the light step: 0 → 1 at sunset, 1 → 0 at sunrise); lnd = clock + $\ell$; step_lnd = clock + "
    r"dark + $\ell$. Held out on the transition steps (trained on the transition steps of earlier blocks; sensitivity: trained "
    r"on all NREM steps of earlier blocks). Δ per transition from the same predictions.",
    r"- **Empirical hazard.** Per 15-min bin of minutes from sunrise / sunset: REM ends / steps, SE $\sqrt{h(1-h)/n}$; with "
    r"the mean full-fit prediction of the clock and step models.",
    "",
    "### C3",
    r"- **Zone** per second (WISER default tracks, `mic_wake_pilot.load_zone` with the `m_off_animal` fixes removed): the "
    r"median position of the second, forward-filled over gaps ≤ 30 s, in house_1 / house_2 = the ROI rectangle + 14 in, else "
    r"field; unknown = no position. A house is 'same house', never body contact.",
    r"- **Company.** $n_{coloc}$ = other tagged animals in the same house at the step's second (0 if the animal is not in a "
    r"house); $n_{mates}$ = those with a known scored state (Phase 5); mates_asleep = share of them in NREM / REM (0 if none). "
    r"House-with-mates step = in a house with $n_{coloc} \ge 1$.",
    r"- **Group model.** B-full + loc_field + loc_unknown (vs house) + $n_{coloc}$ + mates_asleep + dark·$(n_{coloc} - \bar n)$ "
    r"(raw units, centred). Group size effect by phase: light $\beta_n$, dark $\beta_n + \beta_{dn}$ (per mate), on REM vs stay "
    r"and WAKE vs stay; per-animal signs from per-animal fits.",
    r"- **Restriction test.** C1 (b) $\ln\hat\rho$ and C1 (a) $\beta_{dark}$ refitted on house-with-mates steps only; change = "
    r"restricted − all steps.",
    "",
    "### C4",
    r"- **Animal-day.** For night_of date $D$: night = [sunset($D$), sunrise($D$+1)), day = [sunrise($D$+1), sunset($D$+1)) (as "
    r"Phase 3b); kept if ≥ 50 % recorded. Sleep share (%) = (NREM + REM s) / recorded s × 100; NREM min per recorded h = "
    r"NREM s / recorded s × 60.",
    r"- **Covariates.** day = days from the release to the period midpoint; temp_C = mean outdoor temperature over the period "
    r"(console, NWS KITH inside the 09-02/03 uplink hole; ≥ 50 % of 5-min samples); rain_mm = $\sum \text{rate}\,(5/60)$ over "
    r"the period's console samples (mm); outside_pct = share of WISER-known seconds of the period in the field zone (≥ 50 % known).",
    r"- **Models.** OLS $y_{a,D} = \alpha_a + \gamma^\top z_{a,D} + \varepsilon$, SEs clustered by night_of date, t(G − 1) "
    r"inference. $R^2_{within}(z) = 1 - SSR(z)/SSR(\text{animal FE only})$ = the share of the within-animal variation explained "
    r"by $z$. Sets: weather (temp, rain), weather + activity (+ outside_pct), day, full (all four).",
    "",
]


# ================================================================== figures
def fig_c1(PA: pd.DataFrame, RT: pd.DataFrame, CO: pd.DataFrame, path: Path, gc: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sleep_quant import save_fig
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.4))
    labs = list(dict.fromkeys(PA.scores))
    for j, lab in enumerate(labs):
        off = (j - (len(labs) - 1) / 2) * 0.18
        g = PA[(PA.scores == lab) & (PA.model == "a") & PA.ok]
        x = np.arange(len(g))
        axs[0].errorbar(x + off, g.dark_coef, yerr=np.nan_to_num([np.maximum(g.dark_coef - g.dark_ci_lo, 0), np.maximum(g.dark_ci_hi - g.dark_coef, 0)]),
                        fmt="o", ms=5, color=COL[lab], label=lab, capsize=2, lw=1)
        p = CO[(CO.scores == lab) & (CO.model == "a") & (CO.equation == "REM vs stay") & (CO.term == "dark")]
        if len(p):
            axs[0].errorbar([len(g) + 0.5 + off], p.coef, yerr=[[float(p.coef.iloc[0] - p.ci_lo.iloc[0])], [float(p.ci_hi.iloc[0] - p.coef.iloc[0])]],
                            fmt="s", ms=7, color=COL[lab], capsize=3)
        gb = PA[(PA.scores == lab) & (PA.model == "b") & PA.ok]
        axs[1].plot(np.arange(len(gb)) + off, gb.ratio, "o", color=COL[lab], ms=5, label=lab)
        rb = RT[(RT.scores == lab) & (RT.model == "b") & RT.subset.str.startswith("all")]
        if len(rb):
            yb = np.nan_to_num([[max(float(rb.ratio.iloc[0] - rb.ci_lo.iloc[0]), 0.0)], [max(float(rb.ci_hi.iloc[0] - rb.ratio.iloc[0]), 0.0)]])
            axs[1].errorbar([len(gb) + 0.5 + off], rb.ratio, yerr=yb, fmt="s", ms=7, color=COL[lab], capsize=3)
        ticks = list(g.animal) + ["pooled"]
    axs[0].axhline(LN06, color=COL["grey"], ls="--", lw=1, label="ln 0.6 (pass threshold)")
    axs[0].axhline(0, color=COL["ink"], lw=0.6)
    axs[0].set_xticks(list(range(len(ticks) - 1)) + [len(ticks) - 0.5], ticks[:-1] + ["pooled"], fontsize=8)
    axs[0].set_ylabel("dark coefficient, REM vs stay (log-odds)")
    axs[0].set_title("C1 (a) literal model: no 2-harmonic clock; dark + ln d + dark x ln d + P", fontsize=9)
    axs[1].axhline(0.6, color=COL["grey"], ls="--", lw=1, label="0.6")
    axs[1].axhline(1.0, color=COL["ink"], lw=0.6)
    axs[1].set_xticks(list(range(len(ticks) - 1)) + [len(ticks) - 0.5], ticks[:-1] + ["pooled"], fontsize=8)
    axs[1].set_ylabel("night / day ratio of p(REM per 10-s step)")
    axs[1].set_title("C1 (b) clock model: standardised ratio at each step's own P and d", fontsize=9)
    for ax in axs:
        ax.legend(fontsize=7, frameon=False)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(f"Step C1: the night's REM-entry gain at matched prior wake and counter  {gc}", fontsize=9)
    fig.tight_layout()
    save_fig(fig, path)
    plt.close(fig)


def fig_c2(HZ: pd.DataFrame, path: Path, gc: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sleep_quant import save_fig
    labs = list(dict.fromkeys(HZ.scores))
    fig, axs = plt.subplots(len(labs), 2, figsize=(12, 3.6 * len(labs)), squeeze=False, sharey="row")
    for i, lab in enumerate(labs):
        for j, tr in enumerate(("sunrise", "sunset")):
            ax = axs[i, j]
            g = HZ[(HZ.scores == lab) & (HZ.transition == tr)]
            ax.errorbar(g.bin, 1000 * g.hazard, yerr=1000 * 1.96 * g.se, fmt="o", color=COL["ink"], ms=4, capsize=2, lw=1, label="observed (95 % CI)")
            ax.plot(g.bin, 1000 * g.pred_clock, "-", color=COL["grey"], lw=2, label="2-harmonic clock (fit)")
            ax.plot(g.bin, 1000 * g.pred_step, "-", color=COL["dark"], lw=1.5, label="clock + light step (fit)")
            ax.axvline(0, color=COL["light"], lw=1)
            ax.set_xlabel(f"minutes from {tr}")
            ax.set_title(f"{lab}: REM entries per 1000 NREM steps around {tr}", fontsize=9)
            ax.spines[["top", "right"]].set_visible(False)
        axs[i, 0].set_ylabel("REM entries per 1000 steps")
    axs[0, 0].legend(fontsize=7, frameon=False)
    fig.suptitle(f"Step C2: light step vs circadian curve at the transitions (prior wake < 7 min, post-round 3 h excluded)  {gc}", fontsize=9)
    fig.tight_layout()
    save_fig(fig, path)
    plt.close(fig)


def fig_c3(RES: pd.DataFrame, PA1: pd.DataFrame, PA3: pd.DataFrame, COMP: pd.DataFrame, path: Path, gc: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sleep_quant import save_fig
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.4))
    labs = list(dict.fromkeys(RES.scores))
    for j, lab in enumerate(labs):
        a = PA1[(PA1.scores == lab) & (PA1.model == "b") & PA1.ok].set_index("animal").ratio
        b = PA3[PA3.scores == lab].set_index("animal").ratio_house_with_mates if len(PA3) else pd.Series(dtype=float)
        common = [x for x in a.index if x in b.index]
        for an in common:
            axs[0].plot([j * 3, j * 3 + 1], [a[an], b[an]], "-o", color=COL[lab], ms=4, lw=1, alpha=0.8)
            axs[0].text(j * 3 + 1.05, b[an], an, fontsize=7, va="center", color=COL["ink"])
        r = RES[(RES.scores == lab) & RES.quantity.str.startswith("(b)")]
        if len(r):
            axs[0].plot([j * 3, j * 3 + 1], np.exp([r.all_steps.iloc[0], r.house_with_mates.iloc[0]]), "-s", color=COL["ink"], lw=2.5, ms=7)
    axs[0].set_xticks([0, 1, 3, 4][:2 * len(labs)], ["all", "house + mates", "all", "house + mates"][:2 * len(labs)], fontsize=8)
    axs[0].axhline(1, color=COL["ink"], lw=0.6)
    axs[0].set_ylabel("night / day ratio of p(REM per step), C1 (b)")
    axs[0].set_title("C3: per animal (thin) and pooled (thick); " + " | ".join(labs), fontsize=9)
    c = COMP[COMP.scores == labs[0]]
    wh = list(dict.fromkeys(c["where"]))
    x = np.arange(len(wh))
    for k, ph in enumerate(("night", "day")):
        v = [float(c[(c.phase == ph) & (c["where"] == w_)].share.iloc[0]) for w_ in wh]
        axs[1].bar(x + (k - 0.5) * 0.38, v, 0.38, color=COL["dark" if ph == "night" else "light"], label=ph)
    axs[1].set_xticks(x, wh, fontsize=8, rotation=12)
    axs[1].set_ylabel(f"share of NREM steps ({labs[0]})")
    axs[1].set_title("Where the NREM steps are (WISER house = ROI + 14 in; not contact)", fontsize=9)
    axs[1].legend(fontsize=8, frameon=False)
    for ax in axs:
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(f"Step C3: is the night effect a location / company effect?  {gc}", fontsize=9)
    fig.tight_layout()
    save_fig(fig, path)
    plt.close(fig)


def fig_c4(T: pd.DataFrame, path: Path, gc: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sleep_quant import save_fig
    lab = list(dict.fromkeys(T.scores))[0]
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.2))
    for k, per in enumerate(("night", "day")):
        g = T[(T.scores == lab) & (T.period == per) & (T.cover >= 0.5)]
        for an, ga in g.groupby("animal"):
            axs[k].plot(ga.day, ga.sleep_share_pct, "-o", ms=3, lw=1, alpha=0.8, label=an)
        m = g.groupby("night_of").agg(day=("day", "mean"), s=("sleep_share_pct", "mean"))
        axs[k].plot(m.day, m.s, "-", color=COL["ink"], lw=2.5, label="mean")
        axs[k].set_xlabel("days since release")
        axs[k].set_ylabel("sleep share of recorded time (%)")
        axs[k].set_title(f"{lab}: {per} sleep share per animal", fontsize=9)
        axs[k].spines[["top", "right"]].set_visible(False)
    axs[0].legend(fontsize=7, frameon=False, ncol=2)
    g = T[(T.scores == lab) & (T.animal == T.animal.iloc[0])]
    for per, c in (("night", COL["dark"]), ("day", COL["light"])):
        gg = g[g.period == per]
        axs[2].plot(gg.day, gg.temp_C, "-o", color=c, ms=3, label=f"{per} mean temp (°C)")
    ax2 = axs[2].twinx()
    o = T[(T.scores == lab)].groupby(["period", "night_of"]).agg(day=("day", "mean"), out=("outside_pct", "mean")).reset_index()
    for per, c in (("night", COL["dark"]), ("day", COL["light"])):
        oo = o[o.period == per]
        ax2.plot(oo.day, oo.out, "--", color=c, lw=1, label=f"{per} WISER outside (%)")
    axs[2].set_xlabel("days since release")
    axs[2].set_ylabel("temperature (°C)")
    ax2.set_ylabel("time outside the houses (%, mean over animals)")
    axs[2].legend(fontsize=7, frameon=False, loc="upper left")
    ax2.legend(fontsize=7, frameon=False, loc="upper right")
    axs[2].set_title("covariates", fontsize=9)
    fig.suptitle(f"Step C4: the 12-day drift and its candidate covariates  {gc}", fontsize=9)
    fig.tight_layout()
    save_fig(fig, path)
    plt.close(fig)


# ================================================================== step C
def stepC(a) -> None:
    from _common import git_commit, write_json
    from output_paths import figure_dir, report_dir, run_dir
    from sleep_schedule_temp import weather_anomaly
    t_all = time.time()
    parts = [p for p in ("c1", "c2", "c3", "c4") if p in set(a.parts)]
    out = run_dir("sleep_explore_C" + ("_scratch" if a.scratch else ""), "2026c")
    rd, fd = (out, out) if a.scratch else (report_dir("2026c", "ephys_spikes"), figure_dir("2026c", "ephys_spikes"))
    gc = git_commit()
    times = {}
    if a.p_key:
        key, CH = a.p_key, None
    else:
        key, CH = chosen_key(wait_s=a.wait_min * 60)
    kappa = key.split("_k")[-1]
    sens = {"pause": f"P_twinf_k{kappa}", "hard reset >= 7 min": f"R7_k{kappa}"}
    keys = [key] + list(sens.values())
    print(f"P key {key}; sensitivities {sens}", flush=True)
    gaps = gaps_table()
    t0 = time.time()
    zc = Path(a.zone_cache) if a.zone_cache else out / "zone_per_second.npz"
    zone = zone_arrays(zc) if ({"c3", "c4"} & set(parts)) else None
    if zone is not None and zc != out / "zone_per_second.npz":
        np.savez_compressed(out / "zone_per_second.npz", **zone)
    times["zones"] = time.time() - t0
    P = {}
    for lab in a.scorings:
        t0 = time.time()
        P[lab] = prep(lab, SCORINGS[lab], keys, gaps, zone)
        times[f"prep_{lab}"] = time.time() - t0
    sections, verdicts, csvs = [], [], []

    def save(df: pd.DataFrame, name: str) -> None:
        p = rd / f"ephys_spikes_sleep_explore_C_{name}_2026c.csv"
        df.to_csv(p, index=False)
        csvs.append(p.name)

    labs = list(P)
    c1fits = {}
    # ------------------------------------------------------------ C1
    if "c1" in parts or "c3" in parts:
        t0 = time.time()
        CO, RT, PA, HO = [], [], [], []
        allf = run_jobs([j for lab in labs for j in c1_jobs(P[lab], key, sens, a.draws)], a.workers)   # both scorings in one pool
        print(f"C1 fits done ({time.time() - t0:.0f} s)", flush=True)
        for lab in labs:
            fits = split_fits(allf, lab)
            c1fits[lab] = fits
            co, rt, pa = c1_tables(fits, lab)
            CO.append(co)
            RT.append(rt)
            PA.append(pa)
            if "c1" in parts:
                HO.append(c1_heldout(P[lab], key, a.workers))
            print(f"C1 {lab} done ({time.time() - t0:.0f} s)", flush=True)
        CO, RT, PA = (pd.concat(x, ignore_index=True) for x in (CO, RT, PA))
        HO = pd.concat(HO, ignore_index=True) if HO else pd.DataFrame()
        times["c1"] = time.time() - t0
    if "c1" in parts:
        for df, nm in ((CO, "c1_coef"), (RT, "c1_ratio"), (PA, "c1_per_animal"), (HO, "c1_heldout")):
            save(df, nm)
        fig_c1(PA, RT, CO, fd / "ephys_spikes_sleep_explore_C_c1_2026c.png", gc)
        vl = []
        ok_a = {}
        for lab in labs:
            d = CO[(CO.scores == lab) & (CO.model == "a") & (CO.equation == "REM vs stay") & (CO.term == "dark")].iloc[0]
            r = CO[(CO.scores == lab) & (CO.model == "a") & (CO.equation == "REM vs stay") & (CO.term == "dark_x_lnd")].iloc[0]
            pa = PA[(PA.scores == lab) & (PA.model == "a") & PA.ok]
            neg, strict = int((pa.dark_coef < 0).sum()), int((pa.dark_coef <= LN06).sum())
            ok_a[lab] = {"coef": d.coef, "size": bool(d.coef <= LN06), "rats": neg >= 5, "neg": neg, "strict": strict, "n": len(pa),
                         "ci_hi": d.ci_hi}
            vl.append(f"- **{lab}, (a) literal:** dark {fci(d.coef, d.ci_lo, d.ci_hi)} (odds ratio {np.exp(d.coef):.2f}; threshold ln 0.6 = "
                      f"{LN06:+.3f}); per animal dark < 0 in {neg}/{len(pa)}, ≤ ln 0.6 in {strict}/{len(pa)}; night ramp dark × ln(1+d) "
                      f"{fci(r.coef, r.ci_lo, r.ci_hi)} → size {'met' if d.coef <= LN06 else 'NOT met'}, rats {'met' if neg >= 5 else 'NOT met'}.")
        p2 = ok_a.get("pass2med")
        f1 = ok_a.get("FINAL", ok_a[labs[0]])
        same_sign = p2 is None or np.sign(p2["coef"]) == np.sign(f1["coef"])
        va = "PASS" if (f1["size"] and f1["rats"] and same_sign) else ("PARTIAL" if (f1["ci_hi"] < 0 and f1["rats"] and same_sign) else "FAIL")
        vlb, ok_b = [], {}
        for lab in labs:
            rb = RT[(RT.scores == lab) & (RT.model == "b") & RT.subset.str.startswith("all")].iloc[0]
            pb = PA[(PA.scores == lab) & (PA.model == "b") & PA.ok]
            lt1, le06 = int((pb.ratio < 1).sum()), int((pb.ratio <= 0.6).sum())
            ok_b[lab] = {"ratio": rb.ratio, "lt1": lt1, "n": len(pb), "ci_hi": rb.ci_hi}
            sub = RT[(RT.scores == lab) & (RT.model == "b") & ~RT.subset.str.startswith("all")]
            vlb.append(f"- **{lab}, (b) clock model:** night / day ratio {rb.ratio:.2f} [{rb.ci_lo:.2f}, {rb.ci_hi:.2f}] (ln {np.log(rb.ratio):+.3f}); "
                       f"per animal < 1 in {lt1}/{len(pb)}, ≤ 0.6 in {le06}/{len(pb)}; within sub-sets: "
                       + "; ".join(f"{s.subset} {s.ratio:.2f}" for s in sub.itertuples()) + ".")
        fb = ok_b.get("FINAL", ok_b[labs[0]])
        pb2 = ok_b.get("pass2med")
        vb = "PASS" if (fb["ratio"] <= 0.6 and fb["lt1"] >= 5 and (pb2 is None or pb2["ratio"] < 1)) else (
            "PARTIAL" if (fb["ci_hi"] < 1 and fb["lt1"] >= 5) else "FAIL")
        sens_rows = CO[(CO.equation == "REM vs stay") & (CO.term == "dark") & CO.model.str.startswith("a")][["scores", "model", "coef", "ci_lo", "ci_hi"]]
        sens_rat = RT[RT.subset.str.startswith("all")][["scores", "model", "ratio", "ci_lo", "ci_hi", "ln_ratio"]]
        L = ["## C1 — the night's REM-entry gain, independent of the prior wake?", "",
             "**Plan pass rule (C1, quoted):** \"Pass for 'the night is a gain independent of the prior wake': the dark coefficient on "
             "REM vs stay is ≤ ln 0.6 with ln d and P in the model, ≥ 5/6 rats, same sign on `pass2med`. dark × ln d is reported as the "
             "night-only ramp.\" Operationalised on form (a) (the plan's literal model, without the 2-harmonic clock): the pooled FINAL "
             "coefficient (at the mean ln(1+d)) ≤ ln 0.6 = −0.511, ≥ 5 of 6 per-animal coefficients < 0 (the strict count ≤ ln 0.6 is "
             "reported too, as in A3), and the pooled pass2med coefficient < 0. PARTIAL = the direction holds (CI < 0, ≥ 5/6 rats, same "
             "sign) but not the size.", "",
             "**Form (b) is added, not in the plan:** Step B found that the dark step adds nothing once the 2-harmonic clock and P are "
             "in (+0.05 %, n.s.); the night effect is carried by the smooth clock. (b) therefore reads the night / day contrast from the "
             "whole clock (harmonics + step) as a standardised ratio at each step's own P and d. The analogous rule (ratio ≤ 0.6, ≥ 5/6 "
             "rats < 1, pass2med < 1) is applied to it for orientation only; it is not a plan rule.", "",
             "For reference, Step A3's model-free matched-episode ratios (REM bouts per NREM hour, dark / light, after 2–7-min wakes) "
             "were 0.41 (FINAL) and 0.52 (pass2med), 6/6 rats < 1.", "",
             "### Coefficients (pooled; cluster-robust CI by block)", "",
             "Main models; every model and term (also the sensitivities below) is in `ephys_spikes_sleep_explore_C_c1_coef_2026c.csv`.", "",
             *tbl(CO[CO.model.isin(["a", "b", "b_Bfull"])].drop(columns=["clusters", "converged"])), "",
             "### Night / day ratios (b)", "", *tbl(RT), "",
             "![](../figures/ephys_spikes_sleep_explore_C_c1_2026c.png)", "",
             "### Per animal", "", *tbl(PA), "",
             "### Sensitivities: P with a pause or a hard reset, + dark × day, no interaction", "", *tbl(sens_rows), "", *tbl(sens_rat), "",
             "### Held out (forward chaining; post-round 3 h excluded)", "", *tbl(HO), "",
             "### Verdict C1", "", *vl, "", f"**C1 (a) verdict (plan rule): {va}.**", "", *vlb, "",
             f"**C1 (b) (added, orientation only): {vb}.**", ""]
        sections.append(L)
        verdicts.append({"part": "C1 (a)", "question": "night = a gain independent of the prior wake (plan's literal model)", "verdict": va,
                         **{lab: f"dark {ok_a[lab]['coef']:+.3f} (OR {np.exp(ok_a[lab]['coef']):.2f}); rats < 0 {ok_a[lab]['neg']}/{ok_a[lab]['n']}"
                            for lab in labs}})
        verdicts.append({"part": "C1 (b) (added)", "question": "night/day ratio at matched P and d, 2-harmonic clock model", "verdict": vb,
                         **{lab: f"ratio {ok_b[lab]['ratio']:.2f}; rats < 1 {ok_b[lab]['lt1']}/{ok_b[lab]['n']}" for lab in labs}})
    # ------------------------------------------------------------ C2
    if "c2" in parts:
        t0 = time.time()
        rows, hz, cnts, ns = [], [], [], {}
        for lab in labs:
            r = c2_run(P[lab], key, a.workers)
            for x in r["rows"]:
                rows.append({"scores": lab, **x})
            r["hazard"].insert(0, "scores", lab)
            r["counts"].insert(0, "scores", lab)
            hz.append(r["hazard"])
            cnts.append(r["counts"])
            ns[lab] = (r["n"], r["n_rem"])
            print(f"C2 {lab} done ({time.time() - t0:.0f} s)", flush=True)
        C2 = pd.DataFrame(rows)
        HZ, CN = pd.concat(hz, ignore_index=True), pd.concat(cnts, ignore_index=True)
        cols = ["scores", "train", "steps_subset", "comparison", "subset", "n_steps", "n_rem", "delta_pct", "ci_lo_pct", "ci_hi_pct",
                "folds_better", "folds", "animals_better", "animals", "holds"]
        C2 = C2[[c for c in cols if c in C2.columns]]
        save(C2, "c2_heldout")
        save(HZ, "c2_hazard")
        fig_c2(HZ, fd / "ephys_spikes_sleep_explore_C_c2_2026c.png", gc)
        prim = C2[(C2.train == "transition steps only") & (C2.steps_subset == "both transitions") & C2.subset.str.startswith("+ light step vs")]
        hold = {lab: bool(prim[prim.scores == lab].holds.iloc[0]) if len(prim[prim.scores == lab]) else False for lab in labs}
        v2 = "PASS" if all(hold.values()) else ("PARTIAL" if any(hold.values()) else "FAIL")
        vl = [f"- **{lab}:** {ns[lab][0]} transition steps over all blocks ({ns[lab][1]} REM ends); light step vs clock Δ "
              f"{prim[prim.scores == lab].delta_pct.iloc[0]:+.3f} % [{prim[prim.scores == lab].ci_lo_pct.iloc[0]:+.3f}, "
              f"{prim[prim.scores == lab].ci_hi_pct.iloc[0]:+.3f}], animals better {prim[prim.scores == lab].animals_better.iloc[0]}/"
              f"{prim[prim.scores == lab].animals.iloc[0]} → {'holds' if hold[lab] else 'does not hold'}." for lab in labs if len(prim[prim.scores == lab])]
        sub = C2[C2.subset.str.startswith("+ light step vs")]
        for lab in labs:
            parts_ = []
            for (tr_, ss_), nm_ in ((("transition steps only", "dawn (+-2 h of sunrise)"), "dawn only"),
                                    (("transition steps only", "dusk (+-2 h of sunset)"), "dusk only"),
                                    (("all NREM steps (sensitivity)", "both transitions"), "trained on all NREM steps")):
                q = sub[(sub.scores == lab) & (sub.train == tr_) & (sub.steps_subset == ss_)]
                if len(q):
                    q = q.iloc[0]
                    parts_.append(f"{nm_} Δ {q.delta_pct:+.3f} % [{q.ci_lo_pct:+.3f}, {q.ci_hi_pct:+.3f}], {q.animals_better}/{q.animals}"
                                  + (" (holds)" if q.holds else (" (the step makes prediction worse: CI > 0)" if q.ci_lo_pct > 0 else "")))
            if parts_:
                vl.append(f"  - {lab}, not in the rule: " + "; ".join(parts_) + ".")
        L = ["## C2 — light step vs circadian curve vs prior wake at the transitions", "",
             "**Plan pass rule (C2, quoted):** \"Pass for 'light-driven': the step improves held-out log-loss on the transition hours "
             "(holds).\" Applied to the clock vs clock + light-step comparison on the transition steps (trained on transition steps), "
             "both scorings. The plan's data are 'episodes starting within ±2 h of sunset and of sunrise, prior wake < 7 min, P at "
             "onset'; here every NREM step inside the ±2-h windows with a preceding wake < 7 min is used (the step model is the "
             "plan's estimation unit; the episode onset would keep only the first bout of each episode). The 3 h after a battery "
             "round are excluded, which removes much of the morning just after sunrise (rounds are morning / evening); counts below.", "",
             "Steps per transition and side (post-round excluded):", "", *tbl(CN), "",
             *([("Sparse side(s): " + "; ".join(f"{r.scores} {r.transition} {r.side} side {r.steps} steps" for r in CN[CN.steps < 1500].itertuples())
                 + ". After sunset the animals are mostly awake (and the evening rounds' 3-h exclusion falls there), so the dusk step "
                 "is estimated from few dark-side NREM steps; the dawn transition carries most of the test."), ""]
               if (CN.steps < 1500).any() else []),
             "### Held out", "", *tbl(C2), "",
             "![](../figures/ephys_spikes_sleep_explore_C_c2_2026c.png)", "",
             "### Empirical hazard per 15-min bin", "", *tbl(HZ, 5), "",
             "### Verdict C2", "", *vl, "", f"**C2 verdict: {v2}.**", ""]
        sections.append(L)
        verdicts.append({"part": "C2", "question": "a light step beyond the 2-harmonic clock at the transitions (light-driven)", "verdict": v2,
                         **{lab: f"Δ {prim[prim.scores == lab].delta_pct.iloc[0]:+.3f} % [{prim[prim.scores == lab].ci_lo_pct.iloc[0]:+.3f}, "
                            f"{prim[prim.scores == lab].ci_hi_pct.iloc[0]:+.3f}], {prim[prim.scores == lab].animals_better.iloc[0]}/6"
                            for lab in labs if len(prim[prim.scores == lab])}})
        times["c2"] = time.time() - t0
    # ------------------------------------------------------------ C3
    if "c3" in parts:
        t0 = time.time()
        R3 = {k: [] for k in ("COMP", "CO", "RES", "EXTRA", "PA", "HO")}
        allf3 = run_jobs([j for lab in labs for j in c3_jobs(P[lab], key, a.draws, c1fits[lab]["pooled:b"], c1fits[lab]["pooled:a"])],
                         a.workers)
        print(f"C3 fits done ({time.time() - t0:.0f} s)", flush=True)
        for lab in labs:
            fb = c1fits[lab]["pooled:b"]
            fa = c1fits[lab]["pooled:a"]
            r = c3_run(P[lab], key, a.workers, split_fits(allf3, lab), fb, fa)
            for k in R3:
                R3[k].append(r[k])
            print(f"C3 {lab} done ({time.time() - t0:.0f} s)", flush=True)
        R3 = {k: pd.concat(v, ignore_index=True) for k, v in R3.items()}
        for k, nm in (("COMP", "c3_composition"), ("CO", "c3_group_coef"), ("RES", "c3_restriction"), ("EXTRA", "c3_extra"),
                      ("PA", "c3_per_animal"), ("HO", "c3_heldout")):
            save(R3[k], nm)
        fig_c3(R3["RES"], PA, R3["PA"], R3["COMP"], fd / "ephys_spikes_sleep_explore_C_c3_2026c.png", gc)
        vl, okb, oka = [], {}, {}
        for lab in labs:
            rb = R3["RES"][(R3["RES"].scores == lab) & R3["RES"].quantity.str.startswith("(b)")].iloc[0]
            ra = R3["RES"][(R3["RES"].scores == lab) & R3["RES"].quantity.str.startswith("(a)")].iloc[0]
            okb[lab], oka[lab] = bool(abs(rb.change) <= 0.1), bool(abs(ra.change) <= 0.1)
            RS = R3["RES"][R3["RES"].scores == lab]
            st_b = RS[RS.quantity.str.startswith("sensitivity: (b)")]
            st_a = RS[RS.quantity.str.startswith("sensitivity: (a)")]
            EX = R3["EXTRA"][R3["EXTRA"].scores == lab]
            adj = EX[EX.quantity.str.contains("location \\+ group")].value
            vl.append(f"- **{lab}:** (b) ln ratio all steps {rb.all_steps:+.3f} {rb.all_ci} → house-with-mates {rb.house_with_mates:+.3f} "
                      f"{rb.house_with_mates_ci}, change {rb.change:+.3f} ({'≤' if okb[lab] else '>'} 0.1); (a) dark coefficient "
                      f"{ra.all_steps:+.3f} → {ra.house_with_mates:+.3f}, change {ra.change:+.3f} ({'≤' if oka[lab] else '>'} 0.1); "
                      f"steps {int(rb.n_all)} → {int(rb.n_house_with_mates)} ({100 * rb.n_house_with_mates / rb.n_all:.0f} % of the NREM "
                      "steps are house-with-mates, so this restriction can only remove a small minority). Not in the rule: "
                      + (f"the stricter restriction (all known co-located mates asleep, {int(st_b.n_house_with_mates.iloc[0])} steps) changes "
                         f"(b) by {st_b.change.iloc[0]:+.3f} and (a) by {st_a.change.iloc[0]:+.3f}; " if len(st_b) and len(st_a) else "")
                      + (f"adding location + group terms (n_coloc, n_coloc × dark, mates_asleep) to the all-step model moves (b) to "
                         f"{adj.iloc[0]:+.3f} (change {adj.iloc[0] - rb.all_steps:+.3f}); the mates' own sleep state is itself lower at "
                         "night, so this adjustment partly re-expresses the shared night rather than isolating company." if len(adj) else ""))
        allok = all(okb.values()) and all(oka.values())
        anyok = any(okb.values()) or any(oka.values())
        v3 = "PASS" if allok else ("PARTIAL" if anyok else "FAIL")
        L = ["## C3 — where and with whom (WISER)", "",
             "**Plan pass rule (C3, quoted):** \"Pass for 'the gain is not a location / company effect': the dark coefficient changes "
             "by ≤ 0.1 when restricted. Group size is reported with sign counts; 'huddling' is never claimed.\" Restriction = NREM "
             "steps in a house with ≥ 1 co-located tagged animal (WISER). Applied to both C1 quantities: the (a) dark coefficient "
             "(the plan's) and the (b) ln night / day ratio (the task's reading after Step B); PASS needs |change| ≤ 0.1 for both on "
             "both scorings, PARTIAL some. Two numbers outside the rule are reported in the verdict lines: a stricter restriction "
             "(all known co-located mates asleep) and the all-step ratio with location and group terms in the model. "
             "Caveats: WISER house = ROI + 14 in with ~4–7 in jitter: 'in the same house', never contact; "
             "only tagged animals count (SF11 is untagged after 09-07 08:20, so group sizes after it are lower bounds); video is not "
             "in yet.", "",
             "### Where the NREM steps are, by phase", "", *tbl(R3["COMP"]), "",
             "### Restriction to house-with-mates sleep", "", *tbl(R3["RES"]), "", *tbl(R3["EXTRA"]), "",
             "![](../figures/ephys_spikes_sleep_explore_C_c3_2026c.png)", "",
             "Per animal (house-with-mates fits; the all-step per-animal ratios are in C1):", "", *tbl(R3["PA"]), "",
             "### Group size by phase (B-full + location + group; descriptive coefficients per mate; per-animal signs)", "",
             *tbl(R3["CO"]), "", "### Held out: location and group terms", "", *tbl(R3["HO"]), "",
             "### Verdict C3", "", *vl, "", f"**C3 verdict: {v3}.**", ""]
        sections.append(L)
        verdicts.append({"part": "C3", "question": "the night effect is not a location / company effect (abs. change ≤ 0.1)", "verdict": v3,
                         **{lab: f"(b) change {R3['RES'][(R3['RES'].scores == lab) & R3['RES'].quantity.str.startswith('(b)')].change.iloc[0]:+.3f}; "
                            f"(a) change {R3['RES'][(R3['RES'].scores == lab) & R3['RES'].quantity.str.startswith('(a)')].change.iloc[0]:+.3f}"
                            for lab in labs}})
        times["c3"] = time.time() - t0
    # ------------------------------------------------------------ C4
    if "c4" in parts:
        t0 = time.time()
        w = weather_anomaly()
        T = pd.concat([c4_table(P[lab]["recs"], zone, w, lab) for lab in labs], ignore_index=True)
        T.to_csv(out / "c4_animal_days.csv", index=False)
        save(T.drop(columns=["t0", "t1"]), "c4_animal_days")
        M = c4_models(T)
        save(M, "c4_models")
        fig_c4(T, fd / "ephys_spikes_sleep_explore_C_c4_2026c.png", gc)
        vl, res4 = [], {}
        for r in M[M.outcome == "sleep_share_pct"].itertuples():
            ok = bool(r.R2within_weather_activity > 0.5 and r.day_p >= 0.05)
            res4[(r.scores, r.period)] = ok
            vl.append(f"- **{r.scores}, {r.period} sleep share:** within-animal R² weather {r.R2within_weather:.2f}, weather + activity "
                      f"{r.R2within_weather_activity:.2f}, day alone {r.R2within_day:.2f} (day {r.day_alone_coef:+.2f} pp/day, p {r.day_alone_p:.3f}); "
                      f"full model day {fci(r.day_coef, r.day_lo, r.day_hi, 2)} pp/day, p {r.day_p:.3f}; total R² with animal FE "
                      f"{r.R2_weather_activity:.2f} → {'environmental' if ok else 'not environmental'}.")
        v4 = "PASS (environmental)" if res4 and all(res4.values()) else ("PARTIAL" if any(res4.values()) else "FAIL (adaptation / unexplained)")
        tot = {(r.scores, r.period): bool(r.R2_weather_activity > 0.5 and r.day_p >= 0.05) for r in M[M.outcome == "sleep_share_pct"].itertuples()}
        v4t = "PASS" if tot and all(tot.values()) else ("PARTIAL" if any(tot.values()) else "FAIL")
        vl.append(f"- Reading R² as the total R² with the animal intercepts (which alone give "
                  f"{M[M.outcome == 'sleep_share_pct'].R2_animal_FE.min():.2f}–{M[M.outcome == 'sleep_share_pct'].R2_animal_FE.max():.2f}) "
                  "instead: " + "; ".join(f"{s} {p} {'passes' if ok else 'fails'}" for (s, p), ok in tot.items())
                  + f" → that reading would give {v4t}. The verdict uses the within-animal reading.")
        Tshow = T[T.cover >= 0.5].groupby(["scores", "period"]).agg(animal_days=("animal", "size"), sleep_share_mean=("sleep_share_pct", "mean"),
                                                                    temp_mean=("temp_C", "mean"), rain_mm_total=("rain_mm", "sum"),
                                                                    outside_mean=("outside_pct", "mean")).reset_index()
        L = ["## C4 — the 12-day drift", "",
             "**Plan pass rule (C4, quoted):** \"Pass for 'environmental': R² > 0.5 from weather + activity, with the day term n.s. "
             "Otherwise 'adaptation / unexplained'. Description, not regulation.\" R² is read as the within-animal R² (the share of the "
             "variation left after animal fixed effects that weather + activity explain); the total R² with the animal effects is "
             "reported alongside. Day term n.s. = p ≥ 0.05 in the full model (cluster by date, t(G − 1)). Primary outcome = sleep share "
             "(the plan's); NREM min per recorded h reported. Both periods (night, day) and both scorings must pass for PASS. Caveat: "
             "time outside the houses is partly the same thing as being awake (an animal outside is awake), so 'activity' explains "
             "sleep share partly by construction; the weather-only R² is the cleaner number.", "",
             "Animal-days (≥ 50 % recorded):", "", *tbl(Tshow, 2), "",
             "### Models", "", *tbl(M), "",
             "![](../figures/ephys_spikes_sleep_explore_C_c4_2026c.png)", "",
             "### Verdict C4", "", *vl, "", f"**C4 verdict: {v4}.**", ""]
        sections.append(L)
        verdicts.append({"part": "C4", "question": "the 12-day drift is environmental (weather + activity)", "verdict": v4,
                         **{lab: "; ".join(f"{r.period} R²w {r.R2within_weather_activity:.2f}, day p {r.day_p:.3f}"
                                           for r in M[(M.scores == lab) & (M.outcome == "sleep_share_pct")].itertuples()) for lab in labs}})
        times["c4"] = time.time() - t0
    # ------------------------------------------------------------ report
    VT = pd.DataFrame(verdicts)
    save(VT, "verdicts")
    times["total"] = time.time() - t_all
    data = ["## Data", ""]
    for lab in labs:
        D = P[lab]["D"]
        data.append(f"- {lab}: {len(D['y'])} NREM steps ({int(D['post_round'].sum())} in the 3 h after battery rounds, excluded), "
                    f"{int((D['y'] == 1).sum())} REM ends, {int((D['y'] == 2).sum())} WAKE ends; {len(P[lab]['recs'])} records; "
                    f"animals {', '.join(sorted(set(D['animal'])))}.")
    data += ["", f"- P = `{key}` (τ_w = {key.split('_tw')[1].split('_')[0] if '_tw' in key else 'reset'} s, κ = {kappa} s): the grid point "
             "chosen most often over the folds by Step B's nested forward chaining (FINAL)"
             + (f"; chosen per fold: {', '.join(str(x) for x in CH.chosen_B.dropna())}" if CH is not None else " (given on the command line)")
             + f". Sensitivities: {', '.join(f'{k} `{v}`' for k, v in sens.items())}.", ""]
    dev = ["## Deviations from the plan and notes", "",
           "- Written as `ephys/sleep_explore_c.py stepC` (a separate file) instead of a `stepC` command inside `ephys/sleep_explore.py`, "
           "so that stepA's file, CLI and selftest stay untouched.",
           "- C1 (b) and C3's (b) ratio are additions (Step B found the night effect in the 2-harmonic clock, not in a step); the plan's "
           "rule is judged on (a).",
           "- C1 / C3 coefficients come from full-data fits with cluster-robust SEs by day-half block (the task allowed bootstrap over "
           "blocks or cluster SEs); the (b) ratio CI is a parametric draw from that covariance.",
           "- The multinomial is fitted by an in-file Newton solver with the same L2 penalty as Step B's sklearn engine (C = 1e4), for "
           "speed and for the cluster sandwich; held-out comparisons here use the same solver.",
           "- P's grid point was chosen by Step B using all folds; C2 / C3 held-out comparisons share it on both sides, so the "
           "comparison is fair, but Δ is not nested.",
           "- C2 uses NREM steps (with the prior-wake and P definitions of the step model) instead of episode onsets; see C2.",
           "- C3 group size = WISER co-location of tagged animals (n_coloc); Phase 5's n_mates (known state) and mates_asleep enter "
           "the group model as in Phase 5.",
           "- C4: R² read within animals (see C4); rain = integrated console rain rate, from console samples only (a period with "
           "< 50 % console samples, e.g. inside the 09-02/03 uplink hole, has no rain value and is dropped); temperature = the "
           "period's own mean (night temperature for the night outcome, day temperature for the day outcome); activity = WISER "
           "time outside the houses.",
           ""]
    hdr = ["# Sleep behaviour explore — Step C: day vs night, matched (cohort 2026c)", "",
           f"Plan: [{PLAN}](../../../../{PLAN}) (sections 1, 3, 4 and 5 Step C; the pass rules are the plan's, unchanged). Builds on "
           "Step B ([ephys_spikes_sleep_explore_B_2026c.md](ephys_spikes_sleep_explore_B_2026c.md)) and Step A "
           "([ephys_spikes_sleep_explore_A_2026c.md](ephys_spikes_sleep_explore_A_2026c.md)). Driver `ephys/sleep_explore_c.py stepC` "
           f"(commit {gc}, file uncommitted at run time); bulk `{out}`; parts {', '.join(parts)}; runtime {times['total'] / 60:.1f} min.", "",
           "**Status: exploration step; claim statuses are changed in the claim audit, not here.** Inputs: the scored 1-s states "
           "(FINAL and pass2med_remclean), NOAA light, the Phase-0 gap table, WISER default tracks (house / field / co-located "
           "housemates), the weather console. No LFP features. Everything from 2026-09-11 19:40 is cut. The sleep states come from "
           "the scorer, whose EMG is the head IMU; no claim here links movement to state.", "",
           "## Verdicts", "", *tbl(VT), ""]
    flat = [ln for blk in [hdr, data, DEFINITIONS] + sections + [dev] for ln in blk]
    rpt = rd / "ephys_spikes_sleep_explore_C_2026c.md"
    rpt.write_text("\n".join(flat) + "\n", encoding="utf-8")
    write_json(rd / "run_manifest_sleep_explore_C_2026c.json",
               {"run_dir": str(out), "git_commit": gc, "parts": parts, "scorings": labs, "p_key": key, "sensitivity_keys": sens,
                "inputs": {"states_FINAL": str(STATES), "states_pass2med": str(PASS2MED), "review": str(REVIEW), "chosen_B": str(CHOSEN_CSV),
                           "gaps": str(Path(json.load(open(P0_MANIFEST))["run_dir"]) / "gaps.csv"),
                           "wiser_default_tracks": str(OUT / "wiser_default_tracks")},
                "csvs": csvs, "runtime_s": {k: round(v, 1) for k, v in times.items()}, "verdicts": verdicts, "plan": PLAN})
    print(VT.to_string(index=False), flush=True)
    print("written", rpt, f"({times['total'] / 60:.1f} min)", flush=True)


# ================================================================== selftest
def synth_D(rng, n_per: int = 1500, beta_dark: float = -0.9, gamma_n: float = -0.25, step_true: bool = True,
            dark_x_n: float = 0.0) -> dict:
    """Synthetic NREM steps: 6 animals x 22 day-half blocks (09-01 .. 09-11). REM logit = -4.6 + 1.5 (lP - 1) + beta_dark *
    dark (a pure step when step_true, else a smooth curve 0.9 cos(2 pi (h - 2) / 24) with no step) + 0.3 ln(1+d) ... ; WAKE
    logit = -3.8 + gamma_n * n_coloc (+ dark_x_n * dark * n_coloc); n_coloc in 0..4 when in a house."""
    from sleep_schedule_phase3 import light_flags
    rows = []
    for an in ANIMALS:
        for day in range(1, 12):
            for half in ("D", "N"):
                base = pd.Timestamp(f"2026-09-{day:02d}") + pd.Timedelta(hours=6 if half == "D" else 18)
                off = rng.uniform(0, 12 * 3600, n_per)
                rows.append(pd.DataFrame({"animal": an, "block": f"2026-09-{day:02d}{half}", "t": base + pd.to_timedelta(off, unit="s")}))
    S = pd.concat(rows, ignore_index=True)
    n = len(S)
    S["hour"] = S.t.dt.hour + S.t.dt.minute / 60 + S.t.dt.second / 3600
    S["dark"] = (~light_flags(S.t)).astype(float)
    S["T_day"] = (S.t - RELEASE).dt.total_seconds() / 86400
    S["elapsed"] = 10 * rng.integers(0, 60, n)
    S["has_anchor"] = (rng.random(n) < 0.8).astype(float)
    S["d_prev"] = np.where(rng.random(n) < 0.35, 0.0, np.exp(rng.normal(3.0, 1.5, n)))
    S["prev_rem"] = ((S.d_prev == 0) & (rng.random(n) < 0.6)).astype(float)
    S["prev_unk"] = ((S.d_prev == 0) & (S.prev_rem == 0)).astype(float)
    S["fW10"] = rng.beta(1, 6, n)
    lP = np.log1p(rng.exponential(8.0, n))
    zone = np.where(rng.random(n) < 0.85, rng.integers(1, 3, n), np.where(rng.random(n) < 0.5, 3, 0))
    ncol = np.where(np.isin(zone, (1, 2)), rng.integers(0, 5, n), 0).astype(float)
    clock = beta_dark * S.dark.to_numpy() if step_true else 0.9 * np.cos(2 * np.pi * (S.hour.to_numpy() - 2) / 24)
    eR = -4.6 + 1.5 * (lP - 1.0) + clock + 0.3 * np.log1p(S.d_prev.to_numpy()) * 0
    eW = -3.8 + gamma_n * ncol + dark_x_n * S.dark.to_numpy() * ncol
    pr = np.column_stack([np.ones(n), np.exp(eR), np.exp(eW)])
    pr /= pr.sum(1, keepdims=True)
    y = (rng.random(n)[:, None] > pr.cumsum(1)).sum(1)
    D = {"y": y.astype(np.int8), "animal": S.animal.to_numpy().astype(str), "block": S.block.to_numpy().astype(str),
         "hour": S.hour.to_numpy(), "dark": S.dark.to_numpy(), "T_day": S.T_day.to_numpy(), "l_elapsed": np.log(S.elapsed.to_numpy() + 5.0),
         "has_anchor": S.has_anchor.to_numpy(), "l_dprev": np.log1p(S.d_prev.to_numpy()), "d_prev": S.d_prev.to_numpy(),
         "prev_rem": S.prev_rem.to_numpy(), "prev_unk": S.prev_unk.to_numpy(), "fW10": S.fW10.to_numpy(), "lP_K": lP,
         "zone": zone.astype(np.int8), "in_house": np.isin(zone, (1, 2)).astype(float), "loc_field": (zone == 3).astype(float),
         "loc_unknown": (zone == 0).astype(float), "n_coloc": ncol, "mates_asleep": rng.random(n) * (ncol > 0),
         "post_round": np.zeros(n, bool)}
    for k in (1, 2):
        D[f"sin{k}"], D[f"cos{k}"] = np.sin(2 * np.pi * k * D["hour"] / 24), np.cos(2 * np.pi * k * D["hour"] / 24)
    D["with_mates"] = ((D["in_house"] == 1) & (ncol >= 1)).astype(float)
    mr, ms = sun_rel(S.t)
    D["m_rise"], D["m_set"] = mr, ms
    D["trans"] = np.select([np.abs(mr) <= TRANS_MIN, np.abs(ms) <= TRANS_MIN], [1, 2], 0).astype(np.int8)
    D["true_pR"] = pr[:, 1]
    if step_true:                                   # the true standardised ratio: every step with dark = 1 vs dark = 0
        pn = []
        for dk in (1.0, 0.0):
            eRc = eR - clock + beta_dark * dk
            eWc = -3.8 + gamma_n * ncol + dark_x_n * dk * ncol
            pn.append(np.sum(np.exp(eRc) / (1 + np.exp(eRc) + np.exp(eWc))))
        D["true_ratio"] = float(pn[0] / pn[1])
    return D


def selftest() -> None:
    t_start = time.time()
    ok_all = True

    def check(name: str, cond: bool) -> None:
        nonlocal ok_all
        print(("PASS " if cond else "FAIL ") + name, flush=True)
        ok_all &= bool(cond)

    # 1. the solver against sklearn (same penalty) on a small problem
    from sklearn.linear_model import LogisticRegression
    rng = np.random.default_rng(1)
    X = rng.normal(size=(20000, 5))
    e1, e2 = -3 + 0.8 * X[:, 0], -2.5 - 0.5 * X[:, 1]
    pr = np.column_stack([np.ones(len(X)), np.exp(e1), np.exp(e2)])
    pr /= pr.sum(1, keepdims=True)
    y = (rng.random(len(X))[:, None] > pr.cumsum(1)).sum(1)
    f = mnl_fit(X, y, groups=rng.integers(0, 20, len(X)))
    sk = LogisticRegression(C=1e4, max_iter=5000).fit(X, y)
    d_sk = np.r_[sk.intercept_[1] - sk.intercept_[0], sk.coef_[1] - sk.coef_[0]]
    check(f"Newton multinomial = sklearn (REM vs stay, max |diff| {np.max(np.abs(f['B'][:, 0] - d_sk)):.4f}); "
          f"truth 0.8 -> {f['B'][1, 0]:.3f}", np.max(np.abs(f["B"][:, 0] - d_sk)) < 0.01 and abs(f["B"][1, 0] - 0.8) < 0.1)
    # 2. synthetic steps with a known night gain (step) and a known group effect on WAKE
    D = synth_D(np.random.default_rng(7))
    idx = np.arange(len(D["y"]))
    S = specs_c1("K")
    fa = mn_job("a", D, idx, S["a"])
    c = coef(fa, fa["names"], "dark", 0)
    check(f"C1 (a): dark coefficient {fci(c['coef'], c['ci_lo'], c['ci_hi'])} recovers the true -0.9", c["ci_lo"] <= -0.9 <= c["ci_hi"] and abs(c["coef"] + 0.9) < 0.25)
    cx = coef(fa, fa["names"], "dark_x_lnd", 0)
    check(f"C1 (a): dark x ln d {fci(cx['coef'], cx['ci_lo'], cx['ci_hi'])} covers the true 0", cx["ci_lo"] <= 0 <= cx["ci_hi"])
    fb = mn_job("b", D, idx, S["b"], ratio=True, draws=40, clocks=clock_sets(D, idx))
    tr_ = D["true_ratio"]
    check(f"C1 (b): standardised night/day ratio {fb['ratio']:.3f} [{fb['ratio_ci'][0]:.3f}, {fb['ratio_ci'][1]:.3f}] recovers the true "
          f"probability-scale ratio {tr_:.3f} (odds-scale exp(-0.9) = {np.exp(-0.9):.3f})",
          abs(np.log(fb["ratio"] / tr_)) < 0.1 and fb["ratio_ci"][0] < tr_ * 1.05 and fb["ratio_ci"][1] > tr_ * 0.95)
    # exact standardisation identity: with a dark-only model the per-step ratio is the odds-scale step
    Dd = {**D}
    sp = {"harm": False, "dark": True, "L1": None, "lnd": False, "hist": None, "tday": False}
    f0 = mn_job("d", Dd, idx, sp, ratio=True, clocks=clock_sets(Dd, idx))
    obs = (D["y"][D["dark"] == 1] == 1).mean() / (D["y"][D["dark"] == 0] == 1).mean()
    check(f"standardisation: dark-only model ratio {f0['ratio']:.4f} ~ the raw rate ratio {obs:.4f} (animal-adjusted)", abs(np.log(f0["ratio"] / obs)) < 0.05)
    # group effect: WAKE vs stay n_coloc -0.25 (light and dark); REM unaffected
    grp = {**S["b_Bfull"], "raw": ("loc_field", "loc_unknown", "n_coloc", "mates_asleep"), "raw_x_dark": ("n_coloc",)}
    fg = mn_job("g", D, idx, grp)
    gw = lincomb(fg, fg["names"], {"n_coloc": 1.0}, 1)
    gr = lincomb(fg, fg["names"], {"n_coloc": 1.0}, 0)
    gd = lincomb(fg, fg["names"], {"dark_x_n_coloc": 1.0}, 1)
    check(f"C3: WAKE vs stay n_coloc (light) {fci(gw['coef'], gw['ci_lo'], gw['ci_hi'])} recovers -0.25; REM {fci(gr['coef'], gr['ci_lo'], gr['ci_hi'])} "
          f"covers 0; dark - light {fci(gd['coef'], gd['ci_lo'], gd['ci_hi'])} covers 0",
          gw["ci_lo"] <= -0.25 <= gw["ci_hi"] and gw["ci_hi"] < 0 and gr["ci_lo"] <= 0 <= gr["ci_hi"] and gd["ci_lo"] <= 0 <= gd["ci_hi"])
    iw = idx[D["with_mates"] == 1]
    fbr = mn_job("br", D, iw, S["b"], ratio=True, clocks=clock_sets(D, idx))
    check(f"C3: restriction to house-with-mates leaves ln ratio {np.log(fb['ratio']):+.3f} -> {np.log(fbr['ratio']):+.3f} (|change| < 0.15; truth 0)",
          abs(np.log(fbr["ratio"]) - np.log(fb["ratio"])) < 0.15)
    # 3. C2: a true light step beats the 2-harmonic clock held out on the transition steps; a true smooth curve does not
    for step_true in (True, False):
        Dx = synth_D(np.random.default_rng(11 if step_true else 12), n_per=1500, beta_dark=-1.2, step_true=step_true)
        m = Dx["trans"] > 0
        Ds = subset(Dx, m)
        res = run_heldout(Ds, {"clock": c2_specs("K")["clock"], "step": c2_specs("K")["step"]}, folds_of(Ds), workers=4)
        F, FA = ho_tables(res, Ds)
        r = cmp(F, FA, "clock", "step", "selftest")
        if step_true:
            check(f"C2: true step -> step vs clock Δ {r['delta_pct']:+.3f} % [{r['ci_lo_pct']:+.3f}, {r['ci_hi_pct']:+.3f}] holds", bool(r.get("holds")))
        else:
            check(f"C2: true smooth curve -> step vs clock Δ {r['delta_pct']:+.3f} % [{r['ci_lo_pct']:+.3f}, {r['ci_hi_pct']:+.3f}] does not hold",
                  not bool(r.get("holds")))
    # 4. mates arithmetic
    zone = {"SF07": np.array([1, 1, 2, 3, 0], np.int8), "SF08": np.array([1, 2, 2, 3, 0], np.int8), "SF09": np.array([1, 1, 2, 1, 1], np.int8)}
    arr = {"SF07": np.array([N, N, N, N, N], np.int8), "SF08": np.array([R, W, 0, N, N], np.int8), "SF09": np.array([W, N, N, N, N], np.int8)}
    mt = mates_arrays(zone, arr)
    nc, nm, ns = mt["SF07"]
    check(f"mates: SF07 n_coloc {list(nc)} = [2, 1, 2, 0, 0], n_mates {list(nm)} = [2, 1, 1, 0, 0], n_asleep {list(ns)} = [1, 1, 1, 0, 0]",
          list(nc) == [2, 1, 2, 0, 0] and list(nm) == [2, 1, 1, 0, 0] and list(ns) == [1, 1, 1, 0, 0])
    gtest = pd.DataFrame({"animal": ["SF07"], "gap_end": [pd.Timestamp("2026-09-03 10:00")], "cause": ["round_logged"]})
    pm = post_round_mask(np.array(["SF07", "SF07", "SF08"]), pd.Series(pd.to_datetime(["2026-09-03 12:59", "2026-09-03 13:00", "2026-09-03 11:00"])), gtest)
    check("post-round mask = [gap end, + 3 h) of the same animal", list(pm) == [True, False, False])
    # 5. C4: environmental truth -> high within-R2 and day n.s.; adaptation truth -> day significant
    rng = np.random.default_rng(5)
    rows = []
    temps = rng.normal(15, 3, 12)
    rain = rng.exponential(2, 12)
    for an_i, an in enumerate(ANIMALS):
        for d in range(12):
            for per in ("night", "day"):
                out_ = rng.uniform(5, 30)
                rows.append({"scores": "S", "animal": an, "night_of": pd.Timestamp("2026-08-31") + pd.Timedelta(days=d), "period": per, "cover": 1.0,
                             "day": d + 0.5, "temp_C": temps[d], "rain_mm": rain[d], "outside_pct": out_,
                             "sleep_share_pct": 50 + 3 * an_i - 1.5 * (temps[d] - 15) - 0.6 * out_ + rng.normal(0, 1),
                             "nrem_min_per_h": 30 + rng.normal(0, 1)})
    M = c4_models(pd.DataFrame(rows))
    r = M[(M.outcome == "sleep_share_pct") & (M.period == "night")].iloc[0]
    check(f"C4 environmental truth: within R2 weather + activity {r.R2within_weather_activity:.2f} > 0.5, day p {r.day_p:.3f} >= 0.05",
          r.R2within_weather_activity > 0.5 and r.day_p >= 0.05)
    for x in rows:
        x["sleep_share_pct"] += -1.2 * x["day"]
    M2 = c4_models(pd.DataFrame(rows))
    r2 = M2[(M2.outcome == "sleep_share_pct") & (M2.period == "night")].iloc[0]
    check(f"C4 adaptation truth: day coefficient {r2.day_coef:+.2f} (truth -1.2), p {r2.day_p:.4f} < 0.05", r2.day_p < 0.05 and abs(r2.day_coef + 1.2) < 0.4)
    print(f"selftest {'PASS' if ok_all else 'FAIL'} ({time.time() - t_start:.0f} s)", flush=True)
    if not ok_all:
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["stepC"])
    ap.add_argument("--parts", nargs="*", default=["c1", "c2", "c3", "c4"])
    ap.add_argument("--scorings", nargs="+", default=["FINAL", "pass2med"], choices=list(SCORINGS))
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--draws", type=int, default=300, help="parameter draws for the (b) ratio CI")
    ap.add_argument("--p-key", default=None, help="P variant key (default: the modal chosen_B of Step B)")
    ap.add_argument("--wait-min", type=int, default=240, help="minutes to wait for Step B's chosen CSV")
    ap.add_argument("--zone-cache", default=None, help="a zone_per_second.npz from an earlier run (re-read, not re-derived)")
    ap.add_argument("--scratch", action="store_true", help="write the report, CSVs and figures into the run folder only")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(v, "1")
    if a.selftest:
        selftest()
    elif a.cmd == "stepC":
        stepC(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
