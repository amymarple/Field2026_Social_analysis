r"""Sleep behaviour explore, Step D1: natural dawn wakes, and two reusable measurement functions (cohort 2026c).

Plan: implementation_plan/2026-10-08-sleep-behaviour-explore.md (sections 1, 3, 5 Step D and Step E; the pass rules there
are fixed). Every quantity is defined, formula + text, in the report's Definitions section.

Reusable measurement functions (called by the main session on SIMULATED records for Step D2 and Step E):
  payback_from_records(recs, gaps, label, *, baseline="phase_x_day", bins=None, engine="numpy", return_windows=False)
      = exactly Step A's A4 measurement (sleep_explore.part_a4 with the phase x day baselines): 10-min bins of the GIVEN
      records, leave-one-block-out baselines, windows A = 3 h before each usable battery-round gap and B = the first
      1 h / 3 h after it (>= 80 % recorded), and sleep_explore.pay_models (pay ~ debt + animal FE, SEs clustered by the
      block of A; day-demeaned; NREM debt partialled; per-animal signs; pay_nrem ~ debt_nrem; also pay_rem_n, pay_rem_dur).
  budget_from_records(recs, label, *, baseline="phase_x_day", bins=None, engine="numpy", coverage=0.5, return_days=False)
      = plan Step E (vi): per animal and night (sunset d -> sunrise d+1) and the following day (-> sunset d+1), NREM and
      REM deviation (observed - expected, min per recorded h; coverage >= 0.5 each); slope of the day deviation on the
      night deviation within animal, + linear day, + day fixed effects; per-animal signs; and the drift of each deviation.
  dawn_payback_from_records(recs, gaps, label, *, bins=None, engine="numpy", return_windows=False)
      = the D1 measurement below as a function (same input contract).
  baseline_bins(recs, baseline="phase_x_day", engine="numpy") computes the shared bins + baselines once; pass its result
  as `bins=` to call several functions on the same records without refitting.
  Records: dicts {animal, start (Timestamp), state (1-s int8: 0 unknown, 1 WAKE, 3 NREM, 5 REM), record_id, block, ...} as
  sleep_cycles_v2.build_records; simulated records keep animals, starts and lengths and replace the states. The functions
  are deterministic and write nothing. engine="numpy" fits the baselines by IRLS in numpy (verified against the
  statsmodels path, engine="statsmodels", which calls sleep_explore.baselines_d / sleep_schedule_phase2.baselines).

Step D1 (plan section 5): every WAKE bout >= 30 min that ends 05:00-09:00 inside a record, with no handling gap (battery
round, or probe move) of the same animal overlapping the 3 h before its start; windows A = the 3 h before the wake start,
B = the 1 h / 3 h after its end (>= 80 % recorded; the same baselines; cut at the exact second). pay_rem ~ debt_rem +
debt_nrem + main-sleep onset (clock h of the first Watson SLEEP episode >= 20 min starting after the wake end) + animal FE,
SEs clustered by block; day-demeaned; per-animal signs. The same model with the onset covariate on the morning ROUND
windows. Both scorings; the verdict is on pass2med (claim #10 is scoped to fixed thresholds), FINAL reported.
Sensitivities (not in the rule): window A including the wake; 10-min-bin windows (dawn_windows_bins).

Usage: python ephys/sleep_explore_d.py stepD1 [--scorings FINAL pass2med]
       python ephys/sleep_explore_d.py --selftest
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
from sleep_cycles_v2 import build_records  # noqa: E402
from sleep_explore import (COLORS, P0_MANIFEST, PASS2MED, ROUND_CAUSES, SLEEP_MIN_S, baselines_d, ols, pay_models,  # noqa: E402
                           tbl, term)
from sleep_schedule import N, R, REVIEW, STATES, W, included_sessions  # noqa: E402
from sleep_schedule_phase2 import baselines, bins10, comp_windows  # noqa: E402
from sleep_schedule_phase3 import episodes_of, light_flags  # noqa: E402

SCORINGS = {"FINAL": STATES, "pass2med": PASS2MED}
PLAN = "implementation_plan/2026-10-08-sleep-behaviour-explore.md"
A_MANIFEST = ROOT / "results/2026c/ephys_spikes/reports/run_manifest_sleep_explore_A_2026c.json"
A4_CSV = ROOT / "results/2026c/ephys_spikes/reports/ephys_spikes_sleep_explore_A_a4_payback_2026c.csv"
P3B_MANIFEST = ROOT / "results/2026c/ephys_spikes/reports/run_manifest_sleep_schedule_phase3b_2026c.json"
BASELINES = ("phase_x_day", "common_day")
HANDLING = tuple(ROUND_CAUSES) + ("probe_move",)
DAWN_END_H = (5.0, 9.0)            # plan D1: natural wakes ending 05:00-09:00 (clock hours, the plan's own definition)
DAWN_MIN_S = 1800                  # plan D1: >= 30 min
LOOKBACK_S = 3 * 3600              # window A and the handling exclusion
MIN_WIN = 10                       # minimum windows for a pooled fit (as sleep_explore.pay_models)
MIN_RAT_WIN = 3                    # plan D1 rats rule: rats with >= 3 windows
D1_SETS = [("pay_rem", ["debt_rem"]), ("pay_rem", ["debt_rem", "debt_nrem"]), ("pay_rem", ["debt_rem", "debt_nrem", "onset_h"]),
           ("pay_nrem", ["debt_nrem"])]
PRIMARY = ("pay_rem", "debt_rem + debt_nrem + onset_h")
# claim #13 reference numbers (docs/methods/sleep_logic_audit_2026-10-08.md; check_drift.py output on Phase 3b's tables)
CHECK_DRIFT = {("pass2med", "NREM"): (-0.56, -0.06, -0.12), ("pass2med", "REM"): (-0.41, -0.30, -0.20),
               ("FINAL", "NREM"): (-0.33, +0.28, -0.17), ("FINAL", "REM"): (-0.87, -0.85, -0.49)}
BUDGET_MODELS = ("within animal", "within animal + linear day", "within animal + day FE")


# ================================================================== baselines (bins + leave-one-block-out GLMs)
_EPS = np.finfo(float).eps


def _design(df: pd.DataFrame, levels: list[str], dark_terms: bool) -> np.ndarray:
    """The design of sleep_explore._Xd (dark_terms) or sleep_schedule_phase2._X: 1, sin/cos(2 pi k h/24) k = 1, 2, day,
    [dark, dark x day], animal dummies (first level dropped)."""
    h = df.hour.to_numpy(float)
    cols = [np.ones(len(df))] + [fn(2 * np.pi * k * h / 24) for k in (1, 2) for fn in (np.sin, np.cos)]
    day = df.day.to_numpy(float)
    cols.append(day)
    if dark_terms:
        dk = df.dark.to_numpy(float)
        cols += [dk, dk * day]
    an = df.animal.to_numpy()
    cols += [(an == lv).astype(float) for lv in levels[1:]]
    return np.column_stack(cols)


def _wls(X: np.ndarray, z: np.ndarray, w: np.ndarray) -> np.ndarray:
    XtW = X.T * w
    try:
        return np.linalg.solve(XtW @ X, XtW @ z)
    except np.linalg.LinAlgError:
        sw = np.sqrt(w)
        return np.linalg.lstsq(X * sw[:, None], z * sw, rcond=None)[0]


def _irls(X: np.ndarray, y: np.ndarray, fam: str, w=None, off=None, b0=None, tol: float = 1e-10, maxiter: int = 100) -> np.ndarray:
    """IRLS for the binomial (logit; var_weights w) and Poisson (log; offset) GLMs, started as statsmodels does
    (mu0 = (y + 0.5) / 2, resp. (y + mean y) / 2) or warm from b0; converged on the coefficients."""
    n = len(y)
    w = np.ones(n) if w is None else w
    off = np.zeros(n) if off is None else off
    if b0 is None:
        mu = (y + 0.5) / 2 if fam == "binomial" else (y + y.mean()) / 2
        eta = np.log(mu / (1 - mu)) if fam == "binomial" else np.log(mu)
        b = None
    else:
        b = b0
        eta = X @ b + off
        mu = 1 / (1 + np.exp(-eta)) if fam == "binomial" else np.exp(eta)
    for _ in range(maxiter):
        if fam == "binomial":
            p = np.clip(mu, _EPS, 1 - _EPS)
            ww = w * p * (1 - p)
            z = eta + (y - mu) / (p * (1 - p)) - off
        else:
            ww = w * mu
            z = eta + (y - mu) / mu - off
        bn = _wls(X, z, ww)
        eta = X @ bn + off
        mu = 1 / (1 + np.exp(-eta)) if fam == "binomial" else np.exp(eta)
        if b is not None and np.max(np.abs(bn - b)) <= tol * (1 + np.max(np.abs(bn))):
            return bn
        b = bn
    return b


def _baselines_np(B: pd.DataFrame, RB: pd.DataFrame, dark_terms: bool) -> pd.DataFrame:
    """numpy replica of sleep_explore.baselines_d (dark_terms) / sleep_schedule_phase2.baselines: leave-one-block-out
    binomial REM / NREM share (var weights = recorded s), Poisson REM onsets (offset ln recorded 10-min units), OLS on ln
    REM bout duration with smearing."""
    levels = sorted(B.animal.unique())
    B = B.copy()
    X, XR = _design(B, levels, dark_terms), _design(RB, levels, dark_terms)
    rec = B.rec_s.to_numpy(float)
    ok = rec > 0
    blk, rblk = B.block.to_numpy(), RB.block.to_numpy()
    yr = np.where(ok, B.rem_s.to_numpy(float) / np.maximum(rec, 1), 0.0)
    yn = np.where(ok, B.nrem_s.to_numpy(float) / np.maximum(rec, 1), 0.0)
    on = B.rem_on.to_numpy(float)
    off_tr = np.log(np.maximum(rec, 1) / 600)
    ld = np.log(RB.dur_s.to_numpy(float))
    full = {"r": _irls(X[ok], yr[ok], "binomial", rec[ok]), "n": _irls(X[ok], yn[ok], "binomial", rec[ok]),
            "o": _irls(X[ok], on[ok], "poisson", off=off_tr[ok])}
    out = {c: np.full(len(B), np.nan) for c in ("e_rem_s", "e_nrem_s", "e_rem_on", "e_rem_dur")}
    for bk in sorted(set(blk)):
        te = blk == bk
        tr = ok & ~te
        br = _irls(X[tr], yr[tr], "binomial", rec[tr], b0=full["r"])
        bn = _irls(X[tr], yn[tr], "binomial", rec[tr], b0=full["n"])
        bo = _irls(X[tr], on[tr], "poisson", off=off_tr[tr], b0=full["o"])
        out["e_rem_s"][te] = rec[te] / (1 + np.exp(-(X[te] @ br)))
        out["e_nrem_s"][te] = rec[te] / (1 + np.exp(-(X[te] @ bn)))
        out["e_rem_on"][te] = np.exp(X[te] @ bo + off_tr[te]) * (rec[te] > 0)
        rtr = rblk != bk
        bd = np.linalg.lstsq(XR[rtr], ld[rtr], rcond=None)[0]
        out["e_rem_dur"][te] = np.exp(X[te] @ bd) * float(np.mean(np.exp(ld[rtr] - XR[rtr] @ bd)))
    for c, v in out.items():
        B[c] = v
    return B


def baseline_bins(recs: list[dict], baseline: str = "phase_x_day", engine: str = "numpy") -> tuple[pd.DataFrame, pd.DataFrame]:
    """(B, RB): sleep_schedule_phase2.bins10 of the records (10-min bins aligned to each record start; REM bouts not
    touching unknown epochs) with `dark` (NOAA; bin midpoint / bout onset, as sleep_explore.a4_windows) and the expected
    e_rem_s, e_nrem_s, e_rem_on, e_rem_dur. baseline "phase_x_day" = the plan's (sleep_explore.baselines_d), "common_day"
    = Phase 2's (one linear day term, no dark)."""
    if baseline not in BASELINES:
        raise ValueError(f"baseline must be one of {BASELINES}")
    B, RB = bins10(recs)
    B["dark"] = (~light_flags(B.t + pd.Timedelta(minutes=5))).astype(float)
    RB["dark"] = (~light_flags(RB.t)).astype(float)
    if engine == "statsmodels":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return (baselines_d if baseline == "phase_x_day" else baselines)(B, RB), RB
    return _baselines_np(B, RB, baseline == "phase_x_day"), RB


# ================================================================== round windows (= comp_windows' across-gap branch)
_CS = ("rec_s", "rem_s", "e_rem_s", "nrem_s", "e_nrem_s", "rem_on", "e_rem_on")


def _bin_index(B: pd.DataFrame, RB: pd.DataFrame) -> tuple[dict, dict]:
    per = {}
    for an, g in B.groupby("animal", sort=False):
        g = g.sort_values("t", kind="mergesort")
        cs = {c: np.r_[0.0, np.cumsum(g[c].to_numpy(float))] for c in _CS}
        w = np.maximum(g.e_rem_on.to_numpy(float), 1e-9)
        ed = g.e_rem_dur.to_numpy(float)
        cs["w"] = np.r_[0.0, np.cumsum(w)]
        cs["wd"] = np.r_[0.0, np.cumsum(np.nan_to_num(w * ed))]
        cs["nan"] = np.r_[0, np.cumsum(np.isnan(ed))]
        per[an] = (g.t.to_numpy("datetime64[ns]").astype(np.int64), cs, g.block.to_numpy())
    rper = {}
    for an, g in RB.groupby("animal", sort=False):
        g = g.sort_values("t", kind="mergesort")
        rper[an] = (g.t.to_numpy("datetime64[ns]").astype(np.int64), np.r_[0.0, np.cumsum(g.dur_s.to_numpy(float))])
    return per, rper


