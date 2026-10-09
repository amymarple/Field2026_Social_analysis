r"""Sleep behaviour explore, Amendment 1 part G: where does the REM repayment after morning rounds (#43) come from?
(cohort 2026c; plan implementation_plan/2026-10-08-sleep-behaviour-explore.md section 9 "G", written before these results;
the pass rules and the reading rule there are fixed. Definitions shared with every step: plan section 3.)

Parts (every quantity is defined, formula + text, in the report's Definitions section):
  g1  dawn timing without handling: the minimal detectable slope (MDS; 80 % power, two-sided alpha 0.05) of Step D1's
      primary dawn-wake regression (B = 1 h, day-demeaned pay_rem ~ debt_rem + debt_nrem + onset_h + animal FE, SEs
      clustered by block) - analytic from the windows' residualised REM-debt spread and the residual SD, checked by
      planting slopes into the real windows (wild cluster bootstrap of the residuals, cluster-robust test as D1).
      Informative iff the MDS <= 0.34 (the observed round slope, #43).
  g2  H18, handling-specific post-round sleep: post-round vs natural wakes >= 30 min, matched on the wake-length bin
      (30-120 min, >= 2 h) and morning / evening. First-REM latency in NREM time (Cox, animal strata, SEs clustered by
      block) and REM-entry observed / expected (O/E) in the 0-1 h and 1-3 h after (expected = the sum of the held-out
      per-step p_rem of B-full at P_tw600_k0; the perturbation-blind pb_rem reported next to it); matched difference
      with a bootstrap CI over blocks; per-animal signs; both scorings.
  g3  the round's own sleep loss: gap debt (the phase x day baseline REM expected over the unrecorded gap) added next to
      the 3-h pre-round debt in the #43 payback regression; the payback slope by gap-length tertile.
  g4  gate release: morning rounds, the payback slope vs the clock time of the first post-round sleep onset relative to
      sunrise, and vs the held-out clock-only (gate) model's REM-entry rate in window B (interaction terms).
  Reading rule (plan): G2 pass + G3 fail -> handling-specific; G3 pass -> the round's sleep loss; G1 informative and
  positive -> dawn timing; all fail -> #43 stays Candidate (power).

Inputs: the scored 1-s states (FINAL, pass2med) via sleep_model.records_for; the Phase-0 gap table; NOAA light; the
held-out per-step predictions written by the main session (D:/Field2026_analysis_out/2026c/sleep_heldout_steps/
heldout_steps_{final,pass2med}.csv.gz). No LFP features. Everything from 2026-09-11 19:40 is cut (records).

Usage: python ephys/sleep_explore_g.py run [--parts g1 g2 g3 g4] [--scorings final pass2med]
       python ephys/sleep_explore_g.py --selftest
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(ROOT / "common"))
from sleep_cycles import bouts  # noqa: E402
from sleep_explore import COLORS, LONG_S, MA_S, P0_MANIFEST, PASS2MED, ROUND_CAUSES, cox, cterm, ols, tbl, term  # noqa: E402
from sleep_explore_d import (HANDLING, LOOKBACK_S, _add_pay, _design, _irls, baseline_bins,  # noqa: E402
                             dawn_payback_from_records, payback_from_records, round_onsets)
from sleep_schedule import N, R, RELEASE, REVIEW, STATES, W, episode_units  # noqa: E402
from sleep_schedule_phase3 import km_median, light_flags  # noqa: E402

SCORINGS = {"final": ("FINAL", STATES), "pass2med": ("pass2med", PASS2MED)}
HELDOUT = Path("D:/Field2026_analysis_out/2026c/sleep_heldout_steps")
PLAN = "implementation_plan/2026-10-08-sleep-behaviour-explore.md"
PARTS = ("g1", "g2", "g3", "g4")
ROUND_SLOPE = 0.34                   # plan G1: the observed round slope (#43: pass2med, 1 h, day-demeaned, +0.335)
POWER, ALPHA = 0.80, 0.05
PLANT_GRID = np.round(np.arange(0.0, 1.2001, 0.02), 4)
N_SIM = 2000                         # wild-bootstrap replicates per planted slope
N_BOOT = 2000                        # block-bootstrap replicates (G2)
MIN_WIN = 10                         # minimum windows for a pooled fit (as sleep_explore.pay_models)
MIN_RAT_WIN = 3                      # D1's rats rule (rats with >= 3 windows)
PRIMARY_D1 = ["debt_rem", "debt_nrem", "onset_h"]
G2_MIN_S = 1800                      # plan G2: wakes >= 30 min
G2_BINS = (("30-120 min", 1800, 7200), (">= 2 h", 7200, np.inf))      # plan section 3 wake bins at >= 30 min
G2_WINDOWS = (("0-1 h", 0, 3600), ("1-3 h", 3600, 10800))
KINDS = ("morning", "evening")
FALL_MIN = 0.30                      # plan G3: the pre-round debt slope falls by >= 30 %
STEP_COLS = ("animal", "record_id", "block", "t", "y", "p_rem", "pb_rem", "p_rem_gate")
G2_POSTHOC = "post hoc: bin only (any clock time)"


# ================================================================== small helpers
def kind_of(t: pd.Timestamp) -> str:
    """Phase 0's gap kind applied to a time: morning 05:00-11:00, evening 15:30-21:30, else other."""
    h = t.hour + t.minute / 60
    return "morning" if 5 <= h < 11 else ("evening" if 15.5 <= h < 21.5 else "other")


def bin_of(d_s: float) -> str | None:
    for lab, lo, hi in G2_BINS:
        if lo <= d_s < hi:
            return lab
    return None


def _blk(t: pd.Timestamp) -> str:
    d = t.normalize() - (pd.Timedelta(days=1) if t.hour < 6 else pd.Timedelta(0))
    return f"{d:%Y-%m-%d}{'D' if 6 <= t.hour < 18 else 'N'}"


def _norm():
    from scipy.stats import norm
    return norm


def _fmt(d: dict, nd: int = 3, key: str = "coef") -> str:
    v = d.get(key, np.nan)
    if v is None or not np.isfinite(v):
        return "n/a"
    return f"{v:+.{nd}f} [{d['ci_lo']:+.{nd}f}, {d['ci_hi']:+.{nd}f}], p {d['p']:.4f}" if "p" in d and np.isfinite(d.get("p", np.nan)) \
        else f"{v:+.{nd}f} [{d['ci_lo']:+.{nd}f}, {d['ci_hi']:+.{nd}f}]"


# ================================================================== OLS with statsmodels' cluster-robust SEs, vectorised
def design_ols(d: pd.DataFrame, xs: list[str], fe: str | None = "animal") -> tuple[np.ndarray, list[str]]:
    """The design of sleep_explore.ols: a constant, the predictors (constant columns dropped) and the animal dummies
    (first level of the sorted animals dropped)."""
    cols = [c for c in xs if d[c].nunique() > 1]
    parts, names = [np.ones(len(d))] + [d[c].to_numpy(float) for c in cols], ["const"] + cols
    if fe is not None and d[fe].nunique() > 1:
        for v in sorted(d[fe].unique())[1:]:
            parts.append((d[fe].to_numpy() == v).astype(float))
            names.append(f"fe_{v}")
    return np.column_stack(parts), names


class ClusterOLS:
    """OLS for many responses with one design; SE of coefficient j = statsmodels' cluster-robust SE (correction
    G/(G-1) x (N-1)/(N-K)); p from the normal reference (as sleep_explore.ols)."""

    def __init__(self, X: np.ndarray, groups):
        self.X = X
        n, k = X.shape
        self.H = np.linalg.solve(X.T @ X, X.T)                   # k x n
        self.g = pd.factorize(np.asarray(groups))[0]
        self.G = int(self.g.max()) + 1
        self.C = np.zeros((self.G, n))
        self.C[self.g, np.arange(n)] = 1.0
        self.fac = self.G / (self.G - 1) * (n - 1) / (n - k)

    def fit(self, Y: np.ndarray, j: int) -> tuple[np.ndarray, np.ndarray]:
        Y = Y[:, None] if Y.ndim == 1 else Y
        B = self.H @ Y
        U = Y - self.X @ B
        Q = self.C @ (self.H[j][:, None] * U)
        return B[j], np.sqrt(self.fac * (Q ** 2).sum(0))


# ================================================================== G1: the power of the D1 dawn-wake regression
def d1_data(Wd: pd.DataFrame, xs=PRIMARY_D1, bh: int = 1, day_demeaned: bool = True) -> pd.DataFrame:
    """The rows of one Step D1 model (sleep_explore_d.fit_pay): windows of horizon bh, complete cases, and (day-demeaned)
    every variable minus its mean over the windows of the same calendar day."""
    Wn = _add_pay(Wd)
    g = Wn[Wn.B_h == bh]
    d = g[["pay_rem"] + list(xs) + ["animal", "A_block", "cal_day"]].dropna().copy()
    if day_demeaned and len(d):
        for c in ["pay_rem"] + list(xs):
            d[c] = d[c] - d.groupby("cal_day")[c].transform("mean")
    return d.reset_index(drop=True)


def _first_crossing(grid: np.ndarray, pw: np.ndarray, level: float = POWER) -> float:
    above = np.flatnonzero(pw >= level)
    if not above.size:
        return np.inf
    i = int(above[0])
    if i == 0:
        return float(grid[0])
    x0, x1, y0, y1 = grid[i - 1], grid[i], pw[i - 1], pw[i]
    return float(x0 + (level - y0) * (x1 - x0) / (y1 - y0)) if y1 > y0 else float(x1)


def mds_analysis(d: pd.DataFrame, xs: list[str], rng, grid=PLANT_GRID, n_sim: int = N_SIM, min_rat: int = MIN_RAT_WIN):
    """Minimal detectable slope of xs[0] in the model y = pay_rem ~ xs + animal FE (SEs clustered by A_block).
    Returns (summary dict, power table). Analytic: MDS = (z_{1-a/2} + z_{power}) x SE; SE_iid = sigma / sqrt(sum x~^2)
    (x~ = xs[0] residualised on the other columns), SE_cl = the fit's cluster-robust SE. Simulation: y* = m0 + b* x +
    e x v_g (m0 = fitted values without the xs[0] term, e = residuals, v_g = Rademacher signs per cluster), refitted with
    the cluster-robust test; power = P(p < alpha and slope > 0); the D1 rule also needs slope > 0.2 and every rat with
    >= min_rat windows positive (simple slope of y on xs[0])."""
    from scipy.stats import t as tdist
    norm = _norm()
    X, names = design_ols(d, xs)
    j = names.index(xs[0])
    y, x = d.pay_rem.to_numpy(float), d[xs[0]].to_numpy(float)
    co = ClusterOLS(X, d.A_block)
    b_all = co.H @ y
    b, se_cl = co.fit(y, j)
    b, se_cl = float(b[0]), float(se_cl[0])
    n, k = X.shape
    resid = y - X @ b_all
    sigma = float(np.sqrt(resid @ resid / (n - k)))
    Xo = np.delete(X, j, axis=1)
    xt = x - Xo @ np.linalg.lstsq(Xo, x, rcond=None)[0]
    se_iid = sigma / float(np.sqrt(xt @ xt))
    zs = norm.ppf(1 - ALPHA / 2) + norm.ppf(POWER)
    ts = tdist.ppf(1 - ALPHA / 2, n - k) + tdist.ppf(POWER, n - k)
    m0 = X @ b_all - b * x
    an = d.animal.to_numpy()
    rats = [np.flatnonzero(an == a) for a in sorted(set(an)) if (an == a).sum() >= min_rat and np.std(x[an == a]) > 0]
    rows = []
    for beta in grid:
        V = rng.choice(np.array([-1.0, 1.0]), size=(co.G, n_sim))[co.g]
        Y = (m0 + beta * x)[:, None] + resid[:, None] * V
        bb, ss = co.fit(Y, j)
        p = 2 * norm.sf(np.abs(bb / ss))
        sig = (p < ALPHA) & (bb > 0)
        pos = np.ones(n_sim, bool)
        for ix in rats:
            xa = x[ix] - x[ix].mean()
            pos &= (xa @ (Y[ix] - Y[ix].mean(0))) / (xa @ xa) > 0
        rule = sig & (bb > 0.2) & pos & (len(rats) >= 4)
        rows.append({"planted": float(beta), "power_sig": float(sig.mean()), "power_d1_rule": float(rule.mean()),
                     "mean_slope": float(bb.mean()), "sd_slope": float(bb.std()), "mean_se": float(ss.mean()),
                     "power_analytic_iid": float(norm.cdf(beta / se_iid - norm.ppf(1 - ALPHA / 2))),
                     "power_analytic_cl": float(norm.cdf(beta / se_cl - norm.ppf(1 - ALPHA / 2)))})
    P = pd.DataFrame(rows)
    gv = P.planted.to_numpy()
    s = {"n_windows": n, "k_params": k, "clusters": co.G, "rats_qualifying": len(rats), "slope": b, "se_cl": se_cl,
         "sigma_resid": sigma, "sd_debt": float(np.std(x, ddof=1)), "sd_debt_resid": float(np.std(xt, ddof=1)), "se_iid": se_iid,
         "mds_analytic_iid_z": zs * se_iid, "mds_analytic_iid_t": ts * se_iid, "mds_analytic_cl": zs * se_cl,
         "mds_sim": _first_crossing(gv, P.power_sig.to_numpy()), "mds_sim_d1_rule": _first_crossing(gv, P.power_d1_rule.to_numpy()),
         "power_at_round_slope_analytic_iid": float(norm.cdf(ROUND_SLOPE / se_iid - norm.ppf(1 - ALPHA / 2))),
         "power_at_round_slope_sim": float(np.interp(ROUND_SLOPE, gv, P.power_sig.to_numpy())),
         "power_at_round_slope_sim_d1_rule": float(np.interp(ROUND_SLOPE, gv, P.power_d1_rule.to_numpy())),
         "type1_sim": float(P.loc[P.planted == 0, "power_sig"].iloc[0]) * 2 if (P.planted == 0).any() else np.nan}
    return s, P


def g1_verdict(s: dict) -> tuple[str, str]:
    """Plan G1: 'If that slope is > 0.34 (the observed round slope), D1 is uninformative and G1 stays open.' Operationalised:
    informative iff the analytic MDS (iid, z) AND the simulated MDS are both <= 0.34; positive iff D1's slope > 0 with
    p < 0.05."""
    a, sm = s["mds_analytic_iid_z"], s["mds_sim"]
    inf_ = a <= ROUND_SLOPE and sm <= ROUND_SLOPE
    pos = s["slope"] > 0 and s["p"] < ALPHA
    why = (f"MDS analytic {a:.3f}, simulated {sm:.3f} ({'both <=' if inf_ else 'not both <='} {ROUND_SLOPE}); D1 slope "
           f"{s['slope']:+.3f}, p {s['p']:.4f} ({'positive' if pos else 'not positive'})")
    if not inf_:
        return "UNINFORMATIVE (G1 stays open)", why
    return ("INFORMATIVE, POSITIVE" if pos else "INFORMATIVE, NOT POSITIVE"), why


# ================================================================== G3: gap debt
def gap_expectations(B: pd.DataFrame, W: pd.DataFrame) -> pd.DataFrame:
    """Expected REM and NREM minutes over each row's unrecorded gap [gap_start, gap_end): the phase x day baseline shares
    (sleep_explore_d's numpy IRLS of the binomial REM / NREM share, the design of sleep_explore.baselines_d) fitted
    leave-one-block-out without the block of window A, evaluated at each minute's midpoint (the last, partial minute
    weighted by its length) and summed. Adds gap_e_rem_min, gap_e_nrem_min."""
    levels = sorted(B.animal.unique())
    X = _design(B, levels, True)
    rec = B.rec_s.to_numpy(float)
    ok = rec > 0
    blk = B.block.to_numpy()
    yr = np.where(ok, B.rem_s.to_numpy(float) / np.maximum(rec, 1), 0.0)
    yn = np.where(ok, B.nrem_s.to_numpy(float) / np.maximum(rec, 1), 0.0)
    full = (_irls(X[ok], yr[ok], "binomial", rec[ok]), _irls(X[ok], yn[ok], "binomial", rec[ok]))
    cache = {}

    def coefs(bk):
        if bk not in cache:
            tr = ok & (blk != bk)
            cache[bk] = (_irls(X[tr], yr[tr], "binomial", rec[tr], b0=full[0]), _irls(X[tr], yn[tr], "binomial", rec[tr], b0=full[1]))
        return cache[bk]
    er, en = [], []
    for r in W.itertuples():
        gs, ge = pd.Timestamp(r.gap_start), pd.Timestamp(r.gap_end)
        L = (ge - gs).total_seconds() / 60
        k = int(np.ceil(L))
        w = np.minimum(1.0, L - np.arange(k))
        tm = pd.Series(gs + pd.to_timedelta((np.arange(k) + w / 2) * 60, unit="s"))
        df = pd.DataFrame({"animal": r.animal, "hour": (tm.dt.hour + tm.dt.minute / 60 + tm.dt.second / 3600).to_numpy(),
                           "day": ((tm - RELEASE).dt.total_seconds() / 86400).to_numpy(), "dark": (~light_flags(tm)).astype(float)})
        Xg = _design(df, levels, True)
        br, bn = coefs(r.A_block)
        er.append(float(np.sum(w / (1 + np.exp(-(Xg @ br))))))
        en.append(float(np.sum(w / (1 + np.exp(-(Xg @ bn))))))
    W = W.copy()
    W["gap_e_rem_min"], W["gap_e_nrem_min"] = er, en
    return W


def _demean(d: pd.DataFrame, cols: list[str], by: str = "cal_day") -> pd.DataFrame:
    d = d.copy()
    for c in cols:
        d[c] = d[c] - d.groupby(by)[c].transform("mean")
    return d


