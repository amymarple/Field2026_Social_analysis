r"""Sleep behaviour explore, Step F — the WISER / environment / social batch: H4, H14, H15, H16, H17, H22, H25 (cohort 2026c).

Plan: implementation_plan/2026-10-08-sleep-behaviour-explore.md (sections 1 scope, 3 definitions, 5 Step F table, 9 Amendment 1).
The tests and pass rules are the plan's Step F table, quoted unchanged in the report; where the table's wording leaves a
choice open, the choice is fixed in this docstring and in the report's Definitions BEFORE the run (and stated in place).

Hypotheses (Step F table; "pass" column quoted in the report):
  h4   NREM after a wake follows the wake's activity (WISER distance / time in the field during the wake), not only its
       length: NREM excess in the first hour after the sleep onset ~ ln d + activity + dark, within night (night fixed
       effects), animal fixed effects; activity = jitter-floored WISER path (primary) or the share of the wake in the field.
  h14  warmth raises REM share through maintenance, not entry: REM bout duration and the REM -> WAKE hazard ~ temperature
       anomaly at matched prior wake; REM entry (NREM -> REM hazard, Step B's B-full + temperature) must stay null.
  h15  group size (co-located tagged housemates, WISER) changes sleep maintenance, not REM entry: NREM -> WAKE and
       NREM -> REM hazards ~ n co-located by phase (B-full + location + group size); sleep-onset latency after a house
       entry ~ n co-located by phase (Cox).
  h16  a housemate leaving the house ends the partner's sleep: P(partner WAKE within 0-2 min | a co-located housemate exits
       the house to the field while the partner sleeps) vs a time-shift chance level.
  h17  sleeping at a new site after a long wake delays REM: first-REM latency (NREM time, Cox) after wakes >= 7 min when the
       WISER house of the post-wake sleep differs from the pre-wake sleep, ln d (matched wake length) in the model.
  h22  rain disturbs sleep: REM entry and WAKE exits on rainy vs dry nights (night NREM steps, B-full incl. ln d = matched
       prior wake; held out); REM -> WAKE on the night REM steps.
  h25  the five females (from 2026-09-11 19:40): DESCRIPTION ONLY of the after-cut data (never pooled with the inference
       set): per animal the after-cut night / morning against the same clock windows of the earlier nights, and the
       observed / expected REM entries and WAKE exits under the B-full fit of the pre-cut data.

Usage:  python ephys/sleep_explore_f2.py run [--parts h4 h14 h15 h16 h17 h22 h25] [--scorings final pass2med] [--workers 6]
                                           [--zone-cache NPZ] [--pos-cache NPZ] [--scratch]
        python ephys/sleep_explore_f2.py --selftest
Imports, never edits: sleep_explore_c (multinomial engine with cluster-robust SEs, Step C's prep / WISER zone / housemate
terms), sleep_model (records, steps, folds), sleep_explore (post-long-wake table, Cox, OLS helpers), sleep_explore_d
(phase x day baselines), sleep_schedule_phase3 (expected rates, light), sleep_schedule_temp (weather), sleep_sim (REM steps,
in the selftest).
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
import warnings  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(ROOT / "common"))
sys.path.insert(0, str(ROOT / "wiser" / "src"))
import sleep_explore_c as C  # noqa: E402
from sleep_cycles import bouts  # noqa: E402
from sleep_model import PASS2MED, build_data, records_for, to_arrays, variant_specs  # noqa: E402
from sleep_schedule import CUTOFF, N, R, REVIEW, STATES, W  # noqa: E402

PLAN = "implementation_plan/2026-10-08-sleep-behaviour-explore.md"
SCORINGS = {"final": STATES, "pass2med": PASS2MED}
LABEL = {"final": "FINAL", "pass2med": "pass2med"}
KEY = "P_tw600_k0"                          # Step B's modal grid point (plan Amendment 1)
OUT = C.OUT
ZONE_CACHE = OUT / "sleep_explore_C_20261009_0121" / "zone_per_second.npz"
G0, G1, ANIMALS = C.G0, C.G1, C.ANIMALS
PARTS = ("h4", "h14", "h15", "h16", "h17", "h22", "h25")
COL = {**C.COL, "after": "#c0392b"}
BF = C.specs_c1(KEY)["b_Bfull"]             # B-full in Step C's engine: P spline + 2-harmonic clock + dark + ln d + L1 + day

# ---- fixed choices (set before the run; definitions in the report)
H4_MIN_WAKE_S = 120                         # natural wakes >= 2 min (as #31 / Phase 3 Q2)
H4_H_S = 3600                               # the first hour after the sleep onset
H4_KNOWN = 0.9                              # >= 90 % of that hour scored
WISER_COVER = 0.5                           # >= 50 % of the wake's seconds with a WISER zone
PATH_BIN_S = 10                             # path from 10-s median positions
PATH_FLOOR_IN = 7.0                         # displacements < 7 in per 10 s (the WISER jitter floor) count as 0
IN_TO_M = 0.0254
HOUSE_MIN_S = 60                            # a house stay (exit / entry hysteresis)
FIELD_MIN_S = 30                            # a field stay
AWAY_S = 30                                 # H15: a stay ends at the first other-zone / unknown run >= 30 s
ASLEEP_S = 30                               # H16: partner asleep (NREM / REM) for the 30 s before the exit
MATE_SHARE = 0.8                            # H16: partner in the same house for >= 80 % of the 60 s before
H16_WIN_S = 120                             # 0-2 min
MA_S = 40                                   # microarousal limit (Watson 2016)
SHIFTS_MIN = (5, 10, 15, 20, 30, 45, 60)    # H16 time shifts (both signs)
ONSET_NREM_S = 60                           # H15: sleep onset = the first NREM bout >= 60 s
LAT_CAP_S = 4 * 3600
SITE_S = 600                                # H17: the last / first 10 min of sleep before / after the wake
SITE_MIN = 60                               # >= 60 sleep seconds with a WISER zone
RAIN_MM = 1.0                               # rainy night >= 1 mm console rain sunset -> sunrise
COVER = 0.5                                 # >= 50 % console coverage of the night
MIN_EV_ANIMAL = 15
WBINS = ((120, 420, "2-7 min"), (420, 1800, "7-30 min"), (1800, 7200, "30-120 min"), (7200, np.inf, ">= 2 h"))
WB_LEVELS = ["none", "2-7 min", "7-30 min", "30-120 min", ">= 2 h"]


# ================================================================== small helpers
def period_of(t) -> np.ndarray:
    """The 24-h period [sunset of date D, sunset of D + 1) that contains t, as 'YYYY-MM-DD' of D ('night_of')."""
    from sleep_quant import sun_times
    t = pd.to_datetime(pd.Series(t)).reset_index(drop=True)
    d = t.dt.normalize()
    out = d.copy()
    for day in d.unique():
        day = pd.Timestamp(day)
        ss = pd.Timestamp(sun_times(day.date())[1])
        m = (d == day).to_numpy()
        before = m & (t < ss).to_numpy()
        out[before] = day - pd.Timedelta(days=1)
    return out.dt.strftime("%Y-%m-%d").to_numpy().astype("U10")


def block_of(t: pd.Timestamp) -> str:
    """The day-half block label of a time (sleep_cycles_v2.build_records' rule applied to t itself)."""
    h = t.hour
    d = t.normalize() - (pd.Timedelta(days=1) if h < 6 else pd.Timedelta(0))
    return f"{d:%Y-%m-%d}{'D' if 6 <= h < 18 else 'N'}"


def dark_at(ts) -> np.ndarray:
    from sleep_schedule_phase3 import light_flags
    return (~light_flags(pd.Series(pd.to_datetime(ts)))).astype(float)


def wbin(d) -> str:
    if d is None or not np.isfinite(d):
        return "none"
    for lo, hi, lab in WBINS:
        if lo <= d < hi:
            return lab
    return "none"


def runs(z: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Run-length encoding: (starts, ends exclusive, values)."""
    if len(z) == 0:
        return np.zeros(0, int), np.zeros(0, int), np.zeros(0, z.dtype)
    chg = np.flatnonzero(np.diff(z)) + 1
    st, en = np.r_[0, chg], np.r_[chg, len(z)]
    return st, en, z[st]


def verdict(flags: dict) -> str:
    """HOLDS = the rule is met on every scoring; INCONCLUSIVE = met on some only, or computable on none; DOES NOT HOLD =
    met on none of the scorings where it was computable."""
    v = list(flags.values())
    comp = [x for x in v if x is not None]
    if not comp:
        return "INCONCLUSIVE"
    k = sum(bool(x) for x in comp)
    if k == len(v):
        return "HOLDS"
    if k >= 1:
        return "INCONCLUSIVE"
    return "DOES NOT HOLD"


def ols_fe(y, X: pd.DataFrame, fes=(), groups=None):
    """OLS with an intercept, any number of fixed-effect sets (dummies, first level dropped) and SEs clustered by `groups`
    (HC1 if no groups / clustering fails). Constant columns are dropped."""
    import statsmodels.api as sm
    Xd = X.astype(float)
    Xd = Xd.loc[:, [c for c in Xd.columns if Xd[c].nunique() > 1]]
    for k, f in enumerate(fes):
        f = pd.Series(np.asarray(f), index=X.index)
        if f.nunique() > 1:
            Xd = pd.concat([Xd, pd.get_dummies(f, prefix=f"fe{k}", drop_first=True, dtype=float)], axis=1)
    Xd = sm.add_constant(Xd, has_constant="add")
    yv = pd.Series(np.asarray(y, float), index=X.index)
    if groups is not None and pd.Series(np.asarray(groups)).nunique() > 1:
        try:
            return sm.OLS(yv, Xd).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(np.asarray(groups))[0]})
        except Exception:  # noqa: BLE001
            pass
    return sm.OLS(yv, Xd).fit(cov_type="HC1")


def term(fit, t: str) -> dict:
    from sleep_explore import term as _t
    return _t(fit, t)


def nanmed_bins(v: np.ndarray, k: int) -> np.ndarray:
    n = int(np.ceil(len(v) / k)) * k
    p = np.full(n, np.nan)
    p[:len(v)] = v
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return np.nanmedian(p.reshape(-1, k), axis=1)


def floored_path(x: np.ndarray, y: np.ndarray, k: int = PATH_BIN_S, floor: float = PATH_FLOOR_IN) -> float:
    """Path (in) from k-s median positions: sum of the displacements between consecutive known bins, each < floor set to 0."""
    xb, yb = nanmed_bins(x, k), nanmed_bins(y, k)
    d = np.hypot(np.diff(xb), np.diff(yb))
    d = d[np.isfinite(d)]
    d[d < floor] = 0.0
    return float(d.sum())


# ================================================================== shared inputs
def gaps_table() -> pd.DataFrame:
    return C.gaps_table()


def zone_arrays(path: Path) -> dict[str, np.ndarray]:
    return C.zone_arrays(path)


def _pos_one(an: str, dates: list[str], span: int) -> tuple[str, np.ndarray, np.ndarray]:
    fs = [OUT / f"wiser_default_tracks/{an}/{d}.csv.gz" for d in dates]
    fs = [f for f in fs if f.exists()]
    x = np.full(span, np.nan, np.float32)
    y = np.full(span, np.nan, np.float32)
    if not fs:
        return an, x, y
    tr = pd.concat([pd.read_csv(f, usecols=["t_ms", "x", "y", "m_off_animal"]) for f in fs])
    tr = tr[tr.m_off_animal.fillna(0).astype(int) == 0]
    t = (pd.to_datetime(tr.t_ms, unit="ms") - pd.Timedelta(hours=4)).dt.floor("1s")
    i = ((t - G0).dt.total_seconds()).to_numpy().astype(np.int64)
    ok = (i >= 0) & (i < span)
    g = pd.DataFrame({"i": i[ok], "x": tr.x.to_numpy()[ok], "y": tr.y.to_numpy()[ok]}).groupby("i")[["x", "y"]].median()
    x[g.index.to_numpy()] = g.x.to_numpy()
    y[g.index.to_numpy()] = g.y.to_numpy()
    return an, x, y


def pos_arrays(cache: Path | None, out_cache: Path, workers: int) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Per animal, the per-second median default-track position (in, unverified WISER frame) over [G0, G1); NaN where no
    fix (no forward fill); fixes flagged m_off_animal removed (as Step C's zone)."""
    if cache is not None and Path(cache).exists():
        with np.load(cache) as z:
            return {an: (z[f"{an}_x"], z[f"{an}_y"]) for an in ANIMALS if f"{an}_x" in z.files}
    from joblib import Parallel, delayed
    span = int((G1 - G0).total_seconds())
    dates = [d.strftime("%Y%m%d") for d in pd.date_range(G0.normalize(), G1.normalize())]
    res = Parallel(n_jobs=min(workers, len(ANIMALS)), backend="loky")(delayed(_pos_one)(an, dates, span) for an in ANIMALS)
    out = {an: (x, y) for an, x, y in res}
    np.savez_compressed(out_cache, **{f"{an}_{c}": v for an, (x, y) in out.items() for c, v in (("x", x), ("y", y))})
    return out


def weather() -> pd.DataFrame:
    from sleep_schedule_temp import weather_anomaly
    return weather_anomaly()


def night_rain(w: pd.DataFrame) -> pd.DataFrame:
    """Per night_of date D: console rain (mm) and coverage over [sunset D, sunrise D + 1); class rainy (>= 1 mm) / dry (0 mm)
    / unclassified (coverage < 50 %, or 0 < rain < 1 mm)."""
    from sleep_quant import sun_times
    con = w[w.source.astype(str).str.startswith("on-site")]
    rows = []
    for d in pd.date_range("2026-08-29", "2026-09-12"):
        ss0 = pd.Timestamp(sun_times(d.date())[1])
        sr1 = pd.Timestamp(sun_times((d + pd.Timedelta(days=1)).date())[0])
        cc = con[(con.t >= ss0) & (con.t < sr1)]
        cover = len(cc) / ((sr1 - ss0).total_seconds() / 300)
        mm = float((cc.rain_rate_mmh.fillna(0) * 5 / 60).sum())
        rain_min = int((cc.rain_rate_mmh > 0).sum() * 5)
        cls = "unclassified" if cover < COVER else ("rainy" if mm >= RAIN_MM else ("dry" if mm == 0 else "unclassified"))
        rows.append({"night_of": f"{d:%Y-%m-%d}", "sunset": ss0, "sunrise_next": sr1, "console_cover": round(min(cover, 1.0), 3),
                     "rain_mm": round(mm, 2), "rain_min": rain_min, "class": cls})
    return pd.DataFrame(rows)


def join_temp(t, w: pd.DataFrame) -> pd.DataFrame:
    from sleep_schedule_temp import join_weather
    return join_weather(pd.DataFrame({"t": pd.to_datetime(pd.Series(t)).to_numpy()}), "t", w)


def prep_scoring(sc: str, gaps: pd.DataFrame, zone: dict, w: pd.DataFrame, rain: pd.DataFrame) -> dict:
    """Step C's prep (records -> 10-s NREM steps with P, post-round flag, WISER zone / company) + weather + period."""
    P = C.prep(LABEL[sc], SCORINGS[sc], [KEY], gaps, zone)
    D, steps = P["D"], P["steps"]
    j = join_temp(steps.t, w)
    D["temp_anom"] = j.temp_anom.to_numpy(float)
    D["rain_now"] = (j.rain_rate_mmh.fillna(0).to_numpy(float) > 0).astype(float)
    per = period_of(steps.t)
    D["period"] = per
    cls = dict(zip(rain.night_of, rain["class"]))
    c = np.array([cls.get(p, "unclassified") for p in per])
    D["night_cls"] = np.select([c == "rainy", c == "dry"], [1, 0], -1).astype(np.int8)
    D["rain_night"] = (D["night_cls"] == 1).astype(float)
    P["arr"] = C.state_timelines(P["recs"])
    P["sc"] = sc
    return P


# ================================================================== generic fits
def cal_folds(D: dict, mask: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    """Forward chaining over the CALENDAR day-half blocks of all NREM steps (plan section 3; as sleep_model.folds_of), restricted to
    the steps in `mask`: fold k trains on the masked steps of blocks < k and tests on the masked steps of block k (k >= 6;
    folds with no masked test or training steps are skipped). Indices refer to the full D."""
    from sleep_model import FIRST
    blocks = sorted(set(D["block"]))
    out = []
    for k in range(FIRST, len(blocks)):
        tr = np.flatnonzero(mask & np.isin(D["block"], blocks[:k]))
        te = np.flatnonzero(mask & (D["block"] == blocks[k]))
        if len(tr) and len(te):
            out.append((tr, te))
    return out


def heldout(D: dict, mask: np.ndarray, specs: dict, lo: str, hi: str, label: str, workers: int) -> dict:
    res = C.run_heldout(D, specs, cal_folds(D, mask), workers)
    F, FA = C.ho_tables(res, D)
    return C.cmp(F, FA, lo, hi, label)


def step_fits(jobs: list[tuple], workers: int) -> dict:
    return C.run_jobs(jobs, workers)


def lc(fit: dict, w: dict, eq: int) -> dict:
    if not fit or not fit.get("ok") or not all(k in fit["names"] for k in w):
        return {"coef": np.nan, "se": np.nan, "ci_lo": np.nan, "ci_hi": np.nan, "p": np.nan}
    r = C.lincomb(fit, fit["names"], w, eq)
    if not np.isfinite(r["se"]) or r["se"] > 10:          # an unidentified (penalised) term
        return {"coef": np.nan, "se": np.nan, "ci_lo": np.nan, "ci_hi": np.nan, "p": np.nan}
    return r


def term_row(sc: str, hyp: str, model: str, label: str, pooled: dict, per_an: dict[str, float], pred: int, n: int, ev: str = "") -> dict:
    """One coefficient row. pred: +1 / -1 = the hypothesised sign (0 = none); holds = CI excludes 0 with that sign and >= 5
    rats with that sign (two-sided: same sign as the pooled estimate when pred = 0)."""
    vals = np.array([v for v in per_an.values() if np.isfinite(v)])
    s = pred if pred != 0 else (np.sign(pooled["coef"]) if np.isfinite(pooled["coef"]) else 0)
    same = int(np.sum(np.sign(vals) == s)) if s != 0 else 0
    ci_ok = (pooled["ci_lo"] > 0) if s > 0 else ((pooled["ci_hi"] < 0) if s < 0 else False)
    has = len(vals) > 0
    return {"scores": LABEL[sc], "hypothesis": hyp, "model": model, "term": label, "coef": pooled["coef"], "se": pooled["se"],
            "ci_lo": pooled["ci_lo"], "ci_hi": pooled["ci_hi"], "p": pooled["p"], "pred_sign": pred,
            "animals_pred_sign": same if has else np.nan, "animals": len(vals) if has else np.nan, "ci_excl0_pred": bool(ci_ok),
            "holds_term": bool(ci_ok and same >= 5) if has else None,
            "n": n, "events": ev, **{f"an_{a}": per_an.get(a, np.nan) for a in ANIMALS}}


# ================================================================== H4
def h4_events(P: dict, gaps: pd.DataFrame, zone: dict, pos: dict) -> pd.DataFrame:
    """Natural wakes >= 2 min followed by NREM inside a record (known state before), the first hour after the sleep onset
    complete and >= 90 % scored; NREM excess against the phase x day baselines; WISER activity during the wake."""
    from sleep_explore_d import baseline_bins
    from sleep_schedule_phase3 import expected_rates
    recs = P["recs"]
    B, _ = baseline_bins(recs, "phase_x_day")
    expected_rates(recs, B)
    rows = []
    for rc in recs:
        st = rc["state"]
        n = len(st)
        cn, ck = np.r_[0, np.cumsum(st == N)], np.r_[0, np.cumsum(st != 0)]
        off = int((rc["start"] - G0).total_seconds())
        an = rc["animal"]
        z = zone.get(an)
        xy = pos.get(an)
        for s, a, b in bouts(st):
            if not (s == W and (b - a) >= H4_MIN_WAKE_S and a > 0 and st[a - 1] != 0 and b < n and st[b] == N and b + H4_H_S <= n):
                continue
            known = (ck[b + H4_H_S] - ck[b]) / H4_H_S
            if known < H4_KNOWN:
                continue
            obs = (cn[b + H4_H_S] - cn[b]) / 60
            exp = (rc["p_nrem"][b + H4_H_S] - rc["p_nrem"][b]) / 60
            r = {"animal": an, "record_id": rc["record_id"], "block": rc["block"], "t_wake": rc["start"] + pd.Timedelta(seconds=a),
                 "t0": rc["start"] + pd.Timedelta(seconds=b), "d_s": b - a, "nrem_obs_min": obs, "nrem_exp_min": exp, "excess_min": obs - exp,
                 "known_share": known}
            i0, i1 = off + a, off + b
            if z is not None and 0 <= i0 and i1 <= len(z):
                zz = z[i0:i1]
                kn = zz > 0
                r["wiser_cover"] = float(kn.mean())
                r["field_share"] = float((zz[kn] == 3).mean()) if kn.any() else np.nan
                r["field_min"] = float((zz == 3).sum() / 60)
            else:
                r["wiser_cover"] = 0.0
            if xy is not None and 0 <= i0 and i1 <= len(xy[0]):
                r["path_m"] = floored_path(xy[0][i0:i1].astype(float), xy[1][i0:i1].astype(float)) * IN_TO_M
            rows.append(r)
    E = pd.DataFrame(rows)
    E["l_d"] = np.log(E.d_s.astype(float))
    E["darkf"] = dark_at(E.t0)
    E["period"] = period_of(E.t0)
    E["post_round"] = C.post_round_mask(E.animal.to_numpy(), E.t0, gaps)
    E["l_path"] = np.log1p(E.path_m) if "path_m" in E else np.nan
    return E


H4_ACTS = (("l_path", "ln(1 + path m), jitter-floored (primary)"), ("field_share", "share of the wake in the field"))


def h4_models(E: pd.DataFrame, sc: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, pa = [], []
    base = E[(~E.post_round) & (E.wiser_cover >= WISER_COVER)].dropna(subset=["l_path", "field_share", "excess_min"])
    for act, act_lab in H4_ACTS:
        for model in ("primary: + dark, night FE, animal FE", "night only (dark onsets), night FE", "no night FE (animal FE, day linear)",
                      "primary + expected NREM (onset conditioning)"):
            d = base if not model.startswith("night only") else base[base.darkf == 1]
            xs = ["l_d", act] + ([] if model.startswith("night only") else ["darkf"])
            X = d[xs].copy()
            fes = [d.animal]
            if model.startswith("no night FE"):
                X["day"] = (pd.to_datetime(d.t0) - pd.Timestamp("2026-08-30 19:00")).dt.total_seconds() / 86400
            else:
                fes.append(d.period)
            if "expected" in model:
                X["nrem_exp_min"] = d.nrem_exp_min
            if len(d) < 20:
                continue
            f = ols_fe(d.excess_min, X, fes, d.block)
            per = {}
            if model.startswith("primary: "):
                for an, g in d.groupby("animal"):
                    if len(g) >= MIN_EV_ANIMAL and g[act].std() > 0:
                        fa = ols_fe(g.excess_min, g[xs], [g.period] if g.period.nunique() < len(g) - len(xs) - 3 else [])
                        tt = term(fa, act)
                        per[an] = tt["coef"]
                        pa.append({"scores": LABEL[sc], "activity": act, "animal": an, "events": len(g), **tt})
            t_ = term(f, act)
            r = term_row(sc, "H4", model, act_lab, t_, per, +1, len(d), f"{d.block.nunique()} blocks")
            r.update(l_d_coef=term(f, "l_d")["coef"], l_d_ci=f"[{term(f, 'l_d')['ci_lo']:+.2f}, {term(f, 'l_d')['ci_hi']:+.2f}]",
                     dark_coef=term(f, "darkf")["coef"] if "darkf" in xs else np.nan, animals_in_data=d.animal.nunique())
            if not per:
                r["holds_term"] = None
            rows.append(r)
    return pd.DataFrame(rows), pd.DataFrame(pa)


# ================================================================== REM bouts / REM steps (H14, H22)
def rem_bouts(recs: list[dict]) -> pd.DataFrame:
    """Every REM bout with a known start (a > 0 and the second before is scored): onset, duration, exit (1 NREM, 2 WAKE,
    0 unknown / record end), complete (exit known), the wake before its sleep episode (the last WAKE bout > 120 s before
    the onset with no unknown epoch in between; 'none' if an unknown epoch or the record start came first)."""
    rows = []
    for rc in recs:
        st = rc["state"]
        n = len(st)
        last = None
        for s, a, b in bouts(st):
            if s == 0:
                last = None
                continue
            if s == W and (b - a) > 120:
                last = float(b - a)
                continue
            if s != R or a == 0 or st[a - 1] == 0:
                continue
            ex = 0
            if b < n and st[b] in (N, W):
                ex = 1 if st[b] == N else 2
            rows.append({"animal": rc["animal"], "record_id": rc["record_id"], "block": rc["block"], "a": a, "b": b, "dur_s": b - a,
                         "t0": rc["start"] + pd.Timedelta(seconds=a), "exit": ex, "complete": ex > 0, "pre_wake_s": last if last else np.nan,
                         "wbin": wbin(last)})
    return pd.DataFrame(rows)


def rem_step_table(Rb: pd.DataFrame) -> pd.DataFrame:
    """10-s person-period rows of every REM bout (as sleep_sim.rem_steps): y = 0 stay, 1 -> NREM, 2 -> WAKE at the last
    step (0 when the exit is unknown = censored); bout covariates repeated."""
    J = np.ceil(Rb.dur_s.to_numpy() / 10).astype(int)
    rep = np.repeat(np.arange(len(Rb)), J)
    el = np.concatenate([10 * np.arange(j) for j in J]) if len(J) else np.zeros(0)
    last = np.zeros(len(rep), bool)
    last[np.cumsum(J) - 1] = True
    T = Rb.iloc[rep].reset_index(drop=True)
    T["bout"] = rep
    T["elapsed"] = el
    T["y"] = np.where(last, T.exit.to_numpy(), 0).astype(np.int8)
    T["t"] = T.t0 + pd.to_timedelta(el, unit="s")
    T["hour"] = T.t.dt.hour + T.t.dt.minute / 60 + T.t.dt.second / 3600
    T["T_day"] = (T.t - pd.Timestamp("2026-08-30 19:00")).dt.total_seconds() / 86400
    return T


def rem_design(T: pd.DataFrame, idx: np.ndarray, extra: tuple, st: dict | None = None, animal: bool = True,
               dark: bool = True) -> tuple[np.ndarray, list[str], dict]:
    """REM-step design: spline ln(elapsed + 5) (4 knots), (sin, cos)(2 pi k h / 24) k = 1, 2, day (z), dark, prior-wake bins
    (reference 'none'), extra columns centred (raw units), animal dummies."""
    from sklearn.preprocessing import SplineTransformer
    fit = st is None
    st = {} if st is None else st
    g = T.iloc[idx]
    le = np.log(g.elapsed.to_numpy(float) + 5.0)[:, None]
    if fit:
        st["spl"] = SplineTransformer(n_knots=4, degree=3, include_bias=False).fit(le)
        st["mu_T"], st["sd_T"] = float(g.T_day.mean()), float(g.T_day.std()) or 1.0
        st["wb"] = [b for b in WB_LEVELS[1:] if (g.wbin == b).sum() >= 20]
        st["levels"] = sorted(g.animal.unique())
        for c in extra:
            st[f"mu_{c}"] = float(g[c].mean())
    cols, names = [st["spl"].transform(le)], [f"spl_el_{j}" for j in range(st["spl"].transform(le[:1]).shape[1])]
    h = g.hour.to_numpy(float)
    for k in (1, 2):
        cols += [np.sin(2 * np.pi * k * h / 24)[:, None], np.cos(2 * np.pi * k * h / 24)[:, None]]
        names += [f"sin{k}", f"cos{k}"]
    cols.append(((g.T_day.to_numpy(float) - st["mu_T"]) / st["sd_T"])[:, None])
    names.append("T_day")
    if dark:
        cols.append(g.dark.to_numpy(float)[:, None])
        names.append("dark")
    for b in st["wb"]:
        cols.append((g.wbin.to_numpy() == b).astype(float)[:, None])
        names.append(f"wb_{b}")
    for c in extra:
        cols.append((g[c].to_numpy(float) - st[f"mu_{c}"])[:, None])
        names.append(c)
    if animal and len(st["levels"]) > 1:
        an = g.animal.to_numpy()
        for lv in st["levels"][1:]:
            cols.append((an == lv).astype(float)[:, None])
            names.append(f"animal_{lv}")
    return np.column_stack(cols), names, st


def rem_fit(T: pd.DataFrame, idx: np.ndarray, extra: tuple, animal: bool = True, dark: bool = True) -> dict:
    X, names, _ = rem_design(T, idx, extra, None, animal, dark)
    y = T.y.to_numpy()[idx].astype(int)
    if len(np.unique(y)) < 3:
        return {"ok": False}
    f = C.mnl_fit(X, y, T.block.to_numpy()[idx])
    return {"ok": True, "names": names, "B": f["B"], "cov": f["cov"], "n": len(idx), "n_nrem": int((y == 1).sum()),
            "n_wake": int((y == 2).sum()), "clusters": f["clusters"]}


def rem_dur_ols(Rb: pd.DataFrame, x: str, animal_fe: bool = True, dark: bool = True):
    d = Rb
    X = pd.DataFrame({x: d[x].astype(float)}, index=d.index)
    h = (d.t0.dt.hour + d.t0.dt.minute / 60).to_numpy()
    for k in (1, 2):
        X[f"sin{k}"], X[f"cos{k}"] = np.sin(2 * np.pi * k * h / 24), np.cos(2 * np.pi * k * h / 24)
    X["day"] = (d.t0 - pd.Timestamp("2026-08-30 19:00")).dt.total_seconds() / 86400
    if dark:
        X["dark"] = d.dark.astype(float)
    for b in WB_LEVELS[1:]:
        X[f"wb_{b}"] = (d.wbin == b).astype(float)
    return ols_fe(np.log(d.dur_s.astype(float)), X, [d.animal] if animal_fe else [], d.block if animal_fe else None)


def rem_prep(P: dict, w: pd.DataFrame, rain: pd.DataFrame, gaps: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    Rb = rem_bouts(P["recs"])
    j = join_temp(Rb.t0, w)
    Rb["temp_anom"] = j.temp_anom.to_numpy(float)
    Rb["rain_now"] = (j.rain_rate_mmh.fillna(0).to_numpy(float) > 0).astype(float)
    Rb["dark"] = dark_at(Rb.t0)
    Rb["period"] = period_of(Rb.t0)
    cls = dict(zip(rain.night_of, rain["class"]))
    c = np.array([cls.get(p, "unclassified") for p in Rb.period])
    Rb["night_cls"] = np.select([c == "rainy", c == "dry"], [1, 0], -1)
    Rb["rain_night"] = (Rb.night_cls == 1).astype(float)
    Rb["post_round"] = C.post_round_mask(Rb.animal.to_numpy(), Rb.t0, gaps)
    return Rb, rem_step_table(Rb)


# ================================================================== H14
def h14_run(P: dict, Rb: pd.DataFrame, T: pd.DataFrame, workers: int) -> dict:
    sc = P["sc"]
    D = P["D"]
    rows, pa = [], []
    # (1) REM bout duration (complete bouts, temp known, post-round excluded)
    d = Rb[Rb.complete & Rb.temp_anom.notna() & ~Rb.post_round]
    f = rem_dur_ols(d, "temp_anom")
    per = {}
    for an, g in d.groupby("animal"):
        if len(g) >= MIN_EV_ANIMAL:
            fa = rem_dur_ols(g, "temp_anom", animal_fe=False)
            per[an] = term(fa, "temp_anom")["coef"]
            pa.append({"scores": LABEL[sc], "measure": "ln REM bout duration", "animal": an, "n": len(g), **term(fa, "temp_anom")})
    rows.append(term_row(sc, "H14", "M1 ln REM bout duration (OLS)", "temp anomaly (per °C)", term(f, "temp_anom"), per, +1, len(d),
                         f"{len(d)} bouts"))
    # (2) REM -> WAKE and REM -> NREM hazards per 10-s REM step
    idx = np.flatnonzero((T.temp_anom.notna() & ~T.post_round).to_numpy())
    fr = rem_fit(T, idx, ("temp_anom",))
    per_w, per_n = {}, {}
    for an in sorted(T.animal.unique()):
        ia = idx[T.animal.to_numpy()[idx] == an]
        if len(ia) < 500:
            continue
        fa = rem_fit(T, ia, ("temp_anom",), animal=False)
        cw, cn_ = lc(fa, {"temp_anom": 1.0}, 1), lc(fa, {"temp_anom": 1.0}, 0)
        per_w[an], per_n[an] = cw["coef"], cn_["coef"]
        pa.append({"scores": LABEL[sc], "measure": "REM -> WAKE vs stay", "animal": an, "n": len(ia), **cw})
        pa.append({"scores": LABEL[sc], "measure": "REM -> NREM vs stay", "animal": an, "n": len(ia), **cn_})
    rows.append(term_row(sc, "H14", "M2 REM-step hazard: REM -> WAKE vs stay", "temp anomaly (per °C)", lc(fr, {"temp_anom": 1.0}, 1), per_w,
                         -1, len(idx), f"{fr.get('n_wake', 0)} REM -> WAKE"))
    rows.append(term_row(sc, "H14", "REM-step hazard: REM -> NREM vs stay (reported)", "temp anomaly (per °C)", lc(fr, {"temp_anom": 1.0}, 0),
                         per_n, 0, len(idx), f"{fr.get('n_nrem', 0)} REM -> NREM"))
    # (3) entry: NREM steps, B-full + temperature
    m = (~D["post_round"]) & np.isfinite(D["temp_anom"])
    ie = np.flatnonzero(m)
    spec = {**BF, "raw": ("temp_anom",)}
    jobs = [(f"{sc}|pooled", D, ie, spec)]
    for an in ANIMALS:
        ia = ie[D["animal"][ie] == an]
        if len(ia) > 2000:
            jobs.append((f"{sc}|animal:{an}", D, ia, {**spec, "animal": False}))
    fits = step_fits(jobs, workers)
    fp = fits[f"{sc}|pooled"]
    per_r = {an: lc(fits.get(f"{sc}|animal:{an}"), {"temp_anom": 1.0}, 0)["coef"] for an in ANIMALS if f"{sc}|animal:{an}" in fits}
    per_wk = {an: lc(fits.get(f"{sc}|animal:{an}"), {"temp_anom": 1.0}, 1)["coef"] for an in ANIMALS if f"{sc}|animal:{an}" in fits}
    for an in per_r:
        pa.append({"scores": LABEL[sc], "measure": "NREM -> REM vs stay (entry)", "animal": an, **lc(fits[f"{sc}|animal:{an}"], {"temp_anom": 1.0}, 0)})
    rows.append(term_row(sc, "H14", "entry: NREM-step hazard NREM -> REM vs stay", "temp anomaly (per °C)", lc(fp, {"temp_anom": 1.0}, 0), per_r,
                         0, len(ie), f"{fp.get('n_rem', 0)} REM entries"))
    rows.append(term_row(sc, "H14", "NREM-step hazard NREM -> WAKE vs stay (reported)", "temp anomaly (per °C)", lc(fp, {"temp_anom": 1.0}, 1),
                         per_wk, 0, len(ie), f"{fp.get('n_wake', 0)} WAKE exits"))
    ho = heldout(D, m, {"base": BF, "temp": spec}, "base", "temp", "entry: B-full + temp anomaly vs B-full (NREM steps, post-round excluded)",
                 workers)
    ho["scores"] = LABEL[sc]
    return {"rows": rows, "pa": pa, "ho": ho, "counts": {"bouts": len(d), "rem_steps": len(idx), "nrem_steps": len(ie)}}


# ================================================================== H15
def h15_specs() -> dict[str, dict]:
    loc = ("loc_field", "loc_unknown")
    return {"loc": {**BF, "raw": loc}, "group": {**BF, "raw": loc + ("n_coloc",), "raw_x_dark": ("n_coloc",)},
            "group_mates": {**BF, "raw": loc + ("n_coloc", "mates_asleep"), "raw_x_dark": ("n_coloc",)}}


PHASE_W = {"light": {"n_coloc": 1.0}, "dark": {"n_coloc": 1.0, "dark_x_n_coloc": 1.0}}


def house_entries(zone: dict, arr: dict) -> pd.DataFrame:
    """House entries (a field run >= 30 s followed by a house run >= 60 s) with the animal scored awake at the entry second;
    latency to the first NREM bout >= 60 s that starts before the stay ends (the first other-zone or unknown-zone run
    >= 30 s), before an unscored second, and within 4 h; else censored."""
    rows = []
    for an in ANIMALS:
        z, s = zone.get(an), arr.get(an)
        if z is None or s is None:
            continue
        # NREM bouts >= 60 s: their start seconds
        bst, ben, bv = runs(s)
        long_n = np.sort(bst[(bv == N) & ((ben - bst) >= ONSET_NREM_S)])
        unk = np.flatnonzero(s == 0)
        zs, ze, zv = runs(z)
        for k in range(1, len(zs)):
            h = zv[k]
            if h not in (1, 2) or (ze[k] - zs[k]) < HOUSE_MIN_S or zv[k - 1] != 3 or (ze[k - 1] - zs[k - 1]) < FIELD_MIN_S:
                continue
            t_in = int(zs[k])
            if s[t_in] != W:
                continue
            stop = len(z)
            for j in range(k + 1, len(zs)):
                if zv[j] != h and (ze[j] - zs[j]) >= AWAY_S:
                    stop = int(zs[j])
                    break
            u = unk[np.searchsorted(unk, t_in):]
            if len(u):
                stop = min(stop, int(u[0]))
            stop = min(stop, t_in + LAT_CAP_S)
            i = np.searchsorted(long_n, t_in)
            ev = i < len(long_n) and long_n[i] < stop
            T_s = (long_n[i] - t_in) if ev else (stop - t_in)
            others = [b for b in ANIMALS if b != an and b in zone]
            nco = int(sum(zone[b][t_in] == h for b in others))
            t = G0 + pd.Timedelta(seconds=t_in)
            rows.append({"animal": an, "t_in": t, "house": int(h), "T_s": max(int(T_s), 1), "event": int(ev), "n_coloc": nco,
                         "block": block_of(t)})
    E = pd.DataFrame(rows)
    if len(E):
        E["darkf"] = dark_at(E.t_in)
        E["T_day"] = (E.t_in - pd.Timestamp("2026-08-30 19:00")).dt.total_seconds() / 86400
    return E


def h15_run(P: dict, zone: dict, gaps: pd.DataFrame, workers: int) -> dict:
    from sleep_explore import cox, cterm
    sc = P["sc"]
    D = P["D"]
    S = h15_specs()
    idx = np.flatnonzero(~D["post_round"])
    jobs = [(f"{sc}|group", D, idx, S["group"]), (f"{sc}|group_mates", D, idx, S["group_mates"])]
    for an in ANIMALS:
        ia = idx[D["animal"][idx] == an]
        if len(ia) > 2000:
            jobs.append((f"{sc}|animal:{an}", D, ia, {**S["group"], "animal": False}))
    fits = step_fits(jobs, workers)
    rows, pa = [], []
    for model, fk in (("B-full + location + n_coloc (x dark)", "group"), ("+ share of co-located mates asleep (Step C3's model; sensitivity)", "group_mates")):
        fp = fits[f"{sc}|{fk}"]
        for eq, eqn, pred in ((1, "NREM -> WAKE vs stay (maintenance)", 0), (0, "NREM -> REM vs stay (entry)", 0)):
            for ph, wv in PHASE_W.items():
                per = {}
                if fk == "group":
                    for an in ANIMALS:
                        fa = fits.get(f"{sc}|animal:{an}")
                        if fa is not None and fa.get("ok"):
                            v = lc(fa, wv, eq)
                            per[an] = v["coef"]
                            pa.append({"scores": LABEL[sc], "equation": eqn, "phase": ph, "animal": an, **v})
                r = term_row(sc, "H15", f"{model}: {eqn}", f"n_coloc per mate, {ph}", lc(fp, wv, eq), per, pred, fp.get("n", 0),
                             f"{fp.get('n_wake' if eq == 1 else 'n_rem', 0)} {'WAKE exits' if eq == 1 else 'REM entries'}")
                if fk != "group":
                    r["holds_term"] = None
                rows.append(r)
    ho = heldout(D, ~D["post_round"], {"loc": S["loc"], "group": S["group"]}, "loc", "group",
                 "+ n_coloc and n_coloc x dark on B-full + location (post-round excluded)", workers)
    ho["scores"] = LABEL[sc]
    # sleep-onset latency after a house entry
    E = house_entries(zone, P["arr"])
    E["post_round"] = C.post_round_mask(E.animal.to_numpy(), E.t_in, gaps) if len(E) else []
    E = E[~E.post_round] if len(E) else E
    lat = []
    for ph, dk in (("light", 0.0), ("dark", 1.0)):
        g = E[E.darkf == dk]
        cx = cox(g, ["n_coloc", "T_day"], T="T_s", E="event", strata="animal", groups="block") if len(g) else None
        c = cterm(cx, "n_coloc")
        per = {}
        for an, ga in g.groupby("animal"):
            if len(ga) >= MIN_EV_ANIMAL and ga.event.sum() >= 5 and ga.n_coloc.nunique() > 1:
                ca = cterm(cox(ga, ["n_coloc", "T_day"], strata=None, groups=None), "n_coloc")
                per[an] = ca["coef"]
                pa.append({"scores": LABEL[sc], "equation": "sleep onset after a house entry (Cox)", "phase": ph, "animal": an, **{k: ca[k] for k in ("coef", "se", "ci_lo", "ci_hi", "p")}})
        r = term_row(sc, "H15", "sleep-onset latency after a house entry (Cox, animal strata): log HR of falling asleep",
                     f"n_coloc per mate, {ph}", {k: c[k] for k in ("coef", "se", "ci_lo", "ci_hi", "p")}, per, 0, len(g),
                     f"{int(g.event.sum()) if len(g) else 0} onsets / {len(g)} entries")
        r["holds_term"] = None
        rows.append(r)
        lat.append(g.assign(phase=ph))
    return {"rows": rows, "pa": pa, "ho": ho, "entries": E}


# ================================================================== H16
def house_exits(zone: dict) -> pd.DataFrame:
    """Exits: a house run >= 60 s directly followed by a field run >= 30 s; t_e = the first field second."""
    rows = []
    for an in ANIMALS:
        z = zone.get(an)
        if z is None:
            continue
        zs, ze, zv = runs(z)
        for k in range(len(zs) - 1):
            if zv[k] in (1, 2) and (ze[k] - zs[k]) >= HOUSE_MIN_S and zv[k + 1] == 3 and (ze[k + 1] - zs[k + 1]) >= FIELD_MIN_S:
                rows.append({"leaver": an, "t_e": int(zs[k + 1]), "house": int(zv[k])})
    return pd.DataFrame(rows)


def _partner_ok(zb: np.ndarray, sb: np.ndarray, t: int, house: int | None) -> int | None:
    """The partner condition at second t: in a house (house h if given) for >= 80 % of [t - 60, t) and at t - 1, asleep
    (NREM / REM) over [t - 30, t), scored over [t, t + 120). Returns the house or None."""
    if t - HOUSE_MIN_S < 0 or t + H16_WIN_S > len(zb):
        return None
    h = int(zb[t - 1])
    if h not in (1, 2) or (house is not None and h != house):
        return None
    if np.mean(zb[t - HOUSE_MIN_S:t] == h) < MATE_SHARE:
        return None
    pre = sb[t - ASLEEP_S:t]
    if not np.all((pre == N) | (pre == R)):
        return None
    if np.any(sb[t:t + H16_WIN_S] == 0):
        return None
    return h


def _woke(sb: np.ndarray, t: int) -> tuple[int, int]:
    """(any WAKE second in [t, t + 120), a WAKE bout >= 40 s starting in [t, t + 120))."""
    seg = sb[t:t + H16_WIN_S]
    w = seg == W
    if not w.any():
        return 0, 0
    i = int(np.argmax(w))
    long_ = 0
    j = t + i
    while j < t + H16_WIN_S:
        if sb[j] == W:
            k = j
            while k < len(sb) and sb[k] == W:
                k += 1
            if k - j >= MA_S:
                long_ = 1
                break
            j = k
        else:
            j += 1
    return 1, long_


def h16_pairs(zone: dict, arr: dict, exits: pd.DataFrame, shifts=SHIFTS_MIN) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(exit, partner) pairs meeting the partner condition, with the outcome; and the time-shifted chance samples of each
    pair: t' = t_e + delta (delta = +-shifts min) with the partner condition (any house), >= 1 other tagged animal in the
    partner's house at t' - 1, and no exit from that house within 120 s of t'."""
    ex_by_house = {h: np.sort(exits[exits.house == h].t_e.to_numpy()) for h in (1, 2)} if len(exits) else {1: np.zeros(0), 2: np.zeros(0)}
    rows, ch = [], []
    pid = 0
    for e in exits.itertuples():
        for B in ANIMALS:
            if B == e.leaver or B not in zone or B not in arr:
                continue
            zb, sb = zone[B], arr[B]
            if _partner_ok(zb, sb, e.t_e, e.house) is None:
                continue
            o, ol = _woke(sb, e.t_e)
            t = G0 + pd.Timedelta(seconds=int(e.t_e))
            rows.append({"pair": pid, "leaver": e.leaver, "partner": B, "t_e": int(e.t_e), "t": t, "house": e.house, "woke": o, "woke_ge40": ol,
                         "partner_state": "REM" if sb[e.t_e - 1] == R else "NREM", "block": block_of(t)})
            for sgn in (-1, 1):
                for m in shifts:
                    ts = int(e.t_e + sgn * 60 * m)
                    h2 = _partner_ok(zb, sb, ts, None)
                    if h2 is None:
                        continue
                    if not any(zone[A][ts - 1] == h2 for A in ANIMALS if A != B and A in zone):
                        continue
                    ex = ex_by_house[h2]
                    k = np.searchsorted(ex, ts - H16_WIN_S)
                    if k < len(ex) and ex[k] <= ts + H16_WIN_S:
                        continue
                    o2, ol2 = _woke(sb, ts)
                    ch.append({"pair": pid, "partner": B, "shift_min": sgn * m, "woke": o2, "woke_ge40": ol2})
            pid += 1
    return pd.DataFrame(rows), pd.DataFrame(ch)


def h16_ratio(Pp: pd.DataFrame, Ch: pd.DataFrame, col: str, rng=None, n_boot: int = 2000) -> dict:
    """Observed / expected: expected = sum over pairs of the pair's mean time-shifted outcome (pairs with >= 1 chance
    sample); per partner the same; 95 % CI by bootstrap over day-half blocks."""
    if not len(Pp) or not len(Ch):
        return {"ratio": np.nan}
    cm = Ch.groupby("pair")[col].mean().rename("chance")
    d = Pp.join(cm, on="pair").dropna(subset=["chance"])
    if not len(d):
        return {"ratio": np.nan}
    obs, exp = float(d[col].sum()), float(d.chance.sum())
    r = {"pairs": len(d), "observed": obs, "expected": exp, "p_obs": obs / len(d), "p_chance": exp / len(d),
         "ratio": obs / exp if exp > 0 else np.nan}
    per = d.groupby("partner").apply(lambda g: pd.Series({"pairs": len(g), "observed": g[col].sum(), "expected": g.chance.sum()}), include_groups=False)
    per["ratio"] = per.observed / per.expected.replace(0, np.nan)
    r["per"] = per
    rng = rng or np.random.default_rng(0)
    bl = d.block.to_numpy()
    ub = np.unique(bl)
    agg = d.groupby("block").agg(o=(col, "sum"), e=("chance", "sum"))
    o_b, e_b = agg.o.reindex(ub).to_numpy(), agg.e.reindex(ub).to_numpy()
    bs = []
    for _ in range(n_boot):
        i = rng.integers(0, len(ub), len(ub))
        if e_b[i].sum() > 0:
            bs.append(o_b[i].sum() / e_b[i].sum())
    r["ci_lo"], r["ci_hi"] = (float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))) if bs else (np.nan, np.nan)
    return r


# ================================================================== H17
def h17_table(P: dict, zone: dict, gaps: pd.DataFrame) -> pd.DataFrame:
    from sleep_explore import post_wake_table
    tab = post_wake_table(P["recs"])
    if tab.empty:
        return tab
    byid = {rc["record_id"]: rc for rc in P["recs"]}
    pre, post, npre, npost = [], [], [], []
    for r in tab.itertuples():
        rc = byid[r.record_id]
        st = rc["state"]
        an = rc["animal"]
        off = int((rc["start"] - G0).total_seconds())
        z = zone.get(an)

        def site(lo: int, hi: int) -> tuple[int, int]:
            if z is None or hi <= lo:
                return 0, 0
            s_ = st[lo:hi]
            zz = z[off + lo:off + hi] if (off + hi) <= len(z) and off + lo >= 0 else np.zeros(hi - lo, np.int8)
            m = ((s_ == N) | (s_ == R)) & (zz > 0)
            if m.sum() < SITE_MIN:
                return 0, int(m.sum())
            v = np.bincount(zz[m], minlength=4)
            return int(np.argmax(v)), int(m.sum())
        p_, k1 = site(max(0, r.wake_a - SITE_S), r.wake_a)
        q_, k2 = site(r.wake_b, min(r.stop, r.wake_b + SITE_S) if r.stop > r.wake_b else r.wake_b)
        pre.append(p_)
        post.append(q_)
        npre.append(k1)
        npost.append(k2)
    tab["site_pre"], tab["site_post"], tab["n_site_pre"], tab["n_site_post"] = pre, post, npre, npost
    tab["houses_known"] = tab.site_pre.isin([1, 2]) & tab.site_post.isin([1, 2])
    tab["site_change"] = (tab.site_pre != tab.site_post).astype(float)
    tab["post_round"] = C.post_round_mask(tab.animal.to_numpy(), tab.t_wake_end, gaps)
    tab["d_bin"] = [wbin(float(d)) for d in tab.d_s]
    return tab


H17_COLS = ["site_change", "l_d", "l_npre", "anchor", "sin1", "cos1", "sin2", "cos2", "darkf"]


def h17_run(tab: pd.DataFrame, sc: str) -> dict:
    from sleep_explore import cox, cterm, ols
    rows = []
    for nm, d in (("primary: both sites a house (house_1 / house_2)", tab[tab.houses_known]),
                  ("sensitivity: field as a site too", tab[tab.site_pre.isin([1, 2, 3]) & tab.site_post.isin([1, 2, 3])]),
                  ("sensitivity: post-round 3 h excluded", tab[tab.houses_known & ~tab.post_round])):
        cx = cox(d, H17_COLS, strata="animal", groups="block")
        c = cterm(cx, "site_change")
        dd = d.copy()
        dd["strat"] = dd.animal + "|" + dd.d_bin.astype(str)
        cx2 = cox(dd, H17_COLS, strata="strat", groups="block")
        c2 = cterm(cx2, "site_change")
        ev = d[(d.event == 1) & (d.T_s > 0)]
        fo = ols(ev.l_T, ev[H17_COLS], groups=ev.block, fe=ev.animal) if len(ev) >= 20 and ev.site_change.nunique() > 1 else None
        t_ = term(fo, "site_change") if fo is not None else {"coef": np.nan, "ci_lo": np.nan, "ci_hi": np.nan, "p": np.nan}
        per = {}
        for an, g in d.groupby("animal"):
            if len(g) >= 10 and g.event.sum() >= 5 and g.site_change.sum() >= 3:
                ca = cox(g, ["site_change", "l_d", "darkf"], strata=None, groups=None)
                per[an] = -cterm(ca, "site_change")["coef"]
        delay = {"coef": -c["coef"], "se": c["se"], "ci_lo": -c["ci_hi"], "ci_hi": -c["ci_lo"], "p": c["p"]}
        r = term_row(sc, "H17", nm, "site change: delay = -log HR of REM entry", delay, per, +1, len(d),
                     f"{int(d.event.sum())} reach REM; {int(d.site_change.sum())} site changes")
        r["holds_term"] = None
        r.update(HR=c.get("HR"), HR_lo=np.exp(c["ci_lo"]) if np.isfinite(c["ci_lo"]) else np.nan, HR_hi=np.exp(c["ci_hi"]) if np.isfinite(c["ci_hi"]) else np.nan,
                 HR_wakebin_strata=c2.get("HR"), HR_wakebin_lo=np.exp(c2["ci_lo"]) if np.isfinite(c2["ci_lo"]) else np.nan,
                 HR_wakebin_hi=np.exp(c2["ci_hi"]) if np.isfinite(c2["ci_hi"]) else np.nan,
                 ols_lnT_site_change=t_["coef"], ols_lnT_ci=f"[{t_['ci_lo']:+.2f}, {t_['ci_hi']:+.2f}]",
                 n_change=int(d.site_change.sum()), n_same=int((d.site_change == 0).sum()), dark_share_change=float(d[d.site_change == 1].darkf.mean()) if d.site_change.sum() else np.nan,
                 dark_share_same=float(d[d.site_change == 0].darkf.mean()) if (d.site_change == 0).sum() else np.nan,
                 median_d_min_change=float(d[d.site_change == 1].d_s.median() / 60) if d.site_change.sum() else np.nan,
                 median_d_min_same=float(d[d.site_change == 0].d_s.median() / 60) if (d.site_change == 0).sum() else np.nan)
        rows.append(r)
    return {"rows": rows}


# ================================================================== H22
def h22_run(P: dict, T: pd.DataFrame, workers: int) -> dict:
    sc = P["sc"]
    D = P["D"]
    m = (D["dark"] == 1) & (D["night_cls"] >= 0) & (~D["post_round"])
    idx = np.flatnonzero(m)
    base = {**BF, "dark": False}
    sp_r = {**base, "raw": ("rain_night",)}
    sp_n = {**base, "raw": ("rain_now",)}
    jobs = [(f"{sc}|rain", D, idx, sp_r), (f"{sc}|now", D, idx, sp_n)]
    for an in ANIMALS:
        ia = idx[D["animal"][idx] == an]
        if len(ia) > 1500 and len(np.unique(D["rain_night"][ia])) > 1:
            jobs.append((f"{sc}|animal:{an}", D, ia, {**sp_r, "animal": False}))
    fits = step_fits(jobs, workers)
    rows, pa = [], []
    fr = fits[f"{sc}|rain"]
    for eq, eqn, pred in ((0, "NREM -> REM vs stay (REM entry)", -1), (1, "NREM -> WAKE vs stay (WAKE exit)", +1)):
        per = {}
        for an in ANIMALS:
            fa = fits.get(f"{sc}|animal:{an}")
            if fa is not None and fa.get("ok"):
                v = lc(fa, {"rain_night": 1.0}, eq)
                per[an] = v["coef"]
                pa.append({"scores": LABEL[sc], "equation": eqn, "animal": an, **v})
        rows.append(term_row(sc, "H22", f"night NREM steps, B-full (no dark step) + rainy night: {eqn}", "rainy vs dry night",
                             lc(fr, {"rain_night": 1.0}, eq), per, pred, fr.get("n", 0),
                             f"{fr.get('n_rem' if eq == 0 else 'n_wake', 0)} {'REM entries' if eq == 0 else 'WAKE exits'}"))
    fn = fits[f"{sc}|now"]
    for eq, eqn in ((0, "NREM -> REM vs stay"), (1, "NREM -> WAKE vs stay")):
        r = term_row(sc, "H22", f"sensitivity: raining now (console rate > 0, +-15 min): {eqn}", "raining now", lc(fn, {"rain_now": 1.0}, eq), {},
                     0, fn.get("n", 0))
        r["holds_term"] = None
        rows.append(r)
    # REM steps of the same nights: REM -> WAKE
    it = np.flatnonzero(((T.dark == 1) & (T.night_cls >= 0) & ~T.post_round).to_numpy())
    frm = rem_fit(T, it, ("rain_night",), dark=False)
    for eq, eqn in ((1, "REM-step hazard REM -> WAKE vs stay"), (0, "REM-step hazard REM -> NREM vs stay")):
        r = term_row(sc, "H22", f"night REM steps: {eqn}", "rainy vs dry night", lc(frm, {"rain_night": 1.0}, eq), {}, 0, len(it),
                     f"{frm.get('n_wake' if eq == 1 else 'n_nrem', 0)} exits")
        r["holds_term"] = None
        rows.append(r)
    ho = heldout(D, m, {"base": base, "rain": sp_r}, "base", "rain", "night NREM steps: B-full + rainy night vs B-full (post-round excluded)",
                 workers)
    fo = cal_folds(D, m)
    ho["rainy_test_blocks"] = ", ".join(sorted({str(D["block"][te][0]) for _, te in fo if D["rain_night"][te].max() > 0}))
    ho["scores"] = LABEL[sc]
    rf = pd.Series(D["night_cls"][idx]).value_counts()
    return {"rows": rows, "pa": pa, "ho": ho, "counts": {"night_steps": len(idx), "rainy_steps": int(rf.get(1, 0)), "dry_steps": int(rf.get(0, 0)),
                                                          "rem_night_steps": len(it)}}


# ================================================================== H25 (description only, after the cut)
def after_cut_records(states: Path) -> list[dict]:
    """Sessions overlapping [CUTOFF, PADDOCK_END) with the FINAL-score inclusion rules except the cut; whole records (their
    first minutes before the cut give the counter its history; only seconds >= CUTOFF are described)."""
    from sleep_cycles_v2 import build_records
    from sleep_quant import MIN_SESSION_H, PADDOCK_END
    rv = pd.read_csv(REVIEW)
    rv["start"] = pd.to_datetime(rv.start_local)
    keep, ends = [], []
    for r in rv.itertuples():
        tags = r.tags if isinstance(r.tags, str) else ""
        e = PADDOCK_END
        for t in tags.split(";"):
            if t.startswith("valid_until "):
                e = min(e, pd.Timestamp(t[len("valid_until "):]))
        endt = r.start + pd.Timedelta(hours=float(r.duration_h or 0))
        keep.append((states / r.animal / f"{r.session}.states.npz").exists() and r.verdict != "noise" and "SF12_contact_failing" not in tags
                    and (r.duration_h or 0) >= MIN_SESSION_H and r.start < e and endt > CUTOFF)
        ends.append(e)
    rv["end_cut"] = ends
    return build_records(rv[keep].copy(), states)


def window_metrics(recs: list[dict], an: str, t0: pd.Timestamp, t1: pd.Timestamp) -> dict | None:
    rec_s = nrem_s = rem_s = 0
    rem_on = n2w = ma = wl = 0
    rem_d = []
    for rc in recs:
        if rc["animal"] != an or rc["end"] <= t0 or rc["start"] >= t1:
            continue
        st = rc["state"]
        lo = max(0, int(np.ceil((t0 - rc["start"]).total_seconds())))
        hi = min(len(st), int((t1 - rc["start"]).total_seconds()))
        if hi <= lo:
            continue
        seg = st[lo:hi]
        rec_s += int((seg != 0).sum())
        nrem_s += int((seg == N).sum())
        rem_s += int((seg == R).sum())
        for s, a, b in bouts(st):
            if a < lo or a >= hi or a == 0 or st[a - 1] == 0:
                continue
            if s == R:
                rem_on += 1
                if b < len(st) and st[b] != 0:
                    rem_d.append(b - a)
            if s == W and st[a - 1] == N:
                n2w += 1
                if b < len(st) and st[b] == N and (b - a) < MA_S:
                    ma += 1
                elif (b - a) >= MA_S:
                    wl += 1
    if rec_s < 1800:
        return None
    nh = nrem_s / 3600
    return {"rec_h": rec_s / 3600, "sleep_share_pct": 100 * (nrem_s + rem_s) / rec_s, "nrem_min_per_h": 60 * nrem_s / rec_s,
            "rem_min_per_h": 60 * rem_s / rec_s, "rem_share_of_sleep_pct": 100 * rem_s / max(nrem_s + rem_s, 1),
            "rem_bouts_per_nrem_h": rem_on / nh if nh > 0 else np.nan, "nrem_to_wake_per_nrem_h": n2w / nh if nh > 0 else np.nan,
            "ma_per_nrem_h": ma / nh if nh > 0 else np.nan, "wake_ge40_from_nrem_per_nrem_h": wl / nh if nh > 0 else np.nan,
            "mean_rem_bout_s": float(np.mean(rem_d)) if rem_d else np.nan}


H25_METRICS = ["sleep_share_pct", "rem_share_of_sleep_pct", "rem_bouts_per_nrem_h", "nrem_to_wake_per_nrem_h", "ma_per_nrem_h",
               "wake_ge40_from_nrem_per_nrem_h", "mean_rem_bout_s", "OE_rem_entries", "OE_wake_exits"]


def arrays_for(recs: list[dict]) -> tuple[dict, pd.DataFrame]:
    steps = build_data(recs, {KEY: variant_specs()[KEY]})
    D = to_arrays(steps)
    D["hour"] = steps.hour.to_numpy().astype(float)
    D["d_prev"] = steps.d_prev.to_numpy().astype(float)
    return D, steps


def h25_run(sc: str, P: dict) -> dict:
    from sleep_quant import sun_times
    recs_pre = P["recs"]
    recs_after = after_cut_records(SCORINGS[sc])
    # the B-full fit on all pre-cut NREM steps (Step C engine, no exclusion: the after-cut night follows an evening round)
    Dp, sp = P["D"], P["steps"]
    idx = np.arange(len(Dp["y"]))
    levels = sorted(set(Dp["animal"]))
    X, names, st = C.design(Dp, idx, BF, None, levels)
    f = C.mnl_fit(X, Dp["y"].astype(int))
    pp = C.mnl_predict(X, f["B"])
    Da, sa = arrays_for(recs_after)
    ia = np.arange(len(Da["y"]))
    ok_an = np.isin(Da["animal"], levels)
    Xa, _, _ = C.design(Da, ia[ok_an], BF, st, levels)
    pa_ = np.full((len(ia), 3), np.nan)
    pa_[ok_an] = C.mnl_predict(Xa, f["B"])
    animals_after = sorted({rc["animal"] for rc in recs_after})
    rows = []

    def oe(steps: pd.DataFrame, p: np.ndarray, an: str, t0, t1) -> tuple[float, float]:
        m = (steps.animal.to_numpy() == an) & (steps.t >= t0).to_numpy() & (steps.t < t1).to_numpy()
        if m.sum() < 60:
            return np.nan, np.nan
        y = steps.y.to_numpy()[m]
        return float((y == 1).sum() / max(np.nansum(p[m, 1]), 1e-9)), float((y == 2).sum() / max(np.nansum(p[m, 2]), 1e-9))
    for an in animals_after:
        for d in pd.date_range("2026-08-30", "2026-09-11"):
            sr1 = pd.Timestamp(sun_times((d + pd.Timedelta(days=1)).date())[0])
            a0 = d + pd.Timedelta(hours=19, minutes=40)
            a2 = d + pd.Timedelta(days=1, hours=10, minutes=10)
            after = d == pd.Timestamp("2026-09-11")
            recs = recs_after if after else recs_pre
            for part, (t0, t1) in (("night 19:40 -> sunrise", (a0, sr1)), ("morning sunrise -> 10:10", (sr1, a2))):
                m = window_metrics(recs, an, t0, t1)
                if m is None:
                    continue
                o_r, o_w = oe(sa if after else sp, pa_ if after else pp, an, t0, t1)
                rows.append({"scores": LABEL[sc], "animal": an, "night_of": f"{d:%Y-%m-%d}", "after_cut": after, "part": part, **m,
                             "OE_rem_entries": o_r, "OE_wake_exits": o_w})
    T = pd.DataFrame(rows)
    summ = []
    for (an, part), g in T.groupby(["animal", "part"]):
        a = g[g.after_cut]
        b = g[~g.after_cut]
        if not len(a) or not len(b):
            continue
        for mtr in H25_METRICS:
            v = float(a[mtr].iloc[0])
            bv = b[mtr].dropna()
            summ.append({"scores": LABEL[sc], "animal": an, "part": part, "metric": mtr, "after_cut": v, "before_mean": float(bv.mean()),
                         "before_min": float(bv.min()) if len(bv) else np.nan, "before_max": float(bv.max()) if len(bv) else np.nan,
                         "before_nights": len(bv), "after_rank_from_low": int((bv < v).sum()) + 1 if np.isfinite(v) else np.nan,
                         "outside_range": bool(np.isfinite(v) and len(bv) and (v < bv.min() or v > bv.max()))})
    return {"T": T, "S": pd.DataFrame(summ), "animals": animals_after,
            "after_rec_h": float(T[T.after_cut].rec_h.sum()) if len(T) else 0.0}


# ================================================================== figures
def _forest(ax, df: pd.DataFrame, title: str, xlabel: str, ref: float = 0.0) -> None:
    y = np.arange(len(df))[::-1]
    for yy, r in zip(y, df.itertuples()):
        c = COL.get(r.scores, COL["ink"])
        ax.errorbar([r.coef], [yy], xerr=[[max(r.coef - r.ci_lo, 0)], [max(r.ci_hi - r.coef, 0)]] if np.isfinite(r.ci_lo) else None,
                    fmt="s", color=c, ms=6, capsize=3, lw=1.2)
        an = [getattr(r, f"an_{a}", np.nan) for a in ANIMALS]
        ax.plot([v for v in an if np.isfinite(v)], [yy] * sum(np.isfinite(an)), "o", color=c, ms=3, alpha=0.45)
    ax.axvline(ref, color=COL["ink"], lw=0.7)
    ax.set_yticks(y, [f"{r.scores}: {r.label}" for r in df.itertuples()], fontsize=7)
    ax.set_xlabel(xlabel, fontsize=8)
    ax.set_title(title, fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)


def fig_terms(panels: list[tuple[str, pd.DataFrame, str]], path: Path, title: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sleep_quant import save_fig
    n = len(panels)
    h = max(3.0, 0.38 * max(len(p[1]) for p in panels) + 1.4)
    fig, axs = plt.subplots(1, n, figsize=(6.2 * n, h), squeeze=False)
    for ax, (t, df, xl) in zip(axs[0], panels):
        if len(df):
            _forest(ax, df, t, xl)
    fig.suptitle(title, fontsize=9)
    fig.tight_layout()
    save_fig(fig, path)
    plt.close(fig)


def fig_h16(per: pd.DataFrame, path: Path, title: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sleep_quant import save_fig
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.2))
    for ax, col in zip(axs, ("woke", "woke_ge40")):
        g = per[per.outcome == col]
        labs = list(dict.fromkeys(g.scores))
        for j, lab in enumerate(labs):
            q = g[g.scores == lab].reset_index(drop=True)
            x = np.arange(len(q)) + (j - 0.5) * 0.35
            ax.bar(x - 0.08, q.p_obs, 0.16, color=COL.get(lab), label=f"{lab} observed")
            ax.bar(x + 0.08, q.p_chance, 0.16, color=COL.get(lab), alpha=0.35, label=f"{lab} time-shift chance")
            ticks = list(q.partner)
        ax.set_xticks(np.arange(len(ticks)), ticks, fontsize=8)
        ax.set_ylabel("P(partner WAKE within 2 min)" if col == "woke" else "P(partner WAKE bout >= 40 s within 2 min)", fontsize=8)
        ax.legend(fontsize=7, frameon=False)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(title, fontsize=9)
    fig.tight_layout()
    save_fig(fig, path)
    plt.close(fig)


def fig_h17(tabs: dict[str, pd.DataFrame], path: Path, title: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sleep_quant import save_fig
    from sleep_schedule_phase3 import km
    fig, axs = plt.subplots(1, len(tabs), figsize=(6 * len(tabs), 4.2), squeeze=False)
    for ax, (lab, t) in zip(axs[0], tabs.items()):
        d = t[t.houses_known]
        for chg, c, nm in ((0.0, COL["ink"], "same house"), (1.0, COL["after"], "other house")):
            g = d[d.site_change == chg]
            if len(g) < 3:
                continue
            ut, S = km(g.T_s.to_numpy(float) / 60, g.event.to_numpy(int))
            ax.step(np.r_[0, ut], np.r_[1, S], where="post", color=c, label=f"{nm} (n {len(g)})")
        ax.set_xlabel("NREM (+ MA) minutes after the wake", fontsize=8)
        ax.set_ylabel("share not yet in REM (Kaplan-Meier)", fontsize=8)
        ax.set_title(lab, fontsize=9)
        ax.legend(fontsize=7, frameon=False)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(title, fontsize=9)
    fig.tight_layout()
    save_fig(fig, path)
    plt.close(fig)


def fig_h25(T: pd.DataFrame, path: Path, title: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sleep_quant import save_fig
    mets = ["rem_bouts_per_nrem_h", "nrem_to_wake_per_nrem_h", "sleep_share_pct", "OE_rem_entries", "OE_wake_exits"]
    g = T[(T.scores == T.scores.iloc[0]) & (T.part.str.startswith("night"))]
    fig, axs = plt.subplots(1, len(mets), figsize=(3.4 * len(mets), 3.8))
    for ax, m in zip(axs, mets):
        ans = sorted(g.animal.unique())
        for i, an in enumerate(ans):
            b = g[(g.animal == an) & ~g.after_cut][m]
            a = g[(g.animal == an) & g.after_cut][m]
            ax.plot(np.full(len(b), i) + np.random.default_rng(i).uniform(-0.12, 0.12, len(b)), b, "o", color=COL["grey"], ms=3)
            ax.plot(np.full(len(a), i), a, "D", color=COL["after"], ms=6)
        ax.set_xticks(range(len(ans)), ans, fontsize=7)
        ax.set_title(m, fontsize=8)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(title, fontsize=9)
    fig.tight_layout()
    save_fig(fig, path)
    plt.close(fig)


# ================================================================== report text
DEFINITIONS = [
    "## Definitions", "",
    r"Time = field-PC local time. States per second $s_t \in \{0\ \text{unknown}, 1\ \text{WAKE}, 3\ \text{NREM}, 5\ \text{REM}\}$; "
    r"records = sessions joined across splits ≤ 60 s (`sleep_model.records_for`); everything from 2026-09-11 19:40 is cut "
    r"(except H25, which describes only that period). Light = NOAA sunrise–sunset at the field (`sleep_quant.sun_times`); "
    r"**dark** ∈ {0, 1} at the step / event time. Day-half **block** = the record's 06–18 h ('D') or 18–06 h ('N') half "
    r"(events not tied to a record: the half of the event time). **Post-round exclusion** (plan §3): steps / events in "
    r"$[g_{end}, g_{end} + 3\,\text{h})$ of a Phase-0 gap with cause `round_logged` / `round_inferred` of the same animal. "
    r"**Scorings:** FINAL (`states_1s_final`) and pass2med (`states_1s_pass2med`, fixed per-animal thresholds); every test "
    r"below compares different sessions (warm / cold, rainy / dry, active / quiet, after an exit / at shifted times), so "
    r"both are run and a rule must be met on both.",
    "",
    "### Shared estimation",
    r"- **NREM step model** (Step C's engine, `sleep_explore_c.mnl_fit`). Per 10-s NREM step, outcome $y \in$ {stay, REM, WAKE}; "
    r"$\Pr(y = j) = e^{\eta_j}/(1 + e^{\eta_R} + e^{\eta_W})$, $\eta_j = \alpha_j + x^\top\beta_j$, Newton–Raphson with an L2 "
    r"penalty $10^{-4}\lVert\beta\rVert^2/2$. **B-full** $x$ = cubic B-spline of $\ln(e + 5)$ ($e$ = s since the bout start), "
    r"cubic B-spline of $\ln(1 + P_t)$ with the REM-entry count $P$ at `P_tw600_k0` (+1/60 per NREM s, ×$e^{-d/600}$ over a wake "
    r"of $d$ s, emptied by REM, frozen over unknown), $(\sin, \cos)(2\pi k h/24)$, $k = 1, 2$, dark, $\ell = \ln(1 + d) - "
    r"\overline{\ln(1+d)}$ ($d$ = the wake before the NREM bout, 0 after REM / unknown; **matched prior wake**), previous bout "
    r"REM / unknown, wake share of the last 10 min, days since release (z), REM-anchor flag, animal intercepts. Added terms "
    r"enter centred in raw units (coefficient = log-odds per unit). A coefficient on REM vs stay ($\beta_R$) is the log-odds "
    r"ratio of entering REM in the next 10 s rather than staying in NREM; on WAKE vs stay ($\beta_W$) the same for waking.",
    r"- **REM step model.** Per 10-s step of every REM bout with a scored start (as `sleep_sim.rem_steps`): $y \in$ "
    r"{stay, → NREM, → WAKE} (last step; censored if the exit is unscored), $x$ = spline $\ln(e + 5)$, 2-harmonic clock, days "
    r"(z), dark, prior-wake bin of the bout (the last WAKE bout > 120 s before the onset with no unknown epoch between: 2–7, "
    r"7–30, 30–120 min, ≥ 2 h, reference 'none'), added term, animal intercepts; same engine.",
    r"- **Cluster-robust CI.** $\hat V = H^{-1}(\sum_g U_g U_g^\top)H^{-1}\,G/(G-1)$ over day-half blocks $g$ (multinomials, Cox, "
    r"OLS alike); 95 % CI $= \hat\beta \pm 1.96\,\widehat{se}$; for a phase-specific effect $w^\top\hat\beta$ with $\widehat{se} = "
    r"\sqrt{w^\top\hat V w}$.",
    r"- **Per-animal signs.** The same model fitted to each animal alone (no animal terms); count of animals whose estimate "
    r"has the hypothesised sign (or the pooled sign when the rule has none). Estimates with $\widehat{se} > 10$ (an "
    r"unidentified, penalised term) are treated as missing.",
    r"- **A term holds** = its pooled 95 % CI excludes 0 with the hypothesised sign AND ≥ 5 of the 6 rats have that sign in "
    r"per-animal fits. **Held-out comparison holds** (plan §3) = forward chaining over the day-half blocks (train on all "
    r"earlier blocks, test the next, the first 6 blocks only train); $\Delta = 100(\bar\ell_{+} - \bar\ell_{base})/\bar\ell_{base}$ "
    r"(per-step log loss, step-weighted over folds), 95 % CI by bootstrap over folds; holds = CI < 0 and ≥ 5/6 animals better. "
    r"The folds are the calendar blocks of all NREM steps; a comparison on a sub-set of steps (e.g. night steps) trains and "
    r"tests on that sub-set within the same calendar folds.",
    r"- **Verdicts.** HOLDS = the pass rule is met on both scorings; INCONCLUSIVE = met on one scoring only, or not computable "
    r"(too few events); DOES NOT HOLD = met on neither. H25 = DESCRIPTION ONLY.",
    "",
    "### WISER (all parts that use it)",
    r"- **Zone** per second (Step C's cache `zone_per_second.npz`, re-read): the second's median default-track position "
    r"(V3 for the implanted animals, B2 elsewhere; fixes flagged `m_off_animal` removed), forward-filled over gaps ≤ 30 s, "
    r"in house_1 / house_2 = the ROI rectangle + 14 in, else field; unknown = no position. 'Same house' is never body "
    r"contact; WISER jitter ~4–7 in. SF11 has no tag after 2026-09-07 08:20 (its zone is unknown, and it is never counted as a "
    r"housemate after that); the five females released 2026-09-11 19:40 have no tags.",
    r"- **n_coloc** = other tagged animals in the same house at the second (0 when not in a house); **mates_asleep** = share "
    r"of those with a scored state that are in NREM / REM (Step C3).",
    r"- **Position** per second (for H4's path): the second's median default-track position (in, unverified WISER frame), no "
    r"forward fill.",
    "",
    "### H4",
    r"- **Event** = a natural wake bout of $d \ge 120$ s inside a record (scored second before it), followed by NREM at $t_0$ "
    r"(the sleep onset), with $[t_0, t_0 + 60\,\text{min})$ inside the record and ≥ 90 % scored; post-round events excluded; "
    r"WISER zone known for ≥ 50 % of the wake's seconds.",
    r"- **NREM excess** $X = \sum_{t_0 \le t < t_0+3600} (\mathbb 1[s_t = \text{NREM}] - \hat q_t)/60$ (min), $\hat q_t$ = the "
    r"expected NREM probability of second $t$ from the 10-min bin baselines with **phase × day** terms (plan §3 day baselines; "
    r"`sleep_explore_d.baseline_bins('phase_x_day')`: leave-one-block-out binomial GLM on 2-harmonic clock + day + dark + "
    r"dark × day + animal), 0 on unscored seconds. Positive = more NREM than expected for that time, day and animal. The "
    r"window starts at a sleep onset, so part of $X$ is by construction (#31); a sensitivity adds the expected NREM "
    r"$\sum \hat q_t/60$ as a covariate.",
    r"- **Activity during the wake** $[a, b)$: (i) **path** $L = \sum_k \lVert \bar{\mathbf x}_{k+1} - \bar{\mathbf x}_k\rVert\,"
    r"\mathbb 1[\lVert\cdot\rVert \ge 7\,\text{in}]$ over consecutive 10-s bins with known median positions $\bar{\mathbf x}_k$ "
    r"(displacements below the 7-in jitter floor per 10 s count as 0); used as $\ln(1 + L\,[\text{m}])$ (primary); "
    r"(ii) **field share** = seconds in the field / seconds with a known zone (0–1).",
    r"- **Model (plan: 'NREM excess (1 h) ~ ln d + activity + dark, within night').** $X_i = \beta_d \ln d_i + \beta_A A_i + "
    r"\beta_{dark}\,\text{dark}_i + \alpha_{animal} + \gamma_{night} + \varepsilon_i$, OLS, SEs clustered by block; **night** = "
    r"the 24-h period [sunset $D$, sunset $D+1$) containing $t_0$ ('within night' read as night fixed effects: each event is "
    r"compared with the other events of the same night and following day). Sensitivities: only events whose onset is dark "
    r"(night FE, no dark term), no night FE (linear day), + expected NREM. Per animal: the same model with night FE.",
    "",
    "### H14",
    r"- **Temperature anomaly** (°C) = outdoor temperature minus its 2-harmonic fit over the cohort (Phase 4, "
    r"`sleep_schedule_temp.weather_anomaly`; console, NWS KITH inside the 09-02/03 uplink hole), joined to a time by the nearest "
    r"5-min sample within 15 min (none before 2026-08-31 00:00). Anomaly SD ≈ 3 °C. Only outdoor air was measured.",
    r"- **M1 REM bout duration:** complete REM bouts (scored start and exit), post-round excluded: $\ln r_i = \beta\,T_i + "
    r"\text{clock} + \text{day} + \text{dark} + \text{prior-wake bin} + \alpha_{animal}$, OLS clustered by block; $T_i$ = "
    r"anomaly at the onset. Hypothesised sign + (warmer → longer).",
    r"- **M2 REM → WAKE:** REM step model + $T$ at the bout onset; $\beta$ on → WAKE vs stay; hypothesised sign − (warmer → "
    r"fewer REM → WAKE exits per REM step). → NREM vs stay reported.",
    r"- **Entry:** NREM step model B-full + $T$ (at the step); $\beta_R$ (REM vs stay) and the held-out comparison B-full + $T$ "
    r"vs B-full on the same steps. **Entry null** = $\beta_R$'s CI includes 0 AND the held-out comparison does not hold.",
    r"- **Rule (plan: 'one holds, entry stays null'):** (M1 holds or M2 holds) and entry null, on each scoring.",
    "",
    "### H15",
    r"- **Step model:** B-full + loc_field + loc_unknown (vs house) + $n_{coloc}$ + dark·$(n_{coloc} - \bar n)$. Group size "
    r"per mate by phase: light $\beta_n$, dark $\beta_n + \beta_{dn}$, on WAKE vs stay (**maintenance**) and REM vs stay "
    r"(**entry**). Sensitivity: + mates_asleep (Step C3's model). Held out: + $n_{coloc}$ terms on B-full + location.",
    r"- **Sleep-onset latency after a house entry** (secondary, in the plan's test but not its rule): entry = a field run "
    r"≥ 30 s followed by a house run ≥ 60 s (hysteresis against boundary jitter), the animal scored WAKE at the entry second; "
    r"latency = s to the start of the first NREM bout ≥ 60 s; censored at the end of the stay (the first run of another zone "
    r"or of unknown zone ≥ 30 s), an unscored second, or 4 h. Cox per phase at entry: $h(t) = h_{0,animal}(t)\,e^{\beta n_{coloc} + "
    r"\gamma\,\text{day}}$ (Efron ties, animal strata, block clusters); $\beta > 0$ = falls asleep sooner with more mates.",
    r"- **Rule (plan: 'maintenance term holds, entry n.s.'):** the WAKE-vs-stay $n_{coloc}$ term holds in ≥ 1 phase (sign "
    r"free: 'changes'), and the REM-vs-stay $n_{coloc}$ CI includes 0 in both phases, on each scoring.",
    "",
    "### H16",
    r"- **Exit** of a tagged animal A: a house-$h$ run ≥ 60 s directly followed by a field run ≥ 30 s; $t_e$ = the first field "
    r"second. **Partner** B (another tagged animal with a scored state) qualifies when it was in house $h$ for ≥ 80 % of "
    r"$[t_e - 60, t_e)$ and at $t_e - 1$, asleep (NREM / REM) over $[t_e - 30, t_e)$, and scored over $[t_e, t_e + 120)$.",
    r"- **Outcome** $o = \mathbb 1[\exists t \in [t_e, t_e + 120): s^B_t = \text{WAKE}]$ (any WAKE, the plan's 'WAKE hazard "
    r"0–2 min'); secondary $o_{40}$ = a WAKE bout ≥ 40 s (not a microarousal) starts in that window.",
    r"- **Time-shift chance.** For each pair, $t' = t_e + \delta$, $\delta \in \pm\{5, 10, 15, 20, 30, 45, 60\}$ min; a shifted "
    r"sample counts when B meets the partner condition at $t'$ (any house), ≥ 1 other tagged animal is in B's house at "
    r"$t' - 1$, and no exit from that house falls within ±120 s of $t'$. $\hat c_i$ = the pair's mean $o$ over its samples. "
    r"**Ratio** $\rho = \sum_i o_i / \sum_i \hat c_i$ over pairs with ≥ 1 sample (observed / chance-expected); per partner "
    r"the same sums. 95 % CI: bootstrap over day-half blocks (2000).",
    r"- **Rule (plan: 'ratio > 1.5, ≥ 5/6'):** pooled $\rho > 1.5$ and ≥ 5 partners with $\rho_B > 1$ (the count with "
    r"$\rho_B > 1.5$ is reported; as Step C1 read '≥ 5/6'), on each scoring.",
    "",
    "### H17",
    r"- **Events** = Step A1's table (`sleep_explore.post_wake_table`): every WAKE bout ≥ 7 min followed by NREM in its "
    r"record; $T$ = NREM + MA (< 40 s) time from the wake end to the first REM, censored at a wake ≥ 7 min, an unknown epoch "
    r"or the record end; $N_{pre}$ = NREM since the last REM before the wake; anchor = a REM before.",
    r"- **Site** before = the modal zone over the sleep seconds (NREM / REM) with a known zone in the 10 min before the wake "
    r"start; after = the same over the first 10 min after the wake end (up to the event / censoring point); each needs ≥ 60 "
    r"such seconds. **Site change** = 1 if the two differ. Primary: both sites a house.",
    r"- **Model:** Cox $h(T) = h_{0,animal}(T)\exp(\beta\,\text{change} + \beta_d\ln d + \beta_N\ln(1 + N_{pre}) + "
    r"\beta_a\text{anchor} + \text{clock} + \beta_{dark}\text{dark})$ ($\ln d$ = matched wake length), block clusters. **Delay** "
    r"= $-\beta$ (> 0 = REM later at a new site; HR $= e^\beta < 1$). Sensitivities: strata animal × wake bin; field as a site; "
    r"post-round excluded; OLS of $\ln T$ among events.",
    r"- **Rule (plan: 'site change CI > 0'):** the delay's CI > 0, on each scoring.",
    "",
    "### H22",
    r"- **Night classes.** Per night_of date $D$ (the night [sunset $D$, sunrise $D+1$)): console rain $= \sum \text{rate}"
    r"\cdot 5/60$ mm over its 5-min samples; **rainy** ≥ 1 mm, **dry** = 0 mm, both with ≥ 50 % console coverage; else "
    r"unclassified (excluded).",
    r"- **Model:** the dark NREM steps of classified nights (post-round excluded), B-full without the (constant) dark step + "
    r"rainy (0/1); $\beta_R$ (REM entry) and $\beta_W$ (WAKE exit); held out: + rainy vs B-full. Sensitivity: raining now "
    r"(console rate > 0 at the nearest sample within 15 min). REM steps of the same nights: → WAKE / → NREM vs stay.",
    r"- **Rule (plan: 'holds'):** the held-out comparison holds (§3) AND the effect is a disturbance ($\beta_W$ CI > 0 or "
    r"$\beta_R$ CI < 0), on each scoring.",
    "",
    "### H25 (description only)",
    r"- **After-cut data:** sessions overlapping [2026-09-11 19:40, 2026-09-12 10:10) with the FINAL-score inclusion rules "
    r"(SF12 excluded as noise, SF11 retired); windows night = [19:40, sunrise) and morning = [sunrise, 10:10). The same "
    r"windows on every earlier night (2026-08-30 … 09-10) are the reference. The after-cut night, like most earlier "
    r"windows, starts after an evening battery round.",
    r"- **Metrics per window:** sleep share = (NREM + REM)/scored s; REM share of sleep; REM bouts per NREM h; NREM → WAKE "
    r"transitions per NREM h (all; microarousals < 40 s returning to NREM; wakes ≥ 40 s); mean REM bout s; **O/E** = observed "
    r"REM entries (WAKE exits) / $\sum_t \hat p_{REM}$ ($\hat p_{WAKE}$) over the window's NREM steps, $\hat p$ from B-full "
    r"fitted on all pre-cut NREM steps (in-sample for the earlier windows; the after-cut day term is extrapolated ~0.5 day).",
    "",
]


def ni(x) -> str:
    """An animal count for the text: integer, or n/a."""
    try:
        return "n/a" if x is None or not np.isfinite(float(x)) else str(int(round(float(x))))
    except (TypeError, ValueError):
        return "n/a"


def rule_line(rule: str) -> str:
    return f"**Plan pass rule (Step F table, quoted):** {rule}"


def fmt_t(r) -> str:
    g = (lambda k: r[k]) if isinstance(r, (dict, pd.Series)) else (lambda k: getattr(r, k))
    c, lo, hi = (float(g(k)) for k in ("coef", "ci_lo", "ci_hi"))
    return f"{c:+.3f} [{lo:+.3f}, {hi:+.3f}]" if np.isfinite(c) else "n/a"


# ================================================================== run
def run(a) -> None:
    from _common import git_commit, write_json
    from output_paths import figure_dir, report_dir, run_dir
    t_all = time.time()
    parts = [p for p in PARTS if p in set(a.parts)]
    out = run_dir("sleep_explore_F2" + ("_scratch" if a.scratch else ""), "2026c")
    rd, fd = (out, out / "figures") if a.scratch else (report_dir("2026c", "ephys_spikes"), figure_dir("2026c", "ephys_spikes"))
    gc = git_commit()
    times, csvs, figs = {}, [], []
    log = open(out / "run.log", "a", encoding="utf-8")

    def say(msg: str) -> None:
        print(msg, flush=True)
        log.write(msg + "\n")
        log.flush()

    def save(df: pd.DataFrame, name: str) -> None:
        p = rd / f"ephys_spikes_sleep_explore_F2_{name}_2026c.csv"
        df.to_csv(p, index=False)
        csvs.append(p.name)

    def fpath(name: str) -> Path:
        p = fd / f"ephys_spikes_sleep_explore_F2_{name}_2026c.png"
        figs.append(p.name)
        return p
    say(f"F2 parts {parts}, scorings {a.scorings}, workers {a.workers}, out {out}")
    t0 = time.time()
    gaps = gaps_table()
    zone = zone_arrays(Path(a.zone_cache) if a.zone_cache else ZONE_CACHE)
    w = weather()
    rain = night_rain(w)
    rain.to_csv(out / "night_rain.csv", index=False)
    pos = pos_arrays(Path(a.pos_cache) if a.pos_cache else None, out / "pos_per_second.npz", a.workers) if "h4" in parts else {}
    times["inputs"] = time.time() - t0
    say(f"inputs {times['inputs']:.0f} s")
    P = {}
    for sc in a.scorings:
        t0 = time.time()
        P[sc] = prep_scoring(sc, gaps, zone, w, rain)
        times[f"prep_{sc}"] = time.time() - t0
    rems = {}
    if {"h14", "h22"} & set(parts):
        for sc in a.scorings:
            rems[sc] = rem_prep(P[sc], w, rain, gaps)
    sections, verdicts = [], []
    RULES = {
        "h4": "\"activity CI > 0, ≥ 5/6\" (test: \"NREM excess (1 h) ~ ln d + activity + dark, within night\").",
        "h14": "\"one holds, entry stays null\" (test: \"REM bout duration and REM → WAKE exits ~ temperature anomaly\").",
        "h15": "\"maintenance term holds, entry n.s.\" (test: \"NREM → WAKE hazard and sleep-onset latency ~ co-located housemates, by phase\").",
        "h16": "\"ratio > 1.5, ≥ 5/6\" (test: \"partner WAKE hazard 0–2 min after a housemate exits (WISER) vs a time-shift chance\").",
        "h17": "\"site change CI > 0\" (test: \"first-REM latency when the WISER house differs from the pre-wake site, matched wake length\").",
        "h22": "\"holds\" (test: \"REM entry and WAKE exits, rainy vs dry nights, matched prior wake\").",
        "h25": "\"description only\" (test: \"descriptive, after-cut only\").",
    }
    HYP = {
        "h4": "NREM after a wake follows the wake's activity (WISER distance / time in the field during the wake), not only its length",
        "h14": "Warmth raises REM share through maintenance, not entry",
        "h15": "Group size changes sleep maintenance, not REM entry",
        "h16": "A housemate leaving the house ends the partner's sleep",
        "h17": "Sleeping at a new site after a long wake delays REM",
        "h22": "Rain disturbs sleep",
        "h25": "The five females (from 09-11 19:40) change the gate or the arousability",
    }
    TCOLS = ["scores", "model", "term", "n", "events", "coef", "ci_lo", "ci_hi", "p", "pred_sign", "animals_pred_sign", "animals",
             "ci_excl0_pred", "holds_term"]
    # ------------------------------------------------------------ H4
    if "h4" in parts:
        t0 = time.time()
        ev, rows, pas = [], [], []
        for sc in a.scorings:
            E = h4_events(P[sc], gaps, zone, pos)
            E.insert(0, "scores", LABEL[sc])
            ev.append(E)
            r_, p_ = h4_models(E, sc)
            rows.append(r_)
            pas.append(p_)
            say(f"H4 {sc}: {len(E)} events ({time.time() - t0:.0f} s)")
        EV, H4T, H4P = pd.concat(ev, ignore_index=True), pd.concat(rows, ignore_index=True), pd.concat(pas, ignore_index=True)
        EV.to_csv(out / "h4_events.csv.gz", index=False)
        save(H4T, "h4_models")
        save(H4P, "h4_per_animal")
        flags = {}
        vl = []
        for sc in a.scorings:
            r = H4T[(H4T.scores == LABEL[sc]) & H4T.model.str.startswith("primary: ") & H4T.term.str.contains("primary")]
            if not len(r):
                flags[LABEL[sc]] = None
                continue
            r = r.iloc[0]
            flags[LABEL[sc]] = bool(r.holds_term) if r.holds_term is not None else None
            r2 = H4T[(H4T.scores == LABEL[sc]) & H4T.model.str.startswith("primary: ") & H4T.term.str.contains("field")].iloc[0]
            vl.append(f"- **{LABEL[sc]}:** path coefficient {fmt_t(r)} min of NREM excess per unit ln(1 + path m), rats > 0 "
                      f"{ni(r.animals_pred_sign)}/{ni(r.animals)}; ln d {r.l_d_coef:+.2f} {r.l_d_ci}; dark {r.dark_coef:+.2f}; n {r.n}. "
                      f"Field share (secondary): {fmt_t(r2)} per full share, rats > 0 {ni(r2.animals_pred_sign)}/{ni(r2.animals)} → primary rule "
                      f"{'met' if flags[LABEL[sc]] else 'not met'}.")
        v = verdict(flags)
        d0 = EV[(~EV.post_round) & (EV.wiser_cover >= WISER_COVER)]
        desc = d0.groupby(["scores", d0.darkf.map({1.0: "dark onset", 0.0: "light onset"})]).agg(
            events=("excess_min", "size"), median_d_min=("d_s", lambda x: x.median() / 60), median_path_m=("path_m", "median"),
            mean_field_share=("field_share", "mean"), mean_excess_min=("excess_min", "mean")).reset_index().rename(columns={"darkf": "phase"})
        fig_terms([("ln(1 + path m), per animal (dots) and pooled", H4T[H4T.model.str.startswith("primary: ") & H4T.term.str.contains("primary")].assign(label="path"),
                    "min NREM excess per unit"),
                   ("field share", H4T[H4T.model.str.startswith("primary: ") & H4T.term.str.contains("field")].assign(label="field share"), "min per full share")],
                  fpath("h4"), f"H4: NREM excess in the first hour after the sleep onset vs WISER activity during the wake  {gc}")
        L = [f"## H4 — {HYP['h4']}", "", rule_line(RULES["h4"]), "",
             "Read here as: the activity coefficient (primary activity = jitter-floored WISER path, ln(1 + m)) has a pooled CI > 0 "
             "and ≥ 5 of 6 per-animal coefficients > 0, on both scorings; 'within night' = night fixed effects (24-h periods "
             "starting at sunset). The time in the field (share of the wake) is the second activity measure, reported. The "
             "hour starts at a sleep onset (#31), so the excess is partly by construction; the sensitivity with the expected "
             "NREM as a covariate absorbs that part. Per-animal fits are made for the primary model only (the sensitivities "
             "show n/a). Caveat: WISER path inside a house is mostly below the 7-in floor; positions are in the unverified "
             "WISER frame (distances only).", "",
             "### Events (natural wakes ≥ 2 min with a WISER zone for ≥ 50 % of the wake; post-round excluded)", "", *C.tbl(desc, 2), "",
             "### Models", "", *C.tbl(H4T[TCOLS + ["l_d_coef", "l_d_ci", "dark_coef"]]), "",
             f"![](../figures/{figs[-1]})", "", "### Per animal", "", *C.tbl(H4P[["scores", "activity", "animal", "events", "coef", "ci_lo", "ci_hi", "p"]]), "",
             "### Verdict H4", "", *vl, "", f"**H4: {v}.**", ""]
        sections.append(L)
        verdicts.append({"H": "H4", "hypothesis": HYP["h4"], "verdict": v, **{k: ("met" if x else ("n/a" if x is None else "not met")) for k, x in flags.items()}})
        times["h4"] = time.time() - t0
    # ------------------------------------------------------------ H14
    if "h14" in parts:
        t0 = time.time()
        rows, pas, hos, cnt = [], [], [], {}
        for sc in a.scorings:
            Rb, T = rems[sc]
            r = h14_run(P[sc], Rb, T, a.workers)
            rows += r["rows"]
            pas += r["pa"]
            hos.append(r["ho"])
            cnt[LABEL[sc]] = r["counts"]
            say(f"H14 {sc} done ({time.time() - t0:.0f} s)")
        H14T, H14P, H14H = pd.DataFrame(rows), pd.DataFrame(pas), pd.DataFrame(hos)
        save(H14T, "h14_terms")
        save(H14P, "h14_per_animal")
        save(H14H, "h14_heldout")
        flags, vl = {}, []
        for sc in a.scorings:
            lab = LABEL[sc]
            q = H14T[H14T.scores == lab].set_index("model")
            m1 = bool(q.loc["M1 ln REM bout duration (OLS)", "holds_term"])
            m2 = bool(q.loc["M2 REM-step hazard: REM -> WAKE vs stay", "holds_term"])
            e = q.loc["entry: NREM-step hazard NREM -> REM vs stay"]
            hh = H14H[H14H.scores == lab].iloc[0]
            e_null = bool(e.ci_lo <= 0 <= e.ci_hi) and not bool(hh.get("holds", False))
            flags[lab] = bool((m1 or m2) and e_null)
            r1, r2 = q.loc["M1 ln REM bout duration (OLS)"], q.loc["M2 REM-step hazard: REM -> WAKE vs stay"]
            vl.append(f"- **{lab}:** M1 ln REM duration per °C {fmt_t(r1)} (rats > 0 {ni(r1.animals_pred_sign)}/{ni(r1.animals)}) → "
                      f"{'holds' if m1 else 'does not hold'}; M2 REM → WAKE per °C {fmt_t(r2)} (rats < 0 {ni(r2.animals_pred_sign)}/{ni(r2.animals)}) → "
                      f"{'holds' if m2 else 'does not hold'}; entry REM vs stay per °C {fmt_t(e)} and held out Δ {hh.delta_pct:+.3f} % "
                      f"[{hh.ci_lo_pct:+.3f}, {hh.ci_hi_pct:+.3f}], {hh.animals_better}/{hh.animals} → entry {'null' if e_null else 'NOT null'} "
                      f"→ rule {'met' if flags[lab] else 'not met'}.")
        v = verdict(flags)
        fig_terms([("REM maintenance and entry vs temperature anomaly (per °C)", H14T.assign(label=H14T.model.str.slice(0, 48)), "coefficient per °C")],
                  fpath("h14"), f"H14: temperature anomaly and REM maintenance vs entry  {gc}")
        L = [f"## H14 — {HYP['h14']}", "", rule_line(RULES["h14"]), "",
             "Read here as: (M1 REM bout duration longer when warmer: CI > 0, ≥ 5/6 rats > 0, OR M2 fewer REM → WAKE exits per "
             "REM step when warmer: CI < 0, ≥ 5/6 rats < 0) AND REM entry null (REM-vs-stay CI includes 0 and the held-out "
             "comparison does not hold), on both scorings. Matched prior wake: ln(1 + d) in the NREM step model; prior-wake bins "
             "in the REM models. Context (claim audit): #22 warmer → higher REM share (Candidate), #23 temperature does not "
             "predict REM entry (Rejected for this range).", "",
             f"Counts: {json.dumps(cnt)}.", "", "### Terms", "", *C.tbl(H14T[TCOLS]), "", f"![](../figures/{figs[-1]})", "",
             "### Held out (entry)", "", *C.tbl(H14H), "", "### Per animal", "", *C.tbl(H14P), "",
             "### Verdict H14", "", *vl, "", f"**H14: {v}.**", ""]
        sections.append(L)
        verdicts.append({"H": "H14", "hypothesis": HYP["h14"], "verdict": v, **{k: ("met" if x else "not met") for k, x in flags.items()}})
        times["h14"] = time.time() - t0
    # ------------------------------------------------------------ H15
    if "h15" in parts:
        t0 = time.time()
        rows, pas, hos, ents = [], [], [], []
        for sc in a.scorings:
            r = h15_run(P[sc], zone, gaps, a.workers)
            rows += r["rows"]
            pas += r["pa"]
            hos.append(r["ho"])
            ents.append(r["entries"].assign(scores=LABEL[sc]))
            say(f"H15 {sc} done ({time.time() - t0:.0f} s)")
        H15T, H15P, H15H = pd.DataFrame(rows), pd.DataFrame(pas), pd.DataFrame(hos)
        EN = pd.concat(ents, ignore_index=True)
        EN.to_csv(out / "h15_house_entries.csv.gz", index=False)
        save(H15T, "h15_terms")
        save(H15P, "h15_per_animal")
        save(H15H, "h15_heldout")
        flags, vl = {}, []
        for sc in a.scorings:
            lab = LABEL[sc]
            q = H15T[(H15T.scores == lab) & H15T.model.str.startswith("B-full + location + n_coloc")]
            mw = q[q.model.str.contains("WAKE")]
            mr = q[q.model.str.contains("REM vs stay")]
            maint = bool(mw.holds_term.astype(bool).any())
            entry_ns = bool(((mr.ci_lo <= 0) & (mr.ci_hi >= 0)).all())
            flags[lab] = maint and entry_ns
            hh = H15H[H15H.scores == lab].iloc[0]
            lt = H15T[(H15T.scores == lab) & H15T.model.str.startswith("sleep-onset")]
            vl.append(f"- **{lab}:** WAKE vs stay per co-located mate: " + "; ".join(
                f"{r.term.split(', ')[1]} {fmt_t(r)} ({ni(r.animals_pred_sign)}/{ni(r.animals)} rats same sign{', holds' if r.holds_term else ''})" for r in mw.itertuples())
                + " → maintenance " + ("holds" if maint else "does not hold") + "; REM vs stay: " + "; ".join(
                f"{r.term.split(', ')[1]} {fmt_t(r)}" for r in mr.itertuples()) + f" → entry {'n.s.' if entry_ns else 'NOT n.s.'}; "
                f"held out (+ n_coloc terms) Δ {hh.delta_pct:+.3f} % [{hh.ci_lo_pct:+.3f}, {hh.ci_hi_pct:+.3f}], {hh.animals_better}/{hh.animals}; "
                "sleep-onset latency (not in the rule) log HR per mate " + "; ".join(f"{r.term.split(', ')[1]} {fmt_t(r)} ({r.events})" for r in lt.itertuples())
                + f" → rule {'met' if flags[lab] else 'not met'}.")
        v = verdict(flags)
        fig_terms([("per co-located mate: WAKE vs stay", H15T[H15T.model.str.startswith("B-full") & H15T.model.str.contains("WAKE")].assign(label=lambda d: d.term.str.split(", ").str[1]), "log-odds per mate"),
                   ("per co-located mate: REM vs stay", H15T[H15T.model.str.startswith("B-full") & H15T.model.str.contains("REM vs stay")].assign(label=lambda d: d.term.str.split(", ").str[1]), "log-odds per mate"),
                   ("sleep onset after a house entry", H15T[H15T.model.str.startswith("sleep-onset")].assign(label=lambda d: d.term.str.split(", ").str[1]), "log HR per mate")],
                  fpath("h15"), f"H15: group size (WISER co-location; not contact) and sleep maintenance / REM entry / sleep onset  {gc}")
        ensum = EN.groupby(["scores", EN.darkf.map({1.0: "dark", 0.0: "light"})]).agg(entries=("T_s", "size"), onsets=("event", "sum"),
                                                                                       mean_n_coloc=("n_coloc", "mean")).reset_index().rename(columns={"darkf": "phase"})
        L = [f"## H15 — {HYP['h15']}", "", rule_line(RULES["h15"]), "",
             "Read here as: the NREM → WAKE term of n_coloc (per co-located tagged mate) holds in at least one phase (CI excludes "
             "0, ≥ 5/6 rats with the pooled sign) and the NREM → REM term's CI includes 0 in both phases, on both scorings; "
             "'entry' = REM entry, as the hypothesis states. Sleep-onset latency (named in the test, not in the rule) is reported. "
             "Primary model without the mates' sleep state (group size as such); Step C3's model with mates_asleep is the "
             "sensitivity. Caveats: WISER co-location = 'same house', never contact; tagged animals only (SF11 untagged after "
             "09-07 08:20 → group sizes after it are lower bounds); no body-contact claim is made. Context: Step C3 / #38.", "",
             "### Terms", "", *C.tbl(H15T[TCOLS]), "", f"![](../figures/{figs[-1]})", "", "### Held out", "", *C.tbl(H15H), "",
             "### House entries (sleep-onset latency sample; post-round excluded)", "", *C.tbl(ensum), "",
             "### Per animal", "", *C.tbl(H15P), "", "### Verdict H15", "", *vl, "", f"**H15: {v}.**", ""]
        sections.append(L)
        verdicts.append({"H": "H15", "hypothesis": HYP["h15"], "verdict": v, **{k: ("met" if x else "not met") for k, x in flags.items()}})
        times["h15"] = time.time() - t0
    # ------------------------------------------------------------ H16
    if "h16" in parts:
        t0 = time.time()
        exits = house_exits(zone)
        exits.to_csv(out / "h16_exits.csv", index=False)
        rows, per_rows, prs = [], [], []
        flags, vl = {}, []
        for sc in a.scorings:
            lab = LABEL[sc]
            for excl in (False, True):
                Pp, Ch = h16_pairs(zone, P[sc]["arr"], exits)
                if excl and len(Pp):
                    keep = ~C.post_round_mask(Pp.partner.to_numpy(), Pp.t, gaps)
                    Ch = Ch[Ch.pair.isin(Pp[keep].pair)]
                    Pp = Pp[keep]
                if not excl:
                    Pp.assign(scores=lab).to_csv(out / f"h16_pairs_{sc}.csv.gz", index=False)
                    Ch.assign(scores=lab).to_csv(out / f"h16_chance_{sc}.csv.gz", index=False)
                for col in ("woke", "woke_ge40"):
                    r = h16_ratio(Pp, Ch, col)
                    per = r.pop("per", pd.DataFrame())
                    gt1 = int((per.ratio > 1).sum()) if len(per) else 0
                    gt15 = int((per.ratio > 1.5).sum()) if len(per) else 0
                    row = {"scores": lab, "sample": "post-round 3 h excluded (sensitivity)" if excl else "all exits (primary)", "outcome": col,
                           **r, "partners": len(per), "partners_ratio_gt1": gt1, "partners_ratio_gt1.5": gt15,
                           "pairs_partner_REM": int((Pp.partner_state == "REM").sum()) if len(Pp) else 0}
                    rows.append(row)
                    if not excl:
                        for an, q in per.iterrows():
                            per_rows.append({"scores": lab, "outcome": col, "partner": an, **q.to_dict(),
                                             "p_obs": q.observed / q.pairs, "p_chance": q.expected / q.pairs})
                        if col == "woke":
                            flags[lab] = bool(np.isfinite(r.get("ratio", np.nan)) and r["ratio"] > 1.5 and gt1 >= 5) if r.get("pairs", 0) else None
                            vl.append(f"- **{lab}:** {r.get('pairs', 0)} (exit, sleeping co-located partner) pairs from {len(exits)} WISER exits; "
                                      f"P(WAKE within 2 min) observed {r.get('p_obs', np.nan):.3f} vs time-shift chance {r.get('p_chance', np.nan):.3f}, "
                                      f"ratio {r.get('ratio', np.nan):.2f} [{r.get('ci_lo', np.nan):.2f}, {r.get('ci_hi', np.nan):.2f}]; partners with ratio > 1: "
                                      f"{gt1}/{len(per)} (> 1.5: {gt15}) → rule {'met' if flags[lab] else 'not met'}.")
            say(f"H16 {sc} done ({time.time() - t0:.0f} s)")
        H16T, H16P = pd.DataFrame(rows), pd.DataFrame(per_rows)
        save(H16T, "h16_ratio")
        save(H16P, "h16_per_partner")
        v = verdict(flags)
        fig_h16(H16P, fpath("h16"), f"H16: partner waking within 2 min after a co-located housemate's WISER exit vs time-shift chance  {gc}")
        exsum = exits.groupby("leaver").agg(exits=("t_e", "size")).reset_index()
        L = [f"## H16 — {HYP['h16']}", "", rule_line(RULES["h16"]), "",
             "Read here as: pooled observed / chance ratio of the partner's P(WAKE within 0–2 min) > 1.5 and ≥ 5 partners with a "
             "ratio > 1 (the count > 1.5 reported), on both scorings; the ratio with wakes ≥ 40 s (sleep-ending wakes, not "
             "microarousals) is reported. Caveats: the exit is a WISER zone change (ROI + 14 in, hysteresis 60 s house / 30 s "
             "field), not a seen departure; the partner's WAKE is scored from its own head IMU (the scorer turns sustained "
             "movement into WAKE), so a partner moved by the leaver is scored awake — the ratio cannot separate being jostled "
             "from waking; 'which housemate left' is the tag's identity, the body is not seen (video).", "",
             "WISER exits per animal (all, before pairing):", "", *C.tbl(exsum), "",
             "### Ratios", "", *C.tbl(H16T), "", f"![](../figures/{figs[-1]})", "", "### Per partner (primary sample)", "", *C.tbl(H16P), "",
             "### Verdict H16", "", *vl, "", f"**H16: {v}.**", ""]
        sections.append(L)
        verdicts.append({"H": "H16", "hypothesis": HYP["h16"], "verdict": v, **{k: ("met" if x else ("n/a" if x is None else "not met")) for k, x in flags.items()}})
        times["h16"] = time.time() - t0
    # ------------------------------------------------------------ H17
    if "h17" in parts:
        t0 = time.time()
        rows, tabs = [], {}
        flags, vl = {}, []
        for sc in a.scorings:
            lab = LABEL[sc]
            tab = h17_table(P[sc], zone, gaps)
            tab.assign(scores=lab).to_csv(out / f"h17_events_{sc}.csv.gz", index=False)
            tabs[lab] = tab
            r = h17_run(tab, sc)
            rows += r["rows"]
            p0 = r["rows"][0]
            ok = np.isfinite(p0["coef"])
            flags[lab] = bool(p0["ci_lo"] > 0) if ok else None
            vl.append(f"- **{lab}:** {p0['n']} post-wake sleeps with both sites a house ({p0['n_change']} other house, {p0['n_same']} same); "
                      f"site-change HR of REM entry {p0['HR']:.2f} [{p0['HR_lo']:.2f}, {p0['HR_hi']:.2f}] → delay {fmt_t(p0)}; with animal × "
                      f"wake-bin strata HR {p0['HR_wakebin_strata']:.2f} [{p0['HR_wakebin_lo']:.2f}, {p0['HR_wakebin_hi']:.2f}] → rule "
                      f"{'met' if flags[lab] else ('not computable' if flags[lab] is None else 'not met')}.")
            say(f"H17 {sc} done ({time.time() - t0:.0f} s)")
        H17T = pd.DataFrame(rows)
        save(H17T, "h17_cox")
        v = verdict(flags)
        fig_h17(tabs, fpath("h17"), f"H17: first REM after wakes >= 7 min, sleep in the same vs the other house (WISER)  {gc}")
        sitesum = pd.concat([t.assign(scores=k) for k, t in tabs.items()]).groupby("scores").agg(
            events=("T_s", "size"), both_houses=("houses_known", "sum"), site_pre_known=("site_pre", lambda x: int((x > 0).sum())),
            site_post_known=("site_post", lambda x: int((x > 0).sum()))).reset_index()
        L = [f"## H17 — {HYP['h17']}", "", rule_line(RULES["h17"]), "",
             "Read here as: the delay (= −log HR of REM entry for a change of house, Cox in NREM time with ln d, ln(1 + N_pre), "
             "anchor, clock, dark, animal strata) has a CI > 0, on both scorings. Matched wake length = ln d in the model "
             "(sensitivity: strata animal × wake bin). Caveat: site = WISER house (ROI + 14 in), the modal zone of 10 min of "
             "sleep; 'new' means the other house than before the wake, not a never-used site.", "",
             "### Sample", "", *C.tbl(sitesum), "", "### Cox", "",
             *C.tbl(H17T[["scores", "model", "n", "events", "n_change", "n_same", "HR", "HR_lo", "HR_hi", "coef", "ci_lo", "ci_hi", "p",
                          "HR_wakebin_strata", "HR_wakebin_lo", "HR_wakebin_hi", "ols_lnT_site_change", "ols_lnT_ci", "dark_share_change",
                          "dark_share_same", "median_d_min_change", "median_d_min_same"]]), "",
             f"![](../figures/{figs[-1]})", "", "### Verdict H17", "", *vl, "", f"**H17: {v}.**", ""]
        sections.append(L)
        verdicts.append({"H": "H17", "hypothesis": HYP["h17"], "verdict": v, **{k: ("met" if x else ("n/a" if x is None else "not met")) for k, x in flags.items()}})
        times["h17"] = time.time() - t0
    # ------------------------------------------------------------ H22
    if "h22" in parts:
        t0 = time.time()
        rows, pas, hos, cnt = [], [], [], {}
        for sc in a.scorings:
            r = h22_run(P[sc], rems[sc][1], a.workers)
            rows += r["rows"]
            pas += r["pa"]
            hos.append(r["ho"])
            cnt[LABEL[sc]] = r["counts"]
            say(f"H22 {sc} done ({time.time() - t0:.0f} s)")
        H22T, H22P, H22H = pd.DataFrame(rows), pd.DataFrame(pas), pd.DataFrame(hos)
        save(H22T, "h22_terms")
        save(H22P, "h22_per_animal")
        save(H22H, "h22_heldout")
        save(rain, "h22_nights")
        flags, vl = {}, []
        for sc in a.scorings:
            lab = LABEL[sc]
            q = H22T[(H22T.scores == lab) & H22T.model.str.startswith("night NREM steps, B-full")]
            rr = q[q.model.str.contains("REM entry")].iloc[0]
            ww = q[q.model.str.contains("WAKE exit")].iloc[0]
            hh = H22H[H22H.scores == lab].iloc[0]
            disturb = bool(ww.ci_lo > 0 or rr.ci_hi < 0)
            flags[lab] = bool(hh.get("holds", False)) and disturb
            vl.append(f"- **{lab}:** rainy vs dry night, REM entry {fmt_t(rr)} (rats < 0 {ni(rr.animals_pred_sign)}/{ni(rr.animals)}), WAKE exit "
                      f"{fmt_t(ww)} (rats > 0 {ni(ww.animals_pred_sign)}/{ni(ww.animals)}); held out Δ {hh.delta_pct:+.3f} % [{hh.ci_lo_pct:+.3f}, "
                      f"{hh.ci_hi_pct:+.3f}], {hh.animals_better}/{hh.animals} → {'holds' if hh.get('holds', False) else 'does not hold'}; "
                      f"disturbance direction {'yes' if disturb else 'no'} → rule {'met' if flags[lab] else 'not met'}.")
        v = verdict(flags)
        fig_terms([("rainy vs dry nights (night steps)", H22T.assign(label=H22T.model.str.replace("night NREM steps, B-full (no dark step) + rainy night: ", "", regex=False).str.slice(0, 50)),
                    "log-odds (rainy − dry)")], fpath("h22"), f"H22: rainy vs dry nights, REM entry and WAKE exits  {gc}")
        L = [f"## H22 — {HYP['h22']}", "", rule_line(RULES["h22"]), "",
             "Read here as: adding 'rainy night' to B-full improves held-out prediction of the night NREM steps (plan §3 'holds': "
             "CI < 0, ≥ 5/6 rats better) AND the coefficients point to disturbance (WAKE exits up with CI > 0 or REM entry down "
             "with CI < 0), on both scorings. Matched prior wake: ln(1 + d) in the model. Only three nights are rainy (two "
             "of them in the test folds), so the held-out test rests on two nights. Context: #39 (the drift is not weather).", "",
             "### Nights", "", *C.tbl(rain.assign(sunset=rain.sunset.dt.strftime("%m-%d %H:%M"), sunrise_next=rain.sunrise_next.dt.strftime("%m-%d %H:%M"))), "", f"Steps: {json.dumps(cnt)}.", "", "### Terms", "", *C.tbl(H22T[TCOLS]), "",
             f"![](../figures/{figs[-1]})", "", "### Held out", "", *C.tbl(H22H), "", "### Per animal", "", *C.tbl(H22P), "",
             "### Verdict H22", "", *vl, "", f"**H22: {v}.**", ""]
        sections.append(L)
        verdicts.append({"H": "H22", "hypothesis": HYP["h22"], "verdict": v, **{k: ("met" if x else "not met") for k, x in flags.items()}})
        times["h22"] = time.time() - t0
    # ------------------------------------------------------------ H25
    if "h25" in parts:
        t0 = time.time()
        Ts, Ss, info = [], [], {}
        for sc in a.scorings:
            r = h25_run(sc, P[sc])
            Ts.append(r["T"])
            Ss.append(r["S"])
            info[LABEL[sc]] = {"animals": r["animals"], "after_cut_recorded_h": round(r["after_rec_h"], 2)}
            say(f"H25 {sc} done ({time.time() - t0:.0f} s)")
        H25T, H25S = pd.concat(Ts, ignore_index=True), pd.concat(Ss, ignore_index=True)
        save(H25T, "h25_windows")
        save(H25S, "h25_summary")
        fig_h25(H25T, fpath("h25"), f"H25 (description): the after-cut night (red) vs earlier nights' 19:40 -> sunrise (grey), FINAL  {gc}")
        piv = H25S[H25S.part.str.startswith("night")].pivot_table(index=["scores", "metric"], values=["after_cut", "before_mean"], aggfunc="mean").reset_index()
        cnt_out = H25S.groupby(["scores", "part", "metric"]).agg(animals=("animal", "size"), outside_range=("outside_range", "sum")).reset_index()
        hi = H25S.assign(above=lambda d: d.after_cut > d.before_mean).groupby(["scores", "part", "metric"]).above.sum().rename("animals_above_mean")
        cnt_out = cnt_out.join(hi, on=["scores", "part", "metric"])
        L = [f"## H25 — {HYP['h25']}", "", rule_line(RULES["h25"]), "",
             "**Description only, never pooled with the inference set.** One after-cut night per animal (n = 1 per animal) "
             "cannot separate the females from that night's weather, the 09-11 evening round, or the 12-day drift (#30); "
             "the earlier nights are a reference range, not a control. The females carry no WISER tags, so no co-location "
             "with them can be measured. Mechanism words ('gate', 'arousability') are the hypothesis's; the numbers below are "
             "REM-entry rates and WAKE-exit rates.", "",
             f"After-cut data: {json.dumps(info)}.", "",
             "### Mean over animals: after-cut night vs the earlier nights' mean (same clock window)", "", *C.tbl(piv), "",
             "### How often the after-cut value lies outside the earlier nights' range", "", *C.tbl(cnt_out), "",
             f"![](../figures/{figs[-1]})", "", "### Per animal", "", *C.tbl(H25S), "",
             "### Verdict H25", "", "**H25: DESCRIPTION ONLY** (no test; see the tables).", ""]
        sections.append(L)
        verdicts.append({"H": "H25", "hypothesis": HYP["h25"], "verdict": "DESCRIPTION ONLY", **{LABEL[sc]: "described" for sc in a.scorings}})
        times["h25"] = time.time() - t0
    # ------------------------------------------------------------ report
    VT = pd.DataFrame(verdicts)
    save(VT, "verdicts")
    times["total"] = time.time() - t_all
    data = ["## Data", ""]
    for sc in a.scorings:
        D = P[sc]["D"]
        data.append(f"- {LABEL[sc]}: {len(D['y'])} NREM steps ({int(D['post_round'].sum())} in the 3 h after battery rounds), "
                    f"{int((D['y'] == 1).sum())} REM ends, {int((D['y'] == 2).sum())} WAKE ends; {len(P[sc]['recs'])} records; "
                    f"NREM steps with a temperature anomaly {int(np.isfinite(D['temp_anom']).sum())}; dark steps on rainy / dry nights "
                    f"{int(((D['dark'] == 1) & (D['night_cls'] == 1)).sum())} / {int(((D['dark'] == 1) & (D['night_cls'] == 0)).sum())}.")
    data += ["", f"- P = `{KEY}` (Step B's modal grid point; τ_w = 600 s, κ = 0). WISER zone cache: `{Path(a.zone_cache) if a.zone_cache else ZONE_CACHE}` "
             "(Step C, re-read, not re-derived). Weather: field2026-sync console export / listener (NWS KITH in the 09-02/03 hole).",
             f"- Runtime: " + ", ".join(f"{k} {v / 60:.1f} min" for k, v in times.items()) + ".", ""]
    dev = ["## Deviations from the plan and notes", "",
           "- Written as `ephys/sleep_explore_f2.py` (the task's file), not as parts of `ephys/sleep_explore.py` (plan §5 Step F says "
           "'a separate short part of sleep_explore.py'); Step A's file stays untouched.",
           "- Where the Step F table's wording leaves a choice open, the reading is stated in each section ('Read here as') and "
           "was fixed in the code before the run: H4 'within night' = night fixed effects, primary activity = path; H14 'holds' "
           "for a term = CI + ≥ 5/6 rats, 'entry stays null' = CI includes 0 and the held-out comparison does not hold; H15 "
           "'entry' = REM entry (the hypothesis's), sleep-onset latency reported outside the rule; H16 '≥ 5/6' = partners with a "
           "ratio > 1 (as Step C1 read '≥ 5/6'); H22 'holds' = the plan §3 held-out rule plus the disturbance direction.",
           "- Both scorings must meet a rule (plan §1: FINAL alone is not used for contrasts whose two sides are different sessions).",
           "- Code check before this run: two scratch runs into a scratch run folder (`sleep_explore_F2_scratch_*`, not reports). "
           "Changes after them, none of a test or rule: the held-out folds were switched to the calendar blocks (decided while "
           "the first scratch run was still at H4, before any H14 / H15 / H22 output), a crash in a text-formatting helper, "
           "and table / text formatting.",
           "- H4 uses the phase × day baselines of Step A4 / D (plan §3), not Phase 3's common-day baselines behind #31; the hour "
           "must be ≥ 90 % scored; post-round events are excluded (plan §3).",
           "- H14 / H22 REM steps exclude REM bouts whose start is unscored (left-truncated; `sleep_sim.rem_steps` keeps them).",
           "- H17 uses Step A1's event table unchanged (NREM + MA time to the first REM, censoring as A1); the site needs WISER, "
           "so SF11 after 09-07 and wakes without 60 s of zoned sleep on both sides drop out.",
           "- H25 uses sessions that start before the cut and run past it (records rebuilt without the cut); only seconds from "
           "19:40 are described; SF12 is excluded (noise / contact failing) and SF11 retired.",
           "- The multinomial engine and cluster-robust SEs are Step C's (`sleep_explore_c.mnl_fit`); held-out comparisons use "
           "forward chaining over the calendar day-half blocks of all NREM steps (`sleep_model.folds_of`'s blocks; a sub-set "
           "comparison such as H22's night steps keeps those calendar folds instead of re-counting 'the first 6 blocks' on the "
           "sub-set, which would have moved the 09-03 rainy night into the training-only blocks).",
           ""]
    hdr = ["# Sleep behaviour explore — Step F: the WISER / environment / social batch (H4, H14, H15, H16, H17, H22, H25), cohort 2026c", "",
           f"Plan: [{PLAN}](../../../../{PLAN}) (§1 scope, §3 definitions, §5 Step F table — the pass rules are the plan's, "
           "quoted unchanged —, §9 Amendment 1 'F — WISER / environment / social batch'). Builds on Steps A–E "
           "([C](ephys_spikes_sleep_explore_C_2026c.md) for the step engine, WISER zones and housemate terms). Driver "
           f"`ephys/sleep_explore_f2.py run` (commit {gc}, file uncommitted at run time); bulk `{out}`; parts {', '.join(parts)}; "
           f"runtime {times['total'] / 60:.1f} min.", "",
           "**Status: exploration step; a hypothesis gets a claim number only if it holds, and claim statuses are changed in the "
           "claim audit, not here.** Inputs (plan §1): scored 1-s states (FINAL and pass2med_remclean), NOAA light, the Phase-0 "
           "gap table, WISER default tracks (house / field / co-located tagged housemates), outdoor temperature and rain. No LFP "
           "features. The sleep states come from the scorer, whose EMG is the head IMU (sustained head movement is scored "
           "WAKE): any link between movement or disturbance and a scored WAKE carries that caveat. WISER: house = ROI + 14 in, "
           "~4–7 in jitter, 'same house' is never body contact; SF11 untagged after 09-07; the five females (from 09-11 19:40) "
           "have no tags. Video is not in.", "",
           "## Verdicts", "", *C.tbl(VT), ""]
    final = ["## Final verdict table", "", *C.tbl(VT), ""]
    flat = [ln for blk in [hdr, data, DEFINITIONS] + sections + [final, dev] for ln in blk]
    rpt = rd / "ephys_spikes_sleep_explore_F2_2026c.md"
    rpt.write_text("\n".join(flat) + "\n", encoding="utf-8")
    write_json(rd / "run_manifest_sleep_explore_F2_2026c.json",
               {"run_dir": str(out), "git_commit": gc, "parts": parts, "scorings": [LABEL[s] for s in a.scorings], "p_key": KEY,
                "inputs": {"states_FINAL": str(STATES), "states_pass2med": str(PASS2MED), "review": str(REVIEW),
                           "zone_cache": str(Path(a.zone_cache) if a.zone_cache else ZONE_CACHE),
                           "pos_cache": str(Path(a.pos_cache) if a.pos_cache else out / "pos_per_second.npz"),
                           "gaps": str(Path(json.load(open(C.P0_MANIFEST))["run_dir"]) / "gaps.csv"),
                           "wiser_default_tracks": str(OUT / "wiser_default_tracks")},
                "csvs": csvs, "figures": figs, "runtime_s": {k: round(v, 1) for k, v in times.items()}, "verdicts": verdicts, "plan": PLAN,
                "report": str(rpt)})
    say(VT.to_string(index=False))
    say(f"written {rpt} ({times['total'] / 60:.1f} min)")
    log.close()


# ================================================================== selftest
def selftest() -> None:
    t_start = time.time()
    ok_all = True

    def check(name: str, cond: bool) -> None:
        nonlocal ok_all
        print(("PASS " if cond else "FAIL ") + name, flush=True)
        ok_all &= bool(cond)

    rng = np.random.default_rng(3)
    # 1. verdict logic
    check("verdict: both met -> HOLDS; one -> INCONCLUSIVE; none -> DOES NOT HOLD; none computable -> INCONCLUSIVE",
          verdict({"a": True, "b": True}) == "HOLDS" and verdict({"a": True, "b": False}) == "INCONCLUSIVE"
          and verdict({"a": False, "b": False}) == "DOES NOT HOLD" and verdict({"a": None, "b": None}) == "INCONCLUSIVE"
          and verdict({"a": False, "b": None}) == "DOES NOT HOLD")
    # 2. period_of: before / after sunset
    from sleep_quant import sun_times
    ss = pd.Timestamp(sun_times(pd.Timestamp("2026-09-05").date())[1])
    p = period_of([ss - pd.Timedelta(minutes=1), ss + pd.Timedelta(minutes=1), pd.Timestamp("2026-09-06 03:00")])
    check(f"period_of: {list(p)} = [09-04, 09-05, 09-05]", list(p) == ["2026-09-04", "2026-09-05", "2026-09-05"])
    # 3. floored path: still with jitter -> 0; straight walk 12 in/s for 100 s -> ~1200 in
    xs = 100 + rng.uniform(-2, 2, 300)
    ys = 50 + rng.uniform(-2, 2, 300)
    walk = np.r_[np.full(50, 100.0), 100 + 12 * np.arange(100), np.full(50, 100 + 12 * 99.0)]
    pw = floored_path(walk + rng.uniform(-1, 1, 200), np.full(200, 50.0))
    check(f"floored path: still + jitter {floored_path(xs, ys):.1f} in = 0; walk {pw:.0f} in ~ 1188", floored_path(xs, ys) == 0 and abs(pw - 1188) < 40)
    # 4. REM bouts / steps = sleep_sim.rem_steps on a record without unknowns; prior-wake bins
    from sleep_sim import rem_steps
    st = np.array([N] * 300 + [R] * 95 + [W] * 200 + [N] * 400 + [R] * 61 + [N] * 50 + [W] * 30 + [R] * 20 + [W] * 900 + [N] * 100 + [R] * 33, np.int8)
    rc = {"animal": "SF07", "start": pd.Timestamp("2026-09-03 10:00:00"), "end": pd.Timestamp("2026-09-03 10:00:00") + pd.Timedelta(seconds=len(st)),
          "state": st, "record_id": 0, "block": "2026-09-03D"}
    Rb = rem_bouts([rc])
    Tm = rem_step_table(Rb)
    ref = rem_steps([rc])
    check(f"REM steps = sleep_sim.rem_steps ({len(Tm)} rows; y and elapsed identical)",
          len(Tm) == len(ref) and np.array_equal(Tm.y.to_numpy(), ref.y.to_numpy()) and np.array_equal(Tm.elapsed.to_numpy(), ref.elapsed.to_numpy()))
    check(f"REM prior-wake bins {list(Rb.wbin)} = [none, 2-7 min, 2-7 min, 7-30 min]; exits {list(Rb.exit)} = [2, 1, 2, 0]",
          list(Rb.wbin) == ["none", "2-7 min", "2-7 min", "7-30 min"] and list(Rb.exit) == [2, 1, 2, 0])
    # 5. exits / entries / sleep-onset latency on toy arrays
    span = 3000
    zA = np.r_[np.full(500, 1), np.full(40, 3), np.full(5, 1), np.full(300, 3), np.full(800, 1), np.full(10, 3), np.full(1345, 1)].astype(np.int8)
    zone_t = {"SF07": zA, "SF08": np.full(span, 1, np.int8)}
    ex = house_exits(zone_t)
    check(f"exits (house >= 60 s -> field >= 30 s): {list(ex.t_e)} = [500] (the 5-s house flicker and the 10-s field run do not count)",
          list(ex.t_e) == [500])
    sA = np.full(span, W, np.int8)
    sA[845 + 200:845 + 290] = N                       # 90-s NREM bout 200 s after the entry at 845
    en = house_entries(zone_t, {"SF07": sA, "SF08": np.full(span, N, np.int8)})
    check(f"house entry at 845, latency {list(en.T_s)} = [200], event 1, n_coloc 1",
          len(en) == 1 and int(en.T_s.iloc[0]) == 200 and int(en.event.iloc[0]) == 1 and int(en.n_coloc.iloc[0]) == 1)
    # 6. H16: partner waking raised x4 after exits -> ratio ~ (1 - (1 - p1)^120) / (1 - (1 - p0)^120); null -> ~1
    for p1, lo_, hi_, nm in ((1 / 200, 3.5, 9.0, "raised"), (1 / 1500, 0.7, 1.4, "null")):
        T_ = 10 * 86400
        zl = np.full(T_, 1, np.int8)
        t = 3000
        exits_t = []
        while t < T_ - 5000:
            zl[t:t + 600] = 3
            exits_t.append(t)
            t += int(rng.integers(2400, 4800))
        sB = np.full(T_, N, np.int8)
        p0 = 1 / 1500
        prob = np.full(T_, p0)
        for e in exits_t:
            prob[e:e + 120] = p1
        on = np.flatnonzero(rng.random(T_) < prob)
        for o in on:
            sB[o:o + 20] = W
        zz = {"SF07": zl, "SF08": np.full(T_, 1, np.int8), "SF09": np.full(T_, 1, np.int8)}
        arr = {"SF08": sB}
        ex2 = house_exits(zz)
        Pp, Ch = h16_pairs(zz, arr, ex2)
        r = h16_ratio(Pp, Ch, "woke", n_boot=200) if len(Pp) else {"ratio": np.nan}
        exp_r = (1 - (1 - p1) ** 120) / (1 - (1 - p0) ** 120)
        check(f"H16 {nm}: ratio {r['ratio']:.2f} (theory {exp_r:.2f}; {r.get('pairs', 0)} pairs) in [{lo_}, {hi_}]", lo_ <= r["ratio"] <= hi_)
    # 7. NREM-step term recovery (Step C's synthetic steps): rain on WAKE +0.5, REM 0; n_coloc by phase
    D = C.synth_D(np.random.default_rng(7), n_per=1200, gamma_n=-0.25, dark_x_n=0.2)
    n = len(D["y"])
    blocks = np.unique(D["block"])
    rainy_blocks = set(rng.choice(blocks, 6, replace=False))
    D["rain_night"] = np.isin(D["block"], list(rainy_blocks)).astype(float)
    eR = -4.6 + 1.5 * (D["lP_K"] - 1.0) - 0.9 * D["dark"]
    eW = -3.8 + 0.5 * D["rain_night"] - 0.25 * D["n_coloc"] + 0.2 * D["dark"] * D["n_coloc"]
    pr = np.column_stack([np.ones(n), np.exp(eR), np.exp(eW)])
    pr /= pr.sum(1, keepdims=True)
    D["y"] = (np.random.default_rng(8).random(n)[:, None] > pr.cumsum(1)).sum(1).astype(np.int8)
    spec = {**C.specs_c1("K")["b_Bfull"], "raw": ("rain_night", "n_coloc"), "raw_x_dark": ("n_coloc",)}
    f = C.mn_job("t", D, np.arange(n), spec)
    rw, rr = lc(f, {"rain_night": 1.0}, 1), lc(f, {"rain_night": 1.0}, 0)
    nl, nd = lc(f, PHASE_W["light"], 1), lc(f, PHASE_W["dark"], 1)
    check(f"step model: rain on WAKE {fmt_t(rw)} covers +0.5, on REM {fmt_t(rr)} covers 0; n_coloc WAKE light {fmt_t(nl)} covers -0.25, "
          f"dark {fmt_t(nd)} covers -0.05",
          rw["ci_lo"] <= 0.5 <= rw["ci_hi"] and rr["ci_lo"] <= 0 <= rr["ci_hi"] and nl["ci_lo"] <= -0.25 <= nl["ci_hi"] and nd["ci_lo"] <= -0.05 <= nd["ci_hi"])
    # 8. REM-step model: temperature lowers REM -> WAKE by -0.15 per degC
    m_ = 40000
    Tt = pd.DataFrame({"animal": rng.choice(ANIMALS, m_), "block": rng.choice([f"b{i}" for i in range(20)], m_), "elapsed": 10 * rng.integers(0, 15, m_),
                       "hour": rng.uniform(0, 24, m_), "T_day": rng.uniform(0, 12, m_), "dark": rng.integers(0, 2, m_).astype(float),
                       "wbin": rng.choice(WB_LEVELS, m_), "temp_anom": rng.normal(0, 3, m_)})
    e1 = -2.2 + 0 * Tt.temp_anom
    e2 = -3.0 - 0.15 * Tt.temp_anom
    pr = np.column_stack([np.ones(m_), np.exp(e1), np.exp(e2)])
    pr /= pr.sum(1, keepdims=True)
    Tt["y"] = (rng.random(m_)[:, None] > pr.cumsum(1)).sum(1).astype(np.int8)
    fr = rem_fit(Tt, np.arange(m_), ("temp_anom",))
    cw, cn_ = lc(fr, {"temp_anom": 1.0}, 1), lc(fr, {"temp_anom": 1.0}, 0)
    check(f"REM-step model: temp on -> WAKE {fmt_t(cw)} covers -0.15; on -> NREM {fmt_t(cn_)} covers 0",
          cw["ci_lo"] <= -0.15 <= cw["ci_hi"] and cn_["ci_lo"] <= 0 <= cn_["ci_hi"])
    # 9. H4 OLS with animal + night FE recovers an activity coefficient of +2.0 (and 0 when absent)
    k = 1500
    E = pd.DataFrame({"animal": rng.choice(ANIMALS, k), "period": rng.choice([f"p{i}" for i in range(12)], k), "block": rng.choice([f"b{i}" for i in range(22)], k)})
    E["l_d"] = rng.normal(6, 1, k)
    E["darkf"] = rng.integers(0, 2, k).astype(float)
    E["l_path"] = 0.5 * E.l_d + rng.normal(0, 1, k)
    fe_a = {a: rng.normal(0, 2) for a in ANIMALS}
    fe_p = {f"p{i}": rng.normal(0, 3) for i in range(12)}
    base_y = 1.5 * E.l_d + 4 * E.darkf + E.animal.map(fe_a) + E.period.map(fe_p) + rng.normal(0, 4, k)
    for true in (2.0, 0.0):
        y = base_y + true * E.l_path
        ft = term(ols_fe(y, E[["l_d", "l_path", "darkf"]], [E.animal, E.period], E.block), "l_path")
        check(f"H4 OLS (animal + night FE): activity {fmt_t(ft)} covers {true}", ft["ci_lo"] <= true <= ft["ci_hi"])
    # 10. H17 Cox: site change HR 0.5 recovered
    from sleep_explore import cox, cterm
    k = 1200
    df = pd.DataFrame({"animal": rng.choice(ANIMALS, k), "block": rng.choice([f"b{i}" for i in range(22)], k),
                       "site_change": (rng.random(k) < 0.3).astype(float), "l_d": rng.normal(7, 0.8, k)})
    lam = 1 / 900 * np.exp(np.log(0.5) * df.site_change - 0.3 * (df.l_d - 7))
    tt = rng.exponential(1 / lam)
    cc = rng.uniform(600, 6000, k)
    df["T_s"], df["event"] = np.minimum(tt, cc), (tt <= cc).astype(int)
    c = cterm(cox(df, ["site_change", "l_d"], strata="animal", groups="block"), "site_change")
    check(f"H17 Cox: site-change log HR {fmt_t(c)} covers ln 0.5 = -0.693", c["ci_lo"] <= np.log(0.5) <= c["ci_hi"] and c["ci_hi"] < 0)
    # 11. term_row rule
    tr = term_row("final", "X", "m", "t", {"coef": 0.3, "se": 0.1, "ci_lo": 0.1, "ci_hi": 0.5, "p": 0.01},
                  {a: v for a, v in zip(ANIMALS, [0.2, 0.1, 0.4, 0.3, -0.1, 0.2])}, +1, 100)
    tr2 = term_row("final", "X", "m", "t", {"coef": 0.3, "se": 0.1, "ci_lo": 0.1, "ci_hi": 0.5, "p": 0.01},
                   {a: v for a, v in zip(ANIMALS, [0.2, -0.1, 0.4, 0.3, -0.1, 0.2])}, +1, 100)
    check("term rule: CI > 0 with 5/6 holds; with 4/6 does not", tr["holds_term"] and not tr2["holds_term"])
    print(f"selftest {'PASS' if ok_all else 'FAIL'} ({time.time() - t_start:.0f} s)", flush=True)
    if not ok_all:
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["run"])
    ap.add_argument("--parts", nargs="*", default=list(PARTS), choices=list(PARTS))
    ap.add_argument("--scorings", nargs="+", default=["final", "pass2med"], choices=list(SCORINGS))
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--zone-cache", default=None, help=f"zone_per_second.npz (default: Step C's {ZONE_CACHE})")
    ap.add_argument("--pos-cache", default=None, help="pos_per_second.npz from an earlier F2 run (re-read, not re-derived)")
    ap.add_argument("--scratch", action="store_true", help="write the report, CSVs and figures into the run folder only")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.workers > 6:
        print("workers capped at 6 (shared PC)", flush=True)
        a.workers = 6
    if a.selftest:
        selftest()
    elif a.cmd == "run":
        run(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