def _agg_bins(per: dict, rper: dict, an: str, t0: pd.Timestamp, t1: pd.Timestamp) -> dict | None:
    """sleep_schedule_phase2.comp_windows.agg, vectorised: bins of the animal with t0 <= t <= t1 - 1 s; >= 80 % recorded."""
    if an not in per:
        return None
    tn, cs, blk = per[an]
    lo = int(np.searchsorted(tn, t0.value, "left"))
    hi = int(np.searchsorted(tn, (t1 - pd.Timedelta(seconds=1)).value, "right"))
    if hi <= lo:
        return None
    s = {c: cs[c][hi] - cs[c][lo] for c in cs}
    if s["rec_s"] < 0.8 * (t1 - t0).total_seconds():
        return None
    rem_dur = np.nan
    if an in rper:
        rt, rc = rper[an]
        a, b = int(np.searchsorted(rt, t0.value, "left")), int(np.searchsorted(rt, t1.value, "left"))
        rem_dur = (rc[b] - rc[a]) / (b - a) if b > a else np.nan
    e_dur = (s["wd"] / s["w"] if s["nan"] == 0 else np.nan) if s["e_rem_on"] > 0 else np.nan
    return {"rem_min": s["rem_s"] / 60, "e_rem_min": s["e_rem_s"] / 60, "nrem_min": s["nrem_s"] / 60, "e_nrem_min": s["e_nrem_s"] / 60,
            "rem_n": float(s["rem_on"]), "e_rem_n": float(s["e_rem_on"]), "rem_dur_s": float(rem_dur), "e_rem_dur_s": float(e_dur),
            "block": blk[lo]}


def round_windows(B: pd.DataFrame, RB: pd.DataFrame, gaps: pd.DataFrame, causes=ROUND_CAUSES) -> pd.DataFrame:
    """Window pairs across the usable battery-round gaps: A = [gap start - 3 h, gap start), B = [gap end, + 1 h / 3 h);
    rows and columns as sleep_schedule_phase2.comp_windows (setting 'across gap (<cause>)'), plus gap_start, gap_end."""
    per, rper = _bin_index(B, RB)
    rows = []
    for r in gaps[gaps.usable.astype(bool) & gaps.cause.isin(causes)].itertuples():
        gs, ge = pd.Timestamp(r.gap_start), pd.Timestamp(r.gap_end)
        for bh in (1, 3):
            a_ = _agg_bins(per, rper, r.animal, gs - pd.Timedelta(hours=3), gs)
            b_ = _agg_bins(per, rper, r.animal, ge, ge + pd.Timedelta(hours=bh))
            if a_ and b_:
                rows.append({"setting": f"across gap ({r.cause})", "B_h": bh, "animal": r.animal, "t_A": gs - pd.Timedelta(hours=3),
                             "kind": r.kind, **{f"A_{k}": v for k, v in a_.items()}, **{f"B_{k}": v for k, v in b_.items()},
                             "gap_start": gs, "gap_end": ge})
    return pd.DataFrame(rows)


# ================================================================== function 1: the A4 payback
def payback_from_records(recs: list[dict], gaps: pd.DataFrame, label: str, *, baseline: str = "phase_x_day", bins=None,
                         engine: str = "numpy", return_windows: bool = False):
    """Step A's A4 measurement on the given records. Returns sleep_explore.pay_models' table with `label` and `baseline`
    in front: one row per kind (morning / evening) x B_h (1 / 3) x outcome (pay_rem, pay_rem_n, pay_rem_dur, pay_nrem) x
    predictors x day_demeaned, columns n_windows, clusters, slope, ci_lo, ci_hi, p, animals_positive, animals, mean_x,
    mean_y. `bins` = baseline_bins(recs, baseline) to reuse; return_windows=True also returns the window table."""
    B, RB = bins if bins is not None else baseline_bins(recs, baseline, engine)
    Wn = round_windows(B, RB, gaps)
    if len(Wn):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            T = pay_models(Wn)
    else:
        T = pd.DataFrame(columns=["kind", "B_h", "outcome", "predictors", "day_demeaned", "n_windows", "clusters", "slope", "ci_lo",
                                  "ci_hi", "p", "animals_positive", "animals", "mean_x", "mean_y"])
    T.insert(0, "baseline", baseline)
    T.insert(0, "label", label)
    return (T, Wn) if return_windows else T


# ================================================================== function 2: the night -> next-day budget
def budget_days(B: pd.DataFrame, nights=None) -> pd.DataFrame:
    """Per animal and night d: night = [sunset d, sunrise d+1), day = [sunrise d+1, sunset d+1) (NOAA); bins whose start
    lies in the period (as Phase 3b). cov = recorded s / period s; *_dev_min = (observed - expected) s / 60;
    *_rate_dev = (observed - expected) / max(recorded s, 1) x 60 (min per recorded h)."""
    from sleep_quant import sun_times
    if nights is None:
        nights = pd.date_range(B.t.min().normalize() - pd.Timedelta(days=1), B.t.max().normalize())
    sun = {}

    def st(d):
        k = pd.Timestamp(d).date()
        if k not in sun:
            sun[k] = tuple(pd.Timestamp(x) for x in sun_times(k))
        return sun[k]
    rows = []
    for an, g in B.groupby("animal"):
        g = g.sort_values("t", kind="mergesort")
        tn = g.t.to_numpy("datetime64[ns]").astype(np.int64)
        cs = {c: np.r_[0.0, np.cumsum(g[c].to_numpy(float))] for c in ("rec_s", "rem_s", "e_rem_s", "nrem_s", "e_nrem_s")}
        for d in nights:
            ss0 = st(d)[1]
            sr1, ss1 = st(d + pd.Timedelta(days=1))
            rr = {"animal": an, "night_of": pd.Timestamp(d).normalize()}
            for k, (t0, t1) in {"night": (ss0, sr1), "day": (sr1, ss1)}.items():
                lo, hi = int(np.searchsorted(tn, t0.value, "left")), int(np.searchsorted(tn, t1.value, "left"))
                s = {c: cs[c][hi] - cs[c][lo] for c in cs}
                rr[f"{k}_cov"] = s["rec_s"] / (t1 - t0).total_seconds()
                for q, (o, e) in {"REM": ("rem_s", "e_rem_s"), "NREM": ("nrem_s", "e_nrem_s")}.items():
                    rr[f"{k}_{q}_dev_min"] = (s[o] - s[e]) / 60
                    rr[f"{k}_{q}_rate_dev"] = (s[o] - s[e]) / max(s["rec_s"], 1) * 60
            rows.append(rr)
    return pd.DataFrame(rows)


def _ols_np(y: np.ndarray, X: np.ndarray, groups=None):
    import statsmodels.api as sm
    m = sm.OLS(y, X)
    if groups is not None:
        return m.fit(cov_type="cluster", cov_kwds={"groups": groups})
    return m.fit()


def _dummies(v: np.ndarray) -> np.ndarray:
    lv = sorted(set(v.tolist()))
    return np.column_stack([(v == x).astype(float) for x in lv[1:]]) if len(lv) > 1 else np.zeros((len(v), 0))


def budget_from_records(recs: list[dict], label: str, *, baseline: str = "phase_x_day", bins=None, engine: str = "numpy",
                        coverage: float = 0.5, return_days: bool = False):
    """Plan Step E (vi). Returns one row per quantity (REM / NREM) x model: 'within animal' (day dev ~ night dev + animal
    FE, SEs clustered by night), 'within animal + linear day' (+ experiment day, clustered by night), 'within animal +
    day FE' (+ night-of fixed effects, model-based SEs; = check_drift.py), and the drifts 'drift: night deviation' /
    'drift: day deviation' (dev ~ experiment day + animal FE, clustered by night). Columns: label, baseline, quantity,
    model, x, y, n_animal_days, animals, slope, ci_lo, ci_hi, p, animals_negative, animals_with_slope (per-animal simple
    OLS slopes, >= 4 animal-days; for the day-FE model on night-of-demeaned x and y). Units: min per recorded hour."""
    B, _ = bins if bins is not None else baseline_bins(recs, baseline, engine)
    D = budget_days(B)
    g = D[(D.night_cov >= coverage) & (D.day_cov >= coverage)].copy()
    rows = []
    if len(g):
        g["day"] = (g.night_of - g.night_of.min()).dt.days.astype(float)
        an = g.animal.to_numpy()
        nights = g.night_of.to_numpy()
        grp = pd.factorize(nights)[0]
        A, Dn = _dummies(an), _dummies(nights.astype("datetime64[ns]").astype(np.int64))
        for q in ("NREM", "REM"):
            x, y = f"night_{q}_rate_dev", f"day_{q}_rate_dev"
            xv, yv = g[x].to_numpy(float), g[y].to_numpy(float)
            one = np.ones(len(g))
            specs = {"within animal": (np.column_stack([one, xv, A]), grp),
                     "within animal + linear day": (np.column_stack([one, xv, g.day.to_numpy(), A]), grp),
                     "within animal + day FE": (np.column_stack([one, xv, A, Dn]), None)}
            xd = xv - g.groupby("night_of")[x].transform("mean").to_numpy()
            yd = yv - g.groupby("night_of")[y].transform("mean").to_numpy()
            for mname, (X, gr) in specs.items():
                r = {"label": label, "baseline": baseline, "quantity": q, "model": mname, "x": x, "y": y, "n_animal_days": len(g),
                     "animals": int(g.animal.nunique())}
                if len(g) > X.shape[1] + 1:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        f = _ols_np(yv, X, gr)
                    ci = np.asarray(f.conf_int())[1]
                    r.update(slope=float(f.params[1]), ci_lo=float(ci[0]), ci_hi=float(ci[1]), p=float(f.pvalues[1]))
                xs_, ys_ = (xd, yd) if mname.endswith("day FE") else (xv, yv)
                sg = []
                for a in np.unique(an):
                    m = an == a
                    if m.sum() >= 4 and np.std(xs_[m]) > 0:
                        sg.append(np.sign(np.polyfit(xs_[m], ys_[m], 1)[0]))
                r.update(animals_negative=int(np.sum(np.array(sg) < 0)), animals_with_slope=len(sg))
                rows.append(r)
            for which, col in (("night", x), ("day", y)):
                v = g[col].to_numpy(float)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    f = _ols_np(v, np.column_stack([np.ones(len(g)), g.day.to_numpy(), A]), grp)
                ci = np.asarray(f.conf_int())[1]
                sg = [np.sign(np.polyfit(g.day.to_numpy()[an == a], v[an == a], 1)[0]) for a in np.unique(an) if (an == a).sum() >= 4]
                rows.append({"label": label, "baseline": baseline, "quantity": q, "model": f"drift: {which} deviation", "x": "day",
                             "y": col, "n_animal_days": len(g), "animals": int(g.animal.nunique()), "slope": float(f.params[1]),
                             "ci_lo": float(ci[0]), "ci_hi": float(ci[1]), "p": float(f.pvalues[1]),
                             "animals_negative": int(np.sum(np.array(sg) < 0)), "animals_with_slope": len(sg)})
    T = pd.DataFrame(rows, columns=["label", "baseline", "quantity", "model", "x", "y", "n_animal_days", "animals", "slope", "ci_lo",
                                    "ci_hi", "p", "animals_negative", "animals_with_slope"])
    return (T, D) if return_days else T


# ================================================================== D1: natural dawn wakes
def _hour(t: pd.Timestamp) -> float:
    return (t - t.normalize()).total_seconds() / 3600


def dawn_wakes(recs: list[dict], gaps: pd.DataFrame, end_h=DAWN_END_H, min_s: int = DAWN_MIN_S) -> pd.DataFrame:
    """All WAKE bouts >= min_s that end in [end_h) clock hours, with the flags that make one 'natural' (definitions:
    report). One row per bout."""
    rows = []
    for rc in recs:
        st = rc["state"]
        n = len(st)
        for s, a, b in bouts(st):
            if s != W or (b - a) < min_s:
                continue
            te = rc["start"] + pd.Timedelta(seconds=b)
            if not (end_h[0] <= _hour(te) < end_h[1]):
                continue
            rows.append({"animal": rc["animal"], "record_id": rc["record_id"], "block": rc["block"], "a": a, "b": b,
                         "wake_start": rc["start"] + pd.Timedelta(seconds=a), "wake_end": te, "d_min": (b - a) / 60,
                         "end_h": _hour(te), "inside": bool(a > 0 and st[a - 1] != 0 and b < n and st[b] != 0)})
    D = pd.DataFrame(rows)
    if D.empty:
        return D
    for col, causes in (("round_3h", ROUND_CAUSES), ("probe_3h", ("probe_move",))):
        gg = gaps[gaps.cause.isin(causes)]
        D[col] = [bool(((gg.animal == r.animal) & (pd.to_datetime(gg.gap_end) > r.wake_start - pd.Timedelta(seconds=LOOKBACK_S))
                        & (pd.to_datetime(gg.gap_start) < r.wake_start)).any()) for r in D.itertuples()]
    D["natural"] = D.inside & ~D.round_3h & ~D.probe_3h
    return D