def _per_animal(d: pd.DataFrame, y: str, xs: list[str], min_extra: int = 4) -> tuple[int, int]:
    """Signs of the per-animal partial slope of xs[0] (animals with >= min_extra + len(xs) windows)."""
    sg = []
    for _, ga in d.groupby("animal"):
        if len(ga) >= min_extra + len(xs) and all(ga[c].std() > 0 for c in xs):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                sg.append(np.sign(term(ols(ga[y], ga[xs]), xs[0])["coef"]))
    return int(np.sum(np.array(sg) > 0)), len(sg)


def g3_models(Wk: pd.DataFrame) -> pd.DataFrame:
    """Per horizon and raw / day-demeaned: M0 pay_rem ~ debt_rem (= #43), M1 pay_rem ~ debt_rem + gap_debt_rem, M2
    pay_rem ~ gap_debt_rem; animal FE, SEs clustered by the block of window A. fall = 1 - b1 / b0."""
    rows = []
    for bh in sorted(Wk.B_h.unique()):
        g = Wk[Wk.B_h == bh]
        for dm in (False, True):
            d = g[["pay_rem", "debt_rem", "gap_debt_rem", "gap_min", "animal", "A_block", "cal_day"]].dropna().copy()
            if dm:
                d = _demean(d, ["pay_rem", "debt_rem", "gap_debt_rem", "gap_min"])
            r = {"B_h": int(bh), "day_demeaned": dm, "n_windows": len(d), "clusters": int(d.A_block.nunique()),
                 "sd_debt_rem": float(d.debt_rem.std()), "sd_gap_debt_rem": float(d.gap_debt_rem.std()),
                 "corr_debt_gapdebt": float(np.corrcoef(d.debt_rem, d.gap_debt_rem)[0, 1]) if len(d) > 2 else np.nan}
            if len(d) >= MIN_WIN:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    f0 = ols(d.pay_rem, d[["debt_rem"]], groups=d.A_block, fe=d.animal)
                    f1 = ols(d.pay_rem, d[["debt_rem", "gap_debt_rem"]], groups=d.A_block, fe=d.animal)
                    f2 = ols(d.pay_rem, d[["gap_debt_rem"]], groups=d.A_block, fe=d.animal)
                t0, t1, tg, t2 = term(f0, "debt_rem"), term(f1, "debt_rem"), term(f1, "gap_debt_rem"), term(f2, "gap_debt_rem")
                for nm, t in (("b0_debt", t0), ("b1_debt", t1), ("b1_gap", tg), ("b2_gap_only", t2)):
                    r.update({f"{nm}": t["coef"], f"{nm}_lo": t["ci_lo"], f"{nm}_hi": t["ci_hi"], f"{nm}_p": t["p"]})
                r["fall"] = 1 - t1["coef"] / t0["coef"] if t0["coef"] else np.nan
                r["rats_gap_positive"], r["rats_gap"] = _per_animal(d, "pay_rem", ["gap_debt_rem", "debt_rem"])
            rows.append(r)
    return pd.DataFrame(rows)


def g3_rule(r: pd.Series | dict) -> tuple[str, str]:
    """Plan G3: 'the gap-debt slope > 0 (CI) AND the pre-round debt slope falls by >= 30 %' (one horizon)."""
    if int(r.get("n_windows", 0)) < MIN_WIN or not np.isfinite(r.get("b1_gap", np.nan)):
        return "INCONCLUSIVE", f"{int(r.get('n_windows', 0))} windows"
    g_ok, f_ok = r["b1_gap_lo"] > 0, r["fall"] >= FALL_MIN
    why = (f"gap-debt slope {r['b1_gap']:+.3f} [{r['b1_gap_lo']:+.3f}, {r['b1_gap_hi']:+.3f}] ({'CI > 0' if g_ok else 'CI includes 0 or < 0'}); "
           f"pre-round debt slope {r['b0_debt']:+.3f} -> {r['b1_debt']:+.3f} (fall {100 * r['fall']:.0f} %, {'>=' if f_ok else '<'} 30 %)")
    return ("MET" if g_ok and f_ok else "NOT MET"), why


def combine_horizons(st: dict) -> str:
    v = list(st.values())
    if v and all(x == "MET" for x in v):
        return "MET"
    if any(x == "MET" for x in v):
        return "PARTLY (" + ", ".join(f"{k} h {x}" for k, x in st.items()) + ")"
    if v and all(x == "INCONCLUSIVE" for x in v):
        return "INCONCLUSIVE"
    return "NOT MET"


def g3_tertiles(Wk: pd.DataFrame) -> pd.DataFrame:
    """Day-demeaned pay_rem ~ sum_k debt_rem x [tertile k] + tertile dummies + animal FE (clustered by block); tertiles of
    the gap length over the horizon's windows (day-demeaning over all windows first)."""
    rows = []
    for bh in sorted(Wk.B_h.unique()):
        d = Wk[Wk.B_h == bh][["pay_rem", "debt_rem", "gap_min", "animal", "A_block", "cal_day"]].dropna().copy()
        if len(d) < MIN_WIN:
            continue
        q1, q2 = np.quantile(d.gap_min, [1 / 3, 2 / 3])
        d["tert"] = np.where(d.gap_min <= q1, 1, np.where(d.gap_min <= q2, 2, 3))
        dd = _demean(d, ["pay_rem", "debt_rem"])
        X = pd.DataFrame({f"debt_T{k}": dd.debt_rem * (dd.tert == k) for k in (1, 2, 3)})
        X["T2"], X["T3"] = (dd.tert == 2).astype(float), (dd.tert == 3).astype(float)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            f = ols(dd.pay_rem, X, groups=dd.A_block, fe=dd.animal)
        lims = {1: (d.gap_min.min(), q1), 2: (q1, q2), 3: (q2, d.gap_min.max())}
        for k in (1, 2, 3):
            t = term(f, f"debt_T{k}")
            rows.append({"B_h": int(bh), "tertile": k, "gap_min_range": f"{lims[k][0]:.0f}-{lims[k][1]:.0f}", "n_windows": int((d.tert == k).sum()),
                         "slope": t["coef"], "ci_lo": t["ci_lo"], "ci_hi": t["ci_hi"], "p": t["p"],
                         "mean_gap_min": float(d.gap_min[d.tert == k].mean()), "mean_debt_rem": float(d.debt_rem[d.tert == k].mean())})
    return pd.DataFrame(rows)


# ================================================================== G4: gate release
def rid_after_gap(recs: list[dict]) -> dict:
    """(animal, gap end) -> record_id of the record that starts within 5 s of it (as sleep_explore_d.round_onsets)."""
    out = {}
    for rc in recs:
        out[(rc["animal"], pd.Timestamp(rc["start"]).floor("s"))] = rc["record_id"]
    return out


def _rid_lookup(lk: dict, an: str, t: pd.Timestamp):
    t = pd.Timestamp(t)
    for dt in range(-5, 6):
        k = (an, (t + pd.Timedelta(seconds=dt)).floor("s"))
        if k in lk:
            return lk[k]
    return None


class StepIndex:
    """The held-out per-step table indexed by record: sorted step times (ns) and cumulative sums of the columns."""

    def __init__(self, S: pd.DataFrame, cols=("y1", "p_rem", "pb_rem", "p_rem_gate", "post_round", "one")):
        S = S.copy()
        S["y1"] = (S.y == 1).astype(float)
        S["one"] = 1.0
        S["post_round"] = S["post_round"].astype(str).str.lower().isin(["true", "1", "1.0"]).astype(float) if "post_round" in S else np.nan
        self.cols = cols
        self.idx = {}
        for rid, g in S.sort_values(["record_id", "t"], kind="mergesort").groupby("record_id"):
            tn = g.t.to_numpy("datetime64[ns]").astype(np.int64)
            self.idx[int(rid)] = (tn, {c: np.r_[0.0, np.cumsum(g[c].to_numpy(float))] for c in cols})

    def window(self, rid, t0: pd.Timestamp, t1: pd.Timestamp) -> dict:
        if rid is None or int(rid) not in self.idx:
            return {c: 0.0 for c in self.cols}
        tn, cs = self.idx[int(rid)]
        t0, t1 = pd.Timestamp(t0).floor("s"), pd.Timestamp(t1).floor("s")      # step times are whole seconds
        lo, hi = int(np.searchsorted(tn, t0.value, "left")), int(np.searchsorted(tn, t1.value, "left"))
        return {c: float(cs[c][hi] - cs[c][lo]) for c in self.cols}


def g4_data(Wm: pd.DataFrame, recs: list[dict], steps: StepIndex | None) -> pd.DataFrame:
    """Morning round windows + the first post-round SLEEP onset (round_onsets), its time relative to sunrise, and the two
    gain measures of window B: gain_heldout = 360 x mean held-out clock-only p(REM) over the post-round record's NREM
    steps in B (REM entries per NREM hour), gain_base = the phase x day baseline's expected REM onsets per expected NREM
    hour in B."""
    from sleep_quant import sun_times
    W_ = _add_pay(round_onsets(Wm, recs))
    sr = [pd.Timestamp(sun_times(t.date())[0]) if pd.notna(t) else pd.NaT for t in W_.onset_time]
    W_["sunrise"] = sr
    W_["onset_rel_sunrise_h"] = [(t - s).total_seconds() / 3600 if pd.notna(t) else np.nan for t, s in zip(W_.onset_time, sr)]
    W_["gain_base"] = W_.B_e_rem_n / (W_.B_e_nrem_min / 60)
    lk = rid_after_gap(recs)
    gh, ns = [], []
    for r in W_.itertuples():
        if steps is None:
            gh.append(np.nan), ns.append(0)
            continue
        rid = _rid_lookup(lk, r.animal, r.gap_end)
        ge = pd.Timestamp(r.gap_end)
        w = steps.window(rid, ge, ge + pd.Timedelta(hours=int(r.B_h)))
        ns.append(int(w["one"]))
        gh.append(360 * w["p_rem_gate"] / w["one"] if w["one"] > 0 else np.nan)
    W_["gain_heldout"], W_["n_heldout_steps_B"] = gh, ns
    return W_


G4_MODS = (("gain_heldout", "held-out clock-only REM-entry rate in B (per NREM h)"),
           ("gain_base", "baseline expected REM onsets per expected NREM h in B (sensitivity, all windows)"),
           ("onset_rel_sunrise_h", "first post-round SLEEP onset minus sunrise (h)"))


