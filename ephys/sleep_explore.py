r"""Sleep behaviour explore, Step A: the reproduction gate (cohort 2026c).

Plan: implementation_plan/2026-10-08-sleep-behaviour-explore.md (sections 1, 3 and 5 Step A; the pass rules there are fixed).
Step A re-does, in repo code and with the plan's definitions, five checks that the logic audit
(docs/methods/sleep_logic_audit_2026-10-08.md, Q2 / Q4 / Q5) ran with throwaway scripts.

Inputs (plan section 1):
- the scored 1-s states: FINAL (states_1s_final) and the fixed-threshold check pass2med_remclean (states_1s_pass2med),
  each through sleep_schedule.included_sessions + sleep_cycles_v2.build_records (cut at 2026-09-11 19:40);
- light = NOAA sunrise..sunset (sleep_schedule_phase3.light_flags); never clock hours;
- the Phase-0 gap table (battery rounds); the Phase-6 event library; the pilot sessions scored with the ungated `imu`
  variant (useEMG_NREM = False, no REM-clean rules).

Parts (every quantity is defined, formula + text, in the report's Definitions section):
  a1  #6a  a wake >= 7 min is not resumed: censored Cox (animal strata), the B1b-style OLS on events (the plan's
           literal rule), a simulated resumption benchmark, and a forward-chained RESUME vs RESTART hazard comparison.
  a2  #6b  graded only at night: the a1 table split by dark / light at the wake end, ln d slopes (plan ranges) and
           categorical wake-length bins.
  a3  #14b matched night gain: SLEEP episodes after 2-7 and 7-30-min wakes, REM bouts per NREM hour and first-REM
           latency, dark vs light, the 3 h after battery-round gaps excluded.
  a4  #10  payback across battery-round gaps with phase x day baselines; day-demeaned; NREM debt partialled; bout
           count vs bout duration.
  a5  #28b / #29a  woke60 of first movers vs controls with wakes < 15 s after the onset excluded (library), and the
           same participants re-read under the ungated scoring of the pilot sessions.

Usage: python ephys/sleep_explore.py stepA [--parts a1 a2 a3 a4 a5] [--smoke]
       python ephys/sleep_explore.py --selftest
--smoke runs every part on synthetic data and writes everything into the run folder (never the report paths).
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
from sleep_cycles import bouts, loglosses  # noqa: E402
from sleep_cycles_v2 import build_records  # noqa: E402
from sleep_schedule import N, R, REVIEW, STATES, W, episode_units, included_sessions  # noqa: E402
from sleep_schedule_phase2 import (b1b_fit, baselines, bins10, build_steps, comp_windows, compare, design2,  # noqa: E402
                                   feats2, forward_folds, wake_to_kth_rem)
from sleep_schedule_phase3 import episodes_of, km_median, light_flags  # noqa: E402

PASS2MED = Path("D:/3rd_rat_spikes/analysis/sleep_server/states_1s_pass2med")
SCORINGS = {"FINAL": STATES, "pass2med": PASS2MED}
LIBRARY = Path("D:/Field2026_analysis_out/2026c/sleep_events_20261008_1721")
PILOT_ROOT = Path("D:/3rd_rat_spikes/analysis/sleep")
P0_MANIFEST = ROOT / "results/2026c/ephys_spikes/reports/run_manifest_sleep_schedule_phase0_2026c.json"
PLAN = "implementation_plan/2026-10-08-sleep-behaviour-explore.md"

LONG_S = 420                      # a long wake (plan: >= 7 min; Watson 2016 WAKE-SLEEP mark)
MA_S = 40                         # microarousal limit (Watson 2016)
SLEEP_END_WAKE_S = 120            # SLEEP split rule (Watson 2016)
SLEEP_MIN_S = 1200                # SLEEP >= 20 min
POST_S = 3 * 3600                 # post-handling exclusion (plan section 3) and the a1 record-start sensitivity
ROUND_CAUSES = ("round_logged", "round_inferred")
A2_EDGES_MIN = [7, 15, 30, 60, 120, 240, np.inf]
A2_LABELS = ["7-15", "15-30", "30-60", "60-120", "120-240", ">=240"]
A2_RANGE = {"dark": (420, 4 * 3600), "light": (420, 1800)}      # plan A2: dark 7 min-4 h, light 7-30 min
PW_BINS = (("2-7 min", 120, 420), ("7-30 min", 420, 1800))
EXCL_S = 15                       # A5: wakes beginning < 15 s after the onset are excluded
AMP_FS = 20000
COLORS = {"dark": "#2a78d6", "light": "#eb6834", "ink": "#52514e"}
COX_A1 = ["l_d", "l_npre", "anchor", "sin1", "cos1", "sin2", "cos2", "darkf"]
OLS_A1 = ["l_d", "l_npre", "anchor", "sin1", "cos1", "sin2", "cos2"]        # = sleep_schedule_phase2.b1b_fit


# ================================================================== statistics helpers
def harm(hour, index=None) -> pd.DataFrame:
    h = np.asarray(hour, float)
    return pd.DataFrame({f"{f}{k}": fn(2 * np.pi * k * h / 24) for k in (1, 2) for f, fn in (("sin", np.sin), ("cos", np.cos))},
                        index=index)


def ols(y: pd.Series, X: pd.DataFrame, groups=None, fe=None):
    """OLS with an intercept, optional fixed-effect dummies and SEs clustered by `groups` (HC1 if clustering fails).
    Constant columns are dropped (they would be collinear with the intercept)."""
    import statsmodels.api as sm
    Xd = X.astype(float)
    Xd = Xd.loc[:, [c for c in Xd.columns if Xd[c].nunique() > 1]]
    if fe is not None and pd.Series(fe).nunique() > 1:
        Xd = pd.concat([Xd, pd.get_dummies(pd.Series(np.asarray(fe), index=X.index), prefix="fe", drop_first=True, dtype=float)], axis=1)
    Xd = sm.add_constant(Xd, has_constant="add")
    yv = pd.Series(np.asarray(y, float), index=X.index)
    if groups is not None and pd.Series(groups).nunique() > 1:
        try:
            return sm.OLS(yv, Xd).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(np.asarray(groups))[0]})
        except Exception:  # noqa: BLE001
            pass
    return sm.OLS(yv, Xd).fit(cov_type="HC1")


def term(fit, t: str) -> dict:
    if fit is None or t not in fit.params.index:
        return {"coef": np.nan, "se": np.nan, "ci_lo": np.nan, "ci_hi": np.nan, "p": np.nan}
    ci = fit.conf_int().loc[t]
    return {"coef": float(fit.params[t]), "se": float(fit.bse[t]), "ci_lo": float(ci.iloc[0]), "ci_hi": float(ci.iloc[1]),
            "p": float(fit.pvalues[t])}


def cox(df: pd.DataFrame, cols: list[str], T: str = "T_s", E: str = "event", strata: str | None = "animal",
        groups: str | None = "block") -> pd.DataFrame | None:
    """Cox proportional hazards (statsmodels PHReg, Efron ties), optional strata; SEs = cluster-robust sandwich over
    `groups` (score residuals summed per cluster, small-sample factor G/(G-1)); statsmodels' own grouped SEs are NaN in
    0.14.6, so the sandwich is computed here. Returns one row per term (None if the fit fails)."""
    from scipy.stats import norm
    from statsmodels.duration.hazard_regression import PHReg
    d = df.dropna(subset=list(cols) + [T, E])
    cols = [c for c in cols if d[c].nunique() > 1]
    cols = [c for c in cols if d[c].nunique() > 2 or d[c].value_counts().min() >= 10]   # near-constant binary terms separate
    if len(d) < 10 or d[E].sum() < 3 or not cols:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            m = PHReg(np.maximum(d[T].to_numpy(float), 1.0), d[cols].to_numpy(float), status=d[E].to_numpy(int),
                      strata=pd.factorize(d[strata])[0] if strata else None, ties="efron")
            r = m.fit()
            Hi = np.linalg.inv(-m.hessian(r.params))
            sr = np.nan_to_num(np.asarray(r.score_residuals, float))
    except Exception:  # noqa: BLE001
        return None
    b = np.asarray(r.params, float)
    se_m = np.sqrt(np.diag(Hi))
    G = 0
    if groups:
        g = pd.factorize(d[groups])[0]
        G = int(g.max()) + 1
        U = np.zeros((G, len(cols)))
        np.add.at(U, g, sr)
        se = np.sqrt(np.diag(Hi @ U.T @ U @ Hi) * G / max(G - 1, 1))
    else:
        se = se_m
    return pd.DataFrame({"term": cols, "coef": b, "se": se, "se_model": se_m, "ci_lo": b - 1.96 * se, "ci_hi": b + 1.96 * se,
                         "p": 2 * norm.sf(np.abs(b / se)), "HR": np.exp(b), "n": len(d), "events": int(d[E].sum()),
                         "clusters": G}).set_index("term")


def cterm(cx: pd.DataFrame | None, t: str) -> dict:
    if cx is None or t not in cx.index:
        return {"coef": np.nan, "se": np.nan, "ci_lo": np.nan, "ci_hi": np.nan, "p": np.nan, "HR": np.nan}
    r = cx.loc[t]
    return {"coef": float(r.coef), "se": float(r.se), "ci_lo": float(r.ci_lo), "ci_hi": float(r.ci_hi), "p": float(r.p), "HR": float(r.HR)}


def fmt_ci(d: dict, nd: int = 3) -> str:
    return f"{d['coef']:+.{nd}f} [{d['ci_lo']:+.{nd}f}, {d['ci_hi']:+.{nd}f}]" if np.isfinite(d.get("coef", np.nan)) else "n/a"


# ================================================================== A1 / A2: post-long-wake table
def post_wake_table(recs: list[dict]) -> pd.DataFrame:
    """One row per wake bout >= LONG_S followed by NREM in its record (definitions: report)."""
    rows = []
    for rc in recs:
        st = rc["state"]
        bl = bouts(st)
        ma = {(a, b) for a, b in episode_units(st, MA_S)["ma"]}
        cn = np.r_[0, np.cumsum(st == N)]
        last_rem_end = None
        for i, (s, a, b) in enumerate(bl):
            if s == R:
                last_rem_end = b if (a > 0 and st[a - 1] != 0) else None
                continue
            if not (s == W and (b - a) >= LONG_S and i + 1 < len(bl) and bl[i + 1][0] == N):
                continue
            n_pre = int(cn[a] - cn[last_rem_end]) if last_rem_end is not None else 0
            T, ev, why, stop = 0, 0, "record_end", len(st)
            for s2, a2, b2 in bl[i + 1:]:
                if s2 == 0:
                    why, stop = "unknown", a2
                    break
                if s2 == W and (b2 - a2) >= LONG_S:
                    why, stop = "wake_ge_7min", a2
                    break
                if s2 == R:
                    ev, why, stop = 1, "rem", a2
                    break
                if s2 == N or (s2 == W and (a2, b2) in ma):
                    T += b2 - a2
            t_end = rc["start"] + pd.Timedelta(seconds=b)
            rows.append({"animal": rc["animal"], "record_id": rc["record_id"], "block": rc["block"], "t_wake_end": t_end,
                         "hour": t_end.hour + t_end.minute / 60 + t_end.second / 3600, "d_s": b - a, "n_pre": n_pre,
                         "anchor": int(last_rem_end is not None), "T_s": T, "event": ev, "why": why, "wall_s": stop - b,
                         "wake_a": a, "wake_b": b, "stop": stop, "off_rec_s": b, "left_cens": bool(a == 0 or st[a - 1] == 0)})
    D = pd.DataFrame(rows)
    if D.empty:
        return D
    D["dark"] = ~light_flags(D.t_wake_end)
    D["darkf"] = D.dark.astype(float)
    D["l_d"] = np.log(D.d_s.astype(float))
    D["l_npre"] = np.log1p(D.n_pre.astype(float))
    D["l_T"] = np.log(np.maximum(D.T_s.astype(float), 1.0))
    D = pd.concat([D, harm(D.hour, D.index)], axis=1)
    D["d_bin"] = pd.cut(D.d_s / 60, A2_EDGES_MIN, right=False, labels=A2_LABELS)
    return D


def a1_ols(tab: pd.DataFrame) -> tuple[dict, dict, pd.DataFrame]:
    ev = tab[(tab.event == 1) & (tab.T_s > 0)]
    f = ols(ev.l_T, ev[OLS_A1], groups=ev.block, fe=ev.animal)
    pa = []
    for an, g in ev.groupby("animal"):
        if len(g) >= 15:
            fa = ols(g.l_T, g[OLS_A1])
            pa.append({"animal": an, "events": len(g), "ols_l_npre": term(fa, "l_npre")["coef"], "ols_l_d": term(fa, "l_d")["coef"]})
    return term(f, "l_npre"), term(f, "l_d"), pd.DataFrame(pa)


def a1_cox_per_animal(tab: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for an, g in tab.groupby("animal"):
        if len(g) >= 15 and g.event.sum() >= 5:
            cx = cox(g, ["l_d", "l_npre", "anchor", "darkf", "sin1", "cos1"], strata=None, groups=None)
            rows.append({"animal": an, "episodes": len(g), "episode_events": int(g.event.sum()), "cox_l_npre": cterm(cx, "l_npre")["coef"],
                         "cox_l_d": cterm(cx, "l_d")["coef"]})
    return pd.DataFrame(rows)


def resume_benchmark(tab: pd.DataFrame, rng, n_rep: int = 100) -> pd.DataFrame:
    """Simulated coefficients of ln(1+N_pre) in two worlds (definitions: report). Event times are redrawn from the
    observed post-wake NREM-to-REM distribution; observed censoring times are kept."""
    evT = np.sort(tab.loc[tab.event == 1, "T_s"].to_numpy(float))
    npre = tab.n_pre.to_numpy(float)
    anc = tab.anchor.to_numpy(bool)
    C = np.where(tab.event.to_numpy() == 1, np.inf, tab.T_s.to_numpy(float))
    out = []
    for world in ("restart", "resume"):
        for k in range(n_rep):
            lo = np.where(anc, np.searchsorted(evT, npre, side="right"), 0) if world == "resume" else np.zeros(len(tab), int)
            full = lo >= len(evT)
            idx = np.minimum(lo + np.floor(rng.random(len(tab)) * np.maximum(len(evT) - lo, 1)).astype(int), len(evT) - 1)
            y = evT[idx]
            t = np.where(anc, y - npre, y) if world == "resume" else y
            t = np.maximum(np.where(full, 10.0, t), 1.0)
            Ts = np.minimum(t, C)
            sim = tab.assign(T_s=Ts, event=(t <= C).astype(int), l_T=np.log(Ts))
            ev = sim[sim.event == 1]
            fo = ols(ev.l_T, ev[OLS_A1], fe=ev.animal)
            cx = cox(sim, COX_A1, groups=None)
            out.append({"world": world, "rep": k, "ols_l_npre": term(fo, "l_npre")["coef"], "cox_l_npre": cterm(cx, "l_npre")["coef"]})
    return pd.DataFrame(out)


# ---------------- A1 (iii): held-out RESUME vs RESTART on the 10-s NREM steps of post-long-wake stretches
def stretch_steps(recs: list[dict], tab: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """10-s NREM steps (sleep_schedule.record_steps_s via phase2.build_steps) of anchored post-long-wake stretches
    before their first REM (or censoring). Adds the two counters at the bout start."""
    use = tab[tab.anchor == 1]
    rids = sorted(use.record_id.unique())
    sub = [rc for rc in recs if rc["record_id"] in set(rids)]
    steps = build_steps(sub)
    by_rec = {k: g for k, g in steps.groupby("record_id")}
    cns = {rc["record_id"]: np.r_[0, np.cumsum(rc["state"] == N)] for rc in sub}
    out = []
    for r in use.itertuples():
        g = by_rec.get(r.record_id)
        if g is None:
            continue
        g = g[(g.bout_start >= r.wake_b) & (g.bout_start < r.stop)]
        if g.empty:
            continue
        g = g.copy()
        cn = cns[r.record_id]
        g["n_restart"] = cn[g.bout_start.to_numpy(int)] - cn[r.wake_b]
        g["n_resume"] = r.n_pre + g.n_restart
        g["l_dlong"] = np.log(r.d_s)
        g["row"] = r.Index
        out.append(g)
    if not out:
        return pd.DataFrame(), np.nan
    S = pd.concat(out, ignore_index=True)
    S["dark"] = (~light_flags(S.t)).astype(float)
    return S, float((S.n_since == S.n_resume).mean())


HOLD_TERMS = ["L1", "ntspl", "rem"]
HOLD_EXTRA = ["l_dlong", "dark"]


def design_x(df: pd.DataFrame, terms: list[str], extra: list[str], st: dict | None, levels: list[str]):
    X, st = design2(feats2(df), df.animal, terms, st, levels)
    if extra:
        E = df[extra].astype(float)
        if "x_mu" not in st:
            st["x_mu"], st["x_sd"] = E.mean(), E.std().replace(0, 1).fillna(1)
        X = np.column_stack([X, ((E - st["x_mu"]) / st["x_sd"]).to_numpy()])
    return X, st


def run_cv_x(models: dict[str, tuple[pd.DataFrame, list, list]], folds) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Like sleep_schedule_phase2.run_cv, for models that differ in their data columns (same rows, same folds);
    output columns as run_cv so phase2.compare applies."""
    from sklearn.linear_model import LogisticRegression
    base = next(iter(models.values()))[0]
    F, FA = [], []
    for tr_i, te_i in folds:
        tr0 = base.loc[tr_i]
        te_i = base.loc[te_i].index[base.loc[te_i].animal.isin(tr0.animal.unique())]
        te0 = base.loc[te_i]
        if len(tr0) == 0 or (te0.y == 1).sum() == 0 or tr0.y.nunique() < 3:
            continue
        lv = sorted(tr0.animal.unique())
        LL = {}
        for name, (df, terms, extra) in models.items():
            tr, te = df.loc[tr_i], df.loc[te_i]
            X, st = design_x(tr, terms, extra, None, lv)
            m = LogisticRegression(C=1e4, max_iter=3000).fit(X, tr.y.to_numpy())
            Xt, _ = design_x(te, terms, extra, st, lv)
            p = np.full((len(te), 3), 1e-12)
            p[:, m.classes_] = m.predict_proba(Xt)
            LL[name] = loglosses(p / p.sum(1, keepdims=True), te.y.to_numpy())["ll"]
        blk = te0.block.iloc[0]
        F.append({"fold": blk, "n": len(te0), "n_rem": int((te0.y == 1).sum()), **{f"ll_{n}": LL[n].mean() for n in models}})
        for an, g in te0.groupby("animal"):
            pos = te0.index.get_indexer(g.index)
            FA.append({"fold": blk, "animal": an, "n": len(g), **{f"ll_{n}": LL[n][pos].mean() for n in models}})
    return pd.DataFrame(F), pd.DataFrame(FA)