class _RecSec:
    """Per-second observed and expected arrays of one record (expected from its 10-min baseline bins: the bin's expected
    share / rate per recorded second; bins with nothing recorded and the trailing < 10 min take the neighbouring bin's)."""

    def __init__(self, rc: dict, Brec: pd.DataFrame):
        st = rc["state"]
        n = len(st)
        self.n, self.st, self.block = n, st, rc["block"]
        known = (st != 0).astype(float)
        Brec = Brec.sort_values("t", kind="mergesort")
        rec = Brec.rec_s.to_numpy(float)

        def per_sec(v):
            v = pd.Series(np.where(rec > 0, v, np.nan)).ffill().bfill().to_numpy() if len(v) else np.array([np.nan])
            x = np.repeat(v, 600)[:n]
            return np.r_[x, np.full(n - len(x), v[-1])] if len(x) < n else x
        safe = np.maximum(rec, 1)
        p_rem, p_nrem = per_sec(Brec.e_rem_s.to_numpy(float) / safe), per_sec(Brec.e_nrem_s.to_numpy(float) / safe)
        r_on, e_dur = per_sec(Brec.e_rem_on.to_numpy(float) / safe), per_sec(Brec.e_rem_dur.to_numpy(float))
        on = np.zeros(n)
        on[1:] = (st[1:] == R) & (st[:-1] != R) & (st[:-1] != 0)
        c = lambda v: np.r_[0.0, np.cumsum(v)]  # noqa: E731
        self.cs = {"rec": c(known), "rem": c(st == R), "nrem": c(st == N), "on": c(on), "e_rem": c(np.nan_to_num(p_rem) * known),
                   "e_nrem": c(np.nan_to_num(p_nrem) * known), "e_on": c(np.nan_to_num(r_on) * known),
                   "e_ond": c(np.nan_to_num(r_on * e_dur) * known)}
        rb = [(a, b - a) for s, a, b in bouts(st) if s == R and a > 0 and st[a - 1] != 0 and b < n and st[b] != 0]
        self.rb_on = np.array([a for a, _ in rb], int)
        self.rb_cs = np.r_[0.0, np.cumsum([d for _, d in rb])]
        self._eps = None

    def window(self, lo: int, hi: int) -> dict | None:
        """Seconds [lo, hi) of the record (outside = unrecorded); None if < 80 % recorded."""
        L = hi - lo
        lo_c, hi_c = max(lo, 0), min(hi, self.n)
        if hi_c <= lo_c:
            return None
        s = lambda k, a=lo_c: self.cs[k][hi_c] - self.cs[k][a]  # noqa: E731
        if s("rec") < 0.8 * L:
            return None
        a, b = int(np.searchsorted(self.rb_on, lo_c, "left")), int(np.searchsorted(self.rb_on, hi_c, "left"))
        e_on = s("e_on")
        return {"rem_min": s("rem") / 60, "e_rem_min": s("e_rem") / 60, "nrem_min": s("nrem") / 60, "e_nrem_min": s("e_nrem") / 60,
                "rem_n": float(s("on", min(lo_c + 1, hi_c))), "e_rem_n": float(e_on),
                "rem_dur_s": float((self.rb_cs[b] - self.rb_cs[a]) / (b - a)) if b > a else np.nan,
                "e_rem_dur_s": float(s("e_ond") / e_on) if e_on > 0 else np.nan, "block": self.block, "rec_min": s("rec") / 60}

    def sleep_onset(self, from_s: int) -> int | None:
        """Start (s) of the first Watson SLEEP episode >= 20 min starting at or after from_s (None if none)."""
        if self._eps is None:
            self._eps = episodes_of(self.st, SLEEP_MIN_S)
        for a, _ in self._eps:
            if a >= from_s:
                return a
        return None


def _add_pay(Wn: pd.DataFrame) -> pd.DataFrame:
    Wn = Wn.copy()
    Wn["debt_rem"] = Wn.A_e_rem_min - Wn.A_rem_min
    Wn["pay_rem"] = Wn.B_rem_min - Wn.B_e_rem_min
    Wn["debt_nrem"] = Wn.A_e_nrem_min - Wn.A_nrem_min
    Wn["pay_nrem"] = Wn.B_nrem_min - Wn.B_e_nrem_min
    Wn["pay_rem_n"] = Wn.B_rem_n - Wn.B_e_rem_n
    Wn["pay_rem_dur"] = Wn.B_rem_dur_s - Wn.B_e_rem_dur_s
    if "cal_day" not in Wn:
        Wn["cal_day"] = (pd.to_datetime(Wn.t_A) + pd.Timedelta(hours=3)).dt.normalize()
    return Wn


def dawn_windows(recs: list[dict], B: pd.DataFrame, gaps: pd.DataFrame, horizons=(1, 3), include_wake: bool = False,
                 wakes: pd.DataFrame | None = None, stats: dict | None = None) -> pd.DataFrame:
    """One row per natural dawn wake x B horizon with complete windows (columns as comp_windows' A_* / B_* + wake fields
    and the main-sleep onset). include_wake=True (sensitivity): A = the 3 h before the wake END (the wake included).
    `stats` (a dict) receives the funnel counts."""
    D = dawn_wakes(recs, gaps) if wakes is None else wakes
    if D.empty:
        return pd.DataFrame()
    by_rid = {rc["record_id"]: rc for rc in recs}
    Bg = dict(tuple(B.groupby("record_id")))
    cache, rows = {}, []
    st_ = {"natural": int(D.natural.sum()), "A_ok": 0, **{f"B{bh}_ok": 0 for bh in horizons}, "onset_found": 0}
    for r in D[D.natural].itertuples():
        rc = by_rid[r.record_id]
        if r.record_id not in cache:
            cache[r.record_id] = _RecSec(rc, Bg.get(r.record_id, B.iloc[:0]))
        S = cache[r.record_id]
        a_end = r.b if include_wake else r.a
        A = S.window(a_end - LOOKBACK_S, a_end)
        if A is None:
            continue
        st_["A_ok"] += 1
        ep = S.sleep_onset(r.b)
        st_["onset_found"] += int(ep is not None)
        t_on = rc["start"] + pd.Timedelta(seconds=ep) if ep is not None else pd.NaT
        for bh in horizons:
            Bw = S.window(r.b, r.b + int(bh * 3600))
            if Bw is None:
                continue
            st_[f"B{bh}_ok"] += 1
            rows.append({"setting": "dawn wake" + (" (A includes the wake)" if include_wake else ""), "B_h": bh, "animal": r.animal,
                         "record_id": r.record_id, "t_A": rc["start"] + pd.Timedelta(seconds=a_end - LOOKBACK_S), "kind": "dawn",
                         "wake_start": r.wake_start, "wake_end": r.wake_end, "d_min": r.d_min, "end_h": r.end_h,
                         "cal_day": r.wake_start.normalize(), "onset_time": t_on,
                         "onset_h": _hour(t_on) if ep is not None else np.nan,
                         "onset_latency_min": (ep - r.b) / 60 if ep is not None else np.nan,
                         **{f"A_{k}": v for k, v in A.items()}, **{f"B_{k}": v for k, v in Bw.items()}})
    if stats is not None:
        stats.update(st_)
    return pd.DataFrame(rows)


def dawn_windows_bins(Wd: pd.DataFrame, B: pd.DataFrame, RB: pd.DataFrame) -> pd.DataFrame:
    """Sensitivity: the same dawn wakes with comp_windows-style 10-min-bin windows (bins of the animal whose start lies in
    [t0, t1 - 1 s], any record; >= 80 % recorded) instead of exact-second windows."""
    per, rper = _bin_index(B, RB)
    rows = []
    for r in Wd.to_dict("records"):
        a_ = _agg_bins(per, rper, r["animal"], r["wake_start"] - pd.Timedelta(seconds=LOOKBACK_S), r["wake_start"])
        b_ = _agg_bins(per, rper, r["animal"], r["wake_end"], r["wake_end"] + pd.Timedelta(hours=r["B_h"]))
        if a_ and b_:
            meta = {k: v for k, v in r.items() if not k.startswith(("A_", "B_")) or k == "B_h"}
            meta["setting"] = "dawn wake (10-min-bin windows)"
            rows.append({**meta, **{f"A_{k}": v for k, v in a_.items()}, **{f"B_{k}": v for k, v in b_.items()}})
    return pd.DataFrame(rows)


def round_onsets(Wn: pd.DataFrame, recs: list[dict]) -> pd.DataFrame:
    """Adds the main-sleep onset after each round: the first SLEEP episode >= 20 min in the record that starts at the gap
    end (record start within 5 s of it)."""
    Wn = Wn.copy()
    starts = {}
    for rc in recs:
        starts.setdefault(rc["animal"], []).append(rc)
    cache = {}
    oh, lat, ot = [], [], []
    for r in Wn.itertuples():
        ge = pd.Timestamp(r.gap_end)
        cand = [rc for rc in starts.get(r.animal, []) if abs((rc["start"] - ge).total_seconds()) <= 5]
        if not cand:
            oh.append(np.nan), lat.append(np.nan), ot.append(pd.NaT)
            continue
        rc = cand[0]
        if rc["record_id"] not in cache:
            cache[rc["record_id"]] = episodes_of(rc["state"], SLEEP_MIN_S)
        eps = cache[rc["record_id"]]
        if not eps:
            oh.append(np.nan), lat.append(np.nan), ot.append(pd.NaT)
            continue
        t_on = rc["start"] + pd.Timedelta(seconds=eps[0][0])
        oh.append(_hour(t_on)), lat.append((t_on - ge).total_seconds() / 60), ot.append(t_on)
    Wn["onset_h"], Wn["onset_latency_min"], Wn["onset_time"] = oh, lat, ot
    return Wn


def fit_pay(Wn: pd.DataFrame, sets=D1_SETS, min_rat: int = MIN_RAT_WIN) -> tuple[pd.DataFrame, pd.DataFrame]:
    """pay ~ predictors + animal FE, SEs clustered by the block of window A (sleep_explore.ols), raw and day-demeaned
    (every variable minus its mean over the windows of the same calendar day). Per-animal slopes: simple (y on the first
    predictor; rats with >= min_rat windows; the plan's rats rule) and partial (all predictors; >= 4 + k windows)."""
    Wn = _add_pay(Wn)
    rows, pa = [], []
    for bh in sorted(Wn.B_h.unique()):
        g = Wn[Wn.B_h == bh]
        for y, xs in sets:
            for dm in (False, True):
                d = g[[y] + xs + ["animal", "A_block", "cal_day"]].dropna().copy()
                r = {"B_h": int(bh), "outcome": y, "predictors": " + ".join(xs), "day_demeaned": dm, "n_windows": len(d),
                     "animals_with_windows": int(d.animal.nunique()), "clusters": int(d.A_block.nunique())}
                if dm and len(d):
                    for c in [y] + xs:
                        d[c] = d[c] - d.groupby("cal_day")[c].transform("mean")
                if len(d) >= MIN_WIN:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        f = ols(d[y], d[xs], groups=d.A_block, fe=d.animal)
                    t = term(f, xs[0])
                    r.update(slope=t["coef"], se=t["se"], ci_lo=t["ci_lo"], ci_hi=t["ci_hi"], p=t["p"])
                    for x2 in xs[1:]:
                        t2 = term(f, x2)
                        r[f"coef_{x2}"], r[f"p_{x2}"] = t2["coef"], t2["p"]
                ss, sp = [], []
                for an, ga in d.groupby("animal"):
                    row = {"B_h": int(bh), "outcome": y, "predictors": " + ".join(xs), "day_demeaned": dm, "animal": an, "n_windows": len(ga)}
                    if len(ga) >= min_rat and ga[xs[0]].std() > 0:
                        row["simple_slope"] = float(np.polyfit(ga[xs[0]], ga[y], 1)[0])
                        ss.append(np.sign(row["simple_slope"]))
                    if len(ga) >= 4 + len(xs) and all(ga[c].std() > 0 for c in xs):
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore")
                            row["partial_slope"] = term(ols(ga[y], ga[xs]), xs[0])["coef"]
                        sp.append(np.sign(row["partial_slope"]))
                    pa.append(row)
                r.update(rats_qualifying=len(ss), rats_positive=int(np.sum(np.array(ss) > 0)),
                         rats_partial=len(sp), rats_partial_positive=int(np.sum(np.array(sp) > 0)),
                         mean_x=float(g[xs[0]].mean()) if len(g) else np.nan, mean_y=float(g[y].mean()) if len(g) else np.nan)
                rows.append(r)
    return pd.DataFrame(rows), pd.DataFrame(pa)


def d1_rule(r: pd.Series | dict) -> tuple[str, str]:
    """Plan D1 rule on one model row: slope > 0.2, p < 0.05, >= 4 rats with >= 3 windows and all of them positive.
    Inconclusive when the data cannot carry the test (< 10 windows or < 4 qualifying rats)."""
    n, k = int(r.get("n_windows", 0)), int(r.get("rats_qualifying", 0))
    if n < MIN_WIN or k < 4 or not np.isfinite(r.get("slope", np.nan)):
        return "INCONCLUSIVE", f"{n} windows, {k} rats with >= {MIN_RAT_WIN} windows (needs >= {MIN_WIN} and >= 4)"
    s_ok, p_ok, rat_ok = r["slope"] > 0.2, r["p"] < 0.05, int(r["rats_positive"]) == k
    why = (f"slope {r['slope']:+.3f} ({'>' if s_ok else '<='} 0.2), p {r['p']:.4f} ({'<' if p_ok else '>='} 0.05), "
           f"rats positive {int(r['rats_positive'])}/{k} ({'all' if rat_ok else 'not all'})")
    return ("MET" if s_ok and p_ok and rat_ok else "NOT MET"), why


def dawn_payback_from_records(recs: list[dict], gaps: pd.DataFrame, label: str, *, bins=None, engine: str = "numpy",
                              return_windows: bool = False):
    """The D1 measurement on the given records (phase x day baselines): fit_pay's model table for the natural dawn wakes,
    with `label` in front. return_windows=True also returns the window table."""
    B, _ = bins if bins is not None else baseline_bins(recs, "phase_x_day", engine)
    Wd = dawn_windows(recs, B, gaps)
    T = fit_pay(Wd)[0] if len(Wd) else pd.DataFrame()
    T.insert(0, "label", label)
    return (T, Wd) if return_windows else T