def g4_models(W_: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per moderator m, horizon, raw / day-demeaned: pay_rem ~ debt_rem + m + debt_rem x (m - mean m) + animal FE (SEs
    clustered by block); day-demeaned: pay_rem, debt_rem and m day-demeaned, the product uses the day-demeaned debt and
    the globally centred m. Also the slopes in the halves of m (median split)."""
    rows, hv = [], []
    for m, _ in G4_MODS:
        for bh in sorted(W_.B_h.unique()):
            g = W_[W_.B_h == bh][["pay_rem", "debt_rem", m, "animal", "A_block", "cal_day"]].dropna().copy()
            for dm in (False, True):
                r = {"moderator": m, "B_h": int(bh), "day_demeaned": dm, "n_windows": len(g), "clusters": int(g.A_block.nunique()),
                     "mod_mean": float(g[m].mean()) if len(g) else np.nan, "mod_sd": float(g[m].std()) if len(g) else np.nan}
                if len(g) >= MIN_WIN:
                    d = g.copy()
                    mc = d[m] - d[m].mean()
                    if dm:
                        d = _demean(d, ["pay_rem", "debt_rem", m])
                    X = pd.DataFrame({"debt_rem": d.debt_rem, "mod": d[m], "debt_x_mod": d.debt_rem * mc})
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        f = ols(d.pay_rem, X, groups=d.A_block, fe=d.animal)
                    for nm, t in (("slope_at_mean", term(f, "debt_rem")), ("interaction", term(f, "debt_x_mod")), ("mod_main", term(f, "mod"))):
                        r.update({nm: t["coef"], f"{nm}_lo": t["ci_lo"], f"{nm}_hi": t["ci_hi"], f"{nm}_p": t["p"]})
                    r["interaction_per_sd"] = r["interaction"] * r["mod_sd"]
                    if dm:
                        med = float(np.median(g[m]))
                        hi_ = (g[m] > med).to_numpy()
                        Xh = pd.DataFrame({"debt_low": d.debt_rem * ~hi_, "debt_high": d.debt_rem * hi_, "high": hi_.astype(float)})
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore")
                            fh = ols(d.pay_rem, Xh, groups=d.A_block, fe=d.animal)
                        for half, col in (("low", "debt_low"), ("high", "debt_high")):
                            t = term(fh, col)
                            hv.append({"moderator": m, "B_h": int(bh), "half": half, "n_windows": int((~hi_).sum() if half == "low" else hi_.sum()),
                                       "mod_range": (f"{g[m][~hi_].min():.2f}-{g[m][~hi_].max():.2f}" if half == "low"
                                                     else f"{g[m][hi_].min():.2f}-{g[m][hi_].max():.2f}"),
                                       "slope": t["coef"], "ci_lo": t["ci_lo"], "ci_hi": t["ci_hi"], "p": t["p"]})
                rows.append(r)
    return pd.DataFrame(rows), pd.DataFrame(hv)


def g4_rule(r: pd.Series | dict) -> tuple[str, str]:
    """Plan G4: 'a larger slope where the predicted gain is higher (interaction CI > 0)' (one horizon)."""
    if int(r.get("n_windows", 0)) < MIN_WIN or not np.isfinite(r.get("interaction", np.nan)):
        return "INCONCLUSIVE", f"{int(r.get('n_windows', 0))} windows with the moderator"
    ok = r["interaction_lo"] > 0
    return ("MET" if ok else "NOT MET"), (f"interaction {r['interaction']:+.3f} [{r['interaction_lo']:+.3f}, {r['interaction_hi']:+.3f}] "
                                          f"per unit ({'CI > 0' if ok else 'CI not > 0'}), n {int(r['n_windows'])}")


# ================================================================== G2: post-round vs natural long wakes
def first_rem(st: np.ndarray, bl: list, j0: int, ma: set) -> tuple[int, int, str]:
    """First-REM latency in NREM time from bout j0 on (as Step A's post_wake_table): T = NREM + microarousal seconds
    until the first REM bout; censored at an unknown epoch, a wake >= 7 min or the record end; other wakes pause T."""
    T = 0
    for s, a, b in bl[j0:]:
        if s == 0:
            return T, 0, "unknown"
        if s == W and (b - a) >= LONG_S:
            return T, 0, "wake_ge_7min"
        if s == R:
            return T, 1, "rem"
        if s == N or (s == W and (a, b) in ma):
            T += b - a
    return T, 0, "record_end"


def g2_events(recs: list[dict], gaps: pd.DataFrame, stats: dict | None = None) -> pd.DataFrame:
    """One row per post-round record start (usable round gap, Phase-0 kind) and per natural wake >= 30 min (inside a
    record; no handling gap - round or probe move - of the animal overlapping the 3 h before its start). Definitions:
    report. Columns: group, animal, record_id, block, t_ref (round: record start = gap end; natural: wake end),
    t_first_nrem, d_s (round: gap + initial wake; natural: the wake), d_s_total (round: + the wake that ended the previous
    record), kind_start, kind_end, T_s / event / why (first-REM latency)."""
    by_an: dict[str, list] = {}
    for rc in recs:
        by_an.setdefault(rc["animal"], []).append(rc)
    st_ = {"round_gaps": 0, "round_no_record": 0, "round_no_nrem": 0, "natural_ge30_inside": 0, "natural_handled": 0}
    rows = []
    cache = {}

    def prep(rc):
        if rc["record_id"] not in cache:
            st = rc["state"]
            cache[rc["record_id"]] = (bouts(st), {(a, b) for a, b in episode_units(st, MA_S)["ma"]})
        return cache[rc["record_id"]]
    rg = gaps[gaps.usable.astype(bool) & gaps.cause.isin(ROUND_CAUSES)]
    for g in rg.itertuples():
        st_["round_gaps"] += 1
        gs, ge = pd.Timestamp(g.gap_start), pd.Timestamp(g.gap_end)
        post = [rc for rc in by_an.get(g.animal, []) if abs((rc["start"] - ge).total_seconds()) <= 5]
        if not post:
            st_["round_no_record"] += 1
            continue
        rc = post[0]
        st = rc["state"]
        bl, ma = prep(rc)
        j0 = next((i for i, (s, a, b) in enumerate(bl) if s == N), None)
        if j0 is None:
            st_["round_no_nrem"] += 1
            continue
        f = bl[j0][1]
        pre = [p for p in by_an.get(g.animal, []) if abs((p["end"] - gs).total_seconds()) <= 5]
        w_pre = 0
        if pre:
            bp = bouts(pre[0]["state"])
            if bp and bp[-1][0] == W:
                w_pre = bp[-1][2] - bp[-1][1]
        T, ev, why = first_rem(st, bl, j0, ma)
        d = (ge - gs).total_seconds() + f
        rows.append({"group": "round", "animal": g.animal, "record_id": rc["record_id"], "block": rc["block"], "t_ref": rc["start"],
                     "t_first_nrem": rc["start"] + pd.Timedelta(seconds=f), "t_wake_start": gs - pd.Timedelta(seconds=w_pre),
                     "d_s": d, "d_s_total": d + w_pre, "gap_min": float(g.gap_min), "init_wake_s": f, "pre_wake_s": w_pre,
                     "kind_start": g.kind, "kind_end": kind_of(ge), "cause": g.cause, "T_s": T, "event": ev, "why": why})
    hand = gaps[gaps.cause.isin(HANDLING)].copy()
    hand["g_s"], hand["g_e"] = pd.to_datetime(hand.gap_start), pd.to_datetime(hand.gap_end)
    for rc in recs:
        st = rc["state"]
        n = len(st)
        bl, ma = prep(rc)
        hh = hand[hand.animal == rc["animal"]]
        for i, (s, a, b) in enumerate(bl):
            if s != W or (b - a) < G2_MIN_S or not (a > 0 and st[a - 1] != 0 and b < n and st[b] != 0):
                continue
            st_["natural_ge30_inside"] += 1
            ws, we = rc["start"] + pd.Timedelta(seconds=a), rc["start"] + pd.Timedelta(seconds=b)
            if ((hh.g_e > ws - pd.Timedelta(seconds=LOOKBACK_S)) & (hh.g_s < ws)).any():
                st_["natural_handled"] += 1
                continue
            T, ev, why = first_rem(st, bl, i + 1, ma)
            rows.append({"group": "natural", "animal": rc["animal"], "record_id": rc["record_id"], "block": rc["block"], "t_ref": we,
                         "t_first_nrem": we, "t_wake_start": ws, "d_s": float(b - a), "d_s_total": float(b - a), "gap_min": np.nan,
                         "init_wake_s": 0, "pre_wake_s": 0, "kind_start": kind_of(ws), "kind_end": kind_of(we), "cause": "natural",
                         "T_s": T, "event": ev, "why": why})
    E = pd.DataFrame(rows)
    if len(E):
        E["round"] = (E.group == "round").astype(float)
        E["bin"] = [bin_of(x) for x in E.d_s]
        E["bin_total"] = [bin_of(x) for x in E.d_s_total]
        E["dark_ref"] = (~light_flags(pd.Series(E.t_ref))).astype(float)
    if stats is not None:
        stats.update(st_)
    return E


def cells_of(E: pd.DataFrame, kind_col: str | None = "kind_start", bin_col: str = "bin") -> pd.Series:
    """Cell = kind x wake-length bin (kind_col None: the bin only, any clock time); None = not matched."""
    if kind_col is None:
        return pd.Series(np.where(E[bin_col].notna(), E[bin_col].astype(str), None), index=E.index)
    ok = E[kind_col].isin(KINDS) & E[bin_col].notna()
    return pd.Series(np.where(ok, E[kind_col].astype(str) + " | " + E[bin_col].astype(str), None), index=E.index)


def matched_cells(E: pd.DataFrame, cell: pd.Series) -> list[str]:
    c = E.assign(cell=cell).dropna(subset=["cell"])
    has = c.groupby("cell").group.agg(lambda s: set(s))
    return sorted([k for k, v in has.items() if {"round", "natural"} <= v])


def g2_cox(E: pd.DataFrame, cell: pd.Series, extra: tuple = ()) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """Cox of the first-REM hazard in NREM time ~ round + cell dummies, animal strata, SEs clustered by block, on the
    matched cells; KM medians per group x cell; per-animal Cox (no strata, no clusters) for animals with >= 3 events of
    each group."""
    mc = matched_cells(E, cell)
    d = E.assign(cell=cell)
    d = d[d.cell.isin(mc)].copy()
    dums = []
    for c in mc[1:]:
        nm = "c_" + c.replace(" | ", "_").replace(" ", "").replace(">=", "ge").replace("-", "to")
        d[nm] = (d.cell == c).astype(float)
        dums.append(nm)
    cx = cox(d, ["round"] + dums + list(extra), T="T_s", E="event", strata="animal", groups="block")
    r = {**cterm(cx, "round"), "n": len(d), "rounds": int(d["round"].sum()), "naturals": int((d["round"] == 0).sum()),
         "events": int(d.event.sum()), "cells": "; ".join(mc), "terms_kept": ", ".join(cx.index) if cx is not None else ""}
    km = []
    for (gp, c), g in d.groupby(["group", "cell"]):
        km.append({"group": gp, "cell": c, "n": len(g), "rem_reached": int(g.event.sum()), "km_median_nrem_min": km_median(g.T_s, g.event) / 60,
                   "median_d_min": float(g.d_s.median() / 60)})
    pa = []
    for an, g in d.groupby("animal"):
        row = {"animal": an, "rounds": int(g["round"].sum()), "naturals": int((g["round"] == 0).sum()), "events": int(g.event.sum())}
        if row["rounds"] >= 3 and row["naturals"] >= 3 and g.event.sum() >= 3:
            ca = cox(g, ["round"] + [x for x in dums if g[x].nunique() > 1], T="T_s", E="event", strata=None, groups=None)
            row["cox_round_coef"] = cterm(ca, "round")["coef"]
        pa.append(row)
    return r, pd.DataFrame(km), pd.DataFrame(pa)


def g2_oe_events(E: pd.DataFrame, steps: StepIndex, align: str = "ref") -> pd.DataFrame:
    """Per event x window: O = REM entries (y = 1) among the held-out NREM steps of the event's record whose time lies in
    [t0 + w0, t0 + w1) (t0 = t_ref, or t_first_nrem for align = 'first_nrem'); E_* = the sums of the per-step
    probabilities; n = steps; post_round = steps flagged post-round."""
    rows = []
    for r in E.itertuples():
        t0 = r.t_ref if align == "ref" else r.t_first_nrem
        for wl, w0, w1 in G2_WINDOWS:
            w = steps.window(r.record_id, t0 + pd.Timedelta(seconds=w0), t0 + pd.Timedelta(seconds=w1))
            rows.append({"ev": r.Index, "window": wl, "O": w["y1"], "E": w["p_rem"], "E_pb": w["pb_rem"], "E_gate": w["p_rem_gate"],
                         "n_steps": w["one"], "n_post_round": w["post_round"]})
    return pd.DataFrame(rows)


def _oe_matched(arr: np.ndarray) -> tuple[float, float, float, float]:
    """arr: (2 groups [round, natural], n_cells, 2 [O, E]). Returns (O/E round, natural O/E standardised to the round's
    expected-count weights, difference, natural O/E pooled) over the cells with E > 0 in both groups."""
    Er, En = arr[0, :, 1], arr[1, :, 1]
    ok = (Er > 0) & (En > 0)
    if not ok.any():
        return np.nan, np.nan, np.nan, np.nan
    oe_r = arr[0, ok, 0].sum() / Er[ok].sum()
    w = Er[ok] / Er[ok].sum()
    oe_n = float(np.sum(w * arr[1, ok, 0] / En[ok]))
    return float(oe_r), oe_n, float(oe_r - oe_n), float(arr[1, ok, 0].sum() / En[ok].sum())


def g2_matched(OE: pd.DataFrame, E: pd.DataFrame, cell: pd.Series, ecol: str, rng, n_boot: int = N_BOOT) -> tuple[list[dict], list[dict], list[dict]]:
    """Matched O/E difference per window: O/E_round - sum_c w_c O/E_natural,c (w_c = round expected count share of cell
    c), over the matched cells; 95 % CI by bootstrap over blocks (the event's record block); per-animal differences."""
    mc = matched_cells(E, cell)
    D = OE.merge(E[["group", "animal", "block"]].assign(cell=cell), left_on="ev", right_index=True)
    D = D[D.cell.isin(mc)]
    blocks = sorted(D.block.unique())
    bi = {b: i for i, b in enumerate(blocks)}
    ci = {c: i for i, c in enumerate(mc)}
    res, pa, cells = [], [], []
    for wl, _, _ in G2_WINDOWS:
        g = D[D.window == wl]
        arr = np.zeros((len(blocks), 2, len(mc), 2))
        for r in g.itertuples():
            k = 0 if r.group == "round" else 1
            arr[bi[r.block], k, ci[r.cell], 0] += r.O
            arr[bi[r.block], k, ci[r.cell], 1] += getattr(r, ecol)
        tot = arr.sum(0)
        oe_r, oe_n, diff, oe_np = _oe_matched(tot)
        bs = np.full((n_boot, 3), np.nan)
        for b in range(n_boot):
            cnt = np.bincount(rng.integers(0, len(blocks), len(blocks)), minlength=len(blocks)).astype(float)
            x = np.tensordot(cnt, arr, axes=(0, 0))
            o1, o2, dd, _ = _oe_matched(x)
            bs[b] = (o1, o2, dd)
        lo, hi = np.nanpercentile(bs, [2.5, 97.5], axis=0)
        neg, n_an = 0, 0
        for an, ga in g.groupby("animal"):
            aa = np.zeros((2, len(mc), 2))
            for r in ga.itertuples():
                k = 0 if r.group == "round" else 1
                aa[k, ci[r.cell], 0] += r.O
                aa[k, ci[r.cell], 1] += getattr(r, ecol)
            a1, a2, ad, _ = _oe_matched(aa)
            pa.append({"window": wl, "expected": ecol, "animal": an, "oe_round": a1, "oe_natural_std": a2, "diff": ad,
                       "O_round": float(aa[0, :, 0].sum()), "E_round": float(aa[0, :, 1].sum()), "O_natural": float(aa[1, :, 0].sum()),
                       "E_natural": float(aa[1, :, 1].sum())})
            if np.isfinite(ad):
                n_an += 1
                neg += int(ad < 0)
        for c in mc:
            j = ci[c]
            cells.append({"window": wl, "expected": ecol, "cell": c, "O_round": tot[0, j, 0], "E_round": tot[0, j, 1],
                          "oe_round": tot[0, j, 0] / tot[0, j, 1] if tot[0, j, 1] > 0 else np.nan, "O_natural": tot[1, j, 0],
                          "E_natural": tot[1, j, 1], "oe_natural": tot[1, j, 0] / tot[1, j, 1] if tot[1, j, 1] > 0 else np.nan,
                          "events_round": int(g[(g.cell == c) & (g.group == "round") & (g.n_steps > 0)].ev.nunique()),
                          "events_natural": int(g[(g.cell == c) & (g.group == "natural") & (g.n_steps > 0)].ev.nunique())})
        res.append({"window": wl, "expected": ecol, "oe_round": oe_r, "oe_round_lo": lo[0], "oe_round_hi": hi[0], "oe_natural_std": oe_n,
                    "oe_natural_lo": lo[1], "oe_natural_hi": hi[1], "oe_natural_pooled": oe_np, "diff": diff, "diff_lo": lo[2], "diff_hi": hi[2],
                    "animals_negative": neg, "animals": n_an, "O_round": float(tot[0, :, 0].sum()), "E_round": float(tot[0, :, 1].sum()),
                    "O_natural": float(tot[1, :, 0].sum()), "E_natural": float(tot[1, :, 1].sum()),
                    "events_round": int(g[(g.group == "round") & (g.n_steps > 0)].ev.nunique()),
                    "events_natural": int(g[(g.group == "natural") & (g.n_steps > 0)].ev.nunique()), "blocks": len(blocks), "cells": "; ".join(mc)})
    return res, pa, cells


def g2_rule(r: pd.Series | dict) -> tuple[str, str]:
    """Plan G2 (one window, one scoring): 'post-round REM O/E below the natural-wake O/E (bootstrap CI of the difference
    < 0), >= 5/6 rats'."""
    if not np.isfinite(r.get("diff", np.nan)):
        return "INCONCLUSIVE", "no matched data"
    ok_ci, ok_an = r["diff_hi"] < 0, int(r["animals_negative"]) >= 5
    return ("MET" if ok_ci and ok_an else "NOT MET"), (f"difference {r['diff']:+.3f} [{r['diff_lo']:+.3f}, {r['diff_hi']:+.3f}] "
                                                       f"({'CI < 0' if ok_ci else 'CI not < 0'}), animals negative {int(r['animals_negative'])}/"
                                                       f"{int(r['animals'])} ({'>= 5' if ok_an else '< 5'})")


def load_steps(lab: str) -> pd.DataFrame | None:
    p = HELDOUT / f"heldout_steps_{'final' if lab == 'FINAL' else 'pass2med'}.csv.gz"
    if not p.exists():
        return None
    S = pd.read_csv(p)
    miss = [c for c in STEP_COLS if c not in S]
    if miss:
        raise ValueError(f"{p}: missing columns {miss}")
    S["t"] = pd.to_datetime(S.t)
    return S


def steps_check(S: pd.DataFrame, recs: list[dict]) -> dict:
    """Every held-out step must sit on an NREM second of its record (record_id, t)."""
    by = {rc["record_id"]: rc for rc in recs}
    ok = tot = miss = 0
    for rid, g in S.groupby("record_id"):
        rc = by.get(int(rid))
        if rc is None:
            miss += len(g)
            continue
        off = ((g.t - rc["start"].floor("s")).dt.total_seconds().round().astype(int)).to_numpy()   # t = floor(start) + offset
        inb = (off >= 0) & (off < len(rc["state"]))
        ok += int(np.sum(rc["state"][off[inb]] == N))
        tot += len(g)
    return {"steps": len(S), "records": int(S.record_id.nunique()), "blocks": int(S.block.nunique()), "steps_on_nrem": ok,
            "steps_checked": tot, "steps_unknown_record": miss, "share_on_nrem": ok / tot if tot else np.nan}


# ================================================================== definitions (report)
DEFINITIONS = [
    "## Definitions", "",
    r"Time is field-PC local time. States per second: $s_t \in \{0\ \text{unknown}, 1\ \text{WAKE}, 3\ \text{NREM}, 5\ \text{REM}\}$. "
    r"Animals $a$; blocks $k$ = day-half blocks of `sleep_cycles_v2.build_records` (record start 06–18 h → D, else N).", "",
    "### Shared",
    r"- **Record.** Sessions of an animal joined across splits ≤ 60 s (`sleep_model.records_for`); FINAL exclusions and the "
    r"cut at 2026-09-11 19:40. Same records under both scorings. **Scorings:** FINAL = `states_1s_final`; pass2med = "
    r"`states_1s_pass2med` (fixed per-animal thresholds; the scoring #10 / #43 are scoped to). **Bout** = a maximal run of one "
    r"state, $[a, b)$, length $b - a$.",
    r"- **Light.** $\text{dark}(t) = \neg[\text{sunrise}(t) \le t < \text{sunset}(t)]$, NOAA times (`sleep_quant.sun_times`).",
    r"- **Gaps** (Phase-0 table): the time between two consecutive records of an animal. Usable: ≤ 180 min with ≥ 1 h recorded "
    r"on both sides. Round = cause `round_logged` or `round_inferred`; handling = a round or a `probe_move`. Kind: morning if "
    r"the gap starts 05:00–11:00, evening 15:30–21:30, else other.",
    r"- **Round payback windows (A4 / #43; `sleep_explore_d.payback_from_records`).** For each usable round gap $[g_s, g_e)$: "
    r"A = $[g_s - 3\,\text{h}, g_s)$, B = $[g_e, g_e + h)$, $h \in \{1, 3\}$ h, sums of the animal's 10-min bins (≥ 80 % recorded). "
    r"Expected amounts from the phase × day baselines (leave-one-block-out binomial REM / NREM share with "
    r"$x = [1, \sin/\cos(2\pi j\,\text{hour}/24)_{j=1,2}, \text{day}, \text{dark}, \text{dark}\times\text{day}, \text{animal}]$, "
    r"day = days since 2026-08-30 19:00). $\text{debt}_{REM} = \sum_A E[\text{REM}] - \sum_A \text{REM}$, "
    r"$\text{pay}_{REM} = \sum_B \text{REM} - \sum_B E[\text{REM}]$ (min); the same for NREM.",
    r"- **Pay model.** OLS $\text{pay}_w = \alpha_{a(w)} + \beta\,\text{debt}_w [+ \ldots] + \varepsilon_w$, animal fixed effects, "
    r"SEs clustered by the block of window A (`sleep_explore.ols`), 95 % CI $= \hat\beta \pm 1.96\,\widehat{se}$, normal $p$. "
    r"**Day-demeaned:** every variable minus its mean over the windows of the same calendar day (round: gap-start date; dawn "
    r"wake: wake-start date). #43 = morning rounds, $\text{pay}_{REM} \sim \text{debt}_{REM}$, day-demeaned, pass2med.",
    r"- **Held-out per-step predictions** (the main session, `D:/Field2026_analysis_out/2026c/sleep_heldout_steps/`): one "
    r"row per 10-s NREM step $s$ of the test blocks (forward chaining: a step in block $k$ is predicted by the fit on blocks "
    r"$< k$; the first 6 blocks are never predicted). $y_s \in \{0\ \text{stay}, 1\ \text{REM}, 2\ \text{WAKE}\}$ = the "
    r"transition at the end of the step. $\hat p_{REM,s}$ = B-full at `P_tw600_k0` (the REM-entry count with $\tau_w$ = 600 s, "
    r"full discharge, + the clock terms (2-harmonic time of day, dark) and the step-B covariates); $\hat p^{pb}_{REM,s}$ = the same model trained without the "
    r"3 h after round gaps (perturbation-blind); $\hat p^{clock}_{REM,s}$ = the clock-only model without the counter (clock, "
    r"elapsed-in-bout, day, dark, anchor and the L1 terms: preceding wake, previous bout REM / unknown, wake share of the last "
    r"10 min; step B's 'gate-only' + L1, per the folder's README).", "",
    "### G1",
    r"- **D1 primary model** (Step D1, natural dawn wakes = WAKE bouts ≥ 30 min ending 05:00–09:00 inside a record, no "
    r"handling in the 3 h before; A = the 3 h before the wake, B = the 1 h after it; exact-second windows): day-demeaned "
    r"$\text{pay}_{REM} = \alpha_a + \beta\,\text{debt}_{REM} + \gamma\,\text{debt}_{NREM} + \delta\,\text{onset}_h + \varepsilon$, "
    r"SEs clustered by block; $n$ windows, $k$ parameters, $G$ clusters.",
    r"- **Analytic MDS** (the plan: from the debt variance and the residual SD). $\tilde x$ = the day-demeaned REM debt "
    r"residualised on the other columns (intercept, covariates, animal dummies; Frisch–Waugh); $\hat\sigma = "
    r"\sqrt{\sum \hat\varepsilon^2/(n-k)}$; $\text{SE}_{iid} = \hat\sigma / \sqrt{\sum \tilde x_i^2} = \hat\sigma / "
    r"(\text{SD}(\tilde x)\sqrt{n-1})$; $\text{MDS} = (z_{1-\alpha/2} + z_{0.80})\,\text{SE}_{iid} = 2.80\,\text{SE}_{iid}$ "
    r"($\alpha$ = 0.05 two-sided). Also with $t_{n-k}$ quantiles and with the fit's cluster-robust SE ($\text{MDS}_{cl}$). "
    r"Analytic power at a true slope $\beta^*$: $\Phi(\beta^*/\text{SE} - z_{0.975})$.",
    r"- **Simulated MDS** (planting slopes into the real windows). $\hat m_0 = X\hat b - \hat\beta x$ (the fitted values "
    r"without the debt term), $\hat\varepsilon$ = residuals; replicate $r$: $y^*_i = \hat m_{0,i} + \beta^* x_i + "
    r"\hat\varepsilon_i v_{g(i)}$, $v_g \in \{-1, +1\}$ equiprobable per cluster (wild cluster bootstrap), refit with the "
    r"same cluster-robust test; power$(\beta^*)$ = share of replicates with $p < 0.05$ and $\hat\beta > 0$; MDS$_{sim}$ = the "
    rf"smallest $\beta^*$ (linear interpolation on a grid of step 0.02) with power ≥ 0.80; {N_SIM} replicates per grid point. "
    r"Also the power of D1's full rule ($\hat\beta > 0.2$, $p < 0.05$, every rat with ≥ 3 windows with a positive simple slope).",
    r"- **G1 rule** (plan): informative iff the MDS ≤ 0.34 (the round slope); operationalised: the analytic MDS$_{iid}$ AND "
    r"the simulated MDS ≤ 0.34. Positive = D1's slope > 0 with $p$ < 0.05.", "",
    "### G2 (H18)",
    r"- **Post-round event.** Each usable round gap whose next record starts within 5 s of $g_e$; reference $t_0$ = the record "
    r"start ($= g_e$). Matched wake length $d = (g_e - g_s) + f$, $f$ = seconds from the record start to its first NREM "
    r"second (the gap is counted as wake: the animal was handled). Sensitivity: $d_{tot} = d$ + the WAKE bout that ended "
    r"the previous record.",
    r"- **Natural wake event.** A WAKE bout $[a, b)$ with $b - a \ge 1800$ s inside a record (known seconds on both sides), "
    r"with no handling gap of the animal overlapping $[t_a - 3\,\text{h}, t_a)$; $t_0$ = the wake end $t_b$; $d = b - a$.",
    r"- **Cells.** Kind = Phase 0's clock rule applied to the wake start (round: the gap start, = the Phase-0 kind; natural: "
    r"$t_a$); bin = 30–120 min or ≥ 2 h (plan section 3 bins at ≥ 30 min); cell = kind × bin; events of kind other are not "
    r"matched. Only cells with both groups are used (**matched cells**). Sensitivities: kind by the wake end; $d_{tot}$ bins.",
    r"- **First-REM latency in NREM time** (as Step A's A1): from the first NREM bout after $t_0$, $T$ = NREM + microarousal "
    r"(wake < 40 s between NREM bouts) seconds until the first REM bout; censored at an unknown epoch, a wake ≥ 7 min or the "
    r"record end; other wakes pause $T$. **Cox** (statsmodels PHReg, Efron ties): $h(T) = h_{0,a}(T)\exp(\beta_{round}"
    r"\,\text{round} + \sum_c \gamma_c\,\text{cell}_c)$, animal strata, SEs clustered by block; $\beta_{round} < 0$ = a later "
    r"first REM after rounds (H18's 'round term CI > 0' on the latency scale = CI of $\beta_{round}$ < 0). KM medians per "
    r"group × cell (NREM min).",
    r"- **REM-entry O/E** (as S2). Windows $[t_0, t_0 + 1\,\text{h})$ and $[t_0 + 1\,\text{h}, t_0 + 3\,\text{h})$, the "
    r"held-out NREM steps of the event's record with step time in the window: $O = \sum_s [y_s = 1]$, $E = \sum_s \hat p_{REM,s}$ "
    r"($E^{pb}$ with $\hat p^{pb}$). Per group and cell $c$: $O_{gc}, E_{gc}$ summed over events. "
    r"$\text{O/E}_{round} = \sum_c O_{rc} / \sum_c E_{rc}$; $\text{O/E}_{natural} = \sum_c w_c\,O_{nc}/E_{nc}$ with "
    r"$w_c = E_{rc}/\sum_{c'} E_{rc'}$ (standardised to the rounds' cell mix); $\Delta = \text{O/E}_{round} - \text{O/E}_{natural}$, "
    r"over the matched cells with $E > 0$ in both groups. 95 % CI: percentile bootstrap over blocks (the event record's "
    rf"block; {N_BOOT} replicates). Per animal: the same $\Delta$ from the animal's events. Sensitivity: windows aligned at "
    r"the first NREM second after $t_0$.",
    r"- **G2 rule** (plan, one window): $\Delta$'s CI < 0 and ≥ 5 animals with $\Delta < 0$, on both scorings, with "
    r"$\hat p_{REM}$. Operationalised: applied to each window; G2 passes if one window meets it on both scorings. "
    r"$\hat p^{pb}$ and the Cox term are reported.", "",
    "### G3",
    r"- **Gap debt.** $\text{gapdebt}_{REM} = \sum_{m} \omega_m\,\hat\pi^{REM}(t_m)$ (min): the phase × day baseline REM share "
    r"(the same binomial GLM, fitted leave-one-block-out without window A's block) at the midpoint $t_m$ of each minute $m$ "
    r"of the gap, $\omega_m$ = the minute's length (1, or the last partial minute); the REM the animal would have had in "
    r"the gap at the baseline rate, all counted as missed (no recording). $\text{gapdebt}_{NREM}$ likewise (reported).",
    r"- **Models** (morning rounds; evening reported): M0 $\text{pay}_{REM} \sim \text{debt}_{REM}$ (= #43), M1 "
    r"$\text{pay}_{REM} \sim \text{debt}_{REM} + \text{gapdebt}_{REM}$, M2 $\text{pay}_{REM} \sim \text{gapdebt}_{REM}$; "
    r"animal FE, clustered by block, raw and day-demeaned. $\text{fall} = 1 - \hat\beta_{debt}^{M1}/\hat\beta_{debt}^{M0}$.",
    r"- **G3 rule** (plan, per horizon, day-demeaned, pass2med): the gap-debt slope's CI > 0 AND fall ≥ 30 %. "
    r"Operationalised: met at 1 h and 3 h = MET; at one = PARTLY (not a pass).",
    r"- **By gap-length tertile.** Tertile cut points of the gap length over the horizon's morning windows; one day-demeaned "
    r"model $\text{pay}_{REM} \sim \sum_{k=1}^{3}\beta_k\,\text{debt}_{REM}[\text{tertile} = k] + [T2] + [T3]$ + animal FE.", "",
    "### G4",
    r"- **Onset.** The first Watson SLEEP episode (no WAKE bout > 120 s or unknown epoch inside, ≥ 20 min; `phase3.episodes_of`) "
    r"of the post-round record (`sleep_explore_d.round_onsets`); $\text{onset}_{sr}$ = its start minus NOAA sunrise of that "
    r"date (h).",
    r"- **Predicted REM-entry gain.** $g^{clock}_w = \frac{360}{|S_w|}\sum_{s \in S_w}\hat p^{clock}_{REM,s}$, $S_w$ = the held-out "
    r"NREM steps of the post-round record in window B: the clock-only model's REM entries per NREM hour during the payback "
    r"window (windows in the first 6 blocks have none). Sensitivity, all windows: $g^{base}_w = \sum_B E[\text{on}] / "
    r"(\sum_B E[\text{NREM}]/60)$, the phase × day baseline's expected REM onsets per expected NREM hour in B.",
    r"- **Interaction model.** $\text{pay}_{REM} = \alpha_a + \beta\,\text{debt}_{REM} + \gamma\,m + \delta\,\text{debt}_{REM}"
    r"\,(m - \bar m) + \varepsilon$, animal FE, clustered by block; day-demeaned: $\text{pay}$, $\text{debt}$ and $m$ "
    r"day-demeaned, the product of the day-demeaned debt and the globally centred $m$ (so $\delta$ = the change of the "
    r"within-day payback slope per unit of $m$). Also the slopes in the halves of $m$ (median split, one model).",
    r"- **G4 rule** (plan): $\delta$'s CI > 0 for $g^{clock}$ (day-demeaned, pass2med); operationalised as G3: both horizons "
    r"= MET, one = PARTLY.", "",
    "### Reading rule (plan, section 9)", "",
    "| result | reading |", "|---|---|", "| G2 pass, G3 fail | handling-specific |", "| G3 pass | the round's sleep loss |",
    "| G1 informative and positive | dawn timing |", "| all fail | #43 stays Candidate (power) |", "",
    "G4 has no row in the table; its own pass sentence is \"a deficit released where the gate opens\".", "",
]


# ================================================================== driver
def run(a) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from _common import git_commit, write_json
    from output_paths import figure_dir, report_dir, run_dir
    from sleep_model import records_for
    from sleep_quant import save_fig
    t_all = time.time()
    parts = list(dict.fromkeys(a.parts))
    scs = list(dict.fromkeys(a.scorings))
    labs = [SCORINGS[s][0] for s in scs]
    prim = "pass2med" if "pass2med" in labs else labs[0]
    out = run_dir("sleep_explore_G", "2026c")
    rd, fd = report_dir("2026c", "ephys_spikes"), figure_dir("2026c", "ephys_spikes")
    gc = git_commit()
    rng = np.random.default_rng(20261009)
    gaps_path = Path(json.load(open(P0_MANIFEST))["run_dir"]) / "gaps.csv"
    gaps = pd.read_csv(gaps_path, parse_dates=["gap_start", "gap_end"])
    RT, REPRO = [], []
    G1S, G1P, G2R, G2C, G2K, G2PA, G2CELLS, G2CHK, G2FUN = [], [], [], [], [], [], [], [], []
    G3M, G3T, G3G, G4M, G4H, G4D = [], [], [], [], [], []
    steps_info = {}
    for sc in scs:
        lab, sdir = SCORINGS[sc]
        t0 = time.time()
        recs = records_for(sdir)
        print(f"{lab}: {len(recs)} records ({time.time() - t0:.1f} s)", flush=True)
        bins = baseline_bins(recs)
        T, Wn = payback_from_records(recs, gaps, lab, bins=bins, return_windows=True)
        Wn = _add_pay(Wn)
        Wn.to_csv(out / f"round_windows_{lab}.csv.gz", index=False)
        for bh in (1, 3):
            r_ = T[(T.kind == "morning") & (T.outcome == "pay_rem") & (T.predictors == "debt_rem") & T.day_demeaned & (T.B_h == bh)]
            REPRO.append({"scores": lab, "check": f"#43 morning payback, B = {bh} h (day-demeaned)", "value": float(r_.slope.iloc[0]),
                          "ci": f"[{r_.ci_lo.iloc[0]:+.3f}, {r_.ci_hi.iloc[0]:+.3f}]", "n_windows": int(r_.n_windows.iloc[0])})
        S = load_steps(lab) if ("g2" in parts or "g4" in parts) else None
        SI = None
        if S is not None:
            chk = steps_check(S, recs)
            chk["scores"] = lab
            G2CHK.append(chk)
            SI = StepIndex(S)
            steps_info[lab] = chk
            print(f"   held-out steps: {chk['steps']} steps, {chk['blocks']} blocks, share on NREM {chk['share_on_nrem']:.4f}", flush=True)
        elif "g2" in parts or "g4" in parts:
            print(f"   held-out steps for {lab} NOT FOUND in {HELDOUT}: G2 O/E and G4's held-out gain are skipped", flush=True)
        # ---------------- G1
        if "g1" in parts:
            t1 = time.time()
            Td, Wd = dawn_payback_from_records(recs, gaps, lab, bins=bins, return_windows=True)
            Wd.to_csv(out / f"dawn_windows_{lab}.csv.gz", index=False)
            for spec, xs in (("primary (D1): debt_rem + debt_nrem + onset_h", PRIMARY_D1), ("covariate-free: debt_rem", ["debt_rem"])):
                d = d1_data(Wd, xs)
                ref = Td[(Td.B_h == 1) & (Td.outcome == "pay_rem") & (Td.predictors == " + ".join(xs)) & Td.day_demeaned].iloc[0]
                s, P = mds_analysis(d, xs, rng)
                REPRO.append({"scores": lab, "check": f"D1 dawn-wake model refit ({spec}, B = 1 h): slope / cluster SE vs D1's",
                              "value": float(s["slope"]), "ci": f"D1 {float(ref.slope):+.4f}; SE {s['se_cl']:.4f} vs {float(ref.se):.4f}",
                              "n_windows": int(s["n_windows"])})
                s.update(scores=lab, model=spec, B_h=1, p=float(ref.p), ci_lo=float(ref.ci_lo), ci_hi=float(ref.ci_hi),
                         d1_slope=float(ref.slope), d1_se=float(ref.se))
                v, why = g1_verdict(s)
                s.update(verdict=v, detail=why)
                G1S.append(s)
                P.insert(0, "model", spec)
                P.insert(0, "scores", lab)
                G1P.append(P)
            n3 = int((Wd.B_h == 3).sum()) if len(Wd) else 0
            G1S.append({"scores": lab, "model": "primary (D1), B = 3 h", "B_h": 3, "n_windows": n3,
                        "verdict": "INCONCLUSIVE", "detail": f"{n3} windows (< {MIN_WIN}); no MDS"})
            RT.append({"scores": lab, "part": "g1", "seconds": round(time.time() - t1, 1)})
        # ---------------- G3
        if "g3" in parts:
            t1 = time.time()
            B, _ = bins
            Wg = gap_expectations(B, Wn)
            Wg["gap_debt_rem"], Wg["gap_debt_nrem"] = Wg.gap_e_rem_min, Wg.gap_e_nrem_min
            Wg["gap_min"] = (pd.to_datetime(Wg.gap_end) - pd.to_datetime(Wg.gap_start)).dt.total_seconds() / 60
            Wg.to_csv(out / f"g3_windows_{lab}.csv.gz", index=False)
            for kind in KINDS:
                Wk = Wg[Wg.kind == kind]
                M = g3_models(Wk)
                M.insert(0, "kind", kind)
                M.insert(0, "scores", lab)
                G3M.append(M)
                Tt = g3_tertiles(Wk)
                Tt.insert(0, "kind", kind)
                Tt.insert(0, "scores", lab)
                G3T.append(Tt)
                u = Wk[Wk.B_h == 1]
                G3G.append({"scores": lab, "kind": kind, "windows_1h": len(u), "gap_min_median": float(u.gap_min.median()),
                            "gap_min_range": f"{u.gap_min.min():.0f}-{u.gap_min.max():.0f}", "gap_debt_rem_mean": float(u.gap_debt_rem.mean()),
                            "gap_debt_rem_sd": float(u.gap_debt_rem.std()), "gap_debt_nrem_mean": float(u.gap_debt_nrem.mean()),
                            "debt_rem_mean": float(u.debt_rem.mean()), "debt_rem_sd": float(u.debt_rem.std()),
                            "gap_rem_share_mean": float((u.gap_debt_rem / u.gap_min).mean())})
            RT.append({"scores": lab, "part": "g3", "seconds": round(time.time() - t1, 1)})
        # ---------------- G4
        if "g4" in parts:
            t1 = time.time()
            Wg4 = g4_data(Wn[Wn.kind == "morning"], recs, SI)
            Wg4.to_csv(out / f"g4_windows_{lab}.csv.gz", index=False)
            M, H = g4_models(Wg4)
            M.insert(0, "scores", lab)
            G4M.append(M)
            if len(H):
                H.insert(0, "scores", lab)
                G4H.append(H)
            for bh in (1, 3):
                u = Wg4[Wg4.B_h == bh]
                G4D.append({"scores": lab, "B_h": bh, "windows": len(u), "with_onset": int(u.onset_time.notna().sum()),
                            "with_heldout_gain": int(u.gain_heldout.notna().sum()), "onset_rel_sunrise_h_median": float(u.onset_rel_sunrise_h.median()),
                            "onset_rel_sunrise_h_range": f"{u.onset_rel_sunrise_h.min():.2f}-{u.onset_rel_sunrise_h.max():.2f}",
                            "gain_heldout_mean": float(u.gain_heldout.mean()), "gain_heldout_sd": float(u.gain_heldout.std()),
                            "gain_base_mean": float(u.gain_base.mean()), "gain_base_sd": float(u.gain_base.std()),
                            "corr_gain_heldout_onset": float(u[["gain_heldout", "onset_rel_sunrise_h"]].corr().iloc[0, 1]) if u.gain_heldout.notna().sum() > 2 else np.nan,
                            "corr_gain_base_onset": float(u[["gain_base", "onset_rel_sunrise_h"]].corr().iloc[0, 1])})
            RT.append({"scores": lab, "part": "g4", "seconds": round(time.time() - t1, 1)})
        # ---------------- G2
        if "g2" in parts:
            t1 = time.time()
            fs = {}
            E = g2_events(recs, gaps, fs)
            E.to_csv(out / f"g2_events_{lab}.csv.gz", index=False)
            cell = cells_of(E)
            fs.update(scores=lab, rounds=int((E.group == "round").sum()), naturals=int((E.group == "natural").sum()),
                      rounds_ge30=int(((E.group == "round") & E.bin.notna()).sum()),
                      rounds_matched=int(((E.group == "round") & cell.isin(matched_cells(E, cell))).sum()),
                      naturals_matched=int(((E.group == "natural") & cell.isin(matched_cells(E, cell))).sum()),
                      naturals_kind_other=int(((E.group == "natural") & (E.kind_start == "other")).sum()))
            if SI is not None:
                mcs = matched_cells(E, cell)
                ok_ = (E.group == "natural") & cell.isin(mcs)
                fs["naturals_matched_with_heldout_steps"] = int(sum(SI.window(r.record_id, r.t_ref, r.t_ref + pd.Timedelta(hours=1))["one"] > 0
                                                                     for r in E[ok_].itertuples()))
                fs["rounds_matched_with_heldout_steps"] = int(sum(SI.window(r.record_id, r.t_ref, r.t_ref + pd.Timedelta(hours=1))["one"] > 0
                                                                   for r in E[(E.group == "round") & cell.isin(mcs)].itertuples()))
                fs["naturals_any_clock_with_heldout_steps"] = int(sum(SI.window(r.record_id, r.t_ref, r.t_ref + pd.Timedelta(hours=1))["one"] > 0
                                                                       for r in E[(E.group == "natural") & E.bin.notna()].itertuples()))
            G2FUN.append(fs)
            for spec, cl in (("primary", cell), ("kind by wake end", cells_of(E, "kind_end")), ("round wake incl. pre-gap wake", cells_of(E, "kind_start", "bin_total")),
                             (G2_POSTHOC, cells_of(E, None))):
                r, km, pa = g2_cox(E, cl, ("dark_ref",) if spec == G2_POSTHOC else ())
                G2C.append({"scores": lab, "spec": spec, **r})
                if spec == "primary":
                    km.insert(0, "scores", lab)
                    G2K.append(km)
                    pa.insert(0, "scores", lab)
                    pa["what"] = "cox"
                    G2PA.append(pa)
            if SI is not None:
                for align in ("ref", "first_nrem"):
                    OE = g2_oe_events(E, SI, align)
                    OE.to_csv(out / f"g2_oe_events_{lab}_{align}.csv.gz", index=False)
                    specs = [("primary", cell)] if align == "first_nrem" else [("primary", cell), ("kind by wake end", cells_of(E, "kind_end")),
                                                                              ("round wake incl. pre-gap wake", cells_of(E, "kind_start", "bin_total")),
                                                                              (G2_POSTHOC, cells_of(E, None))]
                    for spec, cl in specs:
                        nm = spec if align == "ref" else "aligned at the first NREM"
                        for ecol in (("E", "E_pb", "E_gate") if nm == "primary" else ("E",)):
                            res, pa, cells = g2_matched(OE, E, cl, ecol, rng)
                            for r in res:
                                v, why = g2_rule(r)
                                G2R.append({"scores": lab, "spec": nm, **r, "rule": v, "detail": why})
                            if nm == "primary":
                                for x in pa:
                                    G2PA.append(pd.DataFrame([{"scores": lab, "what": "oe", **x}]))
                                for x in cells:
                                    G2CELLS.append({"scores": lab, **x})
                    if align == "ref":
                        pr = OE.merge(E[["group"]], left_on="ev", right_index=True)
                        for gp, g in pr.groupby("group"):
                            steps_info.setdefault(f"{lab}_post_round_flag", {})[gp] = (float(g.n_post_round.sum()), float(g.n_steps.sum()))
            RT.append({"scores": lab, "part": "g2", "seconds": round(time.time() - t1, 1)})
    # ================================================================ tables
    cat = lambda L: pd.concat(L, ignore_index=True) if L else pd.DataFrame()  # noqa: E731
    G1S_, G1P_, G2R_, G2C_, G2K_, G3M_, G3T_, G4M_, G4H_ = (pd.DataFrame(G1S), cat(G1P), pd.DataFrame(G2R), pd.DataFrame(G2C), cat(G2K),
                                                            cat(G3M), cat(G3T), cat(G4M), cat(G4H))
    G2PA_ = cat(G2PA)
    outs = {"repro": pd.DataFrame(REPRO), "runtime": pd.DataFrame(RT), "g1_mds": G1S_, "g1_power": G1P_, "g2_funnel": pd.DataFrame(G2FUN),
            "g2_cox": G2C_, "g2_km": G2K_, "g2_oe": G2R_, "g2_oe_cells": pd.DataFrame(G2CELLS), "g2_per_animal": G2PA_,
            "g2_steps_check": pd.DataFrame(G2CHK), "g3_models": G3M_, "g3_tertiles": G3T_, "g3_gaps": pd.DataFrame(G3G),
            "g4_models": G4M_, "g4_halves": G4H_, "g4_data": pd.DataFrame(G4D)}
    for nm, df in outs.items():
        if len(df):
            df.to_csv(rd / f"ephys_spikes_sleep_explore_G_{nm}_2026c.csv", index=False)

    # ================================================================ verdicts
    VER = []
    g1v = g2v = g3v = g4v = "not run"
    g1_inf = g1_pos = False
    if "g1" in parts and len(G1S_):
        r = G1S_[(G1S_.scores == prim) & (G1S_.model.str.startswith("primary (D1): "))].iloc[0]
        g1v = r.verdict
        g1_inf, g1_pos = g1v.startswith("INFORMATIVE"), g1v == "INFORMATIVE, POSITIVE"
        for _, rr in G1S_.iterrows():
            VER.append({"part": "G1", "scores": rr.scores, "row": f"{rr.model}", "rule": rr.verdict, "detail": rr.detail,
                        "role": "verdict" if (rr.scores == prim and str(rr.model).startswith("primary (D1): ")) else "reported"})
    if "g2" in parts and len(G2R_):
        pr = G2R_[(G2R_.spec == "primary") & (G2R_.expected == "E")]
        win_ok = {}
        for wl, _, _ in G2_WINDOWS:
            st = {lab: pr[(pr.scores == lab) & (pr.window == wl)].rule.iloc[0] for lab in labs if len(pr[(pr.scores == lab) & (pr.window == wl)])}
            win_ok[wl] = len(st) == 2 and all(v == "MET" for v in st.values())
        both = len([lab for lab in labs]) == 2
        g2v = ("MET (" + ", ".join(w for w, ok in win_ok.items() if ok) + ")") if any(win_ok.values()) else ("NOT MET" if both else "INCOMPLETE (one scoring)")
        kmax = int(pr.animals.max()) if len(pr) else 0
        if not any(win_ok.values()) and kmax < 5:
            g2v += (f" — power-limited: at most {kmax} animals have matched natural wakes with held-out predictions in a window, so the "
                    "rats condition (>= 5) could not be met")
        for _, rr in G2R_.iterrows():
            VER.append({"part": "G2", "scores": rr.scores, "row": f"{rr.spec}, {rr.window}, expected {rr.expected}", "rule": rr.rule,
                        "detail": rr.detail, "role": "verdict" if (rr.spec == "primary" and rr.expected == "E") else "reported"})
    elif "g2" in parts:
        g2v = "INCOMPLETE (no held-out steps)"
    if "g3" in parts and len(G3M_):
        g3st = {}
        for _, rr in G3M_[G3M_.day_demeaned].iterrows():
            v, why = g3_rule(rr)
            role = "verdict" if (rr.scores == prim and rr.kind == "morning") else "reported"
            VER.append({"part": "G3", "scores": rr.scores, "row": f"{rr.kind}, B = {rr.B_h} h, day-demeaned", "rule": v, "detail": why, "role": role})
            if role == "verdict":
                g3st[int(rr.B_h)] = v
        g3v = combine_horizons(g3st)
    if "g4" in parts and len(G4M_):
        g4st = {}
        for _, rr in G4M_[G4M_.day_demeaned].iterrows():
            v, why = g4_rule(rr)
            role = "verdict" if (rr.scores == prim and rr.moderator == "gain_heldout") else "reported"
            VER.append({"part": "G4", "scores": rr.scores, "row": f"{rr.moderator}, B = {rr.B_h} h, day-demeaned", "rule": v, "detail": why, "role": role})
            if role == "verdict":
                g4st[int(rr.B_h)] = v
        g4v = combine_horizons(g4st)
    VT = pd.DataFrame(VER)
    if len(VT):
        VT.to_csv(rd / "ephys_spikes_sleep_explore_G_verdicts_2026c.csv", index=False)
    g2_pass, g3_pass, g4_pass = g2v.startswith("MET"), g3v == "MET", g4v == "MET"
    readings = []
    if g3_pass:
        readings.append("the round's sleep loss (G3 pass)")
    if g2_pass and not g3_pass:
        readings.append("handling-specific (G2 pass, G3 fail)")
    if g1_inf and g1_pos:
        readings.append("dawn timing (G1 informative and positive)")
    if not readings:
        readings.append("#43 stays Candidate (power) — no row of the reading table applies" + ("; G4's own pass sentence applies: "
                        "'a deficit released where the gate opens'" if g4_pass else ""))
    elif g4_pass:
        readings.append("plus G4's own pass sentence: 'a deficit released where the gate opens'")
    reading = "; ".join(readings)

    # ================================================================ figures
    figs = {}
    if len(G1P_):
        fig, axs = plt.subplots(1, len(labs), figsize=(5.2 * len(labs), 3.8), squeeze=False)
        for i, lab in enumerate(labs):
            ax = axs[0, i]
            P = G1P_[(G1P_.scores == lab) & G1P_.model.str.startswith("primary")]
            s = G1S_[(G1S_.scores == lab) & G1S_.model.str.startswith("primary (D1): ")]
            if not len(P):
                continue
            ax.plot(P.planted, P.power_sig, color=COLORS["dark"], lw=2, label="simulated (p < 0.05, slope > 0)")
            ax.plot(P.planted, P.power_d1_rule, color=COLORS["light"], lw=2, label="simulated, D1's full rule")
            ax.plot(P.planted, P.power_analytic_iid, color=COLORS["ink"], lw=1.2, ls="--", label="analytic (iid SE)")
            ax.axhline(POWER, color=COLORS["ink"], lw=0.6, alpha=0.6)
            ax.axvline(ROUND_SLOPE, color=COLORS["ink"], lw=0.8, ls=":")
            ax.text(ROUND_SLOPE, 0.03, " round slope 0.34", fontsize=7, color=COLORS["ink"])
            ttl = f"G1 {lab}: D1 primary model, B = 1 h"
            if len(s):
                ttl += f"\nMDS analytic {s.mds_analytic_iid_z.iloc[0]:.2f}, simulated {s.mds_sim.iloc[0]:.2f}, n {int(s.n_windows.iloc[0])}"
            ax.set_title(ttl, fontsize=9, color=COLORS["ink"])
            ax.set_xlabel("planted slope (min REM paid back per min of debt)")
            ax.set_ylabel("power")
            ax.set_ylim(0, 1.02)
            ax.spines[["top", "right"]].set_visible(False)
            if i == 0:
                ax.legend(fontsize=7, frameon=False, loc="lower right")
        fig.tight_layout()
        figs["g1"] = "ephys_spikes_sleep_explore_G_g1_power_2026c.png"
        save_fig(fig, fd / figs["g1"])
        plt.close(fig)
    if len(G2R_) or len(G2K_):
        fig, axs = plt.subplots(2, len(labs), figsize=(5.2 * len(labs), 7.2), squeeze=False)
        for i, lab in enumerate(labs):
            ax = axs[0, i]
            pr = G2R_[(G2R_.scores == lab) & (G2R_.spec == "primary") & (G2R_.expected == "E")] if len(G2R_) else pd.DataFrame()
            if len(pr):
                xs_ = np.arange(len(pr))
                for k, (col, lo, hi, c, lb) in enumerate((("oe_round", "oe_round_lo", "oe_round_hi", COLORS["light"], "post-round"),
                                                          ("oe_natural_std", "oe_natural_lo", "oe_natural_hi", COLORS["dark"], "natural (matched)"))):
                    ax.bar(xs_ + (k - 0.5) * 0.36, pr[col], width=0.34, color=c, label=lb)
                    ax.errorbar(xs_ + (k - 0.5) * 0.36, pr[col].to_numpy(), yerr=[(pr[col] - pr[lo]).to_numpy(), (pr[hi] - pr[col]).to_numpy()], fmt="none",
                                ecolor=COLORS["ink"], lw=1)
                ax.set_xticks(xs_, pr.window)
                ax.axhline(1, color=COLORS["ink"], lw=0.6)
                ax.set_ylabel("REM entries, observed / expected (B-full)")
                ax.legend(fontsize=7, frameon=False)
            ax.set_title(f"G2 {lab}: REM-entry O/E after the wake", fontsize=9, color=COLORS["ink"])
            ax.spines[["top", "right"]].set_visible(False)
            ax = axs[1, i]
            Ef = None
            try:
                Ef = pd.read_csv(out / f"g2_events_{lab}.csv.gz")
            except FileNotFoundError:
                pass
            if Ef is not None and len(Ef):
                from sleep_schedule_phase3 import km
                cl = cells_of(Ef)
                mc = matched_cells(Ef, cl)
                Ef = Ef[cl.isin(mc)]
                for gp, c in (("round", COLORS["light"]), ("natural", COLORS["dark"])):
                    g = Ef[Ef.group == gp]
                    ut, S_ = km(g.T_s.to_numpy(float), g.event.to_numpy(int))
                    ax.step(np.r_[0, ut / 60], np.r_[1, S_], where="post", color=c, lw=2, label=f"{'post-round' if gp == 'round' else 'natural'} (n {len(g)})")
                ax.set_xlim(0, 90)
                ax.set_xlabel("NREM minutes after the wake")
                ax.set_ylabel("share without REM yet (KM)")
                ax.legend(fontsize=7, frameon=False)
            ax.set_title(f"G2 {lab}: first-REM latency, matched cells", fontsize=9, color=COLORS["ink"])
            ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        figs["g2"] = "ephys_spikes_sleep_explore_G_g2_2026c.png"
        save_fig(fig, fd / figs["g2"])
        plt.close(fig)
    if len(G3T_):
        fig, axs = plt.subplots(1, len(labs), figsize=(5.2 * len(labs), 3.8), squeeze=False)
        for i, lab in enumerate(labs):
            ax = axs[0, i]
            t_ = G3T_[(G3T_.scores == lab) & (G3T_.kind == "morning")]
            for k, bh in enumerate((1, 3)):
                u = t_[t_.B_h == bh]
                if not len(u):
                    continue
                xx = u.tertile.to_numpy() + (k - 0.5) * 0.25
                ax.errorbar(xx, u.slope.to_numpy(), yerr=[(u.slope - u.ci_lo).to_numpy(), (u.ci_hi - u.slope).to_numpy()], fmt="o", color=[COLORS["dark"], COLORS["light"]][k],
                            label=f"B = {bh} h", capsize=2)
            if len(t_):
                lbl = t_[t_.B_h == 1].sort_values("tertile")
                ax.set_xticks([1, 2, 3], [f"T{int(r.tertile)}\n{r.gap_min_range} min" for r in lbl.itertuples()])
            ax.axhline(0, color=COLORS["ink"], lw=0.6)
            ax.set_ylabel("payback slope (day-demeaned)")
            ax.set_title(f"G3 {lab}: morning payback slope by gap-length tertile", fontsize=9, color=COLORS["ink"])
            ax.legend(fontsize=7, frameon=False)
            ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        figs["g3"] = "ephys_spikes_sleep_explore_G_g3_tertiles_2026c.png"
        save_fig(fig, fd / figs["g3"])
        plt.close(fig)
    if len(G4H_):
        fig, axs = plt.subplots(1, len(labs), figsize=(5.2 * len(labs), 3.8), squeeze=False)
        for i, lab in enumerate(labs):
            ax = axs[0, i]
            h_ = G4H_[G4H_.scores == lab]
            labels = []
            for k, (m, _) in enumerate(G4_MODS):
                for j, bh in enumerate((1, 3)):
                    for q, half in enumerate(("low", "high")):
                        u = h_[(h_.moderator == m) & (h_.B_h == bh) & (h_.half == half)]
                        if not len(u):
                            continue
                        x0 = k * 5 + j * 2.2 + q * 0.9
                        ax.errorbar([x0], u.slope.to_numpy(), yerr=[(u.slope - u.ci_lo).to_numpy(), (u.ci_hi - u.slope).to_numpy()], fmt="o",
                                    color=[COLORS["dark"], COLORS["light"]][q], capsize=2)
                labels.append((k * 5 + 1.5, m.replace("_", " ")))
            ax.set_xticks([x for x, _ in labels], [t for _, t in labels], fontsize=7)
            ax.axhline(0, color=COLORS["ink"], lw=0.6)
            ax.set_ylabel("payback slope (day-demeaned)")
            ax.set_title(f"G4 {lab}: slope in the low (blue) / high (orange) half\nof each moderator; per moderator 1 h then 3 h",
                         fontsize=9, color=COLORS["ink"])
            ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        figs["g4"] = "ephys_spikes_sleep_explore_G_g4_halves_2026c.png"
        save_fig(fig, fd / figs["g4"])
        plt.close(fig)

    # ================================================================ report
    t_total = time.time() - t_all
    write_report(rd, out, gc, labs, prim, parts, t_total, outs, VT, figs, {"G1": g1v, "G2": g2v, "G3": g3v, "G4": g4v}, reading,
                 steps_info, gaps_path)
    write_json(rd / "run_manifest_sleep_explore_G_2026c.json",
               {"run_dir": str(out), "git_commit": gc, "plan": PLAN, "parts": parts, "scorings": labs,
                "inputs": {"states_FINAL": str(STATES), "states_pass2med": str(PASS2MED), "review": str(REVIEW), "gaps": str(gaps_path),
                           "heldout_steps": {lab: str(HELDOUT / f"heldout_steps_{'final' if lab == 'FINAL' else 'pass2med'}.csv.gz") for lab in labs}},
                "verdicts": {"G1": g1v, "G2": g2v, "G3": g3v, "G4": g4v}, "reading": reading, "runtime_s": round(t_total, 1),
                "runtime_per_part": RT, "n_sim": N_SIM, "n_boot": N_BOOT, "seed": 20261009})
    print(f"written ({t_total / 60:.1f} min): G1 {g1v}; G2 {g2v}; G3 {g3v}; G4 {g4v}; reading: {reading}")


def _sel(df: pd.DataFrame, **kw) -> pd.DataFrame:
    m = np.ones(len(df), bool)
    for k, v in kw.items():
        m &= (df[k] == v).to_numpy()
    return df[m]


def _num(df: pd.DataFrame, col: str, **kw) -> float:
    d = _sel(df, **kw) if len(df) else df
    return float(d[col].iloc[0]) if len(d) and col in d and pd.notna(d[col].iloc[0]) else float("nan")


def g1_reading(outs: dict, prim: str) -> list[str]:
    """Computed reading of G1 (numbers only)."""
    g, P0 = outs["g1_mds"], outs["g1_power"]
    s1 = g[(g.scores == prim) & g.model.astype(str).str.startswith("primary (D1): ")]
    if not len(s1):
        return []
    s1 = s1.iloc[0]
    sd0 = P0[(P0.scores == prim) & P0.model.astype(str).str.startswith("primary") & (P0.planted == 0)].sd_slope
    sd0 = float(sd0.iloc[0]) if len(sd0) else float("nan")
    return [f"**Reading.** The plan's formula (residual SD {s1.sigma_resid:.2f} min, SD of the residualised debt {s1.sd_debt_resid:.2f} "
            f"min, n {int(s1.n_windows)}) gives SE {s1.se_iid:.3f} and an MDS of {s1.mds_analytic_iid_z:.2f}. D1's own test used the "
            f"cluster-robust SE, {s1.se_cl:.3f} ({100 * (1 - s1.se_cl / s1.se_iid):.0f} % smaller; {int(s1.clusters)} block clusters), "
            f"which gives an MDS of {s1.mds_analytic_cl:.2f}. The wild cluster bootstrap keeps each block's residuals together, so it "
            f"reproduces the cluster-robust variance by construction (simulated slope SD at a planted 0: {sd0:.3f}); its MDS "
            f"({s1.mds_sim:.2f}) confirms the cluster-robust number, not the iid one. The two variance estimates disagree about 0.34: "
            f"under D1's cluster-robust test the dawn windows would have detected a slope of 0.34 with power "
            f"{s1.power_at_round_slope_sim:.2f}; under the plan's iid formula with power {s1.power_at_round_slope_analytic_iid:.2f}. "
            f"Day-demeaning makes the residuals of one block partly cancel, which can make the clustered SE smaller than the iid "
            f"one, and with {int(s1.clusters)} clusters the clustered SE is itself imprecise. Which one is right cannot be settled "
            f"from {int(s1.n_windows)} windows, so by the rule fixed before the results (both ≤ 0.34) D1 is not informative and G1 "
            f"stays open. With D1's full rule (also slope > 0.2 and every rat positive) the power at 0.34 is "
            f"{s1.power_at_round_slope_sim_d1_rule:.2f}.", "",
            "**In-place deviations.** The plan names one MDS; two are reported (the plan's iid formula and D1's cluster-robust "
            "test), and G1 counts as informative only if both are ≤ 0.34 (fixed before the results). The simulation was meant as a "
            "check of the analytic number; as built it checks the cluster-robust version only (above).", ""]


def g2_reading(outs: dict, labs: list[str]) -> list[str]:
    """Computed reading of G2 (numbers only; no mechanism words)."""
    F, O, C = outs["g2_funnel"], outs["g2_oe"], outs["g2_cox"]
    L = ["**Reading.**", ""]
    for lab in labs:
        f = _sel(F, scores=lab) if len(F) else F
        if not len(f):
            continue
        f = f.iloc[0]
        line = (f"- {lab}: {int(f.naturals)} natural wakes ≥ 30 min (inside a record, no handling in the 3 h before); "
                f"{int(f.naturals_kind_other)} start at hours with no round to match (21:30–05:00, 11:00–15:30); "
                f"{int(f.naturals_matched)} are in matched cells")
        if "naturals_matched_with_heldout_steps" in f and pd.notna(f.naturals_matched_with_heldout_steps):
            line += (f", {int(f.naturals_matched_with_heldout_steps)} of them with held-out steps in the 0–1 h window (rounds: "
                     f"{int(f.rounds_matched_with_heldout_steps)} of {int(f.rounds_matched)}; natural wakes of any clock time: "
                     f"{int(f.naturals_any_clock_with_heldout_steps)})")
        L.append(line + ".")
    if len(O):
        for lab in labs:
            r = _sel(O, scores=lab, spec="primary", expected="E", window="0-1 h")
            q = _sel(O, scores=lab, spec=G2_POSTHOC, expected="E", window="0-1 h")
            q3 = _sel(O, scores=lab, spec=G2_POSTHOC, expected="E", window="1-3 h")
            if len(r):
                r = r.iloc[0]
                txt = (f"- {lab}, 0–1 h: post-round O/E {r.oe_round:.2f} vs matched natural {r.oe_natural_std:.2f} ({r.O_natural:.0f} "
                       f"natural REM entries); difference {r['diff']:+.2f} [{r.diff_lo:+.2f}, {r.diff_hi:+.2f}].")
                if len(q):
                    q = q.iloc[0]
                    txt += (f" Post hoc, matched on the wake-length bin only (any clock time; the expected counts already contain "
                            f"the clock terms): natural {q.oe_natural_std:.2f} ({int(q.events_natural)} events, {q.O_natural:.0f} REM "
                            f"entries), difference {q['diff']:+.2f} [{q.diff_lo:+.2f}, {q.diff_hi:+.2f}], {int(q.animals_negative)}/"
                            f"{int(q.animals)} animals negative")
                    if len(q3):
                        q3 = q3.iloc[0]
                        txt += (f"; 1–3 h {q3['diff']:+.2f} [{q3.diff_lo:+.2f}, {q3.diff_hi:+.2f}], {int(q3.animals_negative)}/"
                                f"{int(q3.animals)} negative")
                    txt += "."
                L.append(txt)
    if len(C):
        for lab in labs:
            c = _sel(C, scores=lab, spec="primary")
            cq = _sel(C, scores=lab, spec=G2_POSTHOC)
            if len(c):
                c = c.iloc[0]
                txt = (f"- {lab}, Cox: HR {c.HR:.2f} [{np.exp(c.ci_lo):.2f}, {np.exp(c.ci_hi):.2f}] for rounds vs {int(c.naturals)} matched "
                       f"natural wakes (HR > 1 = the first REM came sooner in NREM time after rounds; H18 predicted HR < 1)")
                if len(cq):
                    cq = cq.iloc[0]
                    txt += (f"; post hoc, bin only + dark at the wake end (most of these natural wakes end at night): HR {cq.HR:.2f} "
                            f"[{np.exp(cq.ci_lo):.2f}, {np.exp(cq.ci_hi):.2f}] vs {int(cq.naturals)} natural wakes")
                L.append(txt + ".")
    hr = {}
    for lab in labs:
        for spec in ("primary", G2_POSTHOC):
            c = _sel(C, scores=lab, spec=spec) if len(C) else C
            if len(c):
                c = c.iloc[0]
                hr[(lab, spec)] = f"{c.HR:.2f} [{np.exp(c.ci_lo):.2f}, {np.exp(c.ci_hi):.2f}]"
    L += ["- REM entry relative to the held-out model (O/E) is not lower after rounds than after natural long wakes, neither in "
          "the matched cells nor (post hoc) over all natural wakes of the same length bin. The first-REM latency depends on how "
          "the light phase is handled: in the matched cells (few natural wakes, few of them reaching REM before censoring) the "
          "first REM came sooner after rounds (HR " + "; ".join(f"{lab} {hr.get((lab, 'primary'), 'n/a')}" for lab in labs) + "); over "
          "all natural wakes of the same bin with a dark step at the wake end (post hoc) it came later (HR " +
          "; ".join(f"{lab} {hr.get((lab, G2_POSTHOC), 'n/a')}" for lab in labs) + "). The two latency comparisons point in "
          "opposite directions and the second is post hoc, so the latency does not settle H18 either way.",
          "- The plan's matched natural side is small (most natural long wakes are at night, when no round happens), the 1–3 h "
          "natural window holds about one event, and the ≥ 5/6-rats condition could not be evaluated: G2 is power-limited. The "
          "post-hoc rows are not part of the rule.", "",
          "**In-place deviations.** (i) The rounds' wake length counts the unrecorded gap as wake. (ii) Morning / evening is Phase "
          "0's clock rule applied to the wake start (for rounds = the Phase-0 kind). (iii) The plan names two windows and no "
          "primary; G2 passes if one window meets the rule on both scorings (fixed before the results). (iv) The bin-only "
          "matching was added after seeing the small matched natural side; it is reported, not judged.", ""]
    return L


def reading_summary(outs: dict, prim: str, verd: dict) -> list[str]:
    """Which parts failed for want of data and which failed with adequate data (numbers only)."""
    L = ["What the four parts leave:", ""]
    if "g1_mds" in outs and len(outs["g1_mds"]):
        g = outs["g1_mds"]
        s1 = g[(g.scores == prim) & g.model.astype(str).str.startswith("primary (D1): ")]
        if len(s1):
            s1 = s1.iloc[0]
            L.append(f"- Dawn timing (G1): open — D1's null is informative only under its cluster-robust SE (MDS {s1.mds_analytic_cl:.2f}), "
                     f"not under the plan's iid formula (MDS {s1.mds_analytic_iid_z:.2f}).")
    if len(outs.get("g2_oe", [])):
        L.append(f"- Handling-specific REM-entry shortfall (G2): not seen in the REM-entry O/E; "
                 f"{verd['G2'].split(' — ')[1] if ' — ' in verd['G2'] else 'see G2'}; the first-REM latency comparisons disagree in "
                 f"sign between the matched and the post-hoc set.")
    M = outs.get("g3_models", pd.DataFrame())
    if len(M):
        fl = [f"{100 * float(_sel(M, scores=prim, kind='morning', B_h=bh, day_demeaned=True).fall.iloc[0]):.0f} %" for bh in (1, 3)
              if len(_sel(M, scores=prim, kind="morning", B_h=bh, day_demeaned=True))]
        L.append(f"- The round's own sleep loss (G3): not supported with the data in hand — adding the gap debt changes the pre-round "
                 f"slope by {' / '.join(fl)} (1 h / 3 h), and the slope is present in every gap-length tertile.")
    L.append(f"- G4: {verd['G4']}; not consistent across horizons, moderators and scorings.")
    return L + [""]


def g3_reading(outs: dict, prim: str) -> list[str]:
    M, T = outs["g3_models"], outs["g3_tertiles"]
    if not len(M):
        return []
    L = ["**Reading.**", ""]
    for bh in (1, 3):
        r = _sel(M, scores=prim, kind="morning", B_h=bh, day_demeaned=True)
        if len(r):
            r = r.iloc[0]
            L.append(f"- {prim}, {bh} h: next to the gap debt the pre-round debt slope stays {r.b0_debt:+.2f} → {r.b1_debt:+.2f} (fall "
                     f"{100 * r.fall:.0f} %, needs ≥ 30 %); the gap-debt slope is {r.b1_gap:+.3f} [{r.b1_gap_lo:+.3f}, {r.b1_gap_hi:+.3f}] "
                     f"(alone: {r.b2_gap_only:+.3f} [{r.b2_gap_only_lo:+.3f}, {r.b2_gap_only_hi:+.3f}]; day-demeaned correlation of the "
                     f"two debts {r.corr_debt_gapdebt:+.2f}).")
    t = _sel(T, scores=prim, kind="morning") if len(T) else T
    if len(t):
        for bh in (1, 3):
            u = t[t.B_h == bh].sort_values("tertile")
            if len(u):
                L.append(f"- {prim}, {bh} h, by gap-length tertile: " + "; ".join(
                    f"T{int(x.tertile)} ({x.gap_min_range} min) {x.slope:+.2f} [{x.ci_lo:+.2f}, {x.ci_hi:+.2f}]" for x in u.itertuples()) + ".")
    L += ["- The payback slope barely changes when the REM expected during the gap is added, and it is present in every "
          "gap-length tertile; the gap's own REM loss, computed this way, does not account for it.", "",
          "**In-place deviations.** The gap debt uses the baseline fitted without window A's block and counts the whole gap as "
          "REM-free; the verdict uses pass2med and needs both horizons (one = PARTLY), fixed before the results.", ""]
    return L


def g4_reading(outs: dict, prim: str, labs: list[str]) -> list[str]:
    M = outs["g4_models"]
    if not len(M):
        return []
    L = ["**Reading.**", ""]
    for m in ("gain_heldout", "gain_base", "onset_rel_sunrise_h"):
        parts_ = []
        for lab in labs:
            for bh in (1, 3):
                r = _sel(M, scores=lab, moderator=m, B_h=bh, day_demeaned=True)
                if len(r) and np.isfinite(r.iloc[0].get("interaction", np.nan)):
                    r = r.iloc[0]
                    parts_.append(f"{lab} {bh} h {r.interaction:+.3f} [{r.interaction_lo:+.3f}, {r.interaction_hi:+.3f}] (n {int(r.n_windows)}, "
                                  f"{int(r.clusters)} clusters)")
        if parts_:
            L.append(f"- {m}: " + "; ".join(parts_) + ".")
    L += ["- The interaction is not consistent: for the held-out rate its sign differs between the 1-h and 3-h horizons, the "
          "baseline rate (all 49 windows) does not repeat the 1-h result, and for the onset time the two scorings disagree in sign "
          "at 3 h. With 9–12 block clusters the clustered CIs are approximate. G4 is not passed (one horizon of two).", "",
          "**In-place deviations.** The plan's \"predicted REM-entry gain at that time\" is read as the held-out clock-only "
          "model's mean per-step REM probability over the NREM steps of window B (× 360 per NREM hour); windows in the first 6 "
          "blocks have no held-out steps (n 37 of 49), so the baseline rate is the all-window sensitivity. The moderator is "
          "globally centred in the product and day-demeaned as a main effect.", ""]
    return L


def write_report(rd, out, gc, labs, prim, parts, t_total, outs, VT, figs, verd, reading, steps_info, gaps_path) -> None:
    R_ = outs["repro"]
    L = ["# Sleep behaviour explore — Amendment 1, part G: where does the REM repayment after morning rounds (#43) come from? (cohort 2026c)", "",
         f"Plan: [{PLAN}](../../../../{PLAN}), section 9 \"G\" (pass rules and the reading rule written before these results, "
         f"unchanged; definitions as section 3). Driver `ephys/sleep_explore_g.py run` (commit {gc}); bulk `{out}`; scorings "
         f"{', '.join(labs)}; parts {', '.join(parts)}; runtime {t_total / 60:.1f} min. Builds on "
         "[D1](ephys_spikes_sleep_explore_D1_2026c.md) (`sleep_explore_d.py`) and [A4](ephys_spikes_sleep_explore_A_2026c.md); "
         "the held-out per-step predictions come from the main session (S / S2b).", "",
         "**Scope.** Claim #43 (Candidate): REM missed before a morning battery round is repaid afterwards (pass2med, "
         "day-demeaned slope +0.34 at 1 h, +0.96 at 3 h per min of debt); the count rules do not produce it; natural dawn wakes "
         "showed none (D1). Part G asks which of three sources the data favour: the handling itself (G2), the REM lost during "
         "the unrecorded round gap (G3), or dawn timing (G1); G4 asks whether the slope is larger where the held-out clock-only "
         "model predicts a higher REM-entry rate. "
         "Claim statuses change in the claim audit, not here. Inputs: the scored 1-s states, NOAA light, the Phase-0 gap "
         "table, the held-out per-step predictions. No LFP features. Everything from 2026-09-11 19:40 is cut.", "",
         "## Verdict", "",
         f"- **G1 (dawn timing, D1's power):** {verd['G1']}.",
         f"- **G2 (H18, handling-specific post-round sleep):** {verd['G2']}.",
         f"- **G3 (the round's own sleep loss):** {verd['G3']}.",
         f"- **G4 (the plan's \"gate release\" test):** {verd['G4']}.",
         f"- **Reading rule:** {reading}.", ""]
    key = []
    if len(outs["g1_mds"]):
        s = _sel(outs["g1_mds"], scores=prim)
        s = s[s.model.astype(str).str.startswith("primary (D1): ")]
        if len(s):
            s = s.iloc[0]
            key.append(f"- G1 ({prim}): D1's primary 1-h slope {s.d1_slope:+.3f} [{s.ci_lo:+.3f}, {s.ci_hi:+.3f}] (n {int(s.n_windows)}); "
                       f"MDS analytic {s.mds_analytic_iid_z:.3f} (iid SE {s.se_iid:.3f}; with the cluster SE {s.mds_analytic_cl:.3f}), "
                       f"simulated {s.mds_sim:.3f}; power at the round slope 0.34: analytic {s.power_at_round_slope_analytic_iid:.2f}, "
                       f"simulated {s.power_at_round_slope_sim:.2f} (D1's full rule {s.power_at_round_slope_sim_d1_rule:.2f}).")
    if len(outs["g2_oe"]):
        for lab in labs:
            for wl, _, _ in G2_WINDOWS:
                r = _sel(outs["g2_oe"], scores=lab, spec="primary", expected="E", window=wl)
                rb = _sel(outs["g2_oe"], scores=lab, spec="primary", expected="E_pb", window=wl)
                if len(r):
                    r = r.iloc[0]
                    key.append(f"- G2 {lab}, {wl}: REM-entry O/E post-round {r.oe_round:.2f} [{r.oe_round_lo:.2f}, {r.oe_round_hi:.2f}] vs "
                               f"natural (matched) {r.oe_natural_std:.2f} [{r.oe_natural_lo:.2f}, {r.oe_natural_hi:.2f}]; difference "
                               f"{r['diff']:+.2f} [{r.diff_lo:+.2f}, {r.diff_hi:+.2f}], {int(r.animals_negative)}/{int(r.animals)} animals "
                               f"negative → {r.rule}" + (f"; perturbation-blind: {rb.iloc[0].oe_round:.2f} vs {rb.iloc[0].oe_natural_std:.2f}, "
                                                          f"difference {rb.iloc[0]['diff']:+.2f} [{rb.iloc[0].diff_lo:+.2f}, {rb.iloc[0].diff_hi:+.2f}]"
                                                          if len(rb) else "") + ".")
    if len(outs["g2_cox"]):
        for lab in labs:
            r = _sel(outs["g2_cox"], scores=lab, spec="primary")
            if len(r):
                r = r.iloc[0]
                key.append(f"- G2 {lab}, Cox first-REM hazard (round vs natural, matched cells): HR {r.HR:.2f} "
                           f"[{np.exp(r.ci_lo):.2f}, {np.exp(r.ci_hi):.2f}], p {r.p:.4f} ({int(r.rounds)} rounds, {int(r.naturals)} natural wakes).")
    if len(outs["g3_models"]):
        for bh in (1, 3):
            r = _sel(outs["g3_models"], scores=prim, kind="morning", B_h=bh, day_demeaned=True)
            if len(r):
                r = r.iloc[0]
                key.append(f"- G3 {prim}, morning, {bh} h: pre-round debt slope {r.b0_debt:+.3f} → {r.b1_debt:+.3f} with the gap debt "
                           f"(fall {100 * r.fall:.0f} %); gap-debt slope {r.b1_gap:+.3f} [{r.b1_gap_lo:+.3f}, {r.b1_gap_hi:+.3f}].")
    if len(outs["g4_models"]):
        for bh in (1, 3):
            for m in ("gain_heldout", "onset_rel_sunrise_h"):
                r = _sel(outs["g4_models"], scores=prim, moderator=m, B_h=bh, day_demeaned=True)
                if len(r) and np.isfinite(r.iloc[0].get("interaction", np.nan)):
                    r = r.iloc[0]
                    key.append(f"- G4 {prim}, {bh} h, {m}: interaction {r.interaction:+.3f} [{r.interaction_lo:+.3f}, {r.interaction_hi:+.3f}] "
                               f"per unit ({r.interaction_per_sd:+.3f} per SD), n {int(r.n_windows)}.")
    L += key + [""] + DEFINITIONS

    # ---------------- reproduction
    L += ["## Reproduction", "", "The round windows reproduce #43 (A4, pass2med: +0.335 at 1 h, +0.961 at 3 h):", ""] + tbl(R_) + [""]
    if len(outs["g2_steps_check"]):
        L += ["Held-out step table (each step must sit on an NREM second of its record):", ""] + tbl(outs["g2_steps_check"], 4) + [""]
        for lab in labs:
            fl = steps_info.get(f"{lab}_post_round_flag")
            if fl:
                L.append(f"- {lab}: the file's `post_round` flag on the steps of the G2 windows (0–3 h): post-round events "
                         f"{fl.get('round', (0, 0))[0]:.0f} of {fl.get('round', (0, 0))[1]:.0f} steps flagged; natural-wake events "
                         f"{fl.get('natural', (0, 0))[0]:.0f} of {fl.get('natural', (0, 0))[1]:.0f}.")
        L.append("")

    # ---------------- G1
    if "g1" in parts:
        g = outs["g1_mds"]
        L += ["## G1 — dawn timing without handling: the power of D1", "",
              "**Plan (quoted):** \"D1 found no payback after natural dawn wakes (−0.02, 41 windows). Add its power: the minimal "
              "detectable slope (80 % power, α 0.05) from the windows' debt variance and residual SD. If that slope is > 0.34 "
              "(the observed round slope), D1 is uninformative and G1 stays open.\"", "",
              f"**Verdict ({prim}, primary model, B = 1 h): {verd['G1']}.**", ""]
        cols = ["scores", "model", "B_h", "n_windows", "clusters", "rats_qualifying", "d1_slope", "ci_lo", "ci_hi", "p", "sd_debt", "sd_debt_resid",
                "sigma_resid", "se_iid", "se_cl", "mds_analytic_iid_z", "mds_analytic_iid_t", "mds_analytic_cl", "mds_sim", "mds_sim_d1_rule",
                "power_at_round_slope_analytic_iid", "power_at_round_slope_sim", "power_at_round_slope_sim_d1_rule", "type1_sim", "verdict"]
        L += tbl(g[[c for c in cols if c in g]]) + [""]
        L += ["`type1_sim` = twice the simulated share of significant positive slopes at a planted 0 (the two-sided size of the "
              "cluster-robust test in these windows; nominal 0.05). The 3-h horizon has too few windows for a model (D1: "
              "INCONCLUSIVE), so it has no MDS.", ""]
        L += g1_reading(outs, prim)
        if "g1" in figs:
            L += [f"![G1 power](../figures/{figs['g1']})", ""]
        P = outs["g1_power"]
        if len(P):
            sh = P[P.planted.isin([0.0, 0.1, 0.2, 0.3, 0.34, 0.4, 0.5, 0.6, 0.8, 1.0])]
            L += ["Power by planted slope (selected grid points):", ""] + tbl(sh[["scores", "model", "planted", "power_sig", "power_d1_rule",
                                                                             "power_analytic_iid", "power_analytic_cl", "mean_slope", "sd_slope"]]) + [""]
    # ---------------- G2
    if "g2" in parts:
        L += ["## G2 — handling-specific post-round sleep (H18)", "",
              "**Plan (quoted):** \"Compared: post-round vs natural wakes of ≥ 30 min, matched on wake length bin and morning / "
              "evening. Measures: first-REM latency in NREM time (Cox, animal strata); REM-entry O/E (as S2) in the 0–1 h and "
              "1–3 h after. Pass for 'handling delays REM beyond the wake it causes': post-round REM O/E below the natural-wake "
              "O/E (bootstrap CI of the difference < 0), ≥ 5/6 rats, both scorings.\"", "",
              f"**Verdict: {verd['G2']}.**", "", "Events (funnel):", ""] + tbl(outs["g2_funnel"]) + [""]
        L += g2_reading(outs, labs)
        if len(outs["g2_oe"]):
            o = outs["g2_oe"]
            cols = ["scores", "spec", "window", "expected", "events_round", "events_natural", "O_round", "E_round", "oe_round", "oe_round_lo",
                    "oe_round_hi", "O_natural", "E_natural", "oe_natural_pooled", "oe_natural_std", "oe_natural_lo", "oe_natural_hi", "diff",
                    "diff_lo", "diff_hi", "animals_negative", "animals", "rule"]
            L += ["REM-entry O/E (expected `E` = B-full held out, the rule; `E_pb` = perturbation-blind; `E_gate` = clock-only; "
                  "the sensitivities use `E`):", ""] + tbl(o[cols], 3) + [""]
            L += ["Per cell (primary, `E`):", ""] + tbl(_sel(outs["g2_oe_cells"], expected="E")) + [""]
            pa = outs["g2_per_animal"]
            if len(pa) and "expected" in pa:
                pa_ = pa[(pa.what == "oe") & (pa.expected == "E")][["scores", "window", "animal", "oe_round", "oe_natural_std", "diff", "O_round",
                                                                     "E_round", "O_natural", "E_natural"]]
                L += ["Per animal (primary, `E`):", ""] + tbl(pa_) + [""]
        else:
            L += ["(The held-out per-step predictions were not available; the O/E part did not run.)", ""]
        L += ["First-REM latency, Cox (round vs natural, matched cells; HR < 1 = a later first REM after rounds):", ""]
        c = outs["g2_cox"].copy()
        if len(c):
            c["HR_lo"], c["HR_hi"] = np.exp(c.ci_lo), np.exp(c.ci_hi)
            L += tbl(c[["scores", "spec", "n", "rounds", "naturals", "events", "coef", "se", "HR", "HR_lo", "HR_hi", "p", "cells", "terms_kept"]]) + [""]
        L += ["KM medians (NREM min to the first REM; primary cells):", ""] + tbl(outs["g2_km"]) + [""]
        pa = outs["g2_per_animal"]
        if len(pa):
            pc = pa[pa.what == "cox"][["scores", "animal", "rounds", "naturals", "events"] + (["cox_round_coef"] if "cox_round_coef" in pa else [])]
            L += ["Per animal, Cox (no strata; animals with ≥ 3 events of each group):", ""] + tbl(pc) + [""]
        if "g2" in figs:
            L += [f"![G2](../figures/{figs['g2']})", ""]
    # ---------------- G3
    if "g3" in parts:
        L += ["## G3 — the round's own sleep loss", "",
              "**Plan (quoted):** \"Gap debt: the REM expected during the unrecorded gap (the phase × day baseline rate × gap "
              "duration) is added as a second debt term next to the 3-h pre-round debt. Pass for 'the payback is the round's "
              "sleep loss': the gap-debt slope > 0 (CI) AND the pre-round debt slope falls by ≥ 30 %. Also reported: the payback "
              "slope by gap-length tertile.\"", "", f"**Verdict ({prim}, morning rounds, day-demeaned): {verd['G3']}.**", "",
              "Gaps and debts (1-h window set):", ""] + tbl(outs["g3_gaps"]) + [""]
        m = outs["g3_models"]
        cols = ["scores", "kind", "B_h", "day_demeaned", "n_windows", "clusters", "corr_debt_gapdebt", "b0_debt", "b0_debt_lo", "b0_debt_hi", "b1_debt",
                "b1_debt_lo", "b1_debt_hi", "b1_gap", "b1_gap_lo", "b1_gap_hi", "b1_gap_p", "fall", "b2_gap_only", "b2_gap_only_lo", "b2_gap_only_hi",
                "rats_gap_positive", "rats_gap"]
        L += ["Models (`b0` = M0 #43; `b1` = M1 with the gap debt; `b2` = gap debt alone):", ""] + tbl(m[[c for c in cols if c in m]]) + [""]
        L += ["Payback slope by gap-length tertile (day-demeaned, one model per horizon):", ""] + tbl(outs["g3_tertiles"]) + [""]
        L += g3_reading(outs, prim)
        if "g3" in figs:
            L += [f"![G3](../figures/{figs['g3']})", ""]
    # ---------------- G4
    if "g4" in parts:
        L += ["## G4 — the plan's \"gate release\" test", "",
              "**Plan (quoted):** \"For morning rounds only: the payback slope vs the clock time of the first post-round sleep "
              "onset relative to sunrise, and vs the model's predicted REM-entry gain at that time. Pass for 'a deficit released "
              "where the gate opens': a larger slope where the predicted gain is higher (interaction CI > 0). Reported with "
              "caution: n ≈ 49 windows.\"", "", f"**Verdict ({prim}, held-out gate gain, day-demeaned): {verd['G4']}.**", "",
              "Moderators (morning windows):", ""] + tbl(outs["g4_data"]) + [""]
        m = outs["g4_models"]
        cols = ["scores", "moderator", "B_h", "day_demeaned", "n_windows", "clusters", "mod_mean", "mod_sd", "slope_at_mean", "slope_at_mean_lo",
                "slope_at_mean_hi", "interaction", "interaction_lo", "interaction_hi", "interaction_p", "interaction_per_sd", "mod_main", "mod_main_p"]
        L += ["Interaction models:", ""] + tbl(m[[c for c in cols if c in m]]) + [""]
        if len(outs["g4_halves"]):
            L += ["Slopes in the halves of each moderator (day-demeaned):", ""] + tbl(outs["g4_halves"]) + [""]
        L += g4_reading(outs, prim, labs)
        if "g4" in figs:
            L += [f"![G4](../figures/{figs['g4']})", ""]
    # ---------------- reading + verdict rows
    L += ["## Reading rule", "", f"G1 {verd['G1']}; G2 {verd['G2']}; G3 {verd['G3']}; G4 {verd['G4']}.", "", f"**Outcome: {reading}.**", "",
          "Applied as written: the 'G3 pass' row needs G3 to pass; the 'G2 pass, G3 fail' row needs G2 to pass; the 'G1 "
          "informative and positive' row needs D1 to be informative and its slope positive; when none holds, the last row "
          "applies. PARTLY (one horizon of two) and an uninformative G1 count as not passed. G4 has no row; its own pass "
          "sentence is quoted only if G4 passes.", ""] + reading_summary(outs, prim, verd)
    if len(VT):
        L += ["All rule rows (`role` = verdict decides; `reported` = shown only):", ""] + tbl(VT) + [""]
    L += ["## Runtime", ""] + tbl(outs["runtime"]) + [""]
    L += DEVIATIONS
    (rd / "ephys_spikes_sleep_explore_G_2026c.md").write_text("\n".join(L) + "\n", encoding="utf-8")


DEVIATIONS = [
    "## Deviations from the plan and the task, and notes", "",
    "- **G1.** \"That slope\" is computed two ways (analytic from the residualised debt spread and the residual SD, as the "
    "plan says, and by planting slopes into the real windows); G1 counts as informative only when both are ≤ 0.34. The "
    "power is for D1's primary model at B = 1 h (the row D1's −0.02 comes from); the 3-h horizon has 9 windows and no "
    "model. The simulation keeps the windows, the design and the residuals of the real data (wild cluster bootstrap, "
    "Rademacher signs per block) and uses D1's cluster-robust normal test; it therefore reproduces the cluster-robust "
    "variance by construction and checks the cluster-robust MDS, not the iid one.",
    "- **G2, the round's wake length.** The unrecorded gap is counted as wake (the animal was handled) plus the recorded "
    "wake before the first NREM; the wake that ended the previous record is added in a sensitivity. The gap may hold some "
    "sleep before the animal was caught; nothing in the data shows it.",
    "- **G2, morning / evening.** Phase 0's clock rule (05:00–11:00, 15:30–21:30) is applied to the wake START for both "
    "groups (for rounds this is the Phase-0 kind); the wake END is a sensitivity. Natural wakes starting at other hours "
    "have no round to match and are not used.",
    "- **G2, windows.** As S2: rounds from the record start (= gap end), natural wakes from the wake end; a sensitivity "
    "aligns both at the first NREM second. The windows count every held-out NREM step of the record in the window, also "
    "after a later wake. Only test blocks have held-out predictions (the first 6 blocks never do), so the O/E part uses "
    "fewer events than the Cox part.",
    "- **G2, natural wakes** exclude any wake with a round or a probe move ending < 3 h before its start (D1's rule); S2's "
    "natural wakes may differ in this detail.",
    "- **G2, post hoc.** The first full run showed only 3 matched natural wakes with held-out steps in the 0–1 h window; a "
    "matching on the wake-length bin alone (any clock time) was then added as a reported row (O/E and Cox), not judged. The "
    "verdict text states when the rats condition could not be evaluated (fewer than 5 animals with matched data).",
    "- **G2 rule.** The plan names two windows and no primary; the rule is applied per window and G2 passes if one window "
    "meets it on both scorings (stated before the results). The Cox term (H18's own test in the section 5 table) is "
    "reported, not part of the rule.",
    "- **G3 / G4 horizons and scoring.** The verdict uses pass2med (the scoring #43 is established on); FINAL is reported. "
    "A pass needs both horizons (1 h and 3 h, as A4 required); one horizon = PARTLY, read as not passed.",
    "- **G3, gap debt** uses the baseline fitted without window A's block (the fit that gives A's own expectation) and "
    "treats the whole gap as unrecorded REM-free time.",
    "- **G4, gain.** The plan's \"predicted REM-entry gain at that time\" is read as the held-out clock-only model's mean "
    "per-step REM probability over the NREM steps of window B (× 360 = per NREM hour); it includes that model's "
    "elapsed-in-bout and anchor terms besides the clock. Windows in the first 6 blocks have no held-out steps, so n is "
    "smaller than 49; the baseline's expected REM-onset rate is the all-window sensitivity. Day-demeaning removes most of "
    "the between-day spread of the moderators; the interaction uses the globally centred moderator (definitions).",
    "- No mechanism words beyond the plan's reading sentences.", "",
]


# ================================================================== selftest
def _synth_g2(rng, k_post: float = 0.5, animals=("SF07", "SF08", "SF09", "SF10", "SF11", "SF12"), days: int = 10,
              h_rem: float = 0.012, h_wake: float = 0.012):
    """Records on a 10-s grid: per day a night record 19:00 -> 07:00 and a day record 08:00 -> 18:00 (round gaps 07-08
    morning, 18-19 evening; cause round_logged), each record starting with 5 min of WAKE; natural wakes: night 05:00-05:45
    (morning, 45 min), day 15:40-16:30 (evening, 50 min). NREM steps go to REM with h_rem (x k_post in the first hour of a
    record), to WAKE with h_wake; REM lasts ~ geometric 9 steps, short wakes ~ 3 steps."""
    recs, gaps = [], []
    day0 = pd.Timestamp("2026-09-01")
    for an in animals:
        for d in range(days):
            dd = day0 + pd.Timedelta(days=d)
            for t0, t1, nat in ((dd + pd.Timedelta(hours=8), dd + pd.Timedelta(hours=18), (dd + pd.Timedelta(hours=15, minutes=40), 50)),
                                (dd + pd.Timedelta(hours=19), dd + pd.Timedelta(hours=31), (dd + pd.Timedelta(hours=29), 45))):
                n = int((t1 - t0).total_seconds() // 10)
                s = np.empty(n, np.int8)
                ws = int((nat[0] - t0).total_seconds() // 10)
                we = ws + nat[1] * 6
                cur, i = W, 0
                s[:30] = W
                i = 30
                cur = N
                while i < n:
                    if ws <= i < we:
                        s[i] = W
                        i += 1
                        cur = N
                        continue
                    s[i] = cur
                    u = rng.random()
                    if cur == N:
                        hr = h_rem * (k_post if i < 360 else 1.0)
                        cur = R if u < hr else (W if u < hr + h_wake else N)
                    elif cur == R:
                        cur = (N if rng.random() < 0.8 else W) if u < 1 / 9 else R
                    else:
                        cur = N if u < 1 / 3 else W
                    i += 1
                recs.append({"animal": an, "start": t0, "end": t1, "state": np.repeat(s, 10), "block": _blk(t0)})
        rr = [r for r in recs if r["animal"] == an]
        for p, q in zip(rr[:-1], rr[1:]):
            h = p["end"].hour
            gaps.append({"animal": an, "gap_start": p["end"], "gap_end": q["start"], "gap_min": (q["start"] - p["end"]).total_seconds() / 60,
                         "kind": "morning" if 5 <= h < 11 else ("evening" if 15.5 <= h < 21.5 else "other"), "usable": True, "cause": "round_logged"})
    for i, rc in enumerate(recs):
        rc["record_id"] = i
        rc["sessions"] = [f"s{i}"]
    return recs, pd.DataFrame(gaps)


def _synth_steps(recs: list[dict], h_rem: float) -> pd.DataFrame:
    from sleep_schedule_phase2 import build_steps
    S = build_steps(recs)
    S = S[["animal", "record_id", "block", "t", "y"]].copy()
    S["p_rem"] = S["pb_rem"] = S["p_rem_gate"] = h_rem
    S["post_round"] = False
    return S


def _g2_world(recs, gaps, h_rem: float, n_boot: int = 500):
    E = g2_events(recs, gaps)
    cell = cells_of(E)
    mc = matched_cells(E, cell)
    OE = g2_oe_events(E, StepIndex(_synth_steps(recs, h_rem)))
    res, _, _ = g2_matched(OE, E, cell, "E", np.random.default_rng(1), n_boot=n_boot)
    cx, _, _ = g2_cox(E, cell)
    return E, {r["window"]: r for r in res}, cx, mc


def _g2_null(seed: int, h_rem: float):
    recs, gaps = _synth_g2(np.random.default_rng(seed), k_post=1.0, h_rem=h_rem, days=20)
    _, rw, cx, _ = _g2_world(recs, gaps, h_rem, n_boot=300)
    return rw["0-1 h"]["diff"], g2_rule(rw["0-1 h"])[0], cx["coef"]


def selftest() -> None:
    t_start = time.time()
    ok_all = True

    def check(name: str, cond: bool) -> None:
        nonlocal ok_all
        print(("PASS " if cond else "FAIL ") + name, flush=True)
        ok_all &= bool(cond)
    rng = np.random.default_rng(5)
    norm = _norm()

    # 1. vectorised cluster OLS = sleep_explore.ols (statsmodels)
    n = 60
    d = pd.DataFrame({"x": rng.normal(0, 1.5, n), "z": rng.normal(0, 1, n), "animal": rng.choice(["SF07", "SF08", "SF09", "SF10"], n),
                      "A_block": rng.choice([f"b{i}" for i in range(12)], n)})
    d["pay_rem"] = 0.4 * d.x + 0.2 * d.z + rng.normal(0, 1, n)
    f = ols(d.pay_rem, d[["x", "z"]], groups=d.A_block, fe=d.animal)
    X, names = design_ols(d, ["x", "z"])
    co = ClusterOLS(X, d.A_block)
    b, se = co.fit(d.pay_rem.to_numpy(float), names.index("x"))
    t = term(f, "x")
    p_np = 2 * norm.sf(abs(b[0] / se[0]))
    check(f"ClusterOLS = sleep_explore.ols: coef {b[0]:.6f} vs {t['coef']:.6f}, se {se[0]:.6f} vs {t['se']:.6f}, p {p_np:.6f} vs {t['p']:.6f}",
          abs(b[0] - t["coef"]) < 1e-9 and abs(se[0] - t["se"]) < 1e-9 and abs(p_np - t["p"]) < 1e-8)

    # 2. G1: analytic MDS vs simulated power on iid windows
    n, sd_x, sig = 240, 1.5, 2.0
    d = pd.DataFrame({"debt_rem": rng.normal(0, sd_x, n), "animal": np.repeat(["SF07", "SF08", "SF09", "SF10", "SF11", "SF12"], n // 6),
                      "A_block": np.tile([f"b{i}" for i in range(60)], n // 60)})
    d["pay_rem"] = rng.normal(0, sig, n)
    s, P = mds_analysis(d, ["debt_rem"], np.random.default_rng(3), grid=np.round(np.arange(0, 0.8001, 0.02), 4), n_sim=2000)
    truth = 2.8016 * sig / (sd_x * np.sqrt(n))
    pw_at = float(np.interp(s["mds_analytic_iid_z"], P.planted, P.power_sig))
    check(f"G1: analytic MDS {s['mds_analytic_iid_z']:.3f} within 15 % of the generative {truth:.3f}",
          abs(s["mds_analytic_iid_z"] / truth - 1) < 0.15)
    check(f"G1: simulated MDS {s['mds_sim']:.3f} within 15 % of the analytic {s['mds_analytic_iid_z']:.3f}; simulated power at the analytic "
          f"MDS {pw_at:.2f} in [0.70, 0.90]; size at 0 {s['type1_sim']:.3f} < 0.09",
          abs(s["mds_sim"] / s["mds_analytic_iid_z"] - 1) < 0.15 and 0.70 <= pw_at <= 0.90 and s["type1_sim"] < 0.09)
    d2 = d.assign(pay_rem=0.5 * d.debt_rem + rng.normal(0, sig, n))
    s2, P2 = mds_analysis(d2, ["debt_rem"], np.random.default_rng(4), grid=np.array([0.0, 0.5]), n_sim=500)
    check(f"G1: a planted slope is recovered in the fit (0.5 -> {s2['slope']:.2f}); the simulation's mean slope at a planted b* "
          f"is b* ({P2.mean_slope.iloc[1]:.3f} at 0.5)", abs(s2["slope"] - 0.5) < 0.2 and abs(P2.mean_slope.iloc[1] - 0.5) < 0.02)
    v, why = g1_verdict({**s, "slope": -0.02, "p": 0.8})
    v2, _ = g1_verdict({**s, "mds_analytic_iid_z": 0.5, "slope": -0.02, "p": 0.8})
    check(f"G1 verdict: small MDS -> '{v}'; MDS 0.5 -> '{v2}'", v == "INFORMATIVE, NOT POSITIVE" and v2.startswith("UNINFORMATIVE"))

    # 3. G3 gap expectations: constant baseline shares -> share x gap minutes
    rows = []
    t0 = pd.Timestamp("2026-09-01 00:00")
    for an in ("SF07", "SF08", "SF09", "SF10"):
        for i in range(8 * 72):
            t = t0 + pd.Timedelta(minutes=10 * i)
            rows.append({"animal": an, "t": t, "block": _blk(t), "rec_s": 600, "rem_s": 90, "nrem_s": 300})
    Bc = pd.DataFrame(rows)
    Bc["hour"] = Bc.t.dt.hour + Bc.t.dt.minute / 60
    Bc["day"] = (Bc.t - RELEASE).dt.total_seconds() / 86400
    Bc["dark"] = (~light_flags(Bc.t + pd.Timedelta(minutes=5))).astype(float)
    Wc = pd.DataFrame({"animal": ["SF08", "SF10"], "gap_start": [pd.Timestamp("2026-09-03 07:31:10"), pd.Timestamp("2026-09-05 18:02:00")],
                       "gap_end": [pd.Timestamp("2026-09-03 08:18:40"), pd.Timestamp("2026-09-05 19:10:30")], "A_block": ["2026-09-03D", "2026-09-05D"]})
    Wc = gap_expectations(Bc, Wc)
    L_ = ((Wc.gap_end - Wc.gap_start).dt.total_seconds() / 60).to_numpy()
    check(f"G3: gap expectations with constant shares = 0.15 / 0.5 x gap minutes ({Wc.gap_e_rem_min.round(4).tolist()} vs "
          f"{(0.15 * L_).round(4).tolist()})", np.allclose(Wc.gap_e_rem_min, 0.15 * L_, rtol=1e-6) and np.allclose(Wc.gap_e_nrem_min, 0.5 * L_, rtol=1e-6))

    # 4. G3 regression worlds
    def g3_world(seed, world, nd=12):
        r_ = np.random.default_rng(seed)
        na = 6
        rows = []
        for dd in range(nd):
            day_gap = r_.uniform(40, 70)
            for k in range(na):
                gap = day_gap + r_.normal(0, 12)
                gd = 0.15 * gap
                debt = (r_.normal(0, 1.5) + 1.0 * (gd - 0.15 * day_gap)) if world == "confounded" else r_.normal(0, 2.5)
                pay = (0.5 * gd if world in ("gap", "confounded") else 0.5 * debt) + r_.normal(0, 1.0)
                for bh in (1, 3):
                    rows.append({"B_h": bh, "animal": f"SF{7 + k:02d}", "A_block": f"{dd:02d}N", "cal_day": dd, "gap_min": gap, "gap_debt_rem": gd,
                                 "debt_rem": debt, "pay_rem": pay * (1 if bh == 1 else 2)})
        return pd.DataFrame(rows)
    res = {}
    for w in ("gap", "debt", "confounded"):
        M = g3_models(g3_world(11, w))
        rr = M[M.day_demeaned & (M.B_h == 1)].iloc[0]
        res[w] = (rr, g3_rule(rr)[0])
        print(f"   G3 world '{w}': b0 {rr.b0_debt:+.3f}, b1 {rr.b1_debt:+.3f}, gap {rr.b1_gap:+.3f} [{rr.b1_gap_lo:+.3f}, {rr.b1_gap_hi:+.3f}], "
              f"fall {rr.fall:+.2f} -> {res[w][1]}")
    check(f"G3: pay from the gap debt only, debt independent -> gap slope {res['gap'][0].b1_gap:+.2f} (0.5) with CI > 0",
          abs(res["gap"][0].b1_gap - 0.5) < 0.15 and res["gap"][0].b1_gap_lo > 0)
    check(f"G3: pay from the pre-round debt only -> gap slope CI includes 0 and the rule is NOT MET ({res['debt'][1]})",
          res["debt"][0].b1_gap_lo < 0 < res["debt"][0].b1_gap_hi and res["debt"][1] == "NOT MET")
    check(f"G3: pay from the gap debt with a correlated pre-round debt -> the rule is MET (fall {res['confounded'][0].fall:.2f})",
          res["confounded"][1] == "MET")
    Tt = g3_tertiles(g3_world(12, "debt", nd=60))
    check(f"G3 tertiles: pay = 0.5 x debt -> every tertile slope within 0.2 of 0.5 ({Tt[Tt.B_h == 1].slope.round(2).tolist()})",
          bool((np.abs(Tt[Tt.B_h == 1].slope - 0.5) < 0.2).all()) and len(Tt) == 6)
    check(f"combine_horizons: {combine_horizons({1: 'MET', 3: 'MET'})} / {combine_horizons({1: 'MET', 3: 'NOT MET'})} / "
          f"{combine_horizons({1: 'NOT MET', 3: 'NOT MET'})}",
          combine_horizons({1: "MET", 3: "MET"}) == "MET" and combine_horizons({1: "MET", 3: "NOT MET"}).startswith("PARTLY")
          and combine_horizons({1: "NOT MET", 3: "NOT MET"}) == "NOT MET")

    # 5. G4 interaction worlds
    def g4_world(seed, delta):
        r_ = np.random.default_rng(seed)
        rows = []
        for dd in range(14):
            m_day = r_.uniform(0, 2)
            for k in range(6):
                m = m_day + r_.normal(0, 0.1)
                debt = r_.normal(0, 2.5)
                pay = (0.3 + delta * (m - 1.0)) * debt + r_.normal(0, 0.8)
                rows.append({"B_h": 1, "animal": f"SF{7 + k:02d}", "A_block": f"{dd:02d}D", "cal_day": dd, "debt_rem": debt, "pay_rem": pay,
                             "gain_heldout": m, "gain_base": m, "onset_rel_sunrise_h": m})
        return pd.DataFrame(rows)
    M4, H4 = g4_models(g4_world(21, 0.4))
    r4 = M4[(M4.moderator == "gain_heldout") & M4.day_demeaned].iloc[0]
    M0, _ = g4_models(g4_world(22, 0.0))
    r0 = M0[(M0.moderator == "gain_heldout") & M0.day_demeaned].iloc[0]
    hh = H4[(H4.moderator == "gain_heldout")].set_index("half").slope
    check(f"G4: planted interaction 0.4 recovered ({r4.interaction:+.3f} [{r4.interaction_lo:+.3f}, {r4.interaction_hi:+.3f}]) -> "
          f"{g4_rule(r4)[0]}; high-half slope {hh['high']:+.2f} > low-half {hh['low']:+.2f}",
          abs(r4.interaction - 0.4) < 0.12 and g4_rule(r4)[0] == "MET" and hh["high"] > hh["low"])
    check(f"G4: none planted -> |interaction| {abs(r0.interaction):.3f} < 0.12, rule {g4_rule(r0)[0]}",
          abs(r0.interaction) < 0.12 and g4_rule(r0)[0] == "NOT MET")

    # 6. G2 on synthetic records with planted post-round REM suppression (one world), and none (three worlds: one null
    #    world fluctuates; the method's null behaviour is checked on their mean and on the rule in each)
    h_rem = 0.012
    t1 = time.time()
    recs, gaps = _synth_g2(np.random.default_rng(31), k_post=0.5, h_rem=h_rem, days=20)
    E, rw, cx, mc = _g2_world(recs, gaps, h_rem, n_boot=500)
    print(f"   G2 planted 0.5: rounds {int((E.group == 'round').sum())}, natural {int((E.group == 'natural').sum())}, cells {mc}; "
          f"0-1 h O/E {rw['0-1 h']['oe_round']:.2f} vs {rw['0-1 h']['oe_natural_std']:.2f} diff {rw['0-1 h']['diff']:+.2f} "
          f"[{rw['0-1 h']['diff_lo']:+.2f}, {rw['0-1 h']['diff_hi']:+.2f}] {rw['0-1 h']['animals_negative']}/{rw['0-1 h']['animals']}; "
          f"1-3 h diff {rw['1-3 h']['diff']:+.2f}; Cox round coef {cx['coef']:+.2f} [{cx['ci_lo']:+.2f}, {cx['ci_hi']:+.2f}] ({time.time() - t1:.1f} s)")
    n_r, n_n = int((E.group == "round").sum()), int((E.group == "natural").sum())
    rr_ = E[E.group == "round"]
    check(f"G2 events: {n_r} rounds (= 6 x 39 gaps), {n_n} natural wakes (= 6 x 40), round wake length = gap + 5-min initial "
          f"wake ({rr_.d_s.unique()[:3]} s), cells {mc}",
          n_r == 6 * 39 and n_n == 6 * 40 and bool((rr_.d_s == 3900).all()) and mc == ["evening | 30-120 min", "morning | 30-120 min"])
    check(f"G2: planted post-round O/E 0.5 -> 0-1 h O/E round {rw['0-1 h']['oe_round']:.2f}, natural {rw['0-1 h']['oe_natural_std']:.2f}, "
          f"difference within 0.15 of -0.5 and the rule MET; 1-3 h |difference| < 0.15",
          abs(rw["0-1 h"]["diff"] + 0.5) < 0.15 and g2_rule(rw["0-1 h"])[0] == "MET" and abs(rw["1-3 h"]["diff"]) < 0.15)
    check(f"G2: Cox round coefficient < 0 with CI < 0 ({cx['coef']:+.2f} [{cx['ci_lo']:+.2f}, {cx['ci_hi']:+.2f}])", cx["ci_hi"] < 0)
    cb = cells_of(E, None)
    check(f"G2: bin-only cells ignore the clock ({sorted(cb.dropna().unique())}, {int(cb.notna().sum())} of {len(E)} events)",
          sorted(cb.dropna().unique()) == ["30-120 min"] and int(cb.notna().sum()) == len(E))
    from joblib import Parallel, delayed
    t1 = time.time()
    nul = Parallel(n_jobs=3, backend="loky")(delayed(_g2_null)(sd, h_rem) for sd in (100, 101, 102))
    md, mcx = float(np.mean([x[0] for x in nul])), float(np.mean([x[2] for x in nul]))
    print(f"   G2 none planted (3 worlds): 0-1 h differences {[round(x[0], 3) for x in nul]}, rules {[x[1] for x in nul]}, Cox "
          f"{[round(x[2], 3) for x in nul]} ({time.time() - t1:.1f} s)")
    check(f"G2: none planted -> mean 0-1 h difference {md:+.3f} within 0.08 of 0, the rule NOT MET in every world, mean Cox "
          f"coefficient {mcx:+.3f} within 0.15 of 0", abs(md) < 0.08 and all(x[1] == "NOT MET" for x in nul) and abs(mcx) < 0.15)
    # handling exclusion: a natural wake starting < 3 h after a round gap end is not natural
    rc = recs[1]
    gx = pd.DataFrame({"animal": [rc["animal"]], "gap_start": [rc["start"] + pd.Timedelta(hours=20)], "gap_end": [rc["start"] + pd.Timedelta(hours=8, minutes=30)],
                       "cause": ["round_logged"], "usable": [False], "kind": ["other"], "gap_min": [10.0]})
    gx["gap_start"] = gx.gap_end - pd.Timedelta(minutes=10)
    E1 = g2_events([rc], gx.iloc[:0])
    E2 = g2_events([rc], gx)
    check(f"G2: a natural wake 1.5 h after a handling gap end is excluded ({len(E1)} -> {len(E2)} natural events)", len(E1) == 1 and len(E2) == 0)
    T_, ev_, why_ = first_rem(np.array([W] * 5 + [N] * 100 + [W] * 20 + [N] * 50 + [R] * 30, np.int8),
                              bouts(np.array([W] * 5 + [N] * 100 + [W] * 20 + [N] * 50 + [R] * 30, np.int8)), 1, {(105, 125)})
    check(f"G2: first-REM latency counts NREM + microarousal seconds (T {T_} = 170, event {ev_}, {why_})", T_ == 170 and ev_ == 1)
    print(f"selftest {'PASS' if ok_all else 'FAIL'} ({time.time() - t_start:.0f} s)")
    if not ok_all:
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["run"])
    ap.add_argument("--parts", nargs="*", default=list(PARTS), choices=list(PARTS))
    ap.add_argument("--scorings", nargs="*", default=["final", "pass2med"], choices=list(SCORINGS))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.selftest:
        selftest()
    elif a.cmd == "run":
        run(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