def heldout_counters(S: pd.DataFrame, label: str) -> dict:
    if S.empty or S.block.nunique() < 8:
        return {"comparison": "RESTART vs RESUME", "subset": label, "n_steps": len(S)}
    S = S.reset_index(drop=True)
    res, rst = S.copy(), S.copy()
    res["n_since"], rst["n_since"] = S.n_resume, S.n_restart
    F, FA = run_cv_x({"RESUME": (res, HOLD_TERMS, HOLD_EXTRA), "RESTART": (rst, HOLD_TERMS, HOLD_EXTRA)}, forward_folds(S))
    r = compare(F, FA, "RESUME", "RESTART", label)
    r["stretches"] = int(S.row.nunique())
    return r


# ================================================================== A3: SLEEP episodes
def sleep_episode_table(recs: list[dict]) -> pd.DataFrame:
    rows = []
    for rc in recs:
        st = rc["state"]
        bl = bouts(st)
        end_at = {b: (s, a) for s, a, b in bl}
        for a, b in episodes_of(st, SLEEP_MIN_S):
            seg = st[a:b]
            on = [x0 for s, x0, _ in bouts(seg) if s == R]
            pw, pre, pre_cens = end_at.get(a), np.nan, False
            if pw is not None and pw[0] == W:
                wa = pw[1]
                if wa == 0 or st[wa - 1] == 0:
                    pre_cens = True
                elif (a - wa) > SLEEP_END_WAKE_S:
                    pre = float(a - wa)
            t0 = rc["start"] + pd.Timedelta(seconds=a)
            rows.append({"animal": rc["animal"], "block": rc["block"], "record_id": rc["record_id"], "t0": t0, "dur_s": b - a,
                         "nrem_s": int((seg == N).sum()), "rem_s": int((seg == R).sum()), "rem_n": len(on),
                         "lat_s": max(on[0], 1) if on else b - a, "lat_event": int(bool(on)), "pre_wake_s": pre,
                         "pre_left_cens": pre_cens})
    E = pd.DataFrame(rows)
    if E.empty:
        return E
    E["dark"] = ~light_flags(E.t0)
    E["darkf"] = E.dark.astype(float)
    E["nrem_h"] = E.nrem_s / 3600
    E["l_dur"] = np.log(E.dur_s.astype(float))
    E["l_pw"] = np.log(E.pre_wake_s)
    return E


def after_gap_mask(df: pd.DataFrame, tcol: str, gaps: pd.DataFrame, causes, seconds: int = POST_S) -> np.ndarray:
    m = np.zeros(len(df), bool)
    for g in gaps[gaps.cause.isin(causes)].itertuples():
        ge = pd.Timestamp(g.gap_end)
        m |= ((df.animal == g.animal) & (df[tcol] >= ge) & (df[tcol] < ge + pd.Timedelta(seconds=seconds))).to_numpy()
    return m