# ================================================================== Step D1 driver + report
DEFINITIONS = [
    "## Definitions", "",
    r"Time is field-PC local time. States per second: $s_t \in \{0\ \text{unknown}, 1\ \text{WAKE}, 3\ \text{NREM}, 5\ \text{REM}\}$. "
    r"Animals $a$; blocks $k$ = day-half blocks of `sleep_cycles_v2.build_records` (record start 06–18 h → D, else N).",
    "",
    r"- **Record.** Sessions of an animal joined across splits ≤ 60 s (unknown seconds in between); FINAL exclusions and the "
    r"cut at 2026-09-11 19:40 (`sleep_schedule.included_sessions`). Same session set under both scorings.",
    r"- **Scorings.** FINAL = `states_1s_final`; pass2med = `states_1s_pass2med` (`pass2med_remclean`, fixed per-animal "
    r"thresholds), the scoring claim #10 is scoped to (plan section 1: the two sides of a round or a wake are compared "
    r"against different parts of the record).",
    r"- **Bout.** A maximal run of one state value, $[a, b)$ in seconds of the record; length $d = b - a$.",
    r"- **Dark.** $\text{dark}(t) = \neg[\text{sunrise}(t) \le t < \text{sunset}(t)]$, NOAA times at the field site "
    r"(`sleep_quant.sun_times`).",
    r"- **Harmonics.** $(\sin, \cos)(2\pi j h / 24)$, $j = 1, 2$, $h$ = clock hour (decimal).",
    "",
    "### Shared by the three measurements",
    r"- **10-min bins** (`sleep_schedule_phase2.bins10`). Bin $i$ of a record covers its seconds $[600i, 600i + 600)$ (the "
    r"trailing < 10 min is not binned): $\text{rec}_i$ = known seconds, $\text{REM}_i$, $\text{NREM}_i$ = seconds in the state, "
    r"$\text{on}_i$ = REM onsets (a REM second whose predecessor in the bin is a known non-REM second). REM bouts whose "
    r"neighbours are known give the durations $\text{dur}_j$.",
    r"- **Baselines, phase × day** (plan section 3; `sleep_explore.baselines_d`). Leave-one-block-out (bins of block $k$ are "
    r"predicted from a fit on all other blocks): $\text{logit}\,\pi^{X}_i = x_i^\top\beta_X$ for $X \in \{\text{REM}, \text{NREM}\}$, "
    r"binomial on the share $X_i/\text{rec}_i$ with weights $\text{rec}_i$; $\ln E[\text{on}_i] = x_i^\top\beta_o + \ln(\text{rec}_i/600)$ "
    r"(Poisson); $\ln \text{dur}_j = x_j^\top\beta_d + \varepsilon_j$ (OLS, smearing factor $\overline{e^{\hat\varepsilon}}$). "
    r"$x = [1, \text{harmonics}, \text{day}, \text{dark}, \text{dark} \times \text{day}, \text{animal dummies}]$, day = days since "
    r"2026-08-30 19:00, dark at the bin midpoint (bout onset for durations). Expected: $E[X_i] = \text{rec}_i\,\hat\pi^X_i$, "
    r"$E[\text{on}_i]$, $E[\text{dur}]_i$. **Common day** (Phase 2, `phase2.baselines`): the same without dark and dark × day.",
    r"- **Engine.** `numpy` = the same GLMs by iteratively reweighted least squares in numpy (started as statsmodels, "
    r"converged on the coefficients to $10^{-10}$); `statsmodels` = the original functions. Their equality is checked below.",
    r"- **Debt and payback** (min; s for durations). For a pair of windows (A before, B after): "
    r"$\text{debt}_{REM} = \sum_A E[\text{REM}] - \sum_A \text{REM}$, $\text{pay}_{REM} = \sum_B \text{REM} - \sum_B E[\text{REM}]$; "
    r"the same for NREM; $\text{pay}_n$ = REM onsets in B minus expected; $\text{pay}_{dur}$ = mean REM bout duration in B "
    r"minus the onset-weighted expected duration. A positive slope of pay on debt = more REM after a larger shortfall.",
    r"- **Pay models.** OLS $\text{pay}_w = \alpha_{a(w)} + \beta\,\text{debt}_w [+ \gamma\,\text{debt}_{NREM,w} + \delta\,\text{onset}_w] "
    r"+ \varepsilon_w$ with animal fixed effects $\alpha_a$, SEs clustered by the block of window A (`sleep_explore.ols`; HC1 if "
    r"clustering fails), 95 % CI $= \hat\beta \pm 1.96\,\widehat{se}$. **Day-demeaned**: every variable minus its mean over the "
    r"windows of the same calendar day (round: gap-start date; dawn wake: wake-start date) before the fit. Fits need ≥ 10 "
    r"windows.",
    "",
    "### `payback_from_records` (= Step A's A4)",
    r"- **Round windows** (`phase2.comp_windows`, across-gap branch). For each usable Phase-0 gap $[g_s, g_e)$ (≤ 180 min, "
    r"≥ 1 h recorded on both sides) with cause `round_logged` / `round_inferred`: A = $[g_s - 3\,\text{h}, g_s)$, B = "
    r"$[g_e, g_e + h)$, $h \in \{1, 3\}$ h; a window sums the animal's bins whose start $t$ satisfies $t_0 \le t \le t_1 - 1$ s "
    r"(any record) and is kept if $\sum \text{rec} \ge 0.8\,(t_1 - t_0)$. Kind = the gap's Phase-0 kind (morning: gap start "
    r"05:00–11:00; evening: 15:30–21:30). Outcomes: pay_rem, pay_rem_n, pay_rem_dur on debt_rem; pay_rem on debt_rem + "
    r"debt_nrem; pay_nrem on debt_nrem; raw and day-demeaned (`sleep_explore.pay_models`). Per-animal signs: per-animal OLS "
    r"with all the model's predictors, animals with ≥ 4 + k windows.",
    "",
    "### `budget_from_records` (= plan Step E vi)",
    r"- **Periods.** Night of day $d$ = $[\text{sunset}_d, \text{sunrise}_{d+1})$, the following day = $[\text{sunrise}_{d+1}, "
    r"\text{sunset}_{d+1})$; a period sums the animal's bins whose start lies in it (as Phase 3b). Coverage = recorded s / "
    r"period s. Deviation rate $\text{dev}^X = (\sum X - \sum E[X]) / \max(\sum \text{rec}, 1) \times 60$ (min per recorded "
    r"hour), $X \in$ {REM, NREM}. Animal-nights kept with coverage ≥ 0.5 in both periods.",
    r"- **Models** for $y = \text{dev}^X_{day}$, $x = \text{dev}^X_{night}$: (1) within animal $y_{a,d} = \alpha_a + \beta x_{a,d} + "
    r"\varepsilon$, SEs clustered by night; (2) + a linear experiment-day term, SEs clustered by night; (3) + night fixed "
    r"effects $\mu_d$ (model-based SEs, as `check_drift.py`). A negative $\beta$ = a night with more than expected is "
    r"followed by a day with less. Per-animal: simple slope of $y$ on $x$ (≥ 4 nights; for (3) on night-demeaned $x, y$). "
    r"Drift: $\text{dev} = \alpha_a + \beta\,\text{day} + \varepsilon$ for each period, clustered by night.",
    "",
    "### D1: natural dawn wakes",
    r"- **Dawn wake.** A WAKE bout $[a, b)$ with $b - a \ge 1800$ s whose end clock hour is in $[5, 9)$ (plan D1, "
    r"05:00–09:00), **inside a record**: $a > 0$, $s_{a-1} \ne 0$, $b < n$, $s_b \ne 0$ (known on both sides). **Natural**: "
    r"no Phase-0 gap of the same animal with cause `round_logged`, `round_inferred` or `probe_move` (handling) overlapping "
    r"$[t_a - 3\,\text{h}, t_a)$, i.e. $g_e > t_a - 3$ h and $g_s < t_a$.",
    r"- **Dawn windows (exact seconds).** A = $[a - 10800, a)$, B = $[b, b + 3600h)$, $h \in \{1, 3\}$, in seconds of the wake's "
    r"record (seconds outside the record are unrecorded); kept if ≥ 80 % of the window is recorded. Observed = seconds in the "
    r"state; expected $= \sum_{t \in \text{window}, s_t \ne 0} \hat\pi_{i(t)}$ with $\hat\pi_i = E[X_i]/\text{rec}_i$ of the "
    r"second's bin $i(t)$ (bins with nothing recorded and the trailing < 10 min take the neighbouring bin's rate); onsets "
    r"counted at seconds whose predecessor is also in the window; expected onsets $\sum \hat r_{i(t)}$ ($\hat r_i = "
    r"E[\text{on}_i]/\text{rec}_i$); expected duration $\sum \hat r\,\widehat{\text{dur}} / \sum \hat r$. Block = the record's block.",
    r"- **Main-sleep onset.** The first Watson SLEEP episode (no WAKE bout > 120 s and no unknown epoch inside, trimmed to "
    r"its first and last sleep second, ≥ 20 min; `phase3.episodes_of`) that starts at or after the wake end $b$; "
    r"$\text{onset}_h$ = its start in decimal clock hours, latency $= (\text{start} - b)/60$ min. Round windows: the first SLEEP "
    r"episode of the record that starts at the gap end (record start within 5 s of $g_e$); latency from $g_e$. Windows "
    r"without an onset in the record are dropped from the models that use it.",
    r"- **D1 model (plan).** $\text{pay}_{REM} = \alpha_a + \beta\,\text{debt}_{REM} + \gamma\,\text{debt}_{NREM} + "
    r"\delta\,\text{onset}_h + \varepsilon$, SEs clustered by block; primary = day-demeaned; also without the covariates, "
    r"and raw. Per-animal: the **simple** slope of $\text{pay}_{REM}$ on $\text{debt}_{REM}$ (rats with ≥ 3 windows; the plan's "
    r"rats rule) on the same (day-demeaned) data; the **partial** slope with all predictors for rats with ≥ 7 windows "
    r"(reported only).",
    r"- **D1 pass rule (plan, quoted):** \"D1 slope > 0.2 with p < 0.05 and ≥ 4/4 rats with windows\" — operationalised "
    r"(task): $\hat\beta > 0.2$, $p < 0.05$, at least 4 rats with ≥ 3 windows and all of them with a positive per-animal "
    r"slope; per horizon (1 h, 3 h; A4 required both). **Inconclusive** when the horizon has < 10 windows or < 4 rats with "
    r"≥ 3 windows. The verdict is on pass2med; FINAL is reported.",
    r"- **Sensitivity: A includes the wake.** A = $[b - 10800, b)$ (the wake and the time before it), so the REM missed during "
    r"the wake counts as debt (not in the rule).",
    r"- **Sensitivity: 10-min-bin windows.** The same wakes with the round-window rule above (bins of the animal whose start "
    r"lies in $[t_0, t_1 - 1\,\text{s}]$, any record, ≥ 80 % recorded) instead of exact seconds (not in the rule). "
    r"Agreement = Pearson $r$ of debt and of payback between the two window versions over the same wakes.",
    r"- **Debt spread (power).** $\text{SD}$ over windows of $\text{debt}_{REM}$ and of the day-demeaned $\text{debt}_{REM}$ "
    r"(min); with the same residual noise, the slope's SE scales as $1/\text{SD}$.",
    r"- **role** (verdict table). `D1 verdict` = the dawn rows on pass2med; `D1, reported` = FINAL; `comparison` = D1's rule "
    r"applied to the morning round windows (A4's own rule had no per-rat condition); `sensitivity` = not in the rule.",
    "",
]


def _fmt(r, nd: int = 3) -> str:
    try:
        return f"{r['slope']:+.{nd}f} [{r['ci_lo']:+.{nd}f}, {r['ci_hi']:+.{nd}f}], p {r['p']:.4f}" if np.isfinite(r["slope"]) else "n/a"
    except (KeyError, TypeError):
        return "n/a"


def _median_time(fn, k: int = 3) -> float:
    ts = []
    for _ in range(k):
        t0 = time.time()
        fn()
        ts.append(time.time() - t0)
    return float(np.median(ts))


def _overall(st: dict) -> str:
    v = list(st.values())
    if all(x == "MET" for x in v):
        return "MET"
    if "NOT MET" in v:
        return "NOT MET"
    if all(x == "INCONCLUSIVE" for x in v):
        return "INCONCLUSIVE"
    return "INCONCLUSIVE (" + ", ".join(f"{k} h {x.lower()}" for k, x in st.items()) + ")"


def stepD1(a) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from _common import git_commit, write_json
    from output_paths import figure_dir, report_dir, run_dir
    from sleep_quant import save_fig
    out = run_dir("sleep_explore_D1", "2026c")
    rd, fd = report_dir("2026c", "ephys_spikes"), figure_dir("2026c", "ephys_spikes")
    gc = git_commit()
    t_all = time.time()
    gaps_path = Path(json.load(open(P0_MANIFEST))["run_dir"]) / "gaps.csv"
    gaps = pd.read_csv(gaps_path, parse_dates=["gap_start", "gap_end"])
    a_run = Path(json.load(open(A_MANIFEST))["run_dir"])
    p3b_run = Path(json.load(open(P3B_MANIFEST))["run_dir"])
    A4 = pd.read_csv(A4_CSV)
    labs = list(dict.fromkeys(a.scorings))
    prim_lab = "pass2med" if "pass2med" in labs else labs[0]
    REP, WREP, BREP, BUDR, RT, FUN, MODS, PAS, DESC, VER = [], [], [], [], [], [], [], [], [], []
    budget_all, plot, key_a4, corr_bins, dawn_info = [], {}, {}, {}, {}
    keys = ["kind", "B_h", "outcome", "predictors", "day_demeaned"]
    for lab in labs:
        sdir = SCORINGS[lab]
        t0 = time.time()
        recs = build_records(included_sessions(REVIEW, sdir), sdir)
        t_load = time.time() - t0
        print(f"{lab}: {len(recs)} records, {sum(len(r['state']) for r in recs) / 3600:.0f} h ({t_load:.1f} s)", flush=True)
        bins = baseline_bins(recs)
        # ---------------- runtime per call
        for fname, mode, fn, k in (
                ("baseline_bins (phase x day)", "-", lambda: baseline_bins(recs), 3),
                ("payback_from_records", "cold (bins + baselines inside)", lambda: payback_from_records(recs, gaps, lab), 3),
                ("payback_from_records", "warm (bins= passed)", lambda: payback_from_records(recs, gaps, lab, bins=bins), 3),
                ("budget_from_records", "cold (bins + baselines inside)", lambda: budget_from_records(recs, lab), 3),
                ("budget_from_records", "warm (bins= passed)", lambda: budget_from_records(recs, lab, bins=bins), 3),
                ("dawn_payback_from_records", "warm (bins= passed)", lambda: dawn_payback_from_records(recs, gaps, lab, bins=bins), 3),
                ("payback_from_records, engine='statsmodels'", "cold (bins + baselines inside)",
                 lambda: payback_from_records(recs, gaps, lab, engine="statsmodels"), 1)):
            RT.append({"scores": lab, "function": fname, "mode": mode, "calls": k, "median_s": round(_median_time(fn, k), 2)})
            print(f"   {fname} [{mode}]: {RT[-1]['median_s']} s", flush=True)
        # ---------------- reproduction of A4
        T, Wn = payback_from_records(recs, gaps, lab, bins=bins, return_windows=True)
        key_a4[lab] = T[(T.kind == "morning") & (T.outcome == "pay_rem") & (T.predictors == "debt_rem") & T.day_demeaned].sort_values("B_h")
        Ts = payback_from_records(recs, gaps, lab, engine="statsmodels")
        Tc = payback_from_records(recs, gaps, lab, baseline="common_day")
        for name, TT, bl in (("numpy engine, phase x day", T, "phase"), ("statsmodels engine, phase x day", Ts, "phase"),
                             ("numpy engine, common day", Tc, "common")):
            ref = A4[(A4.scores == lab) & A4.baseline.str.startswith(bl)]
            m = ref.merge(TT, on=keys, suffixes=("_A4", ""))
            REP.append({"scores": lab, "this": name, "A4_baseline": ref.baseline.iloc[0], "rows_A4": len(ref), "rows_this": len(TT),
                        "rows_matched": len(m), "max_abs_d_slope": float(np.nanmax(np.abs(m.slope - m.slope_A4))),
                        "max_abs_d_ci": float(np.nanmax(np.abs(np.r_[m.ci_lo - m.ci_lo_A4, m.ci_hi - m.ci_hi_A4]))),
                        "max_abs_d_p": float(np.nanmax(np.abs(m.p - m.p_A4))),
                        "n_windows_equal": bool((m.n_windows == m.n_windows_A4).all()),
                        "animal_signs_equal": bool(((m.animals_positive == m.animals_positive_A4) & (m.animals == m.animals_A4)).all())})
        Wa = pd.read_csv(a_run / f"a4_windows_{lab}_phasexday.csv.gz", parse_dates=["t_A"])
        Wm = Wn.sort_values(["animal", "t_A", "B_h"]).reset_index(drop=True)
        Wa = Wa.sort_values(["animal", "t_A", "B_h"]).reset_index(drop=True)
        num = [c for c in Wa.columns if c.startswith(("A_", "B_")) and pd.api.types.is_numeric_dtype(Wa[c]) and c != "B_h"]
        same = len(Wa) == len(Wm)
        WREP.append({"scores": lab, "windows_A4_run": len(Wa), "windows_this": len(Wm),
                     "max_abs_diff_window_sums": float(np.nanmax(np.abs(Wm[num].to_numpy(float) - Wa[num].to_numpy(float)))) if same else np.nan,
                     "blocks_and_kinds_equal": bool(same and (Wm.A_block.to_numpy() == Wa.A_block.to_numpy()).all()
                                                    and (Wm.kind.to_numpy() == Wa.kind.to_numpy()).all())})
        Wn.to_csv(out / f"payback_windows_{lab}.csv.gz", index=False)
        # ---------------- budget: reproduction of #13 (common day = Phase 3b) and the plan's phase x day
        Bp, Dp = budget_from_records(recs, lab, bins=bins, return_days=True)
        Bc, Dc = budget_from_records(recs, lab, baseline="common_day", return_days=True)
        Dp.to_csv(out / f"budget_days_{lab}_phasexday.csv", index=False)
        Dc.to_csv(out / f"budget_days_{lab}_commonday.csv", index=False)
        budget_all += [Bp, Bc]
        p3 = pd.read_csv(p3b_run / f"budget_days_{'pass2med_remclean' if lab == 'pass2med' else 'FINAL'}.csv", parse_dates=["night_of"])
        mm = p3.merge(Dc, on=["animal", "night_of"], suffixes=("_p3b", ""))
        cols = [c for c in p3.columns if c.endswith(("_cov", "_dev_min", "_rate_dev"))]
        BREP.append({"scores": lab, "animal_nights_phase3b": len(p3), "matched": len(mm),
                     "max_abs_diff": float(max(np.nanmax(np.abs(mm[c] - mm[f"{c}_p3b"])) for c in cols))})
        for q in ("NREM", "REM"):
            for i, mdl in enumerate(BUDGET_MODELS):
                rc_ = Bc[(Bc.quantity == q) & (Bc.model == mdl)].iloc[0]
                rp_ = Bp[(Bp.quantity == q) & (Bp.model == mdl)].iloc[0]
                BUDR.append({"scores": lab, "quantity": q, "model": mdl, "check_drift (logic audit)": CHECK_DRIFT[(lab, q)][i],
                             "this, common day": round(float(rc_.slope), 3), "common day CI": f"[{rc_.ci_lo:+.2f}, {rc_.ci_hi:+.2f}]",
                             "this, phase x day (default)": round(float(rp_.slope), 3), "phase x day CI": f"[{rp_.ci_lo:+.2f}, {rp_.ci_hi:+.2f}]",
                             "phase x day p": round(float(rp_.p), 4), "n animal-nights": int(rp_.n_animal_days)})
        # ---------------- D1
        B, RB = bins
        Dw = dawn_wakes(recs, gaps)
        Dw.to_csv(out / f"dawn_wakes_{lab}.csv", index=False)
        stats = {}
        Wd = dawn_windows(recs, B, gaps, wakes=Dw, stats=stats)
        Wi = dawn_windows(recs, B, gaps, include_wake=True, wakes=Dw)
        Wb = dawn_windows_bins(Wd, B, RB)
        Wr = round_onsets(Wn[Wn.kind == "morning"], recs)
        for nm, W_ in (("dawn", Wd), ("dawn_incl_wake", Wi), ("dawn_bins", Wb), ("morning_rounds", Wr)):
            W_.to_csv(out / f"windows_{nm}_{lab}.csv.gz", index=False)
        if lab == prim_lab:
            from sleep_quant import sun_times
            u = Wd.drop_duplicates(["animal", "wake_start"])
            hm = lambda t: f"{t:%H:%M}"  # noqa: E731
            srs = [pd.Timestamp(sun_times(t.date())[0]) for t in u.wake_end]
            dawn_info.update(d_med=u.d_min.median(), d_min=u.d_min.min(), d_max=u.d_min.max(),
                             s_lo=hm(min(u.wake_start, key=_hour)), s_hi=hm(max(u.wake_start, key=_hour)),
                             s_med=f"{int(u.wake_start.map(_hour).median()):02d}:{int(u.wake_start.map(_hour).median() % 1 * 60):02d}",
                             e_lo=hm(min(u.wake_end, key=_hour)), e_hi=hm(max(u.wake_end, key=_hour)),
                             e_med=f"{int(u.end_h.median()):02d}:{int(u.end_h.median() % 1 * 60):02d}",
                             sr_lo=hm(min(srs, key=_hour)), sr_hi=hm(max(srs, key=_hour)))
        cb = _add_pay(Wd[Wd.B_h == 1]).merge(_add_pay(Wb[Wb.B_h == 1]), on=["animal", "wake_start"], suffixes=("", "_bin"))
        corr_bins[lab] = (float(np.corrcoef(cb.debt_rem, cb.debt_rem_bin)[0, 1]), float(np.corrcoef(cb.pay_rem, cb.pay_rem_bin)[0, 1]))
        n_w30 = sum(1 for rc in recs for s, a_, b_ in bouts(rc["state"]) if s == W and b_ - a_ >= DAWN_MIN_S)
        FUN.append({"scores": lab, "WAKE bouts >= 30 min": n_w30, "ending 05:00-09:00": len(Dw), "inside a record": int(Dw.inside.sum()),
                    "no round within 3 h": int((Dw.inside & ~Dw.round_3h).sum()), "and no probe move (natural)": int(Dw.natural.sum()),
                    "A >= 80 % recorded": stats.get("A_ok", 0), "B 1 h >= 80 %": stats.get("B1_ok", 0), "B 3 h >= 80 %": stats.get("B3_ok", 0),
                    "main-sleep onset found": stats.get("onset_found", 0)})
        sets = (("dawn wakes", Wd), ("morning rounds", Wr), ("dawn wakes, A includes the wake (sensitivity)", Wi),
                ("dawn wakes, 10-min-bin windows (sensitivity)", Wb))
        for setname, W_ in sets:
            if not len(W_):
                continue
            M, P = fit_pay(W_)
            M.insert(0, "windows", setname)
            M.insert(0, "scores", lab)
            P.insert(0, "windows", setname)
            P.insert(0, "scores", lab)
            MODS.append(M)
            PAS.append(P)
            Wx = _add_pay(W_)
            Wx["debt_rem_dm"] = Wx.debt_rem - Wx.groupby(["B_h", "cal_day"]).debt_rem.transform("mean")
            for bh, g in Wx.groupby("B_h"):
                DESC.append({"scores": lab, "windows": setname, "B_h": int(bh), "n": len(g), "animals": g.animal.nunique(),
                             "sd_debt_rem": float(g.debt_rem.std()), "sd_debt_rem_day_demeaned": float(g.debt_rem_dm.std()),
                             "per animal": ", ".join(f"{k} {v}" for k, v in g.animal.value_counts().sort_index().items()),
                             "median_wake_min": float(g.d_min.median()) if "d_min" in g else np.nan,
                             "median_end_or_gap_end_h": float(g.end_h.median()) if "end_h" in g else float(g.gap_end.map(_hour).median()),
                             "onset_found": int(g.onset_h.notna().sum()), "median_onset_h": float(g.onset_h.median()),
                             "median_onset_latency_min": float(g.onset_latency_min.median()),
                             "mean_debt_rem": float(g.debt_rem.mean()), "mean_pay_rem": float(g.pay_rem.mean()),
                             "mean_debt_nrem": float(g.debt_nrem.mean()), "mean_A_rem_min": float(g.A_rem_min.mean()),
                             "mean_A_e_rem_min": float(g.A_e_rem_min.mean())})
            for bh in (1, 3):
                row = M[(M.B_h == bh) & (M.outcome == PRIMARY[0]) & (M.predictors == PRIMARY[1]) & M.day_demeaned]
                r_ = row.iloc[0].to_dict() if len(row) else {"n_windows": 0, "rats_qualifying": 0}
                v, why = d1_rule(r_)
                role = ("D1 verdict" if lab == prim_lab else "D1, reported") if setname == "dawn wakes" else \
                    ("comparison (D1 rule applied to rounds)" if setname == "morning rounds" else "sensitivity")
                VER.append({"scores": lab, "windows": setname, "role": role, "B_h": bh, "rule": v, "detail": why, "slope": r_.get("slope", np.nan),
                            "ci_lo": r_.get("ci_lo", np.nan), "ci_hi": r_.get("ci_hi", np.nan), "p": r_.get("p", np.nan),
                            "n_windows": int(r_.get("n_windows", 0)), "rats_qualifying": int(r_.get("rats_qualifying", 0)),
                            "rats_positive": int(r_.get("rats_positive", 0)) if np.isfinite(r_.get("rats_positive", np.nan)) else 0})
        for setname, W_ in sets[:2]:
            Wx = _add_pay(W_[W_.B_h == 1]).dropna(subset=["pay_rem", "debt_rem", "debt_nrem", "onset_h"])
            if len(Wx):
                for c in ("pay_rem", "debt_rem"):
                    Wx[c + "_dm"] = Wx[c] - Wx.groupby("cal_day")[c].transform("mean")
            plot[(lab, setname)] = Wx
        print(f"   D1 {lab}: natural dawn wakes {int(Dw.natural.sum())}, windows 1 h {int((Wd.B_h == 1).sum()) if len(Wd) else 0}, "
              f"3 h {int((Wd.B_h == 3).sum()) if len(Wd) else 0}", flush=True)
    MOD, PA, VT = pd.concat(MODS, ignore_index=True), pd.concat(PAS, ignore_index=True), pd.DataFrame(VER)
    BUD = pd.concat(budget_all, ignore_index=True)
    outs = {"models": MOD, "per_animal": PA, "verdicts": VT, "funnel": pd.DataFrame(FUN), "descriptives": pd.DataFrame(DESC),
            "repro_payback": pd.DataFrame(REP), "repro_windows": pd.DataFrame(WREP), "repro_budget_days": pd.DataFrame(BREP),
            "repro_budget": pd.DataFrame(BUDR), "budget": BUD, "runtime": pd.DataFrame(RT)}
    for nm, df in outs.items():
        df.to_csv(rd / f"ephys_spikes_sleep_explore_D1_{nm}_2026c.csv", index=False)

    # ---------------- figure: day-demeaned pay vs debt, 1 h, dawn wakes vs morning rounds
    fig, axs = plt.subplots(len(labs), 2, figsize=(10, 3.9 * len(labs)), squeeze=False, sharex="col")
    for i, lab in enumerate(labs):
        for j, setname in enumerate(("dawn wakes", "morning rounds")):
            ax = axs[i, j]
            Wx = plot.get((lab, setname), pd.DataFrame())
            if len(Wx):
                ax.scatter(Wx.debt_rem_dm, Wx.pay_rem_dm, s=22, color=COLORS["ink"], alpha=0.75, linewidths=0)
                if Wx.debt_rem_dm.std() > 0:
                    k_, c_ = np.polyfit(Wx.debt_rem_dm, Wx.pay_rem_dm, 1)
                    xx = np.linspace(Wx.debt_rem_dm.min(), Wx.debt_rem_dm.max(), 20)
                    ax.plot(xx, k_ * xx + c_, color=COLORS["dark"], lw=2)
            r_ = VT[(VT.scores == lab) & (VT.windows == setname) & (VT.B_h == 1)]
            ttl = f"{lab}, {setname}, B = 1 h"
            if len(r_) and np.isfinite(r_.slope.iloc[0]):
                ttl += f"\nprimary slope {r_.slope.iloc[0]:+.2f} [{r_.ci_lo.iloc[0]:+.2f}, {r_.ci_hi.iloc[0]:+.2f}], n {r_.n_windows.iloc[0]}"
            ax.set_title(ttl, fontsize=9, color=COLORS["ink"])
            ax.axhline(0, color=COLORS["ink"], lw=0.6, alpha=0.5)
            ax.axvline(0, color=COLORS["ink"], lw=0.6, alpha=0.5)
            ax.spines[["top", "right"]].set_visible(False)
            if i == len(labs) - 1:
                ax.set_xlabel("REM debt in A (min, day-demeaned)")
            if j == 0:
                ax.set_ylabel("REM payback in B (min, day-demeaned)")
    fig.tight_layout()
    fig_name = "ephys_spikes_sleep_explore_D1_payback_2026c.png"
    save_fig(fig, fd / fig_name)
    plt.close(fig)

    # ---------------- verdict text
    st = {bh: VT[(VT.scores == prim_lab) & (VT.windows == "dawn wakes") & (VT.B_h == bh)].rule.iloc[0] for bh in (1, 3)}
    verdict = _overall(st)
    vlines = []
    for lab in labs:
        for setname in ("dawn wakes", "morning rounds"):
            for bh in (1, 3):
                r_ = VT[(VT.scores == lab) & (VT.windows == setname) & (VT.B_h == bh)]
                if not len(r_):
                    continue
                r_ = r_.iloc[0]
                vlines.append(f"- **{lab}, {setname}, B = {bh} h:** primary slope "
                              f"{_fmt(r_.to_dict())}, n {r_.n_windows} windows, rats with ≥ 3 windows {r_.rats_qualifying} "
                              f"(positive {r_.rats_positive}) → **{r_.rule}** ({r_.detail}).")
    rp = pd.DataFrame(REP)
    rb = pd.DataFrame(BUDR)
    rt = pd.DataFrame(RT)
    t_total = time.time() - t_all

    def mrow(lab, setname, bh, pred, dm, y="pay_rem"):
        m_ = MOD[(MOD.scores == lab) & (MOD.windows == setname) & (MOD.B_h == bh) & (MOD.outcome == y) & (MOD.predictors == pred)
                 & (MOD.day_demeaned == dm)]
        return m_.iloc[0].to_dict() if len(m_) else {}
    show_cols = ["scores", "windows", "B_h", "outcome", "predictors", "day_demeaned", "n_windows", "animals_with_windows", "clusters",
                 "slope", "ci_lo", "ci_hi", "p", "coef_debt_nrem", "p_debt_nrem", "coef_onset_h", "p_onset_h", "rats_qualifying",
                 "rats_positive", "rats_partial", "rats_partial_positive"]
    show_cols = [c for c in show_cols if c in MOD]
    pa_show = PA[(PA.outcome == PRIMARY[0]) & (PA.predictors == PRIMARY[1]) & PA.day_demeaned & PA.windows.isin(["dawn wakes", "morning rounds"])]
    pa_show = pa_show[["scores", "windows", "B_h", "animal", "n_windows"] + [c for c in ("simple_slope", "partial_slope") if c in pa_show]]
    key_p = mrow(prim_lab, "dawn wakes", 1, PRIMARY[1], True)
    key_s = mrow(prim_lab, "dawn wakes", 1, "debt_rem", True)
    key_r = mrow(prim_lab, "morning rounds", 1, PRIMARY[1], True)
    key_r0 = mrow(prim_lab, "morning rounds", 1, "debt_rem", True)
    key_b = mrow(prim_lab, "dawn wakes, 10-min-bin windows (sensitivity)", 1, PRIMARY[1], True)
    key_i = mrow(prim_lab, "dawn wakes, A includes the wake (sensitivity)", 1, PRIMARY[1], True)
    DS = pd.DataFrame(DESC)
    sd_ = lambda w: float(DS[(DS.scores == prim_lab) & (DS.windows == w) & (DS.B_h == 1)].sd_debt_rem_day_demeaned.iloc[0])  # noqa: E731
    ea_ = lambda w: float(DS[(DS.scores == prim_lab) & (DS.windows == w) & (DS.B_h == 1)].mean_A_e_rem_min.iloc[0])  # noqa: E731
    bq = lambda lab, q, m: BUD[(BUD.label == lab) & (BUD.baseline == "phase_x_day") & (BUD.quantity == q) & (BUD.model == m)].iloc[0]  # noqa: E731
    vi_fe = "; ".join(f"{lab} {q} {_fmt(bq(lab, q, 'within animal + day FE').to_dict(), 2)}" for lab in labs for q in ("NREM", "REM"))
    vi_ld = "; ".join(f"{lab} {q} {_fmt(bq(lab, q, 'within animal + linear day').to_dict(), 2)}" for lab in labs for q in ("NREM", "REM"))
    hdr = ["# Sleep behaviour explore — Step D1: natural dawn wakes, and the two measurement functions (cohort 2026c)", "",
           f"Plan: [{PLAN}](../../../../{PLAN}) (sections 1, 3, 5 Step D and Step E (vi); the pass rules are the plan's, unchanged). "
           f"Driver `ephys/sleep_explore_d.py stepD1` (commit {gc}); bulk `{out}`; scorings {', '.join(labs)}; runtime "
           f"{t_total / 60:.1f} min. Step A report: [ephys_spikes_sleep_explore_A_2026c.md](ephys_spikes_sleep_explore_A_2026c.md).", "",
           "**Status: Step D1 only.** D1 is the first half of the plan's Step D rule for \"a slow REM deficit exists\" (D1 slope "
           "> 0.2, p < 0.05, ≥ 4/4 rats AND the D2 simulated slope < 0.1); D2 (the step-B model simulated without D) is run by "
           "the main session with `payback_from_records`. Claim statuses change in the claim audit, not here. Inputs: the "
           "scored 1-s states (FINAL, pass2med), NOAA light, the Phase-0 gap table. No LFP features. Everything from "
           "2026-09-11 19:40 is cut.", "",
           "## Verdict", "",
           f"**D1 (natural dawn wakes, pass2med, the plan's rule): {verdict}** — 1 h: {st[1]}; 3 h: {st[3]}.", "",
           f"- Primary model (day-demeaned, pay_rem ~ debt_rem + debt_nrem + onset + animal FE), B = 1 h, {prim_lab}: "
           f"{_fmt(key_p)}, n {key_p.get('n_windows', 0)} windows, {key_p.get('rats_positive', 0)}/{key_p.get('rats_qualifying', 0)} "
           f"rats positive. Without the covariates: {_fmt(key_s)}.",
           f"- The same model on the morning ROUND windows (B = 1 h, {prim_lab}): {_fmt(key_r)} (A4's specification without "
           f"covariates: {_fmt(key_r0)}). The round payback "
           + ("survives" if key_r.get("p", 1) < 0.05 else "does not survive") + " the NREM-debt and main-sleep-onset covariates; "
           "the dawn-wake slope is " + ("significant" if min(key_p.get("p", 1), key_s.get("p", 1)) < 0.05 else
                                        "not significant with or without them") + ".",
           f"- Sensitivities (not in the rule), {prim_lab}, 1 h, primary model: 10-min-bin windows {_fmt(key_b)}; window A "
           f"including the wake {_fmt(key_i)}. Exact-second vs 10-min-bin windows ({prim_lab}, 1 h): debt r = "
           f"{corr_bins[prim_lab][0]:.2f}, payback r = {corr_bins[prim_lab][1]:.2f}.",
           f"- Power caveat: the dawn-wake debts are small. Window A lies in the dark, where 3 h hold only "
           f"{ea_('dawn wakes'):.1f} min of expected REM (rounds {ea_('morning rounds'):.1f} min); the day-demeaned REM debt "
           f"has SD {sd_('dawn wakes'):.2f} min vs {sd_('morning rounds'):.2f} min for the morning rounds. The primary CI "
           + ("excludes" if key_p.get("ci_hi", np.inf) < 0.2 else "does not exclude") + " the 0.2 threshold; the "
           "covariate-free CI " + ("reaches" if key_s.get("ci_hi", -np.inf) >= key_r0.get("slope", np.inf) else "stays below")
           + f" the round slope ({key_r0.get('slope', np.nan):+.2f}).",
           "- `payback_from_records` reproduces A4 exactly on the real data (table below: max |Δ slope| "
           f"{rp[rp.this.str.startswith('numpy engine, phase')].max_abs_d_slope.max():.1e}, every window count and per-animal "
           "sign equal, both scorings, both baselines).",
           "- `budget_from_records` reproduces the #13 drift check: with the Phase-3b (common-day) baselines the per-animal-night "
           f"deviations equal Phase 3b's to {pd.DataFrame(BREP).max_abs_diff.max():.1e} min per recorded h and the slopes equal "
           "`check_drift.py`'s; with the plan's phase × day baselines (the function's default, what Step E (vi) will use) the "
           f"day-FE slope is ≈ 0 for both quantities and scorings ({vi_fe}). **The day term matters for Step E (vi):** with a "
           f"linear day term instead of day fixed effects, NREM stays ≈ 0 but REM is negative ({vi_ld}); apply the same term "
           "to the observed and the simulated records.",
           f"- Runtime per call (this PC, one process): payback {rt[(rt.function == 'payback_from_records') & rt['mode'].str.startswith('cold')].median_s.max():.1f} s "
           f"cold / {rt[(rt.function == 'payback_from_records') & rt['mode'].str.startswith('warm')].median_s.max():.1f} s with `bins=`; "
           f"budget {rt[(rt.function == 'budget_from_records') & rt['mode'].str.startswith('cold')].median_s.max():.1f} s cold / "
           f"{rt[(rt.function == 'budget_from_records') & rt['mode'].str.startswith('warm')].median_s.max():.2f} s with `bins=`; "
           f"`baseline_bins` {rt[rt.function.str.startswith('baseline_bins')].median_s.max():.1f} s.", "",
           "Rule per horizon (the primary model; `role` says which rows decide: the round rows apply D1's rule to the "
           "morning rounds only for comparison — A4's own rule had no per-rat condition and is met on pass2med):", "",
           *tbl(VT[VT.role != "sensitivity"]), ""]
    d1 = ["## D1 — natural dawn wakes", "",
          "**Plan (Step D, D1, quoted):** \"Natural wakes ≥ 30 min ending 05:00–09:00 without a round; the same debt / payback "
          "regression as #10 (fixed thresholds), with NREM debt and the main-sleep onset time as covariates.\" Pass for \"a slow "
          "REM deficit exists\": \"D1 slope > 0.2 with p < 0.05 and ≥ 4/4 rats with windows; and the D2 slope < 0.1.\"", "",
          "### Data", "", "Funnel (counts of wakes; the B columns count wakes with a complete A and B window):", "",
          *tbl(pd.DataFrame(FUN)), "",
          f"The dawn wakes ({prim_lab}, natural, with an A window) are long night wakes: length median {dawn_info['d_med']:.0f} min "
          f"(range {dawn_info['d_min']:.0f}–{dawn_info['d_max']:.0f}); start {dawn_info['s_lo']} – {dawn_info['s_hi']} (median "
          f"{dawn_info['s_med']}); end {dawn_info['e_lo']} – {dawn_info['e_hi']} (median {dawn_info['e_med']}); sunrise on these "
          f"days {dawn_info['sr_lo']} – {dawn_info['sr_hi']}. Window A therefore lies in the dark and B straddles sunrise. The "
          "3-h B windows are cut by the morning battery round (records end at the round), which leaves few complete 3-h windows.", "",
          *tbl(pd.DataFrame(DESC)), "",
          "### Models (dawn windows; the primary row is day-demeaned with both covariates)", "",
          *tbl(MOD[MOD.windows == "dawn wakes"][show_cols]), "",
          "### The morning round windows with the same covariates (comparison)", "",
          *tbl(MOD[MOD.windows == "morning rounds"][show_cols]), "",
          "### Per animal (primary model, day-demeaned; simple = pay_rem on debt_rem, the rats rule; partial = all predictors)", "",
          *tbl(pa_show), "",
          "### Sensitivity: window A includes the wake (not in the rule)", "",
          "A = the 3 h before the wake END, so REM missed during the wake counts as debt (debt then mostly measures the wake's "
          "own expected REM).", "",
          *tbl(MOD[MOD.windows.str.startswith("dawn wakes, A includes")][show_cols]), "",
          "### Sensitivity: 10-min-bin windows (not in the rule)", "",
          "The same wakes with `comp_windows`-style windows (bins aligned to the record start; A may hold up to 10 min of the "
          "wake, B may start up to 10 min late). Against the exact-second windows (1 h): "
          + "; ".join(f"{lab} debt r = {v[0]:.2f}, payback r = {v[1]:.2f}" for lab, v in corr_bins.items()) + ".", "",
          *tbl(MOD[MOD.windows.str.startswith("dawn wakes, 10-min-bin")][show_cols]), "",
          "Sensitivity rules (primary model):", "", *tbl(VT[VT.role == "sensitivity"]), "",
          f"![](../figures/{fig_name})", "",
          "Figure: REM payback in B (1 h) against REM debt in A, both day-demeaned, one dot per window; the line is the simple "
          "least-squares fit for display; the title gives the primary model's slope (with NREM debt and onset, animal FE).", "",
          "### Verdict D1", "", *vlines, "",
          f"**D1 verdict (pass2med; the claim is scoped to fixed thresholds): {verdict}.** FINAL is reported above, not used "
          "for the verdict.", ""]
    rep = ["## Reproduction: the functions measure what Step A and Phase 3b measured", "",
           "### `payback_from_records` = A4", "",
           "The function's table against Step A's A4 CSV (`ephys_spikes_sleep_explore_A_a4_payback_2026c.csv`), matched on "
           "kind × B_h × outcome × predictors × day_demeaned:", "", *tbl(rp, 8), "",
           "Window sums against Step A's saved windows (`a4_windows_<scoring>_phasexday.csv.gz` in the Step A run folder):", "",
           *tbl(pd.DataFrame(WREP), 10), "",
           "Key A4 numbers as returned by `payback_from_records` (morning, pay_rem ~ debt_rem, day-demeaned, phase × day): "
           + "; ".join(f"{lab} {r.B_h} h {r.slope:+.4f} [{r.ci_lo:+.3f}, {r.ci_hi:+.3f}] (p {r.p:.5f}, {r.animals_positive}/{r.animals} "
                       f"rats positive)" for lab in labs for r in key_a4[lab].itertuples())
           + ". Step A reported pass2med +0.34 (1 h) / +0.96 (3 h), p ≤ 1e-4, 5/6; FINAL n.s.", ""]
    rep += ["### `budget_from_records` = the #13 drift check (logic audit, `check_drift.py`)", "",
            "Per-animal-night deviations with the Phase-3b baselines (common linear day) against Phase 3b's "
            "`budget_days_*.csv`:", "", *tbl(pd.DataFrame(BREP), 10), "",
            "NREM / REM slopes of the day deviation on the night deviation (min per recorded h; coverage ≥ 0.5 both): "
            "`check_drift.py`'s numbers, this function with the same (common-day) baselines, and with the plan's phase × day "
            "baselines (the default; Step E (vi)):", "", *tbl(rb), "",
            "All rows of the function's output (both baselines; drift rows included):", "", *tbl(BUD), "",
            "Reading: the common-day rows reproduce the logic audit's numbers to the printed precision. With the phase × day "
            "baselines the night and day drifts are absorbed by the baseline itself (NREM drift rows: "
            + "; ".join(f"{lab} night {bq(lab, 'NREM', 'drift: night deviation').slope:+.2f}, day {bq(lab, 'NREM', 'drift: day deviation').slope:+.2f}"
                        for lab in labs)
            + " min per recorded h per day) and the within-animal NREM slope is already small ("
            + "; ".join(f"{lab} {bq(lab, 'NREM', 'within animal').slope:+.2f}" for lab in labs)
            + "). The within-animal REM slope is not ("
            + "; ".join(f"{lab} {_fmt(bq(lab, 'REM', 'within animal').to_dict(), 2)}" for lab in labs)
            + ") and survives a linear day term; only night fixed effects remove it. With day fixed effects every slope is "
            "≈ 0 — the measurement Step E (vi) compares a no-budget model against.", "",
            "### Runtime per call", "", *tbl(rt), "",
            "`cold` = the call computes the 10-min bins and the leave-one-block-out baselines itself; `warm` = "
            "`bins=baseline_bins(recs)` passed (compute it once per simulated replicate and pass it to both functions).", ""]
    api = ["## The functions (for the main session)", "", "```python",
           "import sys; sys.path.insert(0, 'ephys'); from sleep_explore_d import (baseline_bins, payback_from_records,",
           "                                                                     budget_from_records, dawn_payback_from_records)",
           "bins = baseline_bins(recs)                                   # (B, RB); phase x day baselines; engine='numpy'",
           "T = payback_from_records(recs, gaps, 'rep 17', bins=bins)    # = A4",
           "U = budget_from_records(recs, 'rep 17', bins=bins)           # = Step E (vi)",
           "V = dawn_payback_from_records(recs, gaps, 'rep 17', bins=bins)  # = D1",
           "```", "",
           "- `recs`: list of dicts as `sleep_cycles_v2.build_records` (keys used: animal, start, state, record_id, block); "
           "simulated records keep animals, starts and lengths and replace `state` (int8: 0 unknown, 1 WAKE, 3 NREM, 5 REM). "
           "`gaps`: the Phase-0 gap table (animal, gap_start, gap_end, kind, usable, cause).",
           "- `payback_from_records(recs, gaps, label, *, baseline='phase_x_day', bins=None, engine='numpy', return_windows=False)` "
           "→ columns `label, baseline, kind, B_h, outcome, predictors, day_demeaned, n_windows, clusters, slope, ci_lo, ci_hi, p, "
           "animals_positive, animals, mean_x, mean_y`; the D2 number is the row kind = morning, outcome = pay_rem, predictors "
           "= debt_rem, day_demeaned = True, B_h = 1 and 3.",
           "- `budget_from_records(recs, label, *, baseline='phase_x_day', bins=None, engine='numpy', coverage=0.5, return_days=False)` "
           "→ columns `label, baseline, quantity, model, x, y, n_animal_days, animals, slope, ci_lo, ci_hi, p, animals_negative, "
           "animals_with_slope`; models 'within animal', 'within animal + linear day', 'within animal + day FE', 'drift: night "
           "deviation', 'drift: day deviation'; the (vi) number is quantity = NREM (and REM), model = 'within animal + day FE'.",
           "- `dawn_payback_from_records(recs, gaps, label, *, bins=None, engine='numpy', return_windows=False)` → `label` + "
           "`fit_pay` columns (`B_h, outcome, predictors, day_demeaned, n_windows, animals_with_windows, clusters, slope, se, "
           "ci_lo, ci_hi, p, coef_*, p_*, rats_qualifying, rats_positive, rats_partial, rats_partial_positive, mean_x, mean_y`); "
           "`d1_rule(row)` applies the plan's rule to a row.",
           "- All deterministic; nothing is written or printed; statsmodels warnings are suppressed inside.", ""]
    dev = ["## Deviations from the plan and the task, and notes", "",
           "- D1 windows are cut at the exact second (the expected amounts still come from the same 10-min bin baselines). The "
           "bins are aligned to each record's start, which coincides with the gap end for a round but not with a natural wake; "
           "bin windows would put up to 10 min of the wake into A and start B up to 10 min late.",
           f"- \"Without a round\" is read as no handling: rounds and probe moves (a probe move is handled too). Probe moves "
           f"removed {', '.join(f'{r['scores']} {r['no round within 3 h'] - r['and no probe move (natural)']}' for r in FUN)} dawn "
           "wake(s) beyond the rounds.",
           "- The dawn windows are confined to the wake's own record (seconds before its start are unrecorded); a round ends "
           "every record, so a 3-h B window after a dawn wake is usually cut by the morning round (counts in the funnel).",
           "- The plan's rats rule (≥ 3 windows per rat) cannot carry a three-predictor per-animal fit, so the per-animal sign "
           "is the simple slope of pay_rem on debt_rem on the same day-demeaned data; partial slopes are reported for rats "
           "with ≥ 7 windows.",
           "- Both horizons (1 h, 3 h) are tested, as A4 did; a horizon without enough windows is INCONCLUSIVE, not failed.",
           "- Windows whose record has no SLEEP episode ≥ 20 min after the wake (or the gap) are dropped from the models with "
           "the onset covariate only.",
           "- `budget_from_records` uses the plan's phase × day baselines by default (section 3, \"every expected-amount "
           "baseline that compares windows on either side of dawn or dusk\"); the #13 numbers were computed with Phase 3b's "
           "common-day baselines, reproduced with `baseline='common_day'`. SEs follow `check_drift.py` (clustered by night; "
           "model-based with day fixed effects).",
           "- The baselines are fitted by a numpy IRLS (`engine='numpy'`, the default) for speed; the statsmodels path "
           "(`engine='statsmodels'`, the original `baselines_d` / `baselines`) gives the same table (reproduction table).",
           "- The round windows are built by a vectorised copy of `comp_windows`' across-gap branch (`round_windows`), checked "
           "against the original in the selftest and against Step A's saved windows here; `comp_windows` itself also builds "
           "the hourly within-record windows, which A4 discards and which took most of its time.", ""]
    flat = [ln for blk in [hdr, DEFINITIONS, d1, rep, api, dev] for ln in blk]
    rpt = rd / "ephys_spikes_sleep_explore_D1_2026c.md"
    rpt.write_text("\n".join(flat) + "\n", encoding="utf-8")
    write_json(rd / "run_manifest_sleep_explore_D1_2026c.json",
               {"run_dir": str(out), "git_commit": gc, "plan": PLAN, "scorings": labs,
                "inputs": {"states_FINAL": str(STATES), "states_pass2med": str(PASS2MED), "review": str(REVIEW), "gaps": str(gaps_path),
                           "A4_csv": str(A4_CSV), "A_run": str(a_run), "phase3b_run": str(p3b_run)},
                "verdict_D1_pass2med": verdict, "per_horizon": st, "runtime_s": round(t_total, 1),
                "runtime_per_call": RT})
    print("written", rpt, f"({t_total / 60:.1f} min); D1 verdict: {verdict}")