def a3_bin(Eb: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    import statsmodels.api as sm
    r = {}
    for ph, dk in (("dark", True), ("light", False)):
        s = Eb[Eb.dark == dk]
        r[f"n_{ph}"] = len(s)
        r[f"animals_{ph}"] = s.animal.nunique()
        r[f"rate_{ph}"] = s.rem_n.sum() / s.nrem_h.sum() if s.nrem_h.sum() > 0 else np.nan
        r[f"mean_ep_rate_{ph}"] = float((s.rem_n / s.nrem_h).mean()) if len(s) else np.nan
        r[f"km_median_lat_min_{ph}"] = km_median(s.lat_s, s.lat_event) / 60 if len(s) else np.nan
    r["ratio_pooled"] = r["rate_dark"] / r["rate_light"] if r["rate_light"] else np.nan
    r["ratio_mean_ep"] = r["mean_ep_rate_dark"] / r["mean_ep_rate_light"] if r["mean_ep_rate_light"] else np.nan
    # Poisson GLM rate ratio, animal FE + ln duration, offset ln NREM h, SEs by block
    g = Eb[Eb.nrem_h > 0]
    try:
        X = pd.concat([g[["darkf", "l_dur"]], pd.get_dummies(g.animal, prefix="fe", drop_first=True, dtype=float)], axis=1)
        X = sm.add_constant(X.astype(float), has_constant="add")
        f = sm.GLM(g.rem_n.astype(float), X, family=sm.families.Poisson(), offset=np.log(g.nrem_h)).fit(
            cov_type="cluster", cov_kwds={"groups": pd.factorize(g.block)[0]})
        ci = f.conf_int().loc["darkf"]
        r.update(glm_rr=float(np.exp(f.params["darkf"])), glm_rr_lo=float(np.exp(ci.iloc[0])), glm_rr_hi=float(np.exp(ci.iloc[1])),
                 glm_p=float(f.pvalues["darkf"]))
    except Exception:  # noqa: BLE001
        r.update(glm_rr=np.nan, glm_rr_lo=np.nan, glm_rr_hi=np.nan, glm_p=np.nan)
    cx = cox(Eb.dropna(subset=["l_pw"]), ["darkf", "l_pw", "l_dur"], T="lat_s", E="lat_event")
    c = cterm(cx, "darkf")
    r.update(cox_HR_dark=c["HR"], cox_HR_lo=np.exp(c["ci_lo"]), cox_HR_hi=np.exp(c["ci_hi"]), cox_p=c["p"])
    pa = []
    for an, ga in Eb.groupby("animal"):
        d_, l_ = ga[ga.dark], ga[~ga.dark]
        row = {"animal": an, "n_dark": len(d_), "n_light": len(l_)}
        if len(d_) >= 3 and len(l_) >= 3 and l_.rem_n.sum() > 0:
            row["rate_dark"] = d_.rem_n.sum() / d_.nrem_h.sum()
            row["rate_light"] = l_.rem_n.sum() / l_.nrem_h.sum()
            row["ratio"] = row["rate_dark"] / row["rate_light"]
            ed, el = d_.lat_event.sum(), l_.lat_event.sum()
            row["first_rem_rate_ratio"] = (ed / d_.lat_s.sum()) / (el / l_.lat_s.sum()) if el > 0 else np.nan
        pa.append(row)
    PA = pd.DataFrame(pa)
    q = PA.dropna(subset=["ratio"]) if "ratio" in PA else PA.iloc[:0]
    r["animals_qualifying"] = len(q)
    r["animals_ratio_lt1"] = int((q.ratio < 1).sum()) if len(q) else 0
    r["animals_ratio_le06"] = int((q.ratio <= 0.6).sum()) if len(q) else 0
    r["animals_later_first_rem"] = int((q.first_rem_rate_ratio < 1).sum()) if len(q) and "first_rem_rate_ratio" in q else 0
    return r, PA


# ================================================================== A4: baselines with phase x day
def _Xd(df: pd.DataFrame, levels: list[str]) -> np.ndarray:
    import statsmodels.api as sm
    X = harm(df.hour.to_numpy())
    X["day"] = df.day.to_numpy(float)
    dk = df.dark.to_numpy(float)
    X["dark"] = dk
    X["dark_x_day"] = dk * X["day"].to_numpy()
    X = pd.concat([X, pd.get_dummies(pd.Categorical(df.animal, categories=levels), dtype=float).iloc[:, 1:].reset_index(drop=True)], axis=1)
    return sm.add_constant(X, has_constant="add").to_numpy()


def baselines_d(B: pd.DataFrame, RB: pd.DataFrame) -> pd.DataFrame:
    """sleep_schedule_phase2.baselines with a dark step and dark x day added to the design (plan section 3, day
    baselines). Leave-one-block-out; B and RB need a `dark` column."""
    import statsmodels.api as sm
    levels = sorted(B.animal.unique())
    B = B.copy()
    for c in ("e_rem_s", "e_nrem_s", "e_rem_on", "e_rem_dur"):
        B[c] = np.nan
    Bk = B[B.rec_s > 0]
    for blk in sorted(B.block.unique()):
        tr, te = Bk[Bk.block != blk], B[B.block == blk]
        if not len(te):
            continue
        Xtr, Xte = _Xd(tr, levels), _Xd(te, levels)
        for col, ecol in (("rem_s", "e_rem_s"), ("nrem_s", "e_nrem_s")):
            g = sm.GLM(tr[col] / tr.rec_s, Xtr, family=sm.families.Binomial(), var_weights=tr.rec_s).fit()
            B.loc[te.index, ecol] = g.predict(Xte) * te.rec_s.to_numpy()
        g = sm.GLM(tr.rem_on, Xtr, family=sm.families.Poisson(), offset=np.log(tr.rec_s / 600)).fit()
        B.loc[te.index, "e_rem_on"] = g.predict(Xte, offset=np.log(np.maximum(te.rec_s, 1) / 600)) * (te.rec_s > 0)
        rtr = RB[RB.block != blk]
        o = sm.OLS(np.log(rtr.dur_s), _Xd(rtr, levels)).fit()
        B.loc[te.index, "e_rem_dur"] = np.exp(o.predict(Xte)) * float(np.mean(np.exp(o.resid)))
    return B


A4_MODELS = [("pay_rem", ["debt_rem"]), ("pay_rem", ["debt_rem", "debt_nrem"]), ("pay_rem_n", ["debt_rem"]),
             ("pay_rem_dur", ["debt_rem"]), ("pay_nrem", ["debt_nrem"])]


def pay_models(Wn: pd.DataFrame) -> pd.DataFrame:
    Wn = Wn.copy()
    Wn["debt_rem"] = Wn.A_e_rem_min - Wn.A_rem_min
    Wn["pay_rem"] = Wn.B_rem_min - Wn.B_e_rem_min
    Wn["debt_nrem"] = Wn.A_e_nrem_min - Wn.A_nrem_min
    Wn["pay_nrem"] = Wn.B_nrem_min - Wn.B_e_nrem_min
    Wn["pay_rem_n"] = Wn.B_rem_n - Wn.B_e_rem_n
    Wn["pay_rem_dur"] = Wn.B_rem_dur_s - Wn.B_e_rem_dur_s
    Wn["cal_day"] = (pd.to_datetime(Wn.t_A) + pd.Timedelta(hours=3)).dt.normalize()
    rows = []
    for kind in ("morning", "evening"):
        for bh in (1, 3):
            g = Wn[(Wn.kind == kind) & (Wn.B_h == bh)]
            for y, xs in A4_MODELS:
                for dm in (False, True):
                    d = g[[y] + xs + ["animal", "A_block", "cal_day"]].dropna().copy()
                    if len(d) < 10:
                        continue
                    if dm:
                        for c in [y] + xs:
                            d[c] = d[c] - d.groupby("cal_day")[c].transform("mean")
                    f = ols(d[y], d[xs], groups=d.A_block, fe=d.animal)
                    t = term(f, xs[0])
                    sg = []
                    for _, ga in d.groupby("animal"):
                        if len(ga) >= 4 + len(xs) and ga[xs[0]].std() > 0:
                            sg.append(np.sign(term(ols(ga[y], ga[xs]), xs[0])["coef"]))
                    rows.append({"kind": kind, "B_h": bh, "outcome": y, "predictors": " + ".join(xs),
                                 "day_demeaned": dm, "n_windows": len(d), "clusters": d.A_block.nunique(),
                                 "slope": t["coef"], "ci_lo": t["ci_lo"], "ci_hi": t["ci_hi"], "p": t["p"],
                                 "animals_positive": int(np.sum(np.array(sg) > 0)), "animals": len(sg),
                                 "mean_x": float(g[xs[0]].mean()), "mean_y": float(g[y].mean())})
    return pd.DataFrame(rows)


def a4_windows(recs: list[dict], gaps: pd.DataFrame) -> dict[str, pd.DataFrame]:
    B, RB = bins10(recs)
    B["dark"] = (~light_flags(B.t + pd.Timedelta(minutes=5))).astype(float)
    RB["dark"] = (~light_flags(RB.t)).astype(float)
    out = {}
    for bname, fn in (("phase x day (plan)", baselines_d), ("common linear day (Phase 2)", baselines)):
        Wn = comp_windows(fn(B, RB), RB, gaps)
        Wn = Wn[Wn.setting.astype(str).str.startswith("across gap (round_")].copy()
        out[bname] = Wn
    return out


# ================================================================== A5
def _bool(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().eq("true")


def woke_summary(df: pd.DataFrame) -> dict:
    n = len(df)
    k = int(df.woke.sum())
    early = df.woke & (df.lat < EXCL_S)
    n2 = n - int(early.sum())
    k2 = int((df.woke & ~early).sum())
    return {"n": n, "woke60": k / n if n else np.nan, "n_excl15": n2, "woke60_excl15": k2 / n2 if n2 else np.nan,
            "early_wake_share": float(early.mean()) if n else np.nan}


def mover_excess(mov: pd.DataFrame, ctl: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """mov / ctl: columns woke (bool), lat (s), + `by`. Excess = mover - control share, all wakes and excl15."""
    rows = []
    keys = sorted(set(map(tuple, mov[by].drop_duplicates().to_numpy())) & set(map(tuple, ctl[by].drop_duplicates().to_numpy())))
    for k in keys:
        mm = (mov[by] == pd.Series(k, index=by)).all(1)
        cm = (ctl[by] == pd.Series(k, index=by)).all(1)
        a, c = woke_summary(mov[mm]), woke_summary(ctl[cm])
        r = dict(zip(by, k))
        r.update({"mover_n": a["n"], "mover_woke60": a["woke60"], "control_n": c["n"], "control_woke60": c["woke60"],
                  "excess_all": a["woke60"] - c["woke60"], "mover_early_share": a["early_wake_share"],
                  "control_early_share": c["early_wake_share"], "mover_n_excl15": a["n_excl15"],
                  "mover_woke60_excl15": a["woke60_excl15"], "control_n_excl15": c["n_excl15"],
                  "control_woke60_excl15": c["woke60_excl15"], "excess_excl15": a["woke60_excl15"] - c["woke60_excl15"]})
        for sfx, (p1, n1, p0, n0) in (("all", (a["woke60"], a["n"], c["woke60"], c["n"])),
                                      ("excl15", (a["woke60_excl15"], a["n_excl15"], c["woke60_excl15"], c["n_excl15"]))):
            se = np.sqrt(p1 * (1 - p1) / max(n1, 1) + p0 * (1 - p0) / max(n0, 1)) if n1 and n0 else np.nan
            r[f"excess_{sfx}_lo"], r[f"excess_{sfx}_hi"] = r[f"excess_{sfx}"] - 1.96 * se, r[f"excess_{sfx}"] + 1.96 * se
        r["ratio_excl15_to_all"] = r["excess_excl15"] / r["excess_all"] if r["excess_all"] else np.nan
        rows.append(r)
    return pd.DataFrame(rows)


def states_from_mat(path: Path) -> np.ndarray:
    from scipy.io import loadmat
    st = loadmat(path, simplify_cells=True)["SleepState"]["idx"]
    return _place(np.asarray(st["timestamps"]).reshape(-1), np.asarray(st["states"]).reshape(-1))


def states_from_npz(path: Path) -> np.ndarray:
    with np.load(path) as z:
        return _place(z["ts"], z["state"])


def _place(ts, state) -> np.ndarray:
    """1-s array indexed like build_records (index i = second i of the session; scorer timestamps start at 1)."""
    ts = np.asarray(ts, float).round().astype(int)
    out = np.zeros(int(ts.max()), np.int8)
    ok = ts >= 1
    out[ts[ok] - 1] = np.asarray(state)[ok].astype(np.int8)
    return out


def load_pilot() -> list[dict]:
    out = []
    for f in sorted((PILOT_ROOT / "imu").glob("*/*/*.SleepState.states.mat")):
        an, sess = f.parent.parent.name, f.parent.name
        if f.name != f"{sess}.SleepState.states.mat":
            continue
        arrs = {"ungated (imu)": states_from_mat(f)}
        g = PILOT_ROOT / "imu_remclean" / an / sess / f"{sess}.SleepState.states.mat"
        if g.exists():
            arrs["gated, same pilot run (imu_remclean)"] = states_from_mat(g)
        fin = STATES / an / f"{sess}.states.npz"
        if fin.exists():
            arrs["FINAL"] = states_from_npz(fin)
        out.append({"animal": an, "session": sess, "arrays": arrs})
    return out


def pilot_outcomes(P: pd.DataFrame, pilot: list[dict], rng, n_ctl: int = 3000) -> tuple[pd.DataFrame, pd.DataFrame]:
    from sleep_events import outcome
    rows, crows = [], []
    for ps in pilot:
        an, sess, arrs = ps["animal"], ps["session"], ps["arrays"]
        Pp = P[(P.animal == an) & (P.session == sess)]
        # second alignment: the library placed states on the field-PC second grid (IMU t_pc); the integer shift in -2..2
        # that best reproduces the library's pre-state from the session's FINAL states is used for every scoring
        code = {"WAKE": W, "NREM": N, "REM": R}
        ref = arrs.get("FINAL")
        shift, agree = 0, np.nan
        if ref is not None and len(Pp):
            kk = Pp[Pp.pre_state.isin(list(code))]
            best = []
            for sh in range(-2, 3):
                sec_ = (kk.amp_sample // AMP_FS).astype(int).to_numpy() + sh
                okk = (sec_ >= 0) & (sec_ < len(ref))
                best.append((float(np.mean(ref[sec_[okk]] == kk.pre_state.map(code).to_numpy()[okk])) if okk.any() else 0.0, sh))
            agree, shift = max(best)
        ps["shift_s"], ps["shift_agreement"] = shift, agree
        n_min = min(len(a) for a in arrs.values())
        pool = np.arange(60, n_min - 601)
        csec = np.sort(rng.choice(pool, size=min(n_ctl, len(pool)), replace=False)) if len(pool) else np.array([], int)
        for lab, s in arrs.items():
            n = len(s)

            def one(sec: int) -> dict:
                if sec < 0 or sec >= n:
                    return {"pre_state": "outside", "state_ok": False}
                st = int(s[sec])
                ok = bool(sec >= 60 and sec + 60 < n and (s[sec - 60:sec + 61] > 0).all())
                if st in (N, R):
                    o = outcome(s, sec)
                    return {"pre_state": o["pre_state"], "state_ok": ok, "woke": bool(o["woke60"]), "lat": o["wake_latency_s"]}
                return {"pre_state": {W: "WAKE"}.get(st, "unknown"), "state_ok": ok}
            for r in Pp.itertuples():
                sec = int(r.amp_sample // AMP_FS) + shift
                rows.append({"animal": an, "session": sess, "scoring": lab, "event_id": r.event_id, "role": r.role_detail,
                             "imu_ok": bool(r.imu_ok), "sec": sec, "lib_pre_state": r.pre_state, "lib_woke60": r.woke60_b,
                             **one(sec)})
            for sec in csec:
                crows.append({"animal": an, "session": sess, "scoring": lab, "sec": int(sec), "role": "control", **one(int(sec))})
    return pd.DataFrame(rows), pd.DataFrame(crows)


# ================================================================== synthetic data (selftest + smoke)
def _dark_fn():
    from sleep_quant import sun_times
    cache = {}

    def is_dark(t: pd.Timestamp) -> bool:
        d = t.date()
        if d not in cache:
            cache[d] = tuple(pd.Timestamp(x) for x in sun_times(d))
        sr, ss = cache[d]
        return not (sr <= t < ss)
    return is_dark


def synth_state(rng, start: pd.Timestamp, n_s: int, mode: str = "restart", night_grade: float = 0.0, dark_gain: float = 1.0,
                p_long: float = 0.07, is_dark=None, req_sd: float = 0.35) -> np.ndarray:
    """Synthetic 1-s states. REM comes when the NREM counter reaches a requirement drawn per cycle (lognormal, median
    900 s; x dark_gain in the dark). A wake >= LONG_S zeroes the counter (mode 'restart', with a new requirement x
    (d/420)^night_grade in the dark) or leaves it (mode 'resume'); shorter wakes and MAs pause it."""
    is_dark = is_dark or _dark_fn()
    seq, L = [], 0

    def req(dk: bool) -> float:
        return float(np.exp(rng.normal(np.log(900), req_sd))) * (dark_gain if dk else 1.0)
    counter, rq, force_n, last = 0.0, req(is_dark(start)), True, N
    while L < n_s:
        u = rng.random()
        if not force_n and u < p_long:
            d = int(np.exp(rng.uniform(np.log(121), np.log(7200))))
            seq.append((W, d))
            L += d
            if d >= LONG_S and mode == "restart":
                dk = is_dark(start + pd.Timedelta(seconds=L))
                counter, rq = 0.0, req(dk) * ((d / LONG_S) ** night_grade if dk else 1.0)
            force_n, last = True, W
            continue
        if not force_n and last == N and u < p_long + 0.08:
            d = int(rng.integers(5, 36))
            seq.append((W, d))
            L += d
            force_n, last = True, W
            continue
        c = int(rng.integers(30, 240))
        if counter + c >= rq:
            nn = max(int(rq - counter), 1)
            r = int(rng.integers(40, 120))
            seq += [(N, nn), (R, r)]
            L += nn + r
            counter, rq, last = 0.0, req(is_dark(start + pd.Timedelta(seconds=L))), R
        else:
            seq.append((N, c))
            L += c
            counter += c
            last = N
        force_n = False
    return np.concatenate([np.full(d, s, np.int8) for s, d in seq])[:n_s]


def _block(start: pd.Timestamp) -> str:
    h = start.hour
    d = start.normalize() - (pd.Timedelta(days=1) if h < 6 else pd.Timedelta(0))
    return f"{d:%Y-%m-%d}{'D' if 6 <= h < 18 else 'N'}"


def synth_records(rng, animals, days, mode="restart", night_grade=0.0, dark_gain=1.0, rec_h=10.0,
                  starts=("08:00", "19:30"), p_long: float = 0.07, req_sd: float = 0.35) -> list[dict]:
    is_dark = _dark_fn()
    recs = []
    for an in animals:
        for d in days:
            for hh in starts:
                t0 = pd.Timestamp(f"{d} {hh}")
                st = synth_state(rng, t0, int(rec_h * 3600), mode, night_grade, dark_gain, p_long=p_long, is_dark=is_dark, req_sd=req_sd)
                recs.append({"animal": an, "start": t0, "end": t0 + pd.Timedelta(seconds=len(st)), "state": st,
                             "sessions": [f"{len(recs)}_{t0:%Y%m%d_%H%M%S}.000"], "block": _block(t0)})
    for i, rc in enumerate(recs):
        rc["record_id"] = i
    return recs


def synth_gaps(recs: list[dict]) -> pd.DataFrame:
    rows = []
    for an in sorted({rc["animal"] for rc in recs}):
        rr = sorted([rc for rc in recs if rc["animal"] == an], key=lambda x: x["start"])
        for p, n in zip(rr[:-1], rr[1:]):
            gs, ge = p["end"], n["start"]
            h = gs.hour + gs.minute / 60
            kind = "morning" if 5 <= h < 11 else ("evening" if 15.5 <= h < 21.5 else "other")
            rows.append({"animal": an, "gap_start": gs, "gap_end": ge, "gap_min": (ge - gs).total_seconds() / 60, "kind": kind,
                         "pre_h": len(p["state"]) / 3600, "post_h": len(n["state"]) / 3600,
                         "usable": bool((ge - gs).total_seconds() <= 10800), "cause": "round_logged"})
    return pd.DataFrame(rows)


def synth_library(rng, recs: list[dict], n_per_rec: int = 60, early_frac: float = 0.3):
    """Synthetic Phase-6 tables: first movers (a share placed 3-12 s before a wake onset that follows sleep) and random
    asleep controls; outcomes from sleep_events.outcome."""
    from sleep_events import outcome
    P, C = [], []
    for rc in recs:
        s = rc["state"]
        n = len(s)
        asleep = np.flatnonzero(np.isin(s, (N, R)))
        asleep = asleep[(asleep >= 60) & (asleep < n - 601)]
        if not len(asleep):
            continue
        won = np.flatnonzero((s[1:] == W) & np.isin(s[:-1], (N, R))) + 1
        for k in range(n_per_rec):
            if len(won) and rng.random() < early_frac:
                sec = int(rng.choice(won)) - int(rng.integers(3, 13))
                if sec < 60 or sec >= n - 601 or s[sec] not in (N, R):
                    continue
            else:
                sec = int(rng.choice(asleep))
            o = outcome(s, sec)
            P.append({"event_id": f"M_{rc['record_id']}_{k}", "source": "movement", "animal": rc["animal"], "role": "first",
                      "role_detail": "first", "imu_ok": True, "state_ok": True, "session": rc["sessions"][0],
                      "amp_sample": sec * AMP_FS, **o})
        for k, sec in enumerate(rng.choice(asleep, size=min(200, len(asleep)), replace=False)):
            o = outcome(s, int(sec))
            C.append({"event_id": f"C_{rc['record_id']}_{k}", "source": "control", "animal": rc["animal"], "role": "control",
                      "state_ok": True, **o})
    return pd.DataFrame(P), pd.DataFrame(C)


def synth_ctx(rng) -> dict:
    animals = ["SF07", "SF08", "SF09", "SF10", "SF11", "SF12"]
    days = [f"2026-09-{d:02d}" for d in range(1, 7)]
    recs = synth_records(rng, animals, days, night_grade=0.3, dark_gain=2.0)
    recs2 = []
    for rc in recs:                                     # the "fixed-threshold" copy: shorten every REM bout by 3 s
        s = rc["state"].copy()
        for st_, a, b in bouts(s):
            if st_ == R and b - a > 10:
                s[b - 3:b] = N
        recs2.append({**rc, "state": s})
    P, CP = synth_library(rng, recs)
    pilot = []
    for rc in recs[:2]:
        fin = rc["state"]
        ung = fin.copy()
        for r in P[P.session == rc["sessions"][0]].itertuples():   # the ungated copy: early post-mover wakes become NREM
            sec = int(r.amp_sample // AMP_FS)
            w = np.flatnonzero(ung[sec + 1:sec + EXCL_S] == W)
            if len(w):
                a = sec + 1 + w[0]
                b = a
                while b < len(ung) and ung[b] == W and b - a < 60:
                    b += 1
                ung[a:b] = N
        pilot.append({"animal": rc["animal"], "session": rc["sessions"][0],
                      "arrays": {"ungated (imu)": ung, "gated, same pilot run (imu_remclean)": fin.copy(), "FINAL": fin}})
    return {"recs": {"FINAL": recs, "pass2med": recs2}, "gaps": synth_gaps(recs), "P": P, "CP": CP, "pilot": pilot}


# ================================================================== the parts (each returns report lines + verdict row)
def tbl(df: pd.DataFrame, nd: int = 3) -> list[str]:
    from sleep_quant import md_table
    if df is None or not len(df):
        return ["(no rows)"]
    d = df.copy()
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].round(nd)
    return md_table(d)


def part_a1(ctx: dict, out: Path, rd: Path, n_rep: int) -> tuple[list[str], dict, dict]:
    L, tabs, key = [], {}, {}
    cox_rows, ols_rows, pa_rows, bench_rows, ho_rows, repro = [], [], [], [], [], []
    rng = np.random.default_rng(61)
    for lab, recs in ctx["recs"].items():
        tab = post_wake_table(recs)
        tab.to_csv(out / f"a1_post_wake_{lab}.csv.gz", index=False)
        ctx.setdefault("a1_tables", {})[lab] = tab
        for sub_lab, sub in (("all", tab), ("wake ends >= 3 h after the record start", tab[tab.off_rec_s >= POST_S])):
            cx = cox(sub, COX_A1)
            for t in COX_A1:
                cox_rows.append({"scores": lab, "subset": sub_lab, "term": t, **cterm(cx, t),
                                 "n": int(cx.n.iloc[0]) if cx is not None else len(sub),
                                 "events": int(cx.events.iloc[0]) if cx is not None else int(sub.event.sum()),
                                 "clusters": int(cx.clusters.iloc[0]) if cx is not None else 0})
            if sub_lab == "all":                     # the logic audit's spec (no dark term), for the reproduction
                cx0 = cox(sub, [c for c in COX_A1 if c != "darkf"])
                for t in ("l_d", "l_npre", "anchor"):
                    cox_rows.append({"scores": lab, "subset": "all (logic-audit spec: no dark term)", "term": t, **cterm(cx0, t),
                                     "n": len(sub), "events": int(sub.event.sum()),
                                     "clusters": int(cx0.clusters.iloc[0]) if cx0 is not None else 0})
            o_np, o_d, pa = a1_ols(sub)
            ev = sub[(sub.event == 1) & (sub.T_s > 0)]
            ols_rows += [{"scores": lab, "subset": sub_lab, "term": "l_npre", "n_events": len(ev), **o_np},
                         {"scores": lab, "subset": sub_lab, "term": "l_d", "n_events": len(ev), **o_d}]
            evd = ev.copy()
            fd_ = ols(evd.l_T, evd[OLS_A1 + ["darkf"]], groups=evd.block, fe=evd.animal)
            ols_rows.append({"scores": lab, "subset": sub_lab + " (+ dark)", "term": "l_npre", "n_events": len(ev), **term(fd_, "l_npre")})
            pc = a1_cox_per_animal(sub)
            pam = pa.merge(pc, on="animal", how="outer") if len(pa) and len(pc) else (pa if len(pa) else pc)
            if len(pam):
                pam.insert(0, "subset", sub_lab)
                pam.insert(0, "scores", lab)
                pa_rows.append(pam)
            if sub_lab == "all":
                key[lab] = {"ols_npre": o_np, "ols_d": o_d, "cox_npre": cterm(cx, "l_npre"), "cox_d": cterm(cx, "l_d"), "pa": pam,
                            "n": len(sub), "events": int(sub.event.sum()), "anchor_share": float(sub.anchor.mean()),
                            "why": sub.why.value_counts().to_dict(), "left_cens": int(sub.left_cens.sum()),
                            "left_cens_after3h": int(sub[sub.off_rec_s >= POST_S].left_cens.sum())}
        bm = resume_benchmark(tab, rng, n_rep)
        bm.insert(0, "scores", lab)
        bench_rows.append(bm)
        # reproduction of the Phase-2 B1b table (k = 1)
        if not ctx.get("smoke"):
            b1 = b1b_fit(wake_to_kth_rem(recs))
            b1 = b1[b1.k_th_REM_after_wake == 1]
            for r in b1.itertuples():
                repro.append({"scores": lab, "term": r.term, "phase2_b1b_n": r.n, "phase2_b1b_coef": r.coef,
                              "this_n": int(((tab.event == 1) & (tab.T_s > 0)).sum()),
                              "this_coef": key[lab]["ols_npre"]["coef"] if r.term == "l_npre" else key[lab]["ols_d"]["coef"]})
        # held-out
        S, agree = stretch_steps(recs, tab)
        S.to_csv(out / f"a1_stretch_steps_{lab}.csv.gz", index=False) if len(S) else None
        r1 = heldout_counters(S, "anchored post-long-wake stretches")
        r1["n_since_equals_resume_share"] = agree
        keep = tab.index[tab.off_rec_s >= POST_S]
        r2 = heldout_counters(S[S.row.isin(keep)] if len(S) else S, "wake ends >= 3 h after the record start")
        for r_ in (r1, r2):
            r_["scores"] = lab
            ho_rows.append(r_)
        key[lab]["heldout"] = r1
        print(f"A1 {lab}: episodes {len(tab)}, events {int(tab.event.sum())}; OLS l_npre {fmt_ci(key[lab]['ols_npre'])}; "
              f"Cox l_npre {fmt_ci(key[lab]['cox_npre'])}; held-out {r1.get('delta_pct', np.nan):.3f} %", flush=True)
    CX, OL = pd.DataFrame(cox_rows), pd.DataFrame(ols_rows)
    PA = pd.concat(pa_rows, ignore_index=True) if pa_rows else pd.DataFrame()
    BM = pd.concat(bench_rows, ignore_index=True)
    BMs = BM.groupby(["scores", "world"]).agg(ols_median=("ols_l_npre", "median"), ols_lo=("ols_l_npre", lambda x: x.quantile(0.025)),
                                             ols_hi=("ols_l_npre", lambda x: x.quantile(0.975)),
                                             cox_median=("cox_l_npre", "median"), cox_lo=("cox_l_npre", lambda x: x.quantile(0.025)),
                                             cox_hi=("cox_l_npre", lambda x: x.quantile(0.975)), reps=("rep", "size")).reset_index()
    HO = pd.DataFrame(ho_rows)
    RP = pd.DataFrame(repro)
    for nm, df in (("a1_cox", CX), ("a1_ols", OL), ("a1_per_animal", PA), ("a1_benchmark", BMs), ("a1_heldout", HO), ("a1_repro_b1b", RP)):
        df.to_csv(rd / f"ephys_spikes_sleep_explore_A_{nm}_2026c.csv", index=False)
    BM.to_csv(out / "a1_benchmark_reps.csv.gz", index=False)

    # verdict: the plan's literal rule decides; the Cox and held-out checks can only flag a contradiction
    lines_v, ok_all, contra = [], [], []
    for lab in ctx["recs"]:
        o = key[lab]["ols_npre"]
        pa = key[lab]["pa"]
        n_an = int(pa.ols_l_npre.notna().sum()) if len(pa) and "ols_l_npre" in pa else 0
        n_ok = int((pa.ols_l_npre > -0.15).sum()) if n_an else 0
        near0 = (o["ci_lo"] <= 0 <= o["ci_hi"]) or abs(o["coef"]) < 0.05
        lit = bool(o["ci_lo"] > -0.15 and near0)
        rats = n_ok >= 5
        bres = BMs[(BMs.scores == lab) & (BMs.world == "resume")]
        cb = float(bres.cox_median.iloc[0]) if len(bres) else np.nan
        ob = float(bres.ols_median.iloc[0]) if len(bres) else np.nan
        ols_half = bool(np.isfinite(ob) and o["ci_lo"] > 0.5 * ob)
        c = key[lab]["cox_npre"]
        cox_contra = bool(c["ci_lo"] > 0)                    # a significant resumption-direction effect (Cox: + = REM sooner)
        cox_full = bool(np.isfinite(cb) and c["ci_hi"] < cb)  # the CI excludes the full simulated resumption value
        cox_half = bool(np.isfinite(cb) and c["ci_hi"] < 0.5 * cb)
        ho = key[lab]["heldout"]
        ho_contra = bool(ho.get("ci_lo_pct", -1) > 0)         # RESTART significantly worse than RESUME
        ok_all.append(lit and rats)
        contra.append(cox_contra or ho_contra)
        key[lab].update(lit=lit, rats=f"{n_ok}/{n_an}", cox_bench=cb)
        lines_v.append(f"- **{lab}:** OLS ln(1+N_pre) {fmt_ci(o)} → literal rule {'met' if lit else 'NOT met'}; animals with a "
                       f"per-animal coefficient > −0.15: {n_ok}/{n_an} → {'met' if rats else 'NOT met'}. The simulated full-resumption "
                       f"value on the OLS scale is {ob:+.3f} (the plan assumed ≈ −0.3); the OLS CI lower bound "
                       f"{'lies above' if ols_half else 'does not lie above'} half of it ({0.5 * ob:+.3f}). Supporting: Cox ln(1+N_pre) "
                       f"{fmt_ci(c)} vs the simulated full-resumption value {cb:+.3f} — the CI "
                       f"{'excludes it' + (' and half of it' if cox_half else ' (not half of it)') if cox_full else 'does not exclude it (the Cox has little power here)'}"
                       f"{'; a significant resumption-direction effect (contradiction)' if cox_contra else ''}. Held out, RESTART vs "
                       f"RESUME Δ = {ho.get('delta_pct', np.nan):+.3f} % [{ho.get('ci_lo_pct', np.nan):+.3f}, {ho.get('ci_hi_pct', np.nan):+.3f}], "
                       f"animals better {ho.get('animals_better', 'n/a')}/{ho.get('animals', 'n/a')}"
                       f"{' (RESTART significantly worse: contradiction)' if ho_contra else ''}.")
    verdict = "PASS" if all(ok_all) and not any(contra) else ("FAIL" if not any(ok_all) else "PARTIAL")

    L += ["## A1 — #6a: a wake ≥ 7 min is not resumed", "",
          "**Plan pass rule (A1, quoted):** \"N_pre ≈ 0 with CI excluding −0.15 (resumption predicts ≈ −0.3), ≥ 5/6 rats → "
          "#6a Established (scoped).\" Operationalised: the OLS coefficient of ln(1+N_pre) (events, SEs by block) has its 95 % "
          "CI above −0.15 and includes 0 (or |coef| < 0.05); ≥ 5 animals have a per-animal OLS coefficient > −0.15; on both "
          "scorings. Supporting (not in the rule; they can only flag a contradiction): the Cox coefficient against the simulated "
          "full-resumption value, and the held-out RESTART vs RESUME comparison (a contradiction = a significant resumption-direction "
          "Cox effect, or RESTART significantly worse held out). PASS = the rule on both scorings and no contradiction.", "",
          f"Data: post-long-wake sleeps per scoring — " + "; ".join(
              f"{lab} {key[lab]['n']} (reached REM {key[lab]['events']}, anchored {100 * key[lab]['anchor_share']:.0f} %, "
              f"ends: {', '.join(f'{k} {v}' for k, v in key[lab]['why'].items())}; long wakes starting at the record start or after "
              f"an unknown epoch: {key[lab]['left_cens']}, of which {key[lab]['left_cens_after3h']} remain in the ≥ 3-h subset)"
              for lab in ctx["recs"]), "",
          "### (i) Cox model (time = NREM + MA seconds after the wake; animal strata; SEs clustered by block)", "",
          *tbl(CX[CX.term.isin(["l_d", "l_npre", "anchor", "darkf"])][["scores", "subset", "term", "coef", "ci_lo", "ci_hi", "p", "HR",
                                                                       "n", "events", "clusters"]]), "",
          "### (ii) The plan's literal rule on the OLS scale (events only; B1b covariates; animal FE; SEs by block)", "",
          *tbl(OL[["scores", "subset", "term", "n_events", "coef", "ci_lo", "ci_hi", "p"]]), "",
          "Per-animal coefficients (OLS on events with ≥ 15 events; Cox without strata with ≥ 15 sleeps and ≥ 5 events; "
          "per-animal Cox covariates: ln d, ln(1+N_pre), anchor, dark, sin1, cos1):", "",
          *tbl(PA), "",
          "Simulated benchmark (same sleeps, same censoring times, event times redrawn from the observed post-wake "
          "distribution; 'resume' = the post-wake requirement is the residual of a total drawn > N_pre; 'restart' = independent "
          "of N_pre):", "", *tbl(BMs), ""]
    if len(RP):
        L += ["Reproduction of the Phase-2 B1b table (k = 1; `wake_to_kth_rem` + `b1b_fit` on the same records):", "", *tbl(RP), ""]
    L += ["### (iii) Forward-chained held-out comparison of the two counters (same hazard spec)", "",
          "Δ = held-out log-loss change of RESTART relative to RESUME (negative = RESTART better); forward chaining over the "
          "day-half blocks (first test block = block 7).", "",
          *tbl(HO[[c for c in ("scores", "subset", "stretches", "n_steps", "n_rem", "delta_pct", "ci_lo_pct", "ci_hi_pct",
                               "folds_better", "folds", "animals_better", "animals", "holds", "n_since_equals_resume_share") if c in HO]]), "",
          "### Verdict A1", "", *lines_v, "", f"**A1 verdict: {verdict}.**", ""]
    vrow = {"part": "A1", "claim": "#6a a wake ≥ 7 min is not resumed", "verdict": verdict,
            "key": " | ".join(f"{lab}: OLS N_pre {fmt_ci(key[lab]['ols_npre'], 3)}, rats {key[lab]['rats']}, Cox N_pre "
                              f"{fmt_ci(key[lab]['cox_npre'], 3)}, held-out Δ {key[lab]['heldout'].get('delta_pct', np.nan):+.2f} %"
                              for lab in ctx["recs"])}
    return L, vrow, key


def part_a2(ctx: dict, out: Path, rd: Path, fd: Path) -> tuple[list[str], dict]:
    rows, bins_rows, cnt_rows, inter_rows = [], [], [], []
    for lab, recs in ctx["recs"].items():
        tab = ctx.get("a1_tables", {}).get(lab)
        if tab is None:
            tab = post_wake_table(recs)
        for ph, dk in (("dark", True), ("light", False)):
            lo, hi = A2_RANGE[ph]
            for rlab, sub in ((f"plan range {lo // 60}-{hi // 60} min", tab[(tab.dark == dk) & (tab.d_s >= lo) & (tab.d_s < hi)]),
                              ("all wake lengths", tab[tab.dark == dk])):
                ev = sub[(sub.event == 1) & (sub.T_s > 0)]
                f = ols(ev.l_T, ev[OLS_A1], groups=ev.block, fe=ev.animal) if len(ev) >= 15 else None
                sg = []
                for _, g in ev.groupby("animal"):
                    if len(g) >= 10 and g.l_d.std() > 0:
                        sg.append(np.sign(term(ols(g.l_T, g[OLS_A1]), "l_d")["coef"]))
                cx = cox(sub, [c for c in COX_A1 if c != "darkf"])
                o, c = term(f, "l_d"), cterm(cx, "l_d")
                rows.append({"scores": lab, "phase": ph, "wakes": rlab, "sleeps": len(sub), "events": len(ev),
                             "median_d_min": float(sub.d_s.median() / 60) if len(sub) else np.nan,
                             "ols_ln_d": o["coef"], "ols_ci_lo": o["ci_lo"], "ols_ci_hi": o["ci_hi"], "ols_p": o["p"],
                             "animals_positive": int(np.sum(np.array(sg) > 0)), "animals": len(sg),
                             "cox_ln_d": c["coef"], "cox_ci_lo": c["ci_lo"], "cox_ci_hi": c["ci_hi"], "cox_p": c["p"]})
        ev = tab[(tab.event == 1) & (tab.T_s > 0)].copy()
        ev["ld_x_dark"] = ev.l_d * ev.darkf
        f = ols(ev.l_T, ev[OLS_A1 + ["darkf", "ld_x_dark"]], groups=ev.block, fe=ev.animal)
        inter_rows += [{"scores": lab, "term": t, **term(f, t)} for t in ("l_d", "ld_x_dark", "darkf")]
        # categorical bins
        for ph, dk in (("dark", True), ("light", False)):
            sub = tab[tab.dark == dk].copy()
            present = [b for b in A2_LABELS[1:] if ((sub.d_bin == b) & (sub.event == 1)).sum() >= 3]
            for b in present:
                sub[f"bin_{b}"] = (sub.d_bin == b).astype(float)
            bcols = [f"bin_{b}" for b in present]
            evs = sub[(sub.event == 1) & (sub.T_s > 0)]
            f = ols(evs.l_T, evs[bcols + ["l_npre", "anchor", "sin1", "cos1", "sin2", "cos2"]], groups=evs.block, fe=evs.animal) \
                if bcols and len(evs) >= 15 else None
            cx = cox(sub, bcols + ["l_npre", "anchor", "sin1", "cos1", "sin2", "cos2"]) if bcols else None
            for b in present:
                o, c = term(f, f"bin_{b}"), cterm(cx, f"bin_{b}")
                bins_rows.append({"scores": lab, "phase": ph, "bin_min": b, "vs": "7-15", "ols_coef": o["coef"], "ols_ci_lo": o["ci_lo"],
                                  "ols_ci_hi": o["ci_hi"], "cox_coef": c["coef"], "cox_ci_lo": c["ci_lo"], "cox_ci_hi": c["ci_hi"]})
            for b in A2_LABELS:
                g = sub[sub.d_bin == b]
                if len(g):
                    cnt_rows.append({"scores": lab, "phase": ph, "bin_min": b, "sleeps": len(g), "reached_rem": int(g.event.sum()),
                                     "share_rem": float(g.event.mean()), "animals": g.animal.nunique(),
                                     "median_T_min_events": float(g[g.event == 1].T_s.median() / 60) if g.event.sum() else np.nan,
                                     "km_median_T_min": km_median(g.T_s, g.event) / 60})
    A2, BN, CN, IN = pd.DataFrame(rows), pd.DataFrame(bins_rows), pd.DataFrame(cnt_rows), pd.DataFrame(inter_rows)
    for nm, df in (("a2_slopes", A2), ("a2_bins", BN), ("a2_counts", CN), ("a2_interaction", IN)):
        df.to_csv(rd / f"ephys_spikes_sleep_explore_A_{nm}_2026c.csv", index=False)
    # figure: categorical bins
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sleep_quant import save_fig
    labs = list(ctx["recs"])
    fig, axs = plt.subplots(1, len(labs), figsize=(5.5 * len(labs), 4), sharey=True)
    axs = np.atleast_1d(axs)
    for ax, lab in zip(axs, labs):
        for ph, off in (("dark", -0.1), ("light", 0.1)):
            g = BN[(BN.scores == lab) & (BN.phase == ph)]
            x = [A2_LABELS.index(b) + off for b in g.bin_min]
            ax.errorbar(x, g.ols_coef, yerr=[g.ols_coef - g.ols_ci_lo, g.ols_ci_hi - g.ols_coef], fmt="o", ms=6, lw=2, capsize=0,
                        color=COLORS[ph], label=ph)
        ax.axhline(0, color=COLORS["ink"], lw=0.8)
        ax.set_xticks(range(len(A2_LABELS)), A2_LABELS)
        ax.set_xlabel("wake length (min); reference 7-15 min")
        ax.set_title(lab, fontsize=9, color=COLORS["ink"])
        ax.spines[["top", "right"]].set_visible(False)
    axs[0].set_ylabel("Δ ln(NREM + MA before the first REM) vs 7-15 min")
    axs[0].legend(fontsize=8, frameon=False)
    fig.tight_layout()
    save_fig(fig, fd / "ephys_spikes_sleep_explore_A_a2_bins_2026c.png")
    plt.close(fig)
    # verdict
    vl, oks, rescope, caveats = [], [], [], []
    for lab in labs:
        d = A2[(A2.scores == lab) & (A2.phase == "dark") & A2.wakes.str.startswith("plan")].iloc[0]
        lt = A2[(A2.scores == lab) & (A2.phase == "light") & A2.wakes.str.startswith("plan")].iloc[0]
        dark_ok = d.ols_ci_lo > 0
        light_null = lt.ols_ci_lo <= 0 <= lt.ols_ci_hi
        oks.append(bool(dark_ok and light_null))
        rescope.append(bool(lt.ols_ci_lo > 0 or lt.ols_ci_hi < 0))
        cav = []
        if not d.cox_ci_hi < 0:
            cav.append(f"the censored Cox does not confirm the dark slope ({d.cox_ln_d:+.3f} [{d.cox_ci_lo:+.3f}, {d.cox_ci_hi:+.3f}])")
        if d.animals_positive < 5:
            cav.append(f"only {d.animals_positive}/{d.animals} rats have a positive dark slope")
        caveats.append(f"{lab}: " + "; ".join(cav) if cav else "")
        vl.append(f"- **{lab}:** dark (7 min–4 h) ln d slope {d.ols_ln_d:+.3f} [{d.ols_ci_lo:+.3f}, {d.ols_ci_hi:+.3f}] "
                  f"(n {d.events} events, {d.animals_positive}/{d.animals} rats positive; Cox {d.cox_ln_d:+.3f} "
                  f"[{d.cox_ci_lo:+.3f}, {d.cox_ci_hi:+.3f}]); light (7–30 min) {lt.ols_ln_d:+.3f} [{lt.ols_ci_lo:+.3f}, "
                  f"{lt.ols_ci_hi:+.3f}] (n {lt.events}, {lt.animals_positive}/{lt.animals} positive; Cox {lt.cox_ln_d:+.3f} "
                  f"[{lt.cox_ci_lo:+.3f}, {lt.cox_ci_hi:+.3f}]) → {'rule met' if oks[-1] else 'rule NOT met'}"
                  + (" (a light dose effect: CI excludes 0)" if rescope[-1] else "") + "."
                  + (f" Caveat (not in the rule): {caveats[-1].split(': ', 1)[1]}." if caveats[-1] else ""))
    verdict = "PASS" if all(oks) else ("FAIL" if any(rescope) or not any(oks) else "PARTIAL")
    L = ["## A2 — #6b: graded with wake length only at night", "",
         "**Plan pass rule (A2, quoted):** \"Dark slope > 0 with CI > 0 and light CI including 0 → #6b stays 'night only'. Any "
         "light dose effect → #6b re-scoped.\" Slope = OLS coefficient of ln d on ln(NREM + MA before the first REM) (events), "
         "in the plan's ranges (dark 7 min–4 h, light 7–30 min), phase at the wake end; both scorings. The Cox coefficient has "
         "the opposite sign convention (negative = REM later).", "",
         "### ln d slopes by phase", "", *tbl(A2), "",
         "Pooled interaction model (events, all wake lengths): `l_d` = the light slope, `ld_x_dark` = dark minus light:", "",
         *tbl(IN), "",
         "### Categorical wake-length bins (reference 7–15 min; with N_pre, anchor, 2-harmonic hour, animal)", "", *tbl(BN), "",
         "![](../figures/ephys_spikes_sleep_explore_A_a2_bins_2026c.png)", "",
         "Counts per bin and phase:", "", *tbl(CN), "", "### Verdict A2", "", *vl, "",
         f"**A2 verdict: {verdict}** ({'#6b stays night only, by the letter of the rule' if verdict == 'PASS' else 'see the lines above'})"
         + (f"; caveat — {' | '.join(c for c in caveats if c)}" if any(caveats) else "") + ".", ""]
    vrow = {"part": "A2", "claim": "#6b graded only at night", "verdict": verdict,
            "key": " | ".join(
                f"{lab}: dark {r.ols_ln_d:+.2f} [{r.ols_ci_lo:+.2f}, {r.ols_ci_hi:+.2f}], light {q.ols_ln_d:+.2f} [{q.ols_ci_lo:+.2f}, {q.ols_ci_hi:+.2f}]"
                for lab in labs
                for r in [A2[(A2.scores == lab) & (A2.phase == "dark") & A2.wakes.str.startswith("plan")].iloc[0]]
                for q in [A2[(A2.scores == lab) & (A2.phase == "light") & A2.wakes.str.startswith("plan")].iloc[0]])
            + (f" | caveat: {' | '.join(c for c in caveats if c)}" if any(caveats) else "")}
    return L, vrow


def part_a3(ctx: dict, out: Path, rd: Path, fd: Path) -> tuple[list[str], dict]:
    gaps = ctx["gaps"]
    rows, pa_rows, sens = [], [], []
    for lab, recs in ctx["recs"].items():
        E = sleep_episode_table(recs)
        E["post_round"] = after_gap_mask(E, "t0", gaps, ROUND_CAUSES)
        E["post_probe"] = after_gap_mask(E, "t0", gaps, ("probe_move",))
        E.to_csv(out / f"a3_episodes_{lab}.csv.gz", index=False)
        for blab, lo, hi in PW_BINS:
            inb = (E.pre_wake_s >= lo) & (E.pre_wake_s < hi)
            for slab, m in (("primary: post-round 3 h excluded", inb & ~E.post_round),
                            ("sensitivity: + post-probe-move 3 h excluded", inb & ~E.post_round & ~E.post_probe),
                            ("sensitivity: no post-handling exclusion", inb)):
                r, PA = a3_bin(E[m])
                r = {"scores": lab, "prior_wake": blab, "subset": slab, **r}
                (rows if slab.startswith("primary") else sens).append(r)
                if slab.startswith("primary"):
                    PA.insert(0, "prior_wake", blab)
                    PA.insert(0, "scores", lab)
                    pa_rows.append(PA)
        print(f"A3 {lab}: episodes {len(E)}, with a prior wake in the bins {int(E.pre_wake_s.between(120, 1799).sum())}", flush=True)
    A3, A3s = pd.DataFrame(rows), pd.DataFrame(sens)
    PA = pd.concat(pa_rows, ignore_index=True)
    for nm, df in (("a3_main", A3), ("a3_sensitivity", A3s), ("a3_per_animal", PA)):
        df.to_csv(rd / f"ephys_spikes_sleep_explore_A_{nm}_2026c.csv", index=False)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sleep_quant import save_fig
    labs = list(ctx["recs"])
    fig, axs = plt.subplots(len(labs), len(PW_BINS), figsize=(4.2 * len(PW_BINS), 3.4 * len(labs)), sharey=True, squeeze=False)
    for i, lab in enumerate(labs):
        for j, (blab, _, _) in enumerate(PW_BINS):
            ax = axs[i, j]
            g = PA[(PA.scores == lab) & (PA.prior_wake == blab)].dropna(subset=["ratio"]) if "ratio" in PA else PA.iloc[:0]
            for r in g.itertuples():
                ax.plot([0, 1], [r.rate_light, r.rate_dark], "-o", color=COLORS["ink"], lw=1, ms=4, alpha=0.7)
                ax.text(1.04, r.rate_dark, r.animal, fontsize=7, va="center", color=COLORS["ink"])
            m = A3[(A3.scores == lab) & (A3.prior_wake == blab)]
            if len(m):
                ax.plot([0, 1], [m.rate_light.iloc[0], m.rate_dark.iloc[0]], "-s", color=COLORS["dark"], lw=2.5, ms=7, label="pooled")
            ax.set_xticks([0, 1], ["light", "dark"])
            ax.set_xlim(-0.2, 1.3)
            ax.set_title(f"{lab}, prior wake {blab}", fontsize=9, color=COLORS["ink"])
            ax.spines[["top", "right"]].set_visible(False)
        axs[i, 0].set_ylabel("REM bouts per NREM hour")
    axs[0, 0].legend(fontsize=8, frameon=False)
    fig.tight_layout()
    save_fig(fig, fd / "ephys_spikes_sleep_explore_A_a3_matched_2026c.png")
    plt.close(fig)
    vl, ok, size_ok = [], [], []
    for lab in labs:
        for blab, _, _ in PW_BINS:
            r = A3[(A3.scores == lab) & (A3.prior_wake == blab)].iloc[0]
            s_ok = bool(r.ratio_pooled <= 0.6)
            k = int(r.animals_qualifying)
            rats_ok = bool(k >= 5 and r.animals_ratio_lt1 >= 5)
            ok.append(s_ok and rats_ok)
            size_ok.append(s_ok)
            vl.append(f"- **{lab}, prior wake {blab}:** dark {r.rate_dark:.2f} vs light {r.rate_light:.2f} REM bouts per NREM h "
                      f"(n {r.n_dark} / {r.n_light}) → pooled ratio {r.ratio_pooled:.2f} (per-episode mean ratio "
                      f"{r.ratio_mean_ep:.2f}; GLM rate ratio {r.glm_rr:.2f} [{r.glm_rr_lo:.2f}, {r.glm_rr_hi:.2f}]); "
                      f"per-animal ratio < 1 in {r.animals_ratio_lt1}/{k} qualifying animals (≤ 0.6 in {r.animals_ratio_le06}/{k}); "
                      f"first-REM latency Cox HR dark {r.cox_HR_dark:.2f} [{r.cox_HR_lo:.2f}, {r.cox_HR_hi:.2f}], KM median "
                      f"{r.km_median_lat_min_dark:.1f} vs {r.km_median_lat_min_light:.1f} min → size {'met' if s_ok else 'NOT met'}, "
                      f"rats {'met' if rats_ok else ('NOT met' if k >= 5 else f'cannot be met ({k} animals qualify)')}.")
    verdict = "PASS" if all(ok) else ("PARTIAL" if any(size_ok) else "FAIL")
    L = ["## A3 — #14b: the night's REM-entry rate at matched prior wake", "",
         "**Plan pass rule (A3, quoted):** \"Night ratio ≤ 0.6 in both bins, ≥ 5/6 rats, both scorings → #14b Established.\" "
         "Operationalised: the pooled ratio (sum of REM bouts / sum of NREM hours, dark over light) ≤ 0.6 in the 2–7-min and the "
         "7–30-min bins, and ≥ 5 animals with a per-animal ratio < 1 among animals with ≥ 3 episodes in each phase (≥ 5 such "
         "animals needed), on both scorings. Per-animal ratios ≤ 0.6 are counted too (the strict reading).", "",
         "### Main table (post-round 3 h excluded)", "", *tbl(A3), "",
         "![](../figures/ephys_spikes_sleep_explore_A_a3_matched_2026c.png)", "",
         "### Per animal", "", *tbl(PA), "", "### Sensitivity", "",
         *tbl(A3s[["scores", "prior_wake", "subset", "n_dark", "n_light", "rate_dark", "rate_light", "ratio_pooled", "ratio_mean_ep",
                   "glm_rr", "cox_HR_dark", "animals_qualifying", "animals_ratio_lt1"]]), "",
         "### Verdict A3", "", *vl, "", f"**A3 verdict: {verdict}.**", ""]
    vrow = {"part": "A3", "claim": "#14b night REM-entry ratio at matched prior wake", "verdict": verdict,
            "key": " | ".join(f"{lab}: ratio 2-7 {A3[(A3.scores == lab) & (A3.prior_wake == '2-7 min')].ratio_pooled.iloc[0]:.2f} "
                              f"({A3[(A3.scores == lab) & (A3.prior_wake == '2-7 min')].animals_ratio_lt1.iloc[0]}/"
                              f"{A3[(A3.scores == lab) & (A3.prior_wake == '2-7 min')].animals_qualifying.iloc[0]} rats), 7-30 "
                              f"{A3[(A3.scores == lab) & (A3.prior_wake == '7-30 min')].ratio_pooled.iloc[0]:.2f} "
                              f"({A3[(A3.scores == lab) & (A3.prior_wake == '7-30 min')].animals_ratio_lt1.iloc[0]}/"
                              f"{A3[(A3.scores == lab) & (A3.prior_wake == '7-30 min')].animals_qualifying.iloc[0]})" for lab in labs)}
    return L, vrow


def part_a4(ctx: dict, out: Path, rd: Path) -> tuple[list[str], dict]:
    allr, counts = [], []
    for lab, recs in ctx["recs"].items():
        Ws = a4_windows(recs, ctx["gaps"])
        for bname, Wn in Ws.items():
            Wn.to_csv(out / f"a4_windows_{lab}_{'phasexday' if bname.startswith('phase') else 'commonday'}.csv.gz", index=False)
            T = pay_models(Wn)
            T.insert(0, "baseline", bname)
            T.insert(0, "scores", lab)
            allr.append(T)
            c = Wn.groupby(["kind", "B_h"]).size().rename("windows").reset_index()
            c.insert(0, "baseline", bname)
            c.insert(0, "scores", lab)
            counts.append(c)
        print(f"A4 {lab}: windows {len(Ws['phase x day (plan)'])}", flush=True)
    A4, CNT = pd.concat(allr, ignore_index=True), pd.concat(counts, ignore_index=True)
    A4.to_csv(rd / "ephys_spikes_sleep_explore_A_a4_payback_2026c.csv", index=False)
    prim = A4[A4.baseline.str.startswith("phase")]
    key_sel = prim[(prim.kind == "morning") & (prim.outcome == "pay_rem")]
    vl, res = [], {}
    for lab in ctx["recs"]:
        ok = []
        for bh in (1, 3):
            r = key_sel[(key_sel.scores == lab) & (key_sel.B_h == bh) & (key_sel.predictors == "debt_rem") & key_sel.day_demeaned]
            r2 = key_sel[(key_sel.scores == lab) & (key_sel.B_h == bh) & (key_sel.predictors == "debt_rem + debt_nrem") & key_sel.day_demeaned]
            if not len(r):
                ok.append(False)
                continue
            r, r2 = r.iloc[0], (r2.iloc[0] if len(r2) else None)
            ok.append(bool(r.slope > 0.2 and r.p < 0.05))
            vl.append(f"- **{lab}, morning, B = {bh} h:** day-demeaned REM-debt slope {r.slope:+.3f} [{r.ci_lo:+.3f}, {r.ci_hi:+.3f}], "
                      f"p {r.p:.4f}, n {r.n_windows}, rats positive {r.animals_positive}/{r.animals}"
                      + (f"; with NREM debt partialled {r2.slope:+.3f} [{r2.ci_lo:+.3f}, {r2.ci_hi:+.3f}], p {r2.p:.4f}" if r2 is not None else "")
                      + f" → {'met' if ok[-1] else 'NOT met'}.")
        res[lab] = ok
    fx = res.get("pass2med", [False, False])
    verdict = "PASS" if all(fx) else ("PARTIAL" if any(fx) else "FAIL")
    fin_ok = all(res.get("FINAL", [False]))
    note = ("met on the fixed thresholds (the scoring the claim is scoped to); " if all(fx) else
            ("met at one horizon only on the fixed thresholds; " if any(fx) else "not met on the fixed thresholds; "))
    note += "FINAL meets it too." if fin_ok else "FINAL does not meet it."
    show = prim[(prim.outcome.isin(["pay_rem", "pay_rem_n", "pay_rem_dur", "pay_nrem"]))]
    L = ["## A4 — #10: REM payback across battery rounds", "",
         "**Plan pass rule (A4, quoted):** \"REM-debt slope > 0.2 with p < 0.05 at 1 and 3 h, day-demeaned → #10 stays Candidate "
         "(strong) (promotion needs step D).\" Applied to morning rounds, `pay_rem ~ debt_rem + animal`, day-demeaned, on the "
         "fixed-threshold scoring (`pass2med_remclean`: the two sides of a round are different sessions, plan section 1); FINAL "
         "reported alongside. Baselines with phase × experiment day (plan section 3).", "",
         "Windows (usable battery-round gaps, ≥ 80 % recorded on both sides):", "", *tbl(CNT), "",
         "### Slopes with the phase × day baselines", "", *tbl(show), "",
         "### The same with the Phase-2 baselines (one common linear day term), for comparison", "",
         *tbl(A4[A4.baseline.str.startswith("common") & (A4.outcome == "pay_rem") & (A4.kind == "morning")]), "",
         "### Verdict A4", "", *vl, "", f"**A4 verdict: {verdict}** — {note}", ""]
    kk = []
    for lab in ctx["recs"]:
        s = key_sel[(key_sel.scores == lab) & (key_sel.predictors == "debt_rem") & key_sel.day_demeaned].sort_values("B_h")
        kk.append(f"{lab}: " + ", ".join(f"{r.B_h} h {r.slope:+.2f} (p {r.p:.3f})" for r in s.itertuples()))
    return L, {"part": "A4", "claim": "#10 morning REM payback (day-demeaned)", "verdict": verdict, "key": " | ".join(kk)}


def part_a5(ctx: dict, out: Path, rd: Path, fd: Path) -> tuple[list[str], dict]:
    P, CP = ctx["P"].copy(), ctx["CP"].copy()
    P["imu_ok"], P["state_ok"], CP["state_ok"] = _bool(P.imu_ok), _bool(P.state_ok), _bool(CP.state_ok)
    P["woke"], CP["woke"] = _bool(P.woke60), _bool(CP.woke60)
    P["lat"], CP["lat"] = P.wake_latency_s, CP.wake_latency_s
    P["woke60_b"] = P.woke
    mov = P[(P.source == "movement") & (P.role == "first") & _bool(P.imu_ok) & _bool(P.state_ok) & P.pre_state.isin(["NREM", "REM"])]
    ctl = CP[(CP.role == "control") & _bool(CP.state_ok) & CP.pre_state.isin(["NREM", "REM"])]
    A = mover_excess(mov, ctl, ["pre_state"])
    Aa = mover_excess(mov, ctl, ["animal", "pre_state"])
    A.to_csv(rd / "ephys_spikes_sleep_explore_A_a5a_library_2026c.csv", index=False)
    Aa.to_csv(rd / "ephys_spikes_sleep_explore_A_a5a_library_per_animal_2026c.csv", index=False)
    # (b) pilot sessions
    pilot = ctx["pilot"]
    rows, crows = pilot_outcomes(P, pilot, np.random.default_rng(55))
    rows.to_csv(out / "a5b_pilot_participants.csv.gz", index=False)
    crows.to_csv(out / "a5b_pilot_controls.csv.gz", index=False)
    scor = [k for k in pilot[0]["arrays"]] if pilot else []
    fin = rows[rows.scoring == "FINAL"]
    agree_state = float((fin.pre_state == fin.lib_pre_state).mean()) if len(fin) else np.nan
    fa = fin[fin.lib_pre_state.isin(["NREM", "REM"]) & fin.pre_state.isin(["NREM", "REM"])]
    agree_woke = float((fa.woke.astype(bool) == fa.lib_woke60.astype(bool)).mean()) if len(fa) else np.nan
    first = rows[(rows.role == "first") & rows.imu_ok]
    # own sets per scoring
    own = []
    for lab in scor:
        m = first[(first.scoring == lab) & first.state_ok & first.pre_state.isin(["NREM", "REM"])]
        c = crows[(crows.scoring == lab) & crows.state_ok & crows.pre_state.isin(["NREM", "REM"])]
        t = mover_excess(m.assign(woke=m.woke.astype(bool)), c.assign(woke=c.woke.astype(bool)), ["pre_state"])
        t.insert(0, "set", "own asleep set per scoring")
        t.insert(0, "scoring", lab)
        own.append(t)
    # same participants: NREM (or REM) under FINAL and under the ungated scoring
    same = []
    ung = "ungated (imu)"
    if "FINAL" in scor and ung in scor:
        piv = first.pivot_table(index=["session", "event_id"], columns="scoring", values="pre_state", aggfunc="first")
        okp = first.pivot_table(index=["session", "event_id"], columns="scoring", values="state_ok", aggfunc="first")
        cp_piv = crows.pivot_table(index=["session", "sec"], columns="scoring", values="pre_state", aggfunc="first")
        cp_ok = crows.pivot_table(index=["session", "sec"], columns="scoring", values="state_ok", aggfunc="first")
        for ps in ("NREM", "REM"):
            keep = piv.index[(piv["FINAL"] == ps) & (piv[ung] == ps) & okp["FINAL"].astype(bool) & okp[ung].astype(bool)]
            ckeep = cp_piv.index[(cp_piv["FINAL"] == ps) & (cp_piv[ung] == ps) & cp_ok["FINAL"].astype(bool) & cp_ok[ung].astype(bool)]
            for lab in scor:
                m = first[first.scoring == lab].set_index(["session", "event_id"]).loc[lambda x: x.index.isin(keep)]
                c = crows[crows.scoring == lab].set_index(["session", "sec"]).loc[lambda x: x.index.isin(ckeep)]
                if not len(m) or not len(c):
                    continue
                t = mover_excess(m.reset_index().assign(woke=lambda x: x.woke.astype(bool)),
                                 c.reset_index().assign(woke=lambda x: x.woke.astype(bool)), ["pre_state"])
                t.insert(0, "set", f"same participants ({ps} under FINAL and ungated)")
                t.insert(0, "scoring", lab)
                same.append(t)
        trans = pd.crosstab(piv["FINAL"], piv[ung]).reset_index().rename(columns={"FINAL": "FINAL \\ ungated"})
    else:
        trans = pd.DataFrame()
    B5 = pd.concat(own + same, ignore_index=True) if own or same else pd.DataFrame()
    B5.to_csv(rd / "ephys_spikes_sleep_explore_A_a5b_pilot_2026c.csv", index=False)
    ident = []
    for ps in pilot:
        f_ = ps["arrays"].get("FINAL")
        parts_ = []
        for nm_, lab_ in (("gated, same pilot run (imu_remclean)", "gated pilot"), ("ungated (imu)", "ungated")):
            g_ = ps["arrays"].get(nm_)
            if g_ is not None and f_ is not None:
                n_ = min(len(g_), len(f_))
                parts_.append(f"{lab_} = FINAL in {100 * float(np.mean(g_[:n_] == f_[:n_])):.2f} %")
        ident.append(f"{ps['session']}: " + ", ".join(parts_))
    sess_tab = rows[rows.scoring == "FINAL"].groupby(["animal", "session"]).agg(participants=("event_id", "size"),
                                                                                first_movers=("role", lambda x: int((x == "first").sum()))).reset_index() \
        if len(rows) else pd.DataFrame()
    # figure
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sleep_quant import save_fig
    fig, axs = plt.subplots(1, 2, figsize=(11, 4))
    for i, (ps, g) in enumerate(A.groupby("pre_state")):
        for j, (col, lab_) in enumerate((("woke60", "all wakes"), ("woke60_excl15", "wakes < 15 s excluded"))):
            x = i * 3 + j
            axs[0].bar(x - 0.2, g[f"mover_{col}"].iloc[0], 0.38, color=COLORS["dark"], label="first mover" if x == 0 else None)
            axs[0].bar(x + 0.2, g[f"control_{col}"].iloc[0], 0.38, color=COLORS["light"], label="control" if x == 0 else None)
    axs[0].set_xticks([0, 1, 3, 4], ["NREM\nall", "NREM\nexcl. <15 s", "REM\nall", "REM\nexcl. <15 s"][:4])
    axs[0].set_ylabel("share with a WAKE within 60 s")
    axs[0].set_title("(a) Phase-6 library", fontsize=9, color=COLORS["ink"])
    axs[0].legend(fontsize=8, frameon=False)
    if len(B5):
        g = B5[(B5.set == "own asleep set per scoring") & (B5.pre_state == "NREM")]
        for x, r in enumerate(g.itertuples()):
            axs[1].bar(x - 0.2, r.excess_all, 0.38, color="#1baf7a", label="all wakes" if x == 0 else None)
            axs[1].bar(x + 0.2, r.excess_excl15, 0.38, color="#4a3aa7", label="wakes < 15 s excluded" if x == 0 else None)
        axs[1].set_xticks(range(len(g)), [s.replace(", same pilot run", "\nsame pilot run").replace(" (", "\n(") for s in g.scoring], fontsize=7)
        axs[1].axhline(0, color=COLORS["ink"], lw=0.8)
        axs[1].set_ylabel("mover − control, NREM (share)")
        axs[1].legend(fontsize=8, frameon=False)
    axs[1].set_title("(b) pilot sessions: mover excess by scoring", fontsize=9, color=COLORS["ink"])
    for ax in axs:
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    save_fig(fig, fd / "ephys_spikes_sleep_explore_A_a5_2026c.png")
    plt.close(fig)
    # verdict (NREM: the claim's number)
    a_n = A[A.pre_state == "NREM"].iloc[0]
    ratio_a = float(a_n.ratio_excl15_to_all)
    kept_a = ratio_a >= 0.5
    rb = np.nan
    if len(B5):
        o = B5[(B5.set == "own asleep set per scoring") & (B5.pre_state == "NREM")].set_index("scoring")
        if "FINAL" in o.index and ung in o.index and o.loc["FINAL", "excess_all"]:
            rb = float(o.loc[ung, "excess_all"] / o.loc["FINAL", "excess_all"])
    kept_b = bool(np.isfinite(rb) and rb >= 0.5)
    if kept_a and kept_b:
        verdict, note = "PASS", "the mover excess survives both de-circularising checks; \"movement raises waking\" kept with the caveat."
    elif kept_a and not kept_b:
        verdict, note = "PARTIAL", "(a) keeps the excess but (b) shrinks it below half (or cannot be evaluated): (a) and (b) disagree → plan A5 (c), a full ungated rescore, is the user's decision."
    elif not kept_a and kept_b:
        verdict, note = "PARTIAL", "(a) shrinks the excess below half but (b) does not: (a) and (b) disagree → plan A5 (c) is the user's decision; by the plan's rule (on (a)) the claim's excess is definitional."
    else:
        verdict, note = "FAIL", "the mover excess falls below half under (a): by the plan's rule it is definitional and \"movement raises waking\" is withdrawn."
    na = Aa[Aa.pre_state == "NREM"]
    L = ["## A5 — #28b / #29a: de-circularising the movement → wake contrast", "",
         "**Plan pass rule (A5, quoted):** \"Mover excess (vs control) remains ≥ half its size under (a) → 'movement raises "
         "waking' kept with the caveat; otherwise it is definitional and is withdrawn.\" (a) = the library, wakes beginning "
         "< 15 s after the onset excluded (from movers and controls alike); (b) = the pilot sessions re-read under the ungated "
         "scoring; (c) = a full ungated rescore only if (a) and (b) disagree (a user decision; not run here). Applied to NREM "
         "(the pre-state of #29a's 71 % vs 80.5 %); REM reported.", "",
         "Caveat (plan section 1): the scorer's head-movement rules (`imu_nremgate`: movement + slow wave = WAKE; "
         "`imu_remclean`: REM with ≥ 3 of 5 s of head movement = WAKE) can turn a movement into a scored wake by construction.", "",
         "### (a) Phase-6 library: first movers vs random co-sleep controls", "", *tbl(A), "", "Per animal:", "",
         *tbl(Aa[["animal", "pre_state", "mover_n", "mover_woke60", "control_n", "control_woke60", "excess_all", "mover_n_excl15",
                  "mover_woke60_excl15", "control_woke60_excl15", "excess_excl15", "ratio_excl15_to_all"]]), "",
         f"NREM per animal: excess > 0 with all wakes in {int((na.excess_all > 0).sum())}/{len(na)}, after the exclusion in "
         f"{int((na.excess_excl15 > 0).sum())}/{len(na)}; ratio ≥ 0.5 in {int((na.ratio_excl15_to_all >= 0.5).sum())}/{len(na)}.", "",
         "### (b) Pilot sessions scored without the movement rules", "",
         f"Sessions with an ungated score: {len(pilot)} (the task named 7; only these exist under `{PILOT_ROOT / 'imu'}`): "
         + ", ".join(f"{ps['animal']} {ps['session']}" for ps in pilot) + ".", "",
         *tbl(sess_tab), "",
         "Second mapping (participant second = amp_sample / 20 000 + a per-session shift δ): "
         + "; ".join(f"{ps['session']} δ = {ps.get('shift_s', 0):+d} s ({100 * ps.get('shift_agreement', np.nan):.1f} %)" for ps in pilot)
         + f". With it, the FINAL pre-state agrees with the library for {100 * agree_state:.1f} % of participants and woke60 for "
         f"{100 * agree_woke:.1f} % of the asleep ones.", "",
         "Seconds with the same state as FINAL, per session: " + "; ".join(ident) + ".", "",
         "First movers' pre-state, FINAL (rows) vs ungated (columns):", "", *tbl(trans), "",
         "Mover excess per scoring (controls = random seconds of the same sessions asleep under that scoring; 'same "
         "participants' = asleep in the same state under FINAL and ungated):", "",
         *tbl(B5[["scoring", "set", "pre_state", "mover_n", "mover_woke60", "control_n", "control_woke60", "excess_all",
                  "excess_all_lo", "excess_all_hi", "mover_woke60_excl15", "control_woke60_excl15", "excess_excl15"]] if len(B5) else B5), "",
         "![](../figures/ephys_spikes_sleep_explore_A_a5_2026c.png)", "",
         "### Verdict A5", "",
         f"- (a) NREM: mover {a_n.mover_woke60:.3f} vs control {a_n.control_woke60:.3f} (excess {a_n.excess_all:+.3f} "
         f"[{a_n.excess_all_lo:+.3f}, {a_n.excess_all_hi:+.3f}]); wakes < 15 s excluded: {a_n.mover_woke60_excl15:.3f} vs "
         f"{a_n.control_woke60_excl15:.3f} (excess {a_n.excess_excl15:+.3f} [{a_n.excess_excl15_lo:+.3f}, {a_n.excess_excl15_hi:+.3f}]) "
         f"→ ratio {ratio_a:.2f} ({'≥' if kept_a else '<'} 0.5).",
         f"- (b) NREM mover excess, ungated / FINAL on the pilot sessions: {rb:.2f} ({'≥' if kept_b else '<'} 0.5).", "",
         f"**A5 verdict: {verdict}** — {note}", ""]
    vrow = {"part": "A5", "claim": "#28b / #29a movement raises waking beyond the scorer's rules", "verdict": verdict,
            "key": f"library NREM excess {a_n.excess_all:+.3f} → {a_n.excess_excl15:+.3f} excl. < 15 s (ratio {ratio_a:.2f}); "
                   f"pilot ungated / FINAL excess ratio {rb:.2f} (FINAL only, by nature)"}
    return L, vrow


# ================================================================== report
DEFINITIONS = [
    "## Definitions", "",
    r"Time is field-PC local time. States per second: $s_t \in \{0\ \text{unknown}, 1\ \text{WAKE}, 3\ \text{NREM}, 5\ \text{REM}\}$. "
    r"Animals $a$; blocks $k$ = day-half blocks of `sleep_cycles_v2.build_records` (record start 06–18 h → D, else N); 22 blocks.",
    "",
    r"- **Record.** Sessions of an animal joined across splits ≤ 60 s (unknown seconds in between); FINAL exclusions and the "
    r"cut at 2026-09-11 19:40 (`sleep_schedule.included_sessions`). Same session set under both scorings.",
    r"- **Scorings.** FINAL = `states_1s_final` (per-session thresholds, `imu_remclean` + one substitution); pass2med = "
    r"`states_1s_pass2med` (`pass2med_remclean`, fixed per-animal thresholds), the check for contrasts whose two sides are "
    r"different sessions (plan section 1).",
    r"- **Bout.** A maximal run of one state value, $[a, b)$ in seconds; length $d = b - a$ (s).",
    r"- **Dark.** $\text{dark}(t) = \neg[\text{sunrise}(t) \le t < \text{sunset}(t)]$, NOAA times at 42.45 N, 76.47 W, EDT "
    r"(`sleep_quant.sun_times`). Never clock hours.",
    r"- **Harmonics.** $(\sin, \cos)(2\pi j h / 24)$, $j = 1, 2$, $h$ = clock hour (decimal) of the stated time.",
    r"- **MA (microarousal).** A WAKE bout with $d < 40$ s whose neighbours are both NREM (Watson et al. 2016).",
    "",
    "### A1 / A2",
    r"- **Long wake.** A WAKE bout $[a_w, b_w)$ with $d = b_w - a_w \ge 420$ s (7 min) whose next bout is NREM, inside a record. "
    r"`left_cens` = it starts at the record start or after an unknown epoch ($d$ is then a lower bound; kept, as in Phase 2).",
    r"- **N_pre** (s). $N_{pre} = \sum_{t \in [e_R, a_w)} \mathbb{1}[s_t = 3]$, $e_R$ = end of the last REM bout before the wake "
    r"that follows a known epoch; NREM seconds only (MAs not counted), intervening wakes of any length are skipped. "
    r"Anchor $= 1$ if such a REM exists in the record, else 0 and $N_{pre} = 0$ (the Phase-2 B1b definition).",
    r"- **T** (s, the post-wake NREM time). From $b_w$, bouts are followed in order: NREM and MA seconds are summed; "
    r"other WAKE bouts of 40–419 s are passed without counting. Stop at the first REM onset (event $= 1$) or censor (event "
    r"$= 0$) at an unknown epoch, the next long wake, or the record end. $T$ is the summed time at the stop. Other WAKE "
    r"bouts < 420 s that are not MAs (40–419 s, or < 40 s next to REM) are passed without counting and do not censor.",
    r"- **Cox model (A1 i).** $h(T \mid x) = h_{0,a}(T)\exp(\beta^\top x)$, strata = animal, Efron ties, "
    r"$x = [\ln d, \ln(1+N_{pre}), \text{anchor}, \text{harmonics at } b_w, \text{dark}(b_w)]$. A negative $\beta$ = a lower "
    r"REM hazard per NREM second = REM later. 95 % CI $= \hat\beta \pm 1.96\,\widehat{se}$, $\widehat{se}$ from the "
    r"cluster-robust sandwich $H^{-1}(\sum_k U_k U_k^\top)H^{-1}\,G/(G-1)$ over blocks ($U_k$ = summed score residuals of "
    r"block $k$, $G$ = blocks); model-based SEs in the CSV. Binary covariates with < 10 sleeps in their minority class are "
    r"dropped from a fit (separation). Also reported: the logic audit's specification (the same without dark). In A2 the "
    r"per-phase fits drop dark (constant within a phase).",
    r"- **OLS (A1 ii, B1b-style).** Events only: $\ln T = \alpha_a + \beta_d \ln d + \beta_N \ln(1+N_{pre}) + \gamma\,\text{anchor} "
    r"+ \text{harmonics} + \varepsilon$; SEs clustered by block. A positive $\beta_d$ = more NREM needed after longer wakes. "
    r"Full resumption predicts $\beta_N \approx -0.3$ (plan); no resumption $\beta_N \approx 0$.",
    r"- **Resumption benchmark.** For each sleep $i$ a requirement $Y_i$ is drawn from the observed event times $\{T_j : "
    r"\text{event}_j = 1\}$; world *resume*: anchored sleeps draw $Y_i > N_{pre,i}$ and $T_i^* = Y_i - N_{pre,i}$ (the residual "
    r"of a total that continues across the wake); world *restart*: $T_i^* = Y_i$. Observed censoring times $C_i$ are kept "
    r"($C_i = \infty$ for observed events); $T_i^{sim} = \min(T_i^*, C_i)$. The Cox and OLS models are refitted; median and "
    r"2.5–97.5 % of $\hat\beta_N$ over 100 replicates. It translates the plan's −0.3 to the Cox scale.",
    r"- **RESUME / RESTART counters (A1 iii).** At each 10-s NREM step $j$ of an anchored post-long-wake stretch (from $b_w$ "
    r"to the stop of $T$): RESTART $= n_r + e$, $n_r$ = NREM s from $b_w$ to the bout start; RESUME $= N_{pre} + n_r + e$ "
    r"(= the NREM since the last REM, pausing over wakes; equal to `record_steps_s`'s $N_{since}$, checked); $e$ = elapsed "
    r"s in the bout. Hazard spec (identical for both): multinomial logit stay / REM / WAKE per step on spline($\ln(\text{elapsed}+5)$), "
    r"harmonics, linear experiment day, animal, L1 (ln wake before the bout, after-REM, after-unknown, wake share of the "
    r"last 10 min), ln REM_pre, anchor, $\ln d$ of the long wake, dark at the step, and a cubic spline (4 knots) of "
    r"$\ln(1 + \text{counter})$.",
    r"- **Δ (held-out).** Forward chaining over the day-half blocks (train on blocks $1..k-1$, test block $k$, $k \ge 7$); "
    r"$\Delta = 100 \times (\overline{\ell}_{RESTART} - \overline{\ell}_{RESUME}) / \overline{\ell}_{RESUME}$, $\ell$ = per-step "
    r"log loss, step-weighted over folds; 95 % CI by bootstrap over folds (2000). Negative = RESTART predicts better. "
    r"Animals better = per-animal pooled Δ < 0; holds = CI < 0 and ≥ 5/6 animals.",
    r"- **A2 ranges and bins.** Phase at $b_w$. Plan ranges: dark $7 \le d < 240$ min, light $7 \le d < 30$ min. Bins (min): "
    r"7–15 (reference), 15–30, 30–60, 60–120, 120–240, ≥ 240; bin dummies replace $\ln d$ in the OLS / Cox (bins with ≥ 3 "
    r"events). KM median $T$ = Kaplan–Meier median of $T$ with censoring.",
    "",
    "### A3",
    r"- **SLEEP episode.** A maximal stretch of a record with no WAKE bout > 120 s and no unknown epoch, trimmed to its first "
    r"and last NREM/REM second, kept if ≥ 20 min (Watson 2016; `sleep_schedule_phase3.episodes_of`). Phase = dark at its onset.",
    r"- **Prior wake** (s). The WAKE bout ending at the episode onset, if > 120 s and not left-censored (it must follow a "
    r"known epoch inside the record). Bins: 2–7 min $[120, 420)$ s, 7–30 min $[420, 1800)$ s.",
    r"- **Post-handling exclusion.** Episodes with onset in $[g_{end}, g_{end} + 3\,\text{h})$ of a Phase-0 gap of the same "
    r"animal with cause `round_logged` or `round_inferred` are dropped (plan section 3).",
    r"- **REM rate.** Per phase $p$: $\lambda_p = \sum_i n_{R,i} / \sum_i N_i$, $n_{R,i}$ = REM bouts in episode $i$, $N_i$ = "
    r"its NREM hours. Pooled ratio $= \lambda_{dark} / \lambda_{light}$ (< 1 = fewer REM entries per NREM hour at night). "
    r"Per-episode mean ratio = ratio of the means of $n_{R,i}/N_i$ (the logic audit's 5.0 vs 11.7 used this). GLM rate "
    r"ratio $= e^{\beta}$ from Poisson $n_{R,i} \sim \text{dark} + \ln \text{dur}_i + \text{animal}$, offset $\ln N_i$, SEs by "
    r"block. Per-animal ratio for animals with ≥ 3 episodes in each phase.",
    r"- **First-REM latency** (wall s from the onset to the first REM onset: NREM, MAs and wakes ≤ 120 s; censored at the "
    r"episode end). Cox with dark, ln prior wake, ln duration, animal "
    r"strata, SEs by block; HR < 1 = later first REM at night. Per animal: first-REM rate ratio = $(\sum e_i / \sum L_i)_{dark} / "
    r"(\sum e_i / \sum L_i)_{light}$ ($e_i$ = first REM observed, $L_i$ = latency or censored time, s; exponential MLE); < 1 = "
    r"later first REM at night.",
    "",
    "### A4",
    r"- **10-min bins** (`phase2.bins10`): recorded, REM, NREM s and REM onsets per 10 min of a record; REM bouts not touching "
    r"unknown epochs give the durations.",
    r"- **Baselines (plan section 3).** Leave-one-block-out GLMs as `phase2.baselines` with design $[1, \text{harmonics}, "
    r"\text{day}, \text{dark}, \text{dark} \times \text{day}, \text{animal}]$: binomial REM and NREM share (weights = recorded "
    r"s), Poisson REM onsets (offset ln recorded 10-min units), OLS on ln REM bout duration (smearing). dark at the bin "
    r"midpoint; day = days since the release (2026-08-30 19:00). Phase 2's baselines (no dark terms) are shown for comparison.",
    r"- **Windows** (`phase2.comp_windows`): A = the 3 h before a usable battery-round gap (cause `round_logged` / "
    r"`round_inferred`, ≤ 180 min, ≥ 1 h recorded on both sides), B = the first 1 h / 3 h after it; each ≥ 80 % recorded. "
    r"Kind = the gap's Phase-0 kind (morning: gap start 05:00–11:00; evening: 15:30–21:30).",
    r"- **Debt / payback** (min; s for durations). $\text{debt}_{REM} = E[\text{REM}_A] - \text{REM}_A$, "
    r"$\text{pay}_{REM} = \text{REM}_B - E[\text{REM}_B]$; the same for NREM; $\text{pay}_{n}$ = REM onsets in B minus expected; "
    r"$\text{pay}_{dur}$ = mean REM bout duration in B minus expected. Positive slope of pay on debt = more REM after a "
    r"larger shortfall.",
    r"- **Models.** OLS with animal fixed effects, SEs clustered by the block of window A. Day-demeaned: each variable minus "
    r"its mean over the windows of the same calendar day (gap start date) before fitting. NREM debt partialled: "
    r"$\text{pay}_{REM} \sim \text{debt}_{REM} + \text{debt}_{NREM}$. Per-animal slopes for animals with ≥ 4 + (number of "
    r"predictors) windows.",
    "",
    "### A5",
    r"- **woke60.** For a participant asleep (NREM or REM) at second $t_0$: $\mathbb{1}[\exists u \in [1, 60]: s_{t_0+u} = 1]$ "
    r"(`sleep_events.outcome`); wake latency = the first such $u$ (s).",
    r"- **First mover / control** (Phase-6 library). First mover = the seed of a movement event (role `first`), IMU valid, "
    r"scores known over $t_0 \pm 60$ s, asleep at $t_0$. Control = a random co-sleep second of an asleep member (role "
    r"`control`), scores known over $\pm 60$ s.",
    r"- **Exclusion (< 15 s).** Participants whose first wake begins at $u < 15$ s are removed from numerator and denominator, "
    r"in movers and controls alike: $\text{woke60}_{excl} = \#\{\text{woke}, u \ge 15\} / \#\{\text{not woke or } u \ge 15\}$.",
    r"- **Mover excess** $= \text{woke60}_{mover} - \text{woke60}_{control}$ (share); 95 % CI normal approximation "
    r"$\pm 1.96\sqrt{p_1(1-p_1)/n_1 + p_0(1-p_0)/n_0}$. Ratio = excess after the exclusion / excess with all wakes.",
    r"- **Pilot sessions (A5 b).** Sessions scored with the ungated `imu` variant (`useEMG_NREM = False`, no REM-clean rules); "
    r"the same session's FINAL states and the gated `imu_remclean` states of the same pilot run. 1-s arrays from the scorer "
    r"timestamps (index = timestamp − 1, as in `build_records`). Participant second $= \lfloor \text{amp\_sample} / 20000 \rfloor + \delta$, "
    r"$\delta \in \{-2..2\}$ per session = the shift that best reproduces the library's pre-state from the session's FINAL "
    r"states (the library placed states on the field-PC second grid; the shift absorbs the sub-second session-start offset). "
    r"Within-session controls: up to 3000 random seconds per session (common to all scorings; $60 \le t < n - 601$), kept "
    r"where asleep and known over $\pm 60$ s under that scoring.",
    "",
]


def stepA(a) -> None:
    from _common import git_commit, write_json
    from output_paths import figure_dir, report_dir, run_dir
    parts = [p for p in ("a1", "a2", "a3", "a4", "a5") if p in set(a.parts)]
    out = run_dir("sleep_explore_A" + ("_smoke" if a.smoke else ""), "2026c")
    rd, fd = (out, out) if a.smoke else (report_dir("2026c", "ephys_spikes"), figure_dir("2026c", "ephys_spikes"))
    gc = git_commit()
    t_all = time.time()
    times = {}
    if a.smoke:
        ctx = synth_ctx(np.random.default_rng(3))
        ctx["smoke"] = True
        n_rep = 10
    else:
        t0 = time.time()
        ctx = {"recs": {lab: build_records(included_sessions(REVIEW, d), d) for lab, d in SCORINGS.items()}}
        ctx["gaps"] = pd.read_csv(Path(json.load(open(P0_MANIFEST))["run_dir"]) / "gaps.csv", parse_dates=["gap_start", "gap_end"])
        if "a5" in parts:
            ctx["P"] = pd.read_csv(LIBRARY / "participants.csv.gz", low_memory=False,
                                   usecols=["event_id", "source", "animal", "role", "role_detail", "imu_ok", "state_ok", "pre_state",
                                            "woke60", "wake_latency_s", "session", "amp_sample"])
            ctx["CP"] = pd.read_csv(LIBRARY / "control_participants.csv.gz", low_memory=False,
                                    usecols=["event_id", "source", "animal", "role", "state_ok", "pre_state", "woke60", "wake_latency_s"])
            ctx["pilot"] = load_pilot()
        times["load"] = time.time() - t0
        n_rep = 100
    print("records:", {k: len(v) for k, v in ctx["recs"].items()}, flush=True)
    sections, verdicts = [], []
    for p in parts:
        t0 = time.time()
        if p == "a1":
            L, v, _ = part_a1(ctx, out, rd, n_rep)
        elif p == "a2":
            L, v = part_a2(ctx, out, rd, fd)
        elif p == "a3":
            L, v = part_a3(ctx, out, rd, fd)
        elif p == "a4":
            L, v = part_a4(ctx, out, rd)
        else:
            L, v = part_a5(ctx, out, rd, fd)
        times[p] = time.time() - t0
        print(f"{p} done in {times[p]:.0f} s: {v['verdict']}", flush=True)
        sections.append(L)
        verdicts.append(v)
    VT = pd.DataFrame(verdicts)
    VT.to_csv(rd / "ephys_spikes_sleep_explore_A_verdicts_2026c.csv", index=False)
    times["total"] = time.time() - t_all
    inputs = {"states_FINAL": str(STATES), "states_pass2med": str(PASS2MED), "review": str(REVIEW),
              "gaps": str(Path(json.load(open(P0_MANIFEST))["run_dir"]) / "gaps.csv") if P0_MANIFEST.exists() else "",
              "library": str(LIBRARY), "pilot_root": str(PILOT_ROOT / "imu")}
    if a.smoke:
        inputs = {"synthetic": "synth_ctx(seed 3)"}
    hdr = ["# Sleep behaviour explore — Step A: the reproduction gate (cohort 2026c)" + (" — SMOKE (synthetic data)" if a.smoke else ""), "",
           f"Plan: [{PLAN}](../../../../{PLAN}) (sections 1, 3 and 5 Step A; the pass rules are the plan's, unchanged). "
           f"Logic audit reproduced: [docs/methods/sleep_logic_audit_2026-10-08.md](../../../../docs/methods/sleep_logic_audit_2026-10-08.md) "
           f"(Q2, Q4, Q5). Driver `ephys/sleep_explore.py stepA` (commit {gc}); bulk `{out}`; parts {', '.join(parts)}; "
           f"runtime {times['total'] / 60:.1f} min.", "",
           "**Status: reproduction gate; claim statuses are changed in the claim audit, not here.** Inputs: the scored 1-s "
           "states (FINAL and pass2med), NOAA light, the Phase-0 gap table, the Phase-6 event library, the ungated pilot "
           "scores. No LFP features. Everything from 2026-09-11 19:40 is cut.", "",
           "## Verdicts", "", *tbl(VT), ""]
    dev = ["## Deviations from the plan and the task, and notes", "",
           "- A5 (b): the task named 7 ungated pilot sessions; only "
           f"{len(ctx.get('pilot', []))} exist (`{PILOT_ROOT / 'imu'}`: "
           + ", ".join(f"{ps['animal']} {ps['session']}" for ps in ctx.get('pilot', [])) + "). The gated `imu_remclean` scores of the "
           "same pilot run are added as a third scoring so that the movement rules are isolated from session-to-session "
           "differences between the local pilot and the server's FINAL run.",
           "- A1: the plan's −0.15 / −0.3 numbers are on the OLS scale; the Cox scale has no stated threshold, so a simulated "
           "full-resumption benchmark gives the Cox-scale reference (supporting evidence, not the rule). The Cox SEs are a "
           "block-clustered sandwich computed here (statsmodels 0.14.6 returns NaN for grouped PHReg SEs).",
           "- A1 (iii): restricted to anchored stretches (a REM earlier in the record), where the two counters differ by N_pre; "
           "unanchored stretches have no N_pre.",
           "- A1: long wakes starting at the record start or after an unknown epoch are kept (Phase-2 definition, flagged "
           "`left_cens`; counts in the A1 data line); the 'wake ends ≥ 3 h after the record start' sensitivity removes most of them.",
           "- A3: a prior wake that starts at the record start or after an unknown epoch is treated as unknown (not binned); "
           "Phase 3's table binned it by its observed length.",
           "- A3 / A1 '≥ 5/6 rats' operationalised as stated in each section (direction counts; strict counts reported).",
           "- A4: the dark term of the baselines is evaluated at the 10-min bin midpoint; windows pooled over `round_logged` "
           "and `round_inferred` gaps.",
           ""]
    flat = [ln for blk in [hdr, DEFINITIONS] + sections + [dev] for ln in blk]
    rpt = rd / "ephys_spikes_sleep_explore_A_2026c.md"
    rpt.write_text("\n".join(flat) + "\n", encoding="utf-8")
    write_json(rd / "run_manifest_sleep_explore_A_2026c.json",
               {"run_dir": str(out), "git_commit": gc, "parts": parts, "inputs": inputs, "runtime_s": {k: round(v, 1) for k, v in times.items()},
                "verdicts": verdicts, "plan": PLAN, "smoke": bool(a.smoke)})
    print("written", rpt, f"({times['total'] / 60:.1f} min)")


# ================================================================== selftest
def selftest() -> None:
    t_start = time.time()
    ok_all = True

    def check(name: str, cond: bool) -> None:
        nonlocal ok_all
        print(("PASS " if cond else "FAIL ") + name, flush=True)
        ok_all &= bool(cond)

    # 1. post-wake table on a hand-made record
    seq = [(N, 300), (R, 60), (N, 200), (W, 500), (N, 100), (W, 20), (N, 150), (W, 200), (N, 50), (R, 30),
           (N, 100), (W, 600), (N, 80), (0, 30), (N, 400)]
    st = np.concatenate([np.full(d, s, np.int8) for s, d in seq])
    rc = {"animal": "SF07", "start": pd.Timestamp("2026-09-03 10:00"), "state": st, "record_id": 0, "block": "2026-09-03D"}
    tb = post_wake_table([rc])
    r0, r1 = tb.iloc[0], tb.iloc[1]
    check("A1 table: first long wake d 500, N_pre 200, anchor, T = 100 + 20 (MA) + 150 + 50 = 320, event",
          (r0.d_s, r0.n_pre, r0.anchor, r0.T_s, r0.event, r0.why) == (500, 200, 1, 320, 1, "rem"))
    check("A1 table: second long wake N_pre 100, censored at the unknown epoch with T 80",
          (r1.d_s, r1.n_pre, r1.T_s, r1.event, r1.why) == (600, 100, 80, 0, "unknown"))
    check("A1 table: light phase at 10:2x", not bool(r0.dark))

    # 2. synthetic restart world: N_pre coefficient ~ 0; resume world: clearly negative; benchmark separates them
    animals = ["SF07", "SF08", "SF09"]
    days = [f"2026-09-{d:02d}" for d in range(1, 11)]
    recs = synth_records(np.random.default_rng(11), animals, days, mode="restart", night_grade=0.3, dark_gain=2.0)
    tab = post_wake_table(recs)
    o_np, o_d, _ = a1_ols(tab)
    check(f"A1 restart world: OLS ln(1+N_pre) {fmt_ci(o_np)} has CI above -0.15 and covers 0",
          o_np["ci_lo"] > -0.15 and o_np["ci_lo"] <= 0 <= o_np["ci_hi"])
    c = cterm(cox(tab, COX_A1), "l_npre")
    check(f"A1 restart world: Cox ln(1+N_pre) {fmt_ci(c)} covers 0", c["ci_lo"] <= 0 <= c["ci_hi"])
    bm = resume_benchmark(tab, np.random.default_rng(1), 6)
    rs, rr = bm[bm.world == "resume"], bm[bm.world == "restart"]
    check(f"A1 benchmark: resume world OLS {rs.ols_l_npre.median():+.3f} below restart world {rr.ols_l_npre.median():+.3f} - 0.08; "
          f"Cox {rs.cox_l_npre.median():+.3f} > 0",
          rs.ols_l_npre.median() < rr.ols_l_npre.median() - 0.08 and rs.cox_l_npre.median() > 0.05 and abs(rr.ols_l_npre.median()) < 0.05)
    recs_r = synth_records(np.random.default_rng(12), animals[:2], days[:8], mode="resume")
    o_r, _, _ = a1_ols(post_wake_table(recs_r))
    check(f"A1 resume world: OLS ln(1+N_pre) {fmt_ci(o_r)} has CI below -0.15", o_r["ci_hi"] < -0.15)

    # 3. A2: night-only grading (truth: requirement x (d/420)^0.3 in the dark only); 12-h records, more long wakes
    recs2 = synth_records(np.random.default_rng(202), animals, [f"2026-09-{d:02d}" for d in range(1, 13)], mode="restart",
                          night_grade=0.3, dark_gain=2.0, rec_h=12.0, starts=("07:00", "19:00"), p_long=0.15)
    t2 = post_wake_table(recs2)
    dk = t2[t2.dark & (t2.d_s < 4 * 3600)]
    lt = t2[~t2.dark & (t2.d_s < 1800)]
    de, le = dk[dk.event == 1], lt[lt.event == 1]
    fdk = term(ols(de.l_T, de[OLS_A1], groups=de.block, fe=de.animal), "l_d")
    flt = term(ols(le.l_T, le[OLS_A1], groups=le.block, fe=le.animal), "l_d")
    cdk = cterm(cox(dk, [c_ for c_ in COX_A1 if c_ != "darkf"]), "l_d")
    check(f"A2: dark ln d slope {fmt_ci(fdk)} > 0 (truth 0.3 on the requirement; events-only OLS is biased low), dark Cox "
          f"{fmt_ci(cdk)} < 0, light OLS {fmt_ci(flt)} covers 0",
          fdk["ci_lo"] > 0 and fdk["coef"] > 0.1 and cdk["ci_hi"] < 0 and flt["ci_lo"] <= 0 <= flt["ci_hi"])

    # 3b. held-out: RESTART beats RESUME in the restart world (a smaller world with a tighter requirement: the logistic fits dominate the run time)
    sub = synth_records(np.random.default_rng(13), animals[:2], days[:6], mode="restart", req_sd=0.15, p_long=0.12)
    tsub = post_wake_table(sub)
    S, agree = stretch_steps(sub, tsub)
    check(f"A1 iii: record_steps_s N_since equals the RESUME counter ({100 * agree:.1f} %)", agree == 1.0)
    h = heldout_counters(S, "selftest")
    check(f"A1 iii: held-out RESTART vs RESUME Delta {h.get('delta_pct', np.nan):+.3f} % < 0 ({h.get('folds', 0)} folds)",
          h.get("delta_pct", 1) < 0)

    # 4. A3 episodes: hand-made + known ratio
    seq = [(W, 300), (N, 1500), (R, 60), (N, 600), (W, 300), (N, 800), (R, 50), (N, 600)]
    st = np.concatenate([np.full(d, s, np.int8) for s, d in seq])
    E = sleep_episode_table([{"animal": "SF07", "start": pd.Timestamp("2026-09-03 10:00"), "state": st, "record_id": 0,
                              "block": "2026-09-03D"}])
    check("A3 episode table: first episode's prior wake starts at the record start -> unknown; second: prior 300 s, "
          "1 REM bout, latency 800 s",
          len(E) == 2 and np.isnan(E.pre_wake_s.iloc[0]) and bool(E.pre_left_cens.iloc[0])
          and (E.pre_wake_s.iloc[1], E.rem_n.iloc[1], E.lat_s.iloc[1], E.lat_event.iloc[1]) == (300.0, 1, 800, 1))
    E = sleep_episode_table(recs)
    Eb = E[(E.pre_wake_s >= 120) & (E.pre_wake_s < 1800)]
    r, _ = a3_bin(Eb)
    check(f"A3: synthetic dark gain 2 -> pooled ratio {r['ratio_pooled']:.2f} in [0.3, 0.7], GLM {r['glm_rr']:.2f}, "
          f"Cox HR {r['cox_HR_dark']:.2f} < 1", 0.3 <= r["ratio_pooled"] <= 0.7 and r["cox_HR_dark"] < 1)
    gtest = pd.DataFrame({"animal": ["SF07"], "gap_end": [pd.Timestamp("2026-09-03 10:00")], "cause": ["round_logged"]})
    m = after_gap_mask(pd.DataFrame({"animal": ["SF07", "SF07", "SF08"], "t0": pd.to_datetime(["2026-09-03 12:59", "2026-09-03 13:00",
                                                                                                "2026-09-03 11:00"])}), "t0", gtest, ROUND_CAUSES)
    check("A3: post-round mask = [gap end, + 3 h) of the same animal", list(m) == [True, False, False])

    # 5. A4: day-demeaning recovers the within-day slope; phase x day baselines track opposite trends
    rng = np.random.default_rng(5)
    nW = 240
    W_ = pd.DataFrame({"animal": rng.choice(["SF07", "SF08", "SF09", "SF10"], nW), "day": rng.integers(0, 20, nW), "B_h": 1, "kind": "morning"})
    u = rng.normal(0, 3, 20)[W_.day]
    e = rng.normal(0, 1, nW)
    debt = u + e
    pay = 0.5 * e + 2 * u + rng.normal(0, 0.3, nW)
    W_["t_A"] = pd.Timestamp("2026-09-01 04:00") + pd.to_timedelta(W_.day, unit="D")
    W_["A_block"] = W_.day.astype(str)
    W_["A_e_rem_min"], W_["A_rem_min"] = debt, 0.0
    W_["B_rem_min"], W_["B_e_rem_min"] = pay, 0.0
    for c_ in ("A_e_nrem_min", "A_nrem_min", "B_nrem_min", "B_e_nrem_min", "B_rem_n", "B_e_rem_n", "B_rem_dur_s", "B_e_rem_dur_s"):
        W_[c_] = rng.normal(0, 1, nW)
    T = pay_models(W_)
    raw = T[(T.outcome == "pay_rem") & (T.predictors == "debt_rem") & ~T.day_demeaned].slope.iloc[0]
    dm = T[(T.outcome == "pay_rem") & (T.predictors == "debt_rem") & T.day_demeaned].slope.iloc[0]
    check(f"A4: day confounder -> raw slope {raw:+.2f} (biased), day-demeaned {dm:+.2f} (truth +0.50)", abs(dm - 0.5) < 0.1 and raw > 1.0)
    rows = []
    for an in ("SF07", "SF08"):
        for dd in range(12):
            for i in range(144):
                t = pd.Timestamp("2026-09-01") + pd.Timedelta(days=dd, minutes=10 * i)
                rows.append({"animal": an, "t": t})
    Bs = pd.DataFrame(rows)
    Bs["hour"] = Bs.t.dt.hour + Bs.t.dt.minute / 60
    Bs["day"] = (Bs.t - pd.Timestamp("2026-08-30 19:00")).dt.total_seconds() / 86400
    Bs["dark"] = (~light_flags(Bs.t + pd.Timedelta(minutes=5))).astype(float)
    Bs["block"] = [_block(t) for t in Bs.t]
    Bs["record_id"] = 0
    p_true = 1 / (1 + np.exp(-(-2.0 + 0.6 * (1 - Bs.dark) + 0.12 * (Bs.day - 8) * (1 - Bs.dark) - 0.12 * (Bs.day - 8) * Bs.dark)))
    Bs["rec_s"] = 600
    Bs["rem_s"] = rng.binomial(600, p_true)
    Bs["nrem_s"] = rng.binomial(600, 0.4, len(Bs))
    Bs["rem_on"] = rng.poisson(0.8, len(Bs))
    RBs = Bs.sample(800, random_state=1)[["animal", "block", "t", "hour", "day", "dark"]].assign(dur_s=lambda x: rng.lognormal(4.2, 0.3, len(x)))
    e_d = baselines_d(Bs, RBs).e_rem_s
    e_c = baselines(Bs, RBs).e_rem_s
    mae_d, mae_c = float(np.mean(np.abs(e_d - 600 * p_true))), float(np.mean(np.abs(e_c - 600 * p_true)))
    check(f"A4: phase x day baseline error {mae_d:.1f} s < common-day baseline error {mae_c:.1f} s per 10-min bin", mae_d < 0.7 * mae_c)

    # 6. A5: exclusion arithmetic, outcome mapping, mat/npz placement
    mov = pd.DataFrame({"pre_state": "NREM", "woke": [True] * 40 + [False] * 60, "lat": [5] * 30 + [30] * 10 + [np.nan] * 60})
    ctl = pd.DataFrame({"pre_state": "NREM", "woke": [True] * 150 + [False] * 850, "lat": [30] * 100 + [5] * 50 + [np.nan] * 850})
    X5 = mover_excess(mov, ctl, ["pre_state"]).iloc[0]
    check(f"A5: excess all {X5.excess_all:.4f} (0.25), excl15 {X5.excess_excl15:.4f} (10/70 - 100/950 = 0.0376), ratio "
          f"{X5.ratio_excl15_to_all:.3f}", abs(X5.excess_all - 0.25) < 1e-9 and abs(X5.excess_excl15 - (10 / 70 - 100 / 950)) < 1e-9)
    from sleep_events import outcome
    s5 = np.array([N] * 100 + [W] * 5 + [N] * 200, np.int8)
    o = outcome(s5, 94)
    check("A5: outcome() wake 6 s after the onset second -> woke60, latency 6", bool(o["woke60"]) and o["wake_latency_s"] == 6)
    arr = _place(np.array([1, 2, 3, 5]), np.array([3, 3, 5, 1]))
    check("A5: scorer timestamps 1..n map to index ts - 1 (gaps stay unknown)", list(arr) == [3, 3, 5, 0, 1])
    print(f"selftest {'PASS' if ok_all else 'FAIL'} ({time.time() - t_start:.0f} s)")
    if not ok_all:
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["stepA"])
    ap.add_argument("--parts", nargs="*", default=["a1", "a2", "a3", "a4", "a5"])
    ap.add_argument("--smoke", action="store_true", help="synthetic data; every output goes into the run folder")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.selftest:
        selftest()
    elif a.cmd == "stepA":
        stepA(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