# ================================================================== synthetic records (selftest)
def _sun_fn():
    from sleep_quant import sun_times
    cache = {}

    def light(t: pd.Timestamp) -> bool:
        k = t.date()
        if k not in cache:
            cache[k] = tuple(pd.Timestamp(x) for x in sun_times(k))
        return cache[k][0] <= t < cache[k][1]
    return light


def _blk(t: pd.Timestamp) -> str:
    d = t.normalize() - (pd.Timedelta(days=1) if t.hour < 6 else pd.Timedelta(0))
    return f"{d:%Y-%m-%d}{'D' if 6 <= t.hour < 18 else 'N'}"


def synth_world(rng, animals=("SF07", "SF08", "SF09", "SF10"), n_days: int = 12, beta_round: float = 0.0, beta_dawn: float = 0.0,
                dawn: bool = False, tradeoff: float = 0.0, drift: bool = False, unit_s: int = 30):
    """Synthetic records + gaps. Per animal and day: a night record 19:30 -> 07:00 (dawn worlds: -> 10:00) and a day
    record 08:00 (dawn: 11:00) -> 18:30; rounds in between (morning / evening, cause round_logged). States per 30-s unit:
    sleep with probability p_sleep (light 0.8, dark 0.5), REM with share q (light 0.15, dark 0.10) of sleep.
    beta_round: REM-share factor (1 - u), u ~ U(-0.6, 0.9), in the 3 h before each morning round, and beta x the realised
    REM debt (s; vs the generative expectation) converted NREM -> REM (or back) in the first hour after it.
    dawn / beta_dawn: one wake (30-150 min, ending 05:15-08:30) per animal-night, the same factor in the 3 h before its
    start, a 60-min sleep block after it and beta_dawn x the realised debt added in its first hour.
    tradeoff: per animal-night v ~ N(0, 0.25): night p_sleep x (1 + v), next day's x (1 - tradeoff x v).
    drift: night p_sleep falls 0.015 per day and day p_sleep rises 0.01 per day (all animals), plus independent noise."""
    light = _sun_fn()
    day0 = pd.Timestamp("2026-08-31")
    recs, gaps = [], []
    nend, dstart = ("10:00", "11:00") if dawn else ("07:00", "08:00")
    for an in animals:
        v_prev = 0.0
        for k in range(n_days):
            d = day0 + pd.Timedelta(days=k)
            v = float(rng.normal(0, 0.25)) if tradeoff else 0.0
            wn = float(rng.normal(0, 0.03)) if drift else 0.0
            wd = float(rng.normal(0, 0.02)) if drift else 0.0
            for kind, t0, t1 in (("day", pd.Timestamp(f"{d:%Y-%m-%d} {dstart}"), pd.Timestamp(f"{d:%Y-%m-%d} 18:30")),
                                 ("night", pd.Timestamp(f"{d:%Y-%m-%d} 19:30"), pd.Timestamp(f"{d + pd.Timedelta(days=1):%Y-%m-%d} {nend}"))):
                nu = int((t1 - t0).total_seconds() // unit_s)
                tt = t0 + pd.to_timedelta(np.arange(nu) * unit_s, unit="s")
                lt = np.array([light(t) for t in tt[::20]]).repeat(20)[:nu]
                ps = np.where(lt, 0.8, 0.5)
                q = np.where(lt, 0.15, 0.10)
                if tradeoff:
                    ps = ps * ((1 - tradeoff * v_prev) if kind == "day" else (1 + v))
                if drift:
                    ps = ps + (np.where(lt, 0.01, -0.015) * k) + (wd if kind == "day" else wn)
                ps = np.clip(ps, 0.02, 0.98)
                qf = np.ones(nu)
                dawn_u = None
                if dawn and kind == "night":
                    te = pd.Timestamp(f"{d + pd.Timedelta(days=1):%Y-%m-%d} 05:15") + pd.Timedelta(minutes=float(rng.uniform(0, 195)))
                    dd = float(rng.uniform(30, 150))
                    ws_u = int((te - pd.Timedelta(minutes=dd) - t0).total_seconds() // unit_s)
                    we_u = int((te - t0).total_seconds() // unit_s)
                    u = float(rng.uniform(-0.6, 0.9))
                    qf[max(ws_u - 360, 0):ws_u] = 1 - u
                    dawn_u = (ws_u, we_u)
                if kind == "night" and not dawn:
                    u = float(rng.uniform(-0.6, 0.9))
                    qf[nu - 360:] = 1 - u
                sl = rng.random(nu) < ps
                rem = sl & (rng.random(nu) < np.clip(q * qf, 0, 1))
                s = np.where(sl, np.where(rem, R, N), W).astype(np.int8)
                if dawn_u is not None:
                    ws_u, we_u = dawn_u
                    s[ws_u:we_u] = W
                    blk_ = slice(we_u, min(we_u + 120, nu))
                    s[blk_] = np.where(rng.random(blk_.stop - blk_.start) < 0.1, R, N)
                    lo = max(ws_u - 360, 0)
                    exp_a = float(np.sum(ps[lo:ws_u] * q[lo:ws_u]))
                    debt = exp_a - float(np.sum(s[lo:ws_u] == R))
                    _plant(rng, s, we_u, min(we_u + 120, nu), beta_dawn * debt)
                recs.append({"animal": an, "start": t0, "state": np.repeat(s, unit_s), "kind_": kind, "_qexp": (ps, q)})
            v_prev = v
    out = []
    for an in animals:
        rr = sorted([r for r in recs if r["animal"] == an], key=lambda x: x["start"])
        for i, rc in enumerate(rr):
            if beta_round and rc["kind_"] == "day" and i > 0 and not dawn:
                prev = rr[i - 1]
                ps, q = prev["_qexp"]
                su = prev["state"][::unit_s]
                exp_a = float(np.sum(ps[-360:] * q[-360:]))
                debt = exp_a - float(np.sum(su[-360:] == R))
                s = rc["state"][::unit_s].copy()
                _plant(rng, s, 0, 120, beta_round * debt)
                rc["state"] = np.repeat(s, unit_s)
            out.append(rc)
    for i, rc in enumerate(out):
        rc["end"] = rc["start"] + pd.Timedelta(seconds=len(rc["state"]))
        rc["record_id"] = i
        rc["block"] = _blk(rc["start"])
        rc["sessions"] = [f"s{i}"]
        rc.pop("_qexp")
        rc.pop("kind_")
    for an in animals:
        rr = sorted([r for r in out if r["animal"] == an], key=lambda x: x["start"])
        for p, n in zip(rr[:-1], rr[1:]):
            h = p["end"].hour + p["end"].minute / 60
            gaps.append({"animal": an, "gap_start": p["end"], "gap_end": n["start"], "gap_min": (n["start"] - p["end"]).total_seconds() / 60,
                         "kind": "morning" if 5 <= h < 11 else ("evening" if 15.5 <= h < 21.5 else "other"), "usable": True,
                         "cause": "round_logged"})
    return out, pd.DataFrame(gaps)


def _plant(rng, s: np.ndarray, lo: int, hi: int, extra_units_s: float, unit_s: int = 30) -> None:
    """Convert NREM units in [lo, hi) to REM (extra > 0) or REM units to NREM (extra < 0); extra is in units of the
    generative REM count, i.e. 30-s units (the debt was computed on units)."""
    k = int(round(abs(extra_units_s)))
    if k == 0:
        return
    src, dst = (N, R) if extra_units_s > 0 else (R, N)
    idx = lo + np.flatnonzero(s[lo:hi] == src)
    if len(idx):
        s[rng.choice(idx, size=min(k, len(idx)), replace=False)] = dst


# ================================================================== selftest
def selftest() -> None:
    t_start = time.time()
    ok_all = True

    def check(name: str, cond: bool) -> None:
        nonlocal ok_all
        print(("PASS " if cond else "FAIL ") + name, flush=True)
        ok_all &= bool(cond)

    rng = np.random.default_rng(7)
    # 1. engine equality: numpy IRLS baselines = statsmodels baselines_d / baselines; round_windows = comp_windows
    recs0, gaps0 = synth_world(rng, n_days=6, beta_round=0.6)
    for bl in BASELINES:
        Bn, RBn = baseline_bins(recs0, bl, "numpy")
        Bs, _ = baseline_bins(recs0, bl, "statsmodels")
        rel = max(float(np.nanmax(np.abs(Bn[c] - Bs[c]) / np.maximum(np.abs(Bs[c]), 1e-6))) for c in ("e_rem_s", "e_nrem_s", "e_rem_on", "e_rem_dur"))
        check(f"baselines {bl}: numpy IRLS = statsmodels (max relative difference {rel:.1e} < 1e-5)", rel < 1e-5)
    Wr = round_windows(Bs, RBn, gaps0)
    Wc = comp_windows(Bs.assign(record_id=np.arange(len(Bs))), RBn, gaps0)
    Wc = Wc[Wc.setting.astype(str).str.startswith("across gap (round_")].reset_index(drop=True)
    num = [c for c in Wc.columns if pd.api.types.is_float_dtype(Wc[c])]
    dif = float(np.nanmax(np.abs(Wr[num].to_numpy(float) - Wc[num].to_numpy(float)))) if len(Wc) else np.inf
    check(f"round_windows = comp_windows' across-gap rows ({len(Wr)} vs {len(Wc)} rows; max difference {dif:.1e}; blocks equal "
          f"{bool((Wr.A_block.to_numpy() == Wc.A_block.to_numpy()).all()) if len(Wc) == len(Wr) else False})",
          len(Wr) == len(Wc) and dif < 1e-9 and bool((Wr.B_block.to_numpy() == Wc.B_block.to_numpy()).all()))

    # 2. payback: planted slope recovered; none planted -> ~0
    res = {}
    for beta in (0.6, 0.0):
        recs, gaps = synth_world(np.random.default_rng(11), n_days=14, beta_round=beta, animals=("SF07", "SF08", "SF09", "SF10", "SF11"))
        t0 = time.time()
        T = payback_from_records(recs, gaps, f"beta {beta}")
        el = time.time() - t0
        sel = T[(T.kind == "morning") & (T.outcome == "pay_rem") & (T.predictors == "debt_rem") & T.day_demeaned]
        res[beta] = sel.set_index("B_h").slope
        print(f"   payback beta {beta}: day-demeaned slopes {res[beta].round(3).to_dict()} ({el:.1f} s)")
    check(f"payback: planted 0.6 recovered at 1 h and 3 h ({res[0.6].round(2).to_dict()}, |error| < 0.15)",
          bool((np.abs(res[0.6] - 0.6) < 0.15).all()))
    check(f"payback: none planted -> |slope| < 0.15 ({res[0.0].round(2).to_dict()})", bool((np.abs(res[0.0]) < 0.15).all()))

    # 3. budget: planted trade-off recovered with day FE; drift-only -> negative raw slope under the common-day baseline,
    #    ~0 with day FE and under the phase x day baseline
    recs, _ = synth_world(np.random.default_rng(21), n_days=12, tradeoff=0.3, animals=("SF07", "SF08", "SF09", "SF10", "SF11", "SF12"))
    T, D = budget_from_records(recs, "tradeoff", return_days=True)
    g = D[(D.night_cov >= 0.5) & (D.day_cov >= 0.5)]
    truth = float(np.polyfit(g.night_NREM_rate_dev, g.day_NREM_rate_dev, 1)[0])
    fe = T[(T.quantity == "NREM") & (T.model == "within animal + day FE")].slope.iloc[0]
    check(f"budget: planted NREM trade-off -> day-FE slope {fe:+.2f} < -0.3 and within 0.15 of the data's pooled slope {truth:+.2f}",
          fe < -0.3 and abs(fe - truth) < 0.15)
    recs, _ = synth_world(np.random.default_rng(22), n_days=12, drift=True, animals=("SF07", "SF08", "SF09", "SF10", "SF11", "SF12"))
    Tc = budget_from_records(recs, "drift", baseline="common_day")
    Tp = budget_from_records(recs, "drift")
    gs = lambda T_, m: float(T_[(T_.quantity == "NREM") & (T_.model == m)].slope.iloc[0])  # noqa: E731
    check(f"budget, drift only: common-day baseline raw slope {gs(Tc, 'within animal'):+.2f} < -0.3, day FE "
          f"{gs(Tc, 'within animal + day FE'):+.2f} and phase x day raw {gs(Tp, 'within animal'):+.2f} / day FE "
          f"{gs(Tp, 'within animal + day FE'):+.2f} within 0.2 of 0",
          gs(Tc, "within animal") < -0.3 and abs(gs(Tc, "within animal + day FE")) < 0.2 and abs(gs(Tp, "within animal + day FE")) < 0.2
          and abs(gs(Tp, "within animal")) < 0.2)

    # 4. D1 window arithmetic on a hand-made record
    seq = [(N, 9000), (R, 600), (N, 1200), (W, 2400), (N, 1800), (R, 300), (N, 2000)]
    st = np.concatenate([np.full(d, s, np.int8) for s, d in seq])
    rc = {"animal": "SF07", "start": pd.Timestamp("2026-09-03 01:00:00"), "state": st, "record_id": 0, "block": "2026-09-02N",
          "end": pd.Timestamp("2026-09-03 01:00:00") + pd.Timedelta(seconds=len(st))}
    Bh, _ = bins10([rc])
    for c, v in (("e_rem_s", 0.1), ("e_nrem_s", 0.5), ("e_rem_on", 0.01), ("e_rem_dur", 100.0)):
        Bh[c] = v * (Bh.rec_s if c != "e_rem_dur" else 1)
    gp = pd.DataFrame(columns=["animal", "gap_start", "gap_end", "cause", "usable"])
    Dw = dawn_wakes([rc], gp)
    S = _RecSec(rc, Bh)
    a, b = 10800, 13200
    A = S.window(a - LOOKBACK_S, a)
    Bw = S.window(b, b + 3600)
    check("D1: a 40-min wake ending at 04:40 is not a dawn wake (ends before 05:00)", Dw.empty)
    check(f"D1 windows: A REM {A['rem_min']:.1f} min (10), NREM {A['nrem_min']:.1f} (170), expected REM {A['e_rem_min']:.1f} (18); "
          f"B (1 h) NREM {Bw['nrem_min']:.1f} (55), REM {Bw['rem_min']:.1f} (5), REM onsets {Bw['rem_n']:.0f} (1), duration "
          f"{Bw['rem_dur_s']:.0f} s (300), expected onsets {Bw['e_rem_n']:.1f} (36), expected duration {Bw['e_rem_dur_s']:.0f} s (100)",
          abs(A["rem_min"] - 10) < 1e-9 and abs(A["nrem_min"] - 170) < 1e-9 and abs(A["e_rem_min"] - 18) < 1e-6
          and abs(Bw["nrem_min"] - 55) < 1e-9 and abs(Bw["rem_min"] - 5) < 1e-9 and Bw["rem_n"] == 1 and Bw["rem_dur_s"] == 300
          and abs(Bw["e_rem_n"] - 36) < 1e-6 and abs(Bw["e_rem_dur_s"] - 100) < 1e-6)
    rc2 = {**rc, "start": pd.Timestamp("2026-09-03 02:30:00")}
    Dw2 = dawn_wakes([rc2], gp)
    check(f"D1: the same wake shifted to end 06:10 is found and natural ({len(Dw2)} wake, d {Dw2.d_min.iloc[0] if len(Dw2) else 0:.0f} min)",
          len(Dw2) == 1 and bool(Dw2.natural.iloc[0]) and abs(Dw2.d_min.iloc[0] - 40) < 1e-9)
    check(f"D1: main-sleep onset = the wake end ({S.sleep_onset(b)} = {b})", S.sleep_onset(b) == b)
    gp2 = pd.DataFrame({"animal": ["SF07"], "gap_start": [pd.Timestamp("2026-09-03 01:00")], "gap_end": [pd.Timestamp("2026-09-03 02:35")],
                        "cause": ["round_logged"], "usable": [True]})
    gp3 = gp2.assign(gap_end=pd.Timestamp("2026-09-03 02:29"))
    check("D1: a round ending < 3 h before the wake start excludes it; one ending > 3 h before does not",
          not bool(dawn_wakes([rc2], gp2).natural.iloc[0]) and bool(dawn_wakes([rc2], gp3).natural.iloc[0]))

    # 5. D1 on synthetic dawn worlds: planted slope recovered, none -> ~0
    for beta in (0.6, 0.0):
        recs, gaps = synth_world(np.random.default_rng(31), n_days=14, dawn=True, beta_dawn=beta,
                                 animals=("SF07", "SF08", "SF09", "SF10", "SF11"))
        t0 = time.time()
        T, Wd = dawn_payback_from_records(recs, gaps, f"dawn beta {beta}", return_windows=True)
        el = time.time() - t0
        r1 = T[(T.B_h == 1) & (T.predictors == "debt_rem + debt_nrem + onset_h") & T.day_demeaned & (T.outcome == "pay_rem")].iloc[0]
        r0 = T[(T.B_h == 1) & (T.predictors == "debt_rem") & T.day_demeaned & (T.outcome == "pay_rem")].iloc[0]
        v, why = d1_rule(r1)
        print(f"   dawn beta {beta}: windows {len(Wd)}; 1 h slope (primary) {r1.slope:+.3f} p {r1.p:.4f}, simple-model {r0.slope:+.3f}; "
              f"rule {v} ({why}); {el:.1f} s")
        if beta:
            check(f"D1: planted 0.6 recovered (primary 1-h slope {r1.slope:+.2f}, |error| < 0.2) and the rule is MET", abs(r1.slope - 0.6) < 0.2 and v == "MET")
        else:
            check(f"D1: none planted -> |slope| {abs(r1.slope):.2f} < 0.2 and the rule is NOT MET", abs(r1.slope) < 0.2 and v == "NOT MET")
    print(f"selftest {'PASS' if ok_all else 'FAIL'} ({time.time() - t_start:.0f} s)")
    if not ok_all:
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["stepD1"])
    ap.add_argument("--scorings", nargs="*", default=["FINAL", "pass2med"], choices=list(SCORINGS))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.selftest:
        selftest()
    elif a.cmd == "stepD1":
        stepD1(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
