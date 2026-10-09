r"""Sleep behaviour explore, Step F, the sequence-only batch (F1): H5, H7, H8, H9, H10, H11, H20, H23 (cohort 2026c).

Plan: implementation_plan/2026-10-08-sleep-behaviour-explore.md, section 5 (the Step F table: hypothesis, test and pass
rule, written before results and used unchanged here) and section 9, Amendment 1 (the batch split). Every quantity is
defined, formula + text, in the report's Definitions section (DEFINITIONS below).

Inputs (plan section 1): the scored 1-s states FINAL (states_1s_final) and pass2med (states_1s_pass2med, fixed per-animal
thresholds) through sleep_model.records_for (cut at 2026-09-11 19:40); NOAA light (sleep_schedule_phase3.light_flags);
the Phase-0 gap table (battery rounds); for H7 the weather console (temperature anomaly, Phase 4) and the WISER
per-second zones of Step C (co-located housemates); for H23 the WISER default tracks and the head-IMU seconds cache.
No LFP features.

Parts:
  h5   within dark: ln(NREM before the first REM after a long wake) ~ ln d + hours since sunset + ln(1 + P at onset).
  h7   ln REM bout duration ~ ln(1 + P at onset) + dark + ln(1 + prior wake) + temperature anomaly + co-located housemates.
  h8   REM bouts ending in WAKE vs NREM, night vs day, stratified by REM bout duration.
  h9   REM minutes since sunrise / since the last long wake added to Step B's B-full, held out (forward chaining).
  h10  a second REM within 135 s of a REM end vs the brief wakes in the interval, by phase.
  h11  MAs per NREM step vs the REM-entry count P, by phase.
  h20  the k-th inter-REM interval inside a SLEEP episode vs k (P = 0 at every interval start), with phase.
  h23  2-7-min wakes split by IMU activity / WISER displacement during the wake; held-out carry-over gain (Phase 2 C1
       vs R0) per kind.

Usage: python ephys/sleep_explore_f1.py run [--parts h5 h7 ...] [--scorings final pass2med] [--workers 6] [--scratch]
       python ephys/sleep_explore_f1.py --selftest
--scratch writes the report, CSVs and figures into the run folder only (never the canonical report paths).
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
sys.path.insert(0, str(ROOT / "wiser" / "src"))
from sleep_cycles import boot_ci, bouts, loglosses  # noqa: E402
from sleep_model import (PASS2MED, build_data, counter_starts, design, folds_of, records_for, run_folds,  # noqa: E402
                         to_arrays, variant_specs)
from sleep_schedule import N, R, STATES, W  # noqa: E402
from sleep_schedule_phase3 import episodes_of, light_flags  # noqa: E402

KEY = "P_tw600_k0"                 # Step B's counter (the grid point chosen most often; Steps C-E)
TAU_W, KAPPA = 600.0, 0.0
SCORINGS = {"final": ("FINAL", STATES), "pass2med": ("pass2med", PASS2MED)}
PARTS = ("h5", "h7", "h8", "h9", "h10", "h11", "h20", "h23")
PLAN = "implementation_plan/2026-10-08-sleep-behaviour-explore.md"
OUT = Path("D:/Field2026_analysis_out/2026c")
C_MANIFEST = ROOT / "results/2026c/ephys_spikes/reports/run_manifest_sleep_explore_C_2026c.json"
G0 = pd.Timestamp("2026-08-30 12:00:00")       # per-second grid (as Step C)
G1 = pd.Timestamp("2026-09-12 00:00:00")
SPAN = int((G1 - G0).total_seconds())
UTC_OFF_S = 4 * 3600                            # field-PC local (EDT) = UTC - 4 h
ANIMALS = ["SF07", "SF08", "SF09", "SF10", "SF11", "SF12"]
MA_S = 40                          # MA = WAKE bout < 40 s (Watson 2016)
LONG_S = 420                       # long wake (>= 7 min)
GAP_S = 600                        # an unknown run this long is a gap
PRIOR_S = 120                      # SLEEP split rule: a wake > 120 s ends a SLEEP episode (Watson 2016)
SEQ_S = 135                        # H10 window
LAND_S = 45                        # H10 landmark sensitivity: brief wakes in [e, e + 45 s), REM onset in [e + 45, e + 135]
POST_S = 3 * 3600                  # post-handling exclusion (plan section 3)
H5_RANGE = (420, 4 * 3600)         # Step A2's dark range: 7 min - 4 h
DUR_EDGES = [0, 20, 40, 70, 120, np.inf]
DUR_LABELS = ["< 20 s", "20-40 s", "40-70 s", "70-120 s", ">= 120 s"]
P_EDGES = [0, 1, 2, 5, 10, 20, 40, np.inf]
P_LABELS = ["0-1", "1-2", "2-5", "5-10", "10-20", "20-40", ">= 40"]
DISP_IN = 14.0                     # WISER: the minimum resolvable distance (repo rule)
COLORS = {"dark": "#2a78d6", "light": "#eb6834", "ink": "#52514e", "grey": "#9a9894", "FINAL": "#2a78d6", "pass2med": "#eb6834"}


# ================================================================== small pure helpers (selftested)
def counter_trace(state: np.ndarray, tau: float = TAU_W, kappa: float = KAPPA) -> dict[int, float]:
    """P (min) at the start of EVERY bout of one record, with Step B's rules (sleep_model.counter_starts gives the NREM
    bouts only): NREM adds n / 60, a wake multiplies by exp(-d / tau) (tau 0 = erase, inf = pause), a REM bout by
    exp(-r / kappa) (kappa 0 = full discharge), unknown runs freeze P."""
    P, out = 0.0, {}
    for s, a, b in bouts(state):
        out[a] = P
        n = b - a
        if s == N:
            P += n / 60.0
        elif s == W:
            P = 0.0 if tau == 0 else (P * np.exp(-n / tau) if np.isfinite(tau) else P)
        elif s == R:
            P = 0.0 if kappa == 0 else P * np.exp(-n / kappa)
    return out


def hours_since_sunset(t) -> np.ndarray:
    """Hours since the most recent NOAA sunset before t (the same date's sunset if t is after it, else the day before)."""
    from sleep_quant import sun_times
    t = pd.to_datetime(pd.Series(t)).reset_index(drop=True)
    out = np.full(len(t), np.nan)
    days = t.dt.normalize()
    for d in days.unique():
        d = pd.Timestamp(d)
        ss0 = pd.Timestamp(sun_times(d.date())[1])
        ssm = pd.Timestamp(sun_times((d - pd.Timedelta(days=1)).date())[1])
        m = (days == d).to_numpy()
        tt = t[m]
        out[m] = np.where(tt >= ss0, (tt - ss0).dt.total_seconds(), (tt - ssm).dt.total_seconds()) / 3600
    return out


def grid_index(t) -> np.ndarray:
    """Second index on the [G0, G1) grid of field-PC local timestamps (floor)."""
    t = pd.to_datetime(pd.Series(t))
    return np.floor((t - G0).dt.total_seconds().to_numpy()).astype(np.int64)


def mh_or(df: pd.DataFrame, strata: list[str], expo: str = "darkf", out: str = "exitW", cc: float = 0.0) -> float:
    """Mantel-Haenszel odds ratio of `out` for expo = 1 vs 0 across strata: sum(a d / n) / sum(b c / n). cc > 0: a
    continuity correction added to the four cells of every stratum that has both exposure groups and a zero cell."""
    num = den = 0.0
    for _, g in df.groupby(strata, observed=True):
        e, y = g[expo].to_numpy() == 1, g[out].to_numpy() == 1
        a, b, c, d = (float(v) for v in (np.sum(e & y), np.sum(e & ~y), np.sum(~e & y), np.sum(~e & ~y)))
        if cc and (a + b) > 0 and (c + d) > 0 and min(a, b, c, d) == 0:
            a, b, c, d = a + cc, b + cc, c + cc, d + cc
        n = a + b + c + d
        num += a * d / n
        den += b * c / n
    return float(num / den) if den > 0 and num > 0 else np.nan


def logit(y, X: pd.DataFrame, groups=None, fe=None):
    """Binomial GLM with an intercept, optional fixed-effect dummies; SEs clustered by `groups` (HC0 otherwise).
    Constant columns are dropped. None if the fit fails (e.g. separation)."""
    import statsmodels.api as sm
    Xd = X.astype(float)
    Xd = Xd.loc[:, [c for c in Xd.columns if Xd[c].nunique() > 1]]
    if fe is not None and pd.Series(np.asarray(fe)).nunique() > 1:
        Xd = pd.concat([Xd, pd.get_dummies(pd.Series(np.asarray(fe), index=X.index), prefix="fe", drop_first=True, dtype=float)], axis=1)
    Xd = sm.add_constant(Xd, has_constant="add")
    yv = np.asarray(y, float)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            m = sm.GLM(yv, Xd, family=sm.families.Binomial())
            if groups is not None and pd.Series(np.asarray(groups)).nunique() > 1:
                f = m.fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(np.asarray(groups))[0]})
            else:
                f = m.fit(cov_type="HC0")
            if not np.all(np.isfinite(f.bse)):
                return None
            return f
        except Exception:  # noqa: BLE001
            return None


def fci(d: dict, nd: int = 3) -> str:
    return f"{d['coef']:+.{nd}f} [{d['ci_lo']:+.{nd}f}, {d['ci_hi']:+.{nd}f}]" if np.isfinite(d.get("coef", np.nan)) else "n/a"


def key_lines(ctx: dict, lines: list[str], n: int = 240) -> dict[str, str]:
    """The per-scoring verdict lines ('- **LABEL:** text') as {label: text[:n]} in the scoring order of ctx."""
    def cut(t: str) -> str:
        if len(t) <= n:
            return t
        k = t.rfind("; ", 0, n)
        return (t[:k] if k > 0 else t[:n]) + " …"
    out = {S["label"]: cut(l_.split(":** ", 1)[1]) for S, l_ in zip(ctx["S"].values(), lines)}
    return {"FINAL": out.get("FINAL", ""), "pass2med": out.get("pass2med", "")}


def met_by(ctx: dict, met: list) -> dict[str, str]:
    """{'FINAL rule met': 'yes' / 'no', 'pass2med rule met': ...} in the scoring order of ctx (values may be strings)."""
    out = {S["label"]: (m_ if isinstance(m_, str) else ("yes" if m_ else "no")) for S, m_ in zip(ctx["S"].values(), met)}
    return {"FINAL rule met": out.get("FINAL", ""), "pass2med rule met": out.get("pass2med", "")}


def ci_txt(c: float, lo: float, hi: float, nd: int = 3) -> str:
    return f"{c:+.{nd}f} [{lo:+.{nd}f}, {hi:+.{nd}f}]"


DEV = {
    "h5": "data = Step A2's post-long-wake table unchanged (no post-round exclusion, as A2), dark 7 min–4 h; P at onset = the "
          "counter `P_tw600_k0` at the post-wake NREM bout start; the primary estimate is the events-only OLS that carries #6b's "
          "slope (A2), the censored Cox is supporting. The hypothesis line and the pass column point in opposite directions; "
          "the verdict follows the pass column.",
    "h7": "'ln d' read as the prior wake of the SLEEP stretch (the last wake > 120 s; the plan's matched-prior-wake definition); "
          "'temperature' as Phase 4's temperature anomaly; location dummies (field / unknown vs house) added as nuisance terms "
          "because group size is 0 by construction outside a house; the 'P at onset ≥ 1 min' row was added after the first "
          "(scratch) run and does not enter the verdict.",
    "h8": "'matched duration' = 5 strata of REM bout duration within animal (Mantel–Haenszel), logistic model alongside; "
          "'≥ 5/6 same sign' applied to the per-animal MH log odds ratios, which carry a 0.5 continuity correction in strata with "
          "a zero cell (corrected after the first scratch run: an animal whose dark REM bouts all ended in WAKE had an infinite "
          "OR and was dropped from the sign count).",
    "h9": "Step B's B-full at the fixed key `P_tw600_k0` (no nested choice), so all 16 forward-chaining test folds are used "
          "(Step B dropped fold 0 only for its nested choice); the rule is applied to both added terms; the recorded-hours "
          "rows are a sensitivity.",
    "h10": "'MA count' = brief wakes (< 40 s) in the interval, including the arousal right after a REM bout; the Watson-MA count, "
           "+ longer wakes, + REM duration and a fixed-exposure landmark version are sensitivity rows; 'survives' = the dark "
           "coefficient keeps a CI excluding 0 with the same sign as without the count.",
    "h11": "'by phase' = separate fits per phase, the rule applied in each; MA = Watson MA (WAKE < 40 s between NREM bouts).",
    "h20": "'at matched P': every inter-REM interval starts at P = 0 under the chosen counter (κ = 0) and is measured in NREM "
           "seconds; the primary model has animal (not episode) fixed effects, fixed before the run; the within-episode model and "
           "a step-level model with the full P spline and the clock are supporting.",
    "h23": "two splits (IMU at the median active share, outcome-blind; WISER at 14 in) are both tested; HOLDS needs one split to "
           "differ on both scorings (not corrected for the two splits); the gain is Phase 2's C1 vs R0 fitted on all post-wake "
           "steps and evaluated on the steps after 2–7-min wakes.",
}


def verdict_of(met: list[bool]) -> str:
    """HOLDS = the pass rule met on every scoring; DOES NOT HOLD = met on none; INCONCLUSIVE = met on some only."""
    return "HOLDS" if all(met) else ("DOES NOT HOLD" if not any(met) else "INCONCLUSIVE")


def fold_diff_ci(F: pd.DataFrame, a: str, b: str, base: float, n_boot: int = 2000) -> dict:
    """Step-weighted mean over folds of (gain_a - gain_b) in nats per step and in % of `base`, 95 % bootstrap CI over
    folds. F rows: fold, n_a, n_b, d_a (= mean ll_C1 - ll_R0 over kind a), d_b."""
    G = F.dropna(subset=["d_a", "d_b"]).copy()
    G = G[(G.n_a > 0) & (G.n_b > 0)]
    if len(G) < 3:
        return {"diff_pct": np.nan, "ci_lo_pct": np.nan, "ci_hi_pct": np.nan, "folds": len(G)}
    G["diff"] = G.d_a - G.d_b
    G["n"] = G.n_a + G.n_b
    est, lo, hi = boot_ci(G, "diff", n_boot=n_boot)
    return {"diff_nats": est, "diff_pct": 100 * est / base, "ci_lo_pct": 100 * lo / base, "ci_hi_pct": 100 * hi / base,
            "folds": len(G), "folds_a_better": int((G["diff"] < 0).sum())}


# ================================================================== shared data
def gaps_table() -> pd.DataFrame:
    from sleep_explore_c import gaps_table as gt
    return gt()


def post_round(df: pd.DataFrame, tcol: str, gaps: pd.DataFrame) -> np.ndarray:
    from sleep_explore import ROUND_CAUSES, after_gap_mask
    return after_gap_mask(df, tcol, gaps, ROUND_CAUSES, POST_S)


def load_scoring(key: str, gaps: pd.DataFrame) -> dict:
    """Records -> 10-s NREM steps at the counter KEY (Step B's build_data) + grid index, post-round flag."""
    from sleep_explore_c import post_round_mask
    t0 = time.time()
    label, states = SCORINGS[key]
    recs = records_for(states)
    steps = build_data(recs, {KEY: variant_specs()[KEY]})
    D = to_arrays(steps)
    D["d_prev"] = steps.d_prev.to_numpy().astype(float)
    D["hour"] = steps.hour.to_numpy().astype(float)
    D["t_s"] = grid_index(steps.t)
    D["post_round"] = post_round_mask(steps.animal.to_numpy().astype(str), steps.t, gaps)
    print(f"[{label}] {len(recs)} records, {len(steps)} NREM steps, REM ends {int((D['y'] == 1).sum())}, "
          f"WAKE ends {int((D['y'] == 2).sum())}; {time.time() - t0:.0f} s", flush=True)
    return {"label": label, "recs": recs, "steps": steps, "D": D}


def timelines(recs: list[dict]) -> dict[str, np.ndarray]:
    from sleep_explore_c import state_timelines
    return state_timelines(recs)


def rem_bout_table(recs: list[dict]) -> pd.DataFrame:
    """One row per REM bout: offsets, duration, neighbours, P at onset (KEY), prior wake (> 120 s, walking back; NaN if
    an unknown epoch or the record start comes first), whether it was entered from a wake."""
    rows = []
    for rc in recs:
        st = rc["state"]
        n = len(st)
        bl = bouts(st)
        Pt = counter_trace(st)
        last_prior = np.nan                    # running: length of the last wake > 120 s, NaN after unknown / at start
        for i, (s, a, b) in enumerate(bl):
            if s == 0:
                last_prior = np.nan
            elif s == W and (b - a) > PRIOR_S:
                last_prior = float(b - a)
            if s != R:
                continue
            prev = bl[i - 1][0] if i else 0
            nx = bl[i + 1] if i + 1 < len(bl) else (0, b, b)
            after = bl[i + 2][0] if i + 2 < len(bl) else 0
            rows.append({"animal": rc["animal"], "record_id": rc["record_id"], "block": rc["block"], "a": a, "b": b,
                         "dur_s": b - a, "t_on": rc["start"] + pd.Timedelta(seconds=a), "t_end": rc["start"] + pd.Timedelta(seconds=b),
                         "prev": prev, "next": nx[0] if b < n else 0, "next_len": (nx[2] - nx[1]) if b < n else 0,
                         "after_next": after, "P_on": Pt[a], "d_prior": last_prior, "from_wake": int(prev == W),
                         "complete": bool(a > 0 and prev != 0 and b < n and st[b] != 0)})
    T = pd.DataFrame(rows)
    T["dark"] = ~light_flags(T.t_on)
    T["darkf"] = T.dark.astype(float)
    return T


# ================================================================== H5
def h5_table(recs: list[dict]) -> pd.DataFrame:
    from sleep_explore import post_wake_table
    tab = post_wake_table(recs)
    byrid = {rc["record_id"]: rc for rc in recs}
    cache: dict[int, dict] = {}
    P = []
    for r in tab.itertuples():
        if r.record_id not in cache:
            cache[r.record_id] = counter_starts(byrid[r.record_id]["state"], "disc", TAU_W, KAPPA)
        P.append(cache[r.record_id][r.wake_b])
    tab["P_on"] = P
    tab["l_P"] = np.log1p(tab.P_on.astype(float))
    tab["hss"] = hours_since_sunset(tab.t_wake_end)
    return tab


H5_MODELS = {"A2 repro (ln d, N_pre, anchor, harmonics)": ["l_d", "l_npre", "anchor", "sin1", "cos1", "sin2", "cos2"],
             "H5 test: ln d + hours since sunset + ln(1+P)": ["l_d", "hss", "l_P"],
             "ln d + ln(1+P) (no time of night)": ["l_d", "l_P"],
             "+ (hours since sunset)^2": ["l_d", "hss", "hss2", "l_P"],
             "+ N_pre + anchor": ["l_d", "hss", "l_P", "l_npre", "anchor"]}
H5_MAIN = "H5 test: ln d + hours since sunset + ln(1+P)"


def h5_fit(tab: pd.DataFrame, gaps: pd.DataFrame | None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    from sleep_explore import cox, cterm, ols, term
    lo, hi = H5_RANGE
    base = tab[tab.dark & (tab.d_s >= lo) & (tab.d_s < hi)].copy()
    base["hss2"] = (base.hss - base.hss.mean()) ** 2
    subsets = {"dark, 7 min-4 h (A2 range)": base}
    if gaps is not None:
        subsets["dark, 7 min-4 h, wake end not in post-round 3 h"] = base[~post_round(base, "t_wake_end", gaps)]
    rows, pa = [], []
    info = {}
    for sl, sub in subsets.items():
        ev = sub[(sub.event == 1) & (sub.T_s > 0)]
        info[sl] = {"sleeps": len(sub), "events": len(ev), "r_lnd_hss": float(np.corrcoef(ev.l_d, ev.hss)[0, 1]) if len(ev) > 2 else np.nan}
        for mn, cols in H5_MODELS.items():
            f = ols(ev.l_T, ev[cols], groups=ev.block, fe=ev.animal) if len(ev) >= 15 else None
            for t in ("l_d", "hss", "l_P"):
                if t in cols:
                    rows.append({"subset": sl, "model": mn, "method": "OLS on events (+ = more NREM before REM)", "term": t,
                                 "n": len(ev), **term(f, t)})
        cx = cox(sub, ["l_d", "hss", "l_P"], T="T_s", E="event")
        for t in ("l_d", "hss", "l_P"):
            c = cterm(cx, t)
            rows.append({"subset": sl, "model": H5_MAIN, "method": "Cox, censored (- = REM later)", "term": t, "n": len(sub),
                         **{k: c[k] for k in ("coef", "se", "ci_lo", "ci_hi", "p")}})
        if sl.startswith("dark, 7 min-4 h (A2"):
            for an, g in ev.groupby("animal"):
                if len(g) >= 10:
                    fa = ols(g.l_T, g[H5_MODELS[H5_MAIN]])
                    pa.append({"animal": an, "events": len(g), "ln_d": term(fa, "l_d")["coef"], "hss": term(fa, "hss")["coef"],
                               "l_P": term(fa, "l_P")["coef"]})
    return pd.DataFrame(rows), pd.DataFrame(pa), info


# ================================================================== H7
H7_PRED = {"l_P": "ln(1 + P at onset)", "darkf": "dark (vs light)", "l_dprior": "ln(1 + prior wake s)",
           "temp_anom": "temperature anomaly (degC)", "n_coloc": "co-located tagged housemates (per animal)"}
H7_NUIS = ["loc_field", "loc_unknown"]


def h7_table(recs: list[dict], gaps: pd.DataFrame, w: pd.DataFrame, zone: dict, mates: dict) -> pd.DataFrame:
    from sleep_schedule_temp import join_weather
    T = rem_bout_table(recs)
    T = T[T.complete].copy()
    T["post_round"] = post_round(T, "t_on", gaps)
    T["l_dur"] = np.log(T.dur_s.astype(float))
    T["l_P"] = np.log1p(T.P_on.astype(float))
    T["l_dprior"] = np.log1p(T.d_prior.astype(float))
    T = join_weather(T.reset_index(drop=True), "t_on", w)
    gi = np.clip(grid_index(T.t_on), 0, SPAN - 1)
    zc = np.zeros(len(T), np.int8)
    nc = np.zeros(len(T))
    for an in ANIMALS:
        m = (T.animal == an).to_numpy()
        if an in zone:
            zc[m] = zone[an][gi[m]]
            nc[m] = mates[an][0][gi[m]]
    T["zone"] = zc
    T["n_coloc"] = nc
    T["loc_field"] = (zc == 3).astype(float)
    T["loc_unknown"] = (zc == 0).astype(float)
    T["hour"] = T.t_on.dt.hour + T.t_on.dt.minute / 60
    for k in (1, 2):
        T[f"sin{k}"], T[f"cos{k}"] = np.sin(2 * np.pi * k * T.hour / 24), np.cos(2 * np.pi * k * T.hour / 24)
    from sleep_schedule import RELEASE
    T["T_day"] = (T.t_on - RELEASE).dt.total_seconds() / 86400
    return T


def h7_fit(T: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    from sleep_explore import ols, term
    use = T[~T.post_round]
    models = {"H7 (plan): P + dark + ln d + temperature + group size": (list(H7_PRED) + H7_NUIS, ["l_dprior", "temp_anom"]),
              "without ln d (all bouts with temperature)": ([p for p in H7_PRED if p != "l_dprior"] + H7_NUIS, ["temp_anom"]),
              "+ experiment day + 2-harmonic clock": (list(H7_PRED) + H7_NUIS + ["T_day", "sin1", "cos1", "sin2", "cos2"], ["l_dprior", "temp_anom"]),
              "+ entered from a wake": (list(H7_PRED) + H7_NUIS + ["from_wake"], ["l_dprior", "temp_anom"]),
              "POST HOC: bouts with P at onset >= 1 min (no REM fragments right after a REM)": (list(H7_PRED) + H7_NUIS, ["l_dprior", "temp_anom"])}
    rows, pa = [], []
    info = {"bouts_complete": len(T), "bouts_post_round": int(T.post_round.sum()), "bouts_used": {}}
    for mn, (cols, need) in models.items():
        g = use.dropna(subset=need + cols)
        if mn.startswith("POST HOC"):
            g = g[np.expm1(g.l_P) >= 1.0]
        info["bouts_used"][mn] = len(g)
        f = ols(g.l_dur, g[cols], groups=g.block, fe=g.animal)
        for t in cols:
            if t in H7_PRED or t == "from_wake":
                rows.append({"model": mn, "term": t, "label": H7_PRED.get(t, "entered from a wake"), "n_bouts": len(g), **term(f, t)})
        if mn.startswith("H7 (plan)"):
            for an, ga in g.groupby("animal"):
                if len(ga) >= 30:
                    fa = ols(ga.l_dur, ga[cols])
                    pa.append({"animal": an, "bouts": len(ga), **{t: term(fa, t)["coef"] for t in H7_PRED}})
    return pd.DataFrame(rows), pd.DataFrame(pa), info


def h7_status(co: dict[str, pd.DataFrame], pa: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Per predictor across scorings: 'holds' (pooled CI excludes 0 with the same sign on every scoring and >= 5/6 rats
    share that sign on every scoring), 'n.s.' (pooled CI includes 0 on every scoring), else 'partial'."""
    rows = []
    for t, lab in H7_PRED.items():
        r = {"term": t, "label": lab}
        sig, ns, sgn, rats_ok = [], [], [], []
        for s, C in co.items():
            c = C[(C.model.str.startswith("H7 (plan)")) & (C.term == t)].iloc[0]
            P = pa[s]
            sg = np.sign(c.coef)
            n_same = int((np.sign(P[t]) == sg).sum()) if len(P) else 0
            r[f"{s}_coef"] = c.coef
            r[f"{s}_ci"] = f"[{c.ci_lo:+.3f}, {c.ci_hi:+.3f}]"
            r[f"{s}_pct_per_unit"] = 100 * (np.exp(c.coef) - 1)
            r[f"{s}_rats_same_sign"] = f"{n_same}/{len(P)}"
            excl = bool(c.ci_lo > 0 or c.ci_hi < 0)
            sig.append(excl)
            ns.append(not excl)
            sgn.append(sg)
            rats_ok.append(n_same >= 5)
        if all(sig) and len(set(sgn)) == 1 and all(rats_ok):
            r["status"] = "holds"
        elif all(ns):
            r["status"] = "n.s."
        else:
            r["status"] = "partial"
        rows.append(r)
    return pd.DataFrame(rows)


# ================================================================== H8
def h8_table(recs: list[dict], gaps: pd.DataFrame) -> pd.DataFrame:
    T = rem_bout_table(recs)
    T = T[T.complete & T["next"].isin([N, W])].copy()
    T["post_round"] = post_round(T, "t_on", gaps)
    T["exitW"] = (T["next"] == W).astype(int)
    T["exit_brief"] = ((T["next"] == W) & (T.next_len < MA_S)).astype(int)
    T["dur_bin"] = pd.cut(T.dur_s, DUR_EDGES, right=False, labels=DUR_LABELS)
    return T


def h8_fit(T: pd.DataFrame, rng, n_boot: int = 1000) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    from sleep_explore import term
    use = T[~T.post_round].copy()
    # descriptive: share ending in WAKE per duration bin and phase
    B = use.groupby(["dur_bin", "dark"], observed=True).agg(bouts=("exitW", "size"), share_wake=("exitW", "mean"),
                                                             share_brief_wake=("exit_brief", "mean")).reset_index()
    B["phase"] = np.where(B.dark, "dark", "light")
    B = B.drop(columns="dark")
    # pooled MH (strata animal x duration bin) + block bootstrap
    or_mh = mh_or(use, ["animal", "dur_bin"])
    blocks = use.block.unique()
    byb = {b: g for b, g in use.groupby("block")}
    bs = []
    for _ in range(n_boot):
        pick = rng.choice(blocks, len(blocks), replace=True)
        bs.append(mh_or(pd.concat([byb[b] for b in pick], ignore_index=True), ["animal", "dur_bin"]))
    bs = np.log(np.array([x for x in bs if np.isfinite(x) and x > 0]))
    rows = [{"model": "Mantel-Haenszel OR (strata animal x duration bin), CI by block bootstrap", "term": "dark",
             "coef": float(np.log(or_mh)), "ci_lo": float(np.percentile(bs, 2.5)), "ci_hi": float(np.percentile(bs, 97.5)),
             "OR": or_mh, "n_bouts": len(use)}]
    X = pd.concat([use[["darkf"]], pd.get_dummies(use.dur_bin, prefix="dur", drop_first=True, dtype=float)], axis=1)
    f = logit(use.exitW, X, groups=use.block, fe=use.animal)
    c = term(f, "darkf")
    rows.append({"model": "logistic exit WAKE ~ dark + duration bins + animal (SEs by block)", "term": "dark", **c,
                 "OR": float(np.exp(c["coef"])), "n_bouts": len(use)})
    f2 = logit(use.exitW, use[["darkf"]], groups=use.block, fe=use.animal)
    c2 = term(f2, "darkf")
    rows.append({"model": "logistic exit WAKE ~ dark + animal (NOT duration-matched; reference)", "term": "dark", **c2,
                 "OR": float(np.exp(c2["coef"])), "n_bouts": len(use)})
    X3 = pd.concat([use[["darkf"]], pd.get_dummies(use.dur_bin, prefix="dur", drop_first=True, dtype=float)], axis=1)
    f3 = logit(use[use.exitW == 1].exit_brief, X3[use.exitW == 1], groups=use[use.exitW == 1].block, fe=use[use.exitW == 1].animal)
    c3 = term(f3, "darkf")
    rows.append({"model": "among WAKE exits: brief (< 40 s) ~ dark + duration bins + animal", "term": "dark", **c3,
                 "OR": float(np.exp(c3["coef"])) if np.isfinite(c3["coef"]) else np.nan, "n_bouts": int(use.exitW.sum())})
    pa = []
    for an, g in use.groupby("animal"):
        nd, nl = int(g.dark.sum()), int((~g.dark).sum())
        o = mh_or(g, ["dur_bin"]) if nd >= 5 and nl >= 5 else np.nan
        oc = mh_or(g, ["dur_bin"], cc=0.5) if nd >= 5 and nl >= 5 else np.nan
        pa.append({"animal": an, "bouts_dark": nd, "bouts_light": nl, "share_wake_dark": float(g[g.dark].exitW.mean()) if nd else np.nan,
                   "share_wake_light": float(g[~g.dark].exitW.mean()) if nl else np.nan, "MH_OR_raw": o, "MH_OR": oc,
                   "ln_OR": float(np.log(oc)) if np.isfinite(oc) and oc > 0 else np.nan})
    PA = pd.DataFrame(pa)
    q = PA.ln_OR.dropna()
    info = {"n_pos": int((q > 0).sum()), "n_neg": int((q < 0).sum()), "qualifying": len(q), "or_mh": or_mh}
    return pd.DataFrame(rows), B, PA, info


# ================================================================== H9
def h9_features(D: dict, recs: list[dict], arr: dict[str, np.ndarray] | None = None) -> None:
    """Adds rem_sr / rec_sr (REM minutes / recorded hours since the most recent sunrise) and rem_lw / rec_lw (the same
    since the end of the last wake >= 7 min or unknown run >= 10 min) on each animal's whole timeline (arr: per-animal
    state per grid second; built from recs if None)."""
    from sleep_quant import sun_times
    arr = timelines(recs) if arr is None else arr
    srs = []
    for d in pd.date_range(G0.normalize() - pd.Timedelta(days=1), G1.normalize()):
        srs.append(int((pd.Timestamp(sun_times(d.date())[0]) - G0).total_seconds()))
    srs = np.array(srs)
    for c in ("rem_sr", "rec_sr", "rem_lw", "rec_lw"):
        D[c] = np.zeros(len(D["y"]))
    for an in ANIMALS:
        sel = np.flatnonzero(D["animal"] == an)
        if not len(sel):
            continue
        s = arr[an]
        cR = np.r_[0, np.cumsum(s == R)]
        cK = np.r_[0, np.cumsum(s != 0)]
        i = np.clip(D["t_s"][sel], 0, SPAN - 1)
        j = srs[np.searchsorted(srs, i, side="right") - 1]
        j = np.clip(j, 0, SPAN - 1)
        D["rem_sr"][sel] = (cR[i] - cR[j]) / 60.0
        D["rec_sr"][sel] = (cK[i] - cK[j]) / 3600.0
        ev = [b for st_, a, b in bouts(s) if (st_ == W and b - a >= LONG_S) or (st_ == 0 and b - a >= GAP_S)]
        ev = np.array([0] + ev)
        k = ev[np.searchsorted(ev, i, side="right") - 1]
        D["rem_lw"][sel] = (cR[i] - cR[k]) / 60.0
        D["rec_lw"][sel] = (cK[i] - cK[k]) / 3600.0


H9_SPECS = {"B": (), "B+rem_sr": ("rem_sr",), "B+rem_lw": ("rem_lw",), "B+rec_sr": ("rec_sr",), "B+rec_sr+rem_sr": ("rec_sr", "rem_sr"),
            "B+rec_lw": ("rec_lw",), "B+rec_lw+rem_lw": ("rec_lw", "rem_lw")}
H9_CMP = [("B", "B+rem_sr", "+ REM minutes since sunrise (pass rule)"), ("B", "B+rem_lw", "+ REM minutes since the last long wake (pass rule)"),
          ("B+rec_sr", "B+rec_sr+rem_sr", "+ REM min since sunrise, recorded h since sunrise in both (sensitivity)"),
          ("B+rec_lw", "B+rec_lw+rem_lw", "+ REM min since the last long wake, recorded h since it in both (sensitivity)")]


def fixed_tables(res: list[dict], names) -> tuple[pd.DataFrame, pd.DataFrame]:
    F, FA = [], []
    for r in res:
        F.append({"fold": r["k"], "n": r["n"], "n_rem": r["n_rem"], **{f"ll_{n}": r["ll"][n] for n in names}})
        an = {}
        for n in names:
            for a, (m, k) in r["lla"][n].items():
                an.setdefault(a, {"fold": r["k"], "animal": a, "n": k})[f"ll_{n}"] = m
        FA += list(an.values())
    return pd.DataFrame(F), pd.DataFrame(FA)


def h9_run(S: dict, workers: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    from sleep_model import cmp
    D = S["D"]
    h9_features(D, S["recs"])
    specs = {nm: {"L1": True, "hist": KEY, **({"extra": ex} if ex else {})} for nm, ex in H9_SPECS.items()}
    folds = folds_of(D)
    res = run_folds(D, specs, workers, folds)
    F, FA = fixed_tables(res, specs)
    rows = []
    for lo, hi, lab in H9_CMP:
        r = cmp(F, FA, lo, hi, lab)
        r["scores"] = S["label"]
        rows.append(r)
    # full-data coefficients (multinomial, cluster-robust by block; the extra column z-scored, per SD)
    from sleep_explore_c import coef, mnl_fit
    idx = np.arange(len(D["y"]))
    levels = sorted(set(D["animal"]))
    X0, _ = design(D, idx, {"L1": True, "hist": KEY}, None, levels)
    cf = []
    for nm, ex in H9_SPECS.items():
        if not ex:
            continue
        Z = np.column_stack([(D[c] - D[c].mean()) / (D[c].std() or 1.0) for c in ex])
        names = [f"x{i}" for i in range(X0.shape[1])] + list(ex)
        f = mnl_fit(np.column_stack([X0, Z]), D["y"].astype(int), D["block"])
        for c in ex:
            for eq, eqn in ((0, "REM vs stay"), (1, "WAKE vs stay")):
                cf.append({"scores": S["label"], "model": nm, "term": c, "equation": eqn, "sd": float(D[c].std()), **coef(f, names, c, eq)})
    desc = {c: (float(np.median(D[c])), float(np.percentile(D[c], 90))) for c in ("rem_sr", "rec_sr", "rem_lw", "rec_lw")}
    T = pd.DataFrame(rows)
    T["folds_total"] = len(folds)
    C = pd.DataFrame(cf)
    C.attrs["desc"] = desc
    return T, C


# ================================================================== H10
def h10_table(recs: list[dict], gaps: pd.DataFrame) -> pd.DataFrame:
    """REM bouts whose end is followed by NREM or a WAKE < 40 s, with [e, e + 135 s] known and inside the record."""
    rows = []
    for rc in recs:
        st = rc["state"]
        n = len(st)
        bl = bouts(st)
        for i, (s, a, b) in enumerate(bl):
            if s != R or a == 0 or st[a - 1] == 0 or b + SEQ_S > n or i + 1 >= len(bl):
                continue
            s1, a1, b1 = bl[i + 1]
            if not (s1 == N or (s1 == W and b1 - a1 < MA_S)):
                continue
            win = st[b:b + SEQ_S + 1]
            if np.any(win == 0):
                continue
            # next REM onset in (b, b + 135]
            on = np.flatnonzero((win[1:] == R) & (win[:-1] != R)) + 1
            y = int(len(on) > 0)
            w_end = b + int(on[0]) if y else b + SEQ_S
            nb = nma = nw40 = 0
            exit_brief = int(s1 == W)
            l45 = 0
            for j in range(i + 1, len(bl)):
                s2, a2, b2 = bl[j]
                if a2 >= w_end:
                    break
                if s2 == W:
                    if b2 - a2 < MA_S:
                        nb += 1
                        if j > 0 and bl[j - 1][0] == N and j + 1 < len(bl) and bl[j + 1][0] == N:
                            nma += 1
                        if a2 < b + LAND_S:
                            l45 = 1
                    else:
                        nw40 += 1
            on45 = int(np.any((win[1:LAND_S + 1] == R) & (win[:LAND_S] != R)))
            rows.append({"animal": rc["animal"], "record_id": rc["record_id"], "block": rc["block"], "rem_dur_s": b - a,
                         "t_end": rc["start"] + pd.Timedelta(seconds=b), "y": y, "lat_s": float(on[0]) if y else np.nan,
                         "n_brief": nb, "n_ma": nma, "n_w40": nw40, "exit_brief": exit_brief, "brief_45": l45, "rem_in_45": on45,
                         "nrem_s": int(np.sum(st[b:w_end] == N))})
    T = pd.DataFrame(rows)
    T["dark"] = ~light_flags(T.t_end)
    T["darkf"] = T.dark.astype(float)
    T["post_round"] = post_round(T, "t_end", gaps)
    T["l_rem"] = np.log(T.rem_dur_s.astype(float))
    return T


def h10_fit(T: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    from sleep_explore import term
    use = T[~T.post_round].copy()
    use["any_brief"] = (use.n_brief > 0).astype(float)
    models = {"M0: dark + animal": ["darkf"],
              "M1 (pass rule): dark + brief-wake count in the interval": ["darkf", "n_brief"],
              "M1b: dark + Watson MA count (NREM-NREM) + exit arousal": ["darkf", "n_ma", "exit_brief"],
              "M1c: dark + brief-wake count + wakes >= 40 s in the interval": ["darkf", "n_brief", "n_w40"],
              "M1d: M1 + ln REM duration": ["darkf", "n_brief", "l_rem"]}
    rows = []
    for mn, cols in models.items():
        f = logit(use.y, use[cols], groups=use.block, fe=use.animal)
        for t in cols:
            rows.append({"model": mn, "term": t, "n": len(use), "events": int(use.y.sum()), **term(f, t)})
    land = use[use.rem_in_45 == 0]
    y2 = land.y.astype(int)
    for mn, cols in (("L0 landmark: dark + animal", ["darkf"]), ("L1 landmark: dark + brief wake in [e, e + 45 s)", ["darkf", "brief_45"])):
        f = logit(y2, land[cols], groups=land.block, fe=land.animal)
        for t in cols:
            rows.append({"model": mn, "term": t, "n": len(land), "events": int(y2.sum()), **term(f, t)})
    rates = use.groupby(["dark", use.n_brief.clip(upper=3)]).agg(rem_ends=("y", "size"), p_second_rem=("y", "mean")).reset_index()
    rates["phase"] = np.where(rates.dark, "dark", "light")
    rates = rates.rename(columns={"n_brief": "brief_wakes_in_interval (3 = 3+)"}).drop(columns="dark")
    pa = []
    for an, g in use.groupby("animal"):
        f0 = logit(g.y, g[["darkf"]])
        f1 = logit(g.y, g[["darkf", "n_brief"]])
        pa.append({"animal": an, "n": len(g), "n_dark": int(g.dark.sum()), "p_dark": float(g[g.dark].y.mean()) if g.dark.any() else np.nan,
                   "p_light": float(g[~g.dark].y.mean()), "brief_per_end_dark": float(g[g.dark].n_brief.mean()) if g.dark.any() else np.nan,
                   "brief_per_end_light": float(g[~g.dark].n_brief.mean()), "dark_M0": term(f0, "darkf")["coef"], "dark_M1": term(f1, "darkf")["coef"]})
    return pd.DataFrame(rows), rates, pd.DataFrame(pa)


# ================================================================== H11
def ma_flags(recs: list[dict]) -> dict[tuple[int, int], int]:
    """(record_id, NREM bout start) -> 1 if the bout ends in an MA (WAKE < 40 s followed by NREM), 2 if in a brief wake
    (< 40 s) followed by REM, 3 if in a longer wake / other, 0 otherwise."""
    out = {}
    for rc in recs:
        bl = bouts(rc["state"])
        for i, (s, a, b) in enumerate(bl):
            if s != N:
                continue
            f = 0
            if i + 1 < len(bl) and bl[i + 1][0] == W:
                d = bl[i + 1][2] - bl[i + 1][1]
                nx = bl[i + 2][0] if i + 2 < len(bl) else 0
                f = 1 if (d < MA_S and nx == N) else (2 if (d < MA_S and nx == R) else 3)
            out[(rc["record_id"], a)] = f
    return out


def h11_arrays(S: dict) -> pd.DataFrame:
    st_, D = S["steps"], S["D"]
    fl = ma_flags(S["recs"])
    f = np.array([fl[(r, b)] for r, b in zip(st_.record_id.to_numpy(), st_.bout_start.to_numpy())])
    y = D["y"]
    df = pd.DataFrame({"animal": D["animal"], "block": D["block"], "dark": D["dark"].astype(bool), "post_round": D["post_round"],
                       "y_ma": ((y == 2) & (f == 1)).astype(int), "y_pre": ((y == 2) & (f == 2)).astype(int),
                       "P": np.expm1(D[f"lP_{KEY}"].astype(float)), "l_P": D[f"lP_{KEY}"].astype(float),
                       "l_elapsed": D["l_elapsed"], "T_day": D["T_day"], "sin1": D["sin1"], "cos1": D["cos1"], "sin2": D["sin2"], "cos2": D["cos2"]})
    df["P_bin"] = pd.cut(df.P, P_EDGES, right=False, labels=P_LABELS)
    return df


def h11_fit(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    from sklearn.preprocessing import SplineTransformer
    from sleep_explore import term
    use = df[~df.post_round]
    rows, pa = [], []
    for ph, dk in (("light", False), ("dark", True)):
        g = use[use.dark == dk]
        for yname, ylab in (("y_ma", "MA (WAKE < 40 s then NREM)"), ("y_pre", "brief wake < 40 s then REM (reference)")):
            f = logit(g[yname], g[["l_P"]], groups=g.block, fe=g.animal)
            rows.append({"phase": ph, "outcome": ylab, "model": "logit ~ ln(1+P) + animal (pass rule)", "n_steps": len(g),
                         "events": int(g[yname].sum()), **term(f, "l_P")})
            if yname == "y_ma":
                sp = SplineTransformer(n_knots=4, degree=3, include_bias=False).fit(g[["l_elapsed"]])
                E = pd.DataFrame(sp.transform(g[["l_elapsed"]]), index=g.index, columns=[f"el{i}" for i in range(5)])
                X = pd.concat([g[["l_P", "T_day", "sin1", "cos1", "sin2", "cos2"]], E], axis=1)
                f2 = logit(g[yname], X, groups=g.block, fe=g.animal)
                rows.append({"phase": ph, "outcome": ylab, "model": "+ elapsed-in-bout spline + day + 2-harmonic clock", "n_steps": len(g),
                             "events": int(g[yname].sum()), **term(f2, "l_P")})
        for an, ga in g.groupby("animal"):
            fa = logit(ga.y_ma, ga[["l_P"]])
            pa.append({"phase": ph, "animal": an, "n_steps": len(ga), "mas": int(ga.y_ma.sum()), "slope_l_P": term(fa, "l_P")["coef"]})
    R_ = use.groupby(["dark", "P_bin", "animal"], observed=True).agg(steps=("y_ma", "size"), mas=("y_ma", "sum")).reset_index()
    R_ = R_[R_.steps >= 30]
    R_["ma_per_nrem_min"] = R_.mas / (R_.steps * 10 / 60)
    rates = R_.groupby(["dark", "P_bin"], observed=True).agg(ma_per_nrem_min=("ma_per_nrem_min", "mean"), animals=("animal", "nunique"),
                                                             steps=("steps", "sum"), mas=("mas", "sum")).reset_index()
    rates["phase"] = np.where(rates.dark, "dark", "light")
    return pd.DataFrame(rows), rates.drop(columns="dark"), pd.DataFrame(pa)


# ================================================================== H20
def h20_intervals(recs: list[dict], gaps: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for rc in recs:
        st = rc["state"]
        cN = np.r_[0, np.cumsum(st == N)]
        for e_i, (ea, eb) in enumerate(episodes_of(st, 1200)):
            rb = [(a, b) for s, a, b in bouts(st[ea:eb]) if s == R]
            rb = [(ea + a, ea + b) for a, b in rb]
            t_ep = rc["start"] + pd.Timedelta(seconds=ea)
            for k in range(1, len(rb) + 1):
                e_k = rb[k - 1][1]
                o = rb[k][0] if k < len(rb) else eb
                rows.append({"animal": rc["animal"], "record_id": rc["record_id"], "block": rc["block"], "episode": f"{rc['record_id']}_{e_i}",
                             "t_episode": t_ep, "k": k, "event": int(k < len(rb)), "nrem_s": int(cN[o] - cN[e_k]), "wall_s": int(o - e_k),
                             "rem_k_s": rb[k - 1][1] - rb[k - 1][0], "t_start": rc["start"] + pd.Timedelta(seconds=e_k),
                             "m_rem": len(rb)})
    T = pd.DataFrame(rows)
    T["dark"] = ~light_flags(T.t_start)
    T["darkf"] = T.dark.astype(float)
    T["post_round"] = post_round(T, "t_episode", gaps)
    T["l_nrem"] = np.log(np.maximum(T.nrem_s.astype(float), 1.0))
    T["l_wall"] = np.log(np.maximum(T.wall_s.astype(float), 1.0))
    T["l_remk"] = np.log(T.rem_k_s.astype(float))
    T["hour"] = T.t_start.dt.hour + T.t_start.dt.minute / 60
    for k in (1, 2):
        T[f"sin{k}"], T[f"cos{k}"] = np.sin(2 * np.pi * k * T.hour / 24), np.cos(2 * np.pi * k * T.hour / 24)
    return T


def h20_fit(T: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    from sleep_explore import cox, cterm, ols, term
    use = T[~T.post_round]
    comp = use[(use.event == 1) & (use.nrem_s > 0)]
    rows = []
    specs = {"OLS ln NREM interval ~ k + dark + animal (pass rule)": ("l_nrem", ["k", "darkf"], "animal"),
             "OLS, episode fixed effects (within episode)": ("l_nrem", ["k", "darkf"], "episode"),
             "OLS + ln REM_k duration + 2-harmonic clock": ("l_nrem", ["k", "darkf", "l_remk", "sin1", "cos1", "sin2", "cos2"], "animal"),
             "OLS, wall-clock interval": ("l_wall", ["k", "darkf"], "animal"),
             "OLS, episodes with >= 4 REM bouts only": ("l_nrem", ["k", "darkf"], "animal")}
    for mn, (yv, cols, fe) in specs.items():
        g = comp[comp.m_rem >= 4] if ">= 4 REM" in mn else comp
        f = ols(g[yv], g[cols], groups=g.block, fe=g[fe])
        rows.append({"model": mn, "term": "k", "n": len(g), "method": "OLS (- = shorter in later cycles)", **term(f, "k")})
    cx = cox(use.assign(T_s=np.maximum(use.nrem_s, 1)), ["k", "darkf"], T="T_s", E="event")
    c = cterm(cx, "k")
    rows.append({"model": "Cox, censored at the episode end (animal strata)", "term": "k", "n": len(use), "method": "Cox (+ = REM sooner in later cycles)",
                 **{kk: c[kk] for kk in ("coef", "se", "ci_lo", "ci_hi", "p")}})
    byk = comp.assign(k_cap=comp.k.clip(upper=6), phase=np.where(comp.dark, "dark", "light")).groupby(["phase", "k_cap"]).agg(
        intervals=("nrem_s", "size"), median_nrem_s=("nrem_s", "median"), mean_ln_nrem=("l_nrem", "mean"),
        median_wall_s=("wall_s", "median")).reset_index().rename(columns={"k_cap": "k (6 = 6+)"})
    pa = []
    for an, g in comp.groupby("animal"):
        if len(g) >= 15 and g.k.nunique() > 1:
            fa = ols(g.l_nrem, g[["k", "darkf"]])
            pa.append({"animal": an, "intervals": len(g), "max_k": int(g.k.max()), "slope_k": term(fa, "k")["coef"],
                       "ci_lo": term(fa, "k")["ci_lo"], "ci_hi": term(fa, "k")["ci_hi"]})
    return pd.DataFrame(rows), byk, pd.DataFrame(pa)


def h20_step_k(S: dict) -> np.ndarray:
    """Per NREM step: the number of REM onsets since the start of its SLEEP episode before its bout (0 if none or the
    bout is outside every episode; -1 outside)."""
    st_ = S["steps"]
    out = np.full(len(st_), -1, np.int32)
    byrid = {rc["record_id"]: rc for rc in S["recs"]}
    for rid, g in st_.groupby("record_id"):
        st = byrid[rid]["state"]
        eps = episodes_of(st, 1200)
        if not eps:
            continue
        es = np.array([a for a, _ in eps])
        ee = np.array([b for _, b in eps])
        onsets = np.array([a for s, a, b in bouts(st) if s == R])
        bs = g.bout_start.to_numpy()
        j = np.searchsorted(es, bs, side="right") - 1
        ok = (j >= 0) & (bs < ee[np.maximum(j, 0)])
        k = np.where(ok, np.searchsorted(onsets, bs, side="left") - np.searchsorted(onsets, es[np.maximum(j, 0)], side="left"), -1)
        out[st_.index.get_indexer(g.index)] = k
    return out


def h20_hazard(S: dict) -> dict:
    """B-full (Step B design at KEY) + k on NREM steps inside SLEEP episodes after their first REM (post-round excluded):
    the REM-vs-stay coefficient of k (cluster-robust by block). + = REM entry more likely at the same count and clock."""
    from sleep_explore_c import coef, mnl_fit
    D = S["D"]
    kk = h20_step_k(S)
    idx = np.flatnonzero((kk >= 1) & ~D["post_round"])
    levels = sorted(set(D["animal"][idx]))
    X, _ = design(D, idx, {"L1": True, "hist": KEY}, None, levels)
    kc = kk[idx].astype(float)
    names = [f"x{i}" for i in range(X.shape[1])] + ["k"]
    f = mnl_fit(np.column_stack([X, kc - kc.mean()]), D["y"][idx].astype(int), D["block"][idx])
    out = {"n_steps": len(idx), "n_rem": int((D["y"][idx] == 1).sum()), "rem": coef(f, names, "k", 0), "wake": coef(f, names, "k", 1)}
    pa = {}
    for an in levels:
        ia = idx[D["animal"][idx] == an]
        if (D["y"][ia] == 1).sum() < 20:
            continue
        Xa, _ = design(D, ia, {"L1": True, "hist": KEY}, None, [an])
        ka = kk[ia].astype(float)
        fa = mnl_fit(np.column_stack([Xa, ka - ka.mean()]), D["y"][ia].astype(int))
        pa[an] = float(fa["B"][-1, 0])
    out["per_animal"] = pa
    return out


# ================================================================== H23
def imu_grid() -> dict[str, np.ndarray]:
    """Per animal, the head-IMU state per field-PC second on the [G0, G1) grid (0 unusable / missing, 1 still, 2 active,
    3 locomoting) from the IMU seconds cache (sec = Unix s, UTC; local = UTC - 4 h)."""
    g0 = int((G0 - pd.Timestamp("1970-01-01")).total_seconds())
    out = {}
    for an in ANIMALS:
        a = np.zeros(SPAN, np.int8)
        for f in sorted((OUT / "imu_seconds_cache" / an).glob("*.csv.gz")):
            d = pd.read_csv(f, usecols=["sec", "ok", "state"])
            i = d.sec.to_numpy(np.int64) - UTC_OFF_S - g0
            m = (i >= 0) & (i < SPAN)
            a[i[m]] = np.where(d.ok.to_numpy(bool)[m], d.state.to_numpy()[m], 0).astype(np.int8)
        out[an] = a
    return out


def wiser_grid() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Per animal, the median default-track position (in) per field-PC second on the grid (NaN where none); fixes flagged
    m_off_animal removed (as Step C)."""
    g0 = int((G0 - pd.Timestamp("1970-01-01")).total_seconds())
    out = {}
    for an in ANIMALS:
        x = np.full(SPAN, np.nan, np.float32)
        y = np.full(SPAN, np.nan, np.float32)
        for f in sorted((OUT / "wiser_default_tracks" / an).glob("*.csv.gz")):
            d = pd.read_csv(f, usecols=["t_ms", "x", "y", "m_off_animal"])
            d = d[d.m_off_animal.fillna(0).astype(int) == 0]
            i = d.t_ms.to_numpy(np.int64) // 1000 - UTC_OFF_S - g0
            m = (i >= 0) & (i < SPAN)
            g = pd.DataFrame({"i": i[m], "x": d.x.to_numpy()[m], "y": d.y.to_numpy()[m]}).groupby("i")[["x", "y"]].median()
            x[g.index.to_numpy()] = g.x.to_numpy()
            y[g.index.to_numpy()] = g.y.to_numpy()
        out[an] = (x, y)
    return out


def wake_kinds(i0: int, i1: int, imu: np.ndarray | None, pos: tuple[np.ndarray, np.ndarray] | None) -> dict:
    """IMU active share and WISER excursion of one wake [i0, i1) (grid seconds)."""
    r = {"imu_ok_share": np.nan, "imu_active_share": np.nan, "wiser_cover": np.nan, "wiser_excursion_in": np.nan, "wiser_net_in": np.nan}
    if imu is not None:
        s = imu[i0:i1]
        ok = s > 0
        r["imu_ok_share"] = float(ok.mean()) if len(s) else np.nan
        r["imu_active_share"] = float(np.isin(s[ok], (2, 3)).mean()) if ok.sum() else np.nan
    if pos is not None:
        x, y = pos
        xs, ys = x[max(i0 - 30, 0):i0], y[max(i0 - 30, 0):i0]
        xw, yw = x[i0:i1], y[i0:i1]
        fin = np.isfinite(xw)
        r["wiser_cover"] = float(fin.mean()) if len(xw) else np.nan
        if np.isfinite(xs).sum() >= 10 and fin.mean() >= 0.5:
            rx, ry = np.nanmedian(xs), np.nanmedian(ys)
            exc = 0.0
            for j in range(0, len(xw), 5):
                bx, by = xw[j:j + 5], yw[j:j + 5]
                if np.isfinite(bx).any():
                    exc = max(exc, float(np.hypot(np.nanmedian(bx) - rx, np.nanmedian(by) - ry)))
            r["wiser_excursion_in"] = exc
            xa, ya = x[i1:i1 + 30], y[i1:i1 + 30]
            if np.isfinite(xa).sum() >= 10:
                r["wiser_net_in"] = float(np.hypot(np.nanmedian(xa) - rx, np.nanmedian(ya) - ry))
    return r


def h23_wakes(S: dict, imu: dict, pos: dict) -> pd.DataFrame:
    st_ = S["steps"]
    pw = st_[(st_.d_prev >= 120) & (st_.d_prev < 420)].drop_duplicates(["record_id", "bout_start"])
    starts = {rc["record_id"]: rc["start"] for rc in S["recs"]}
    rows = []
    for r in pw.itertuples():
        t_w0 = starts[r.record_id] + pd.Timedelta(seconds=int(r.bout_start - r.d_prev))
        i0 = int(np.floor((t_w0 - G0).total_seconds()))
        i1 = i0 + int(r.d_prev)
        rows.append({"record_id": r.record_id, "bout_start": r.bout_start, "animal": r.animal, "d_s": r.d_prev, "t_wake": t_w0,
                     **wake_kinds(i0, i1, imu.get(r.animal), pos.get(r.animal))})
    Wk = pd.DataFrame(rows)
    Wk["dark"] = ~light_flags(Wk.t_wake)
    return Wk


def _h23_fold(k: int, tr_i, te_i, pw: pd.DataFrame, specs: dict) -> tuple[int, pd.Index, dict]:
    from sleep_schedule_phase2 import fit2, pred2
    tr, te = pw.loc[tr_i], pw.loc[te_i]
    te = te[te.animal.isin(tr.animal.unique())]
    if (te.y == 1).sum() == 0 or len(tr) == 0:
        return k, te.index[:0], {}
    lv = sorted(tr.animal.unique())
    LL = {}
    for nm, terms in specs.items():
        m, st = fit2(tr, terms, lv)
        LL[nm] = loglosses(pred2(m, st, te, terms, lv), te.y.to_numpy())["ll"]
    return k, te.index, LL


H23_SPECS = {"R0": ["cur"], "C1": ["cur", "nspl", "wpre", "rem"]}


def h23_run(S: dict, Wk: pd.DataFrame, workers: int) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    from joblib import Parallel, delayed
    from sleep_schedule_phase2 import compare, forward_folds
    st_ = S["steps"]
    pw = st_[st_.d_prev > 0].copy()
    folds = forward_folds(pw)
    res = Parallel(n_jobs=workers, backend="loky")(delayed(_h23_fold)(k, tr, te, pw, H23_SPECS) for k, (tr, te) in enumerate(folds))
    ll = {nm: pd.Series(np.nan, index=pw.index) for nm in H23_SPECS}
    fold_of = pd.Series(-1, index=pw.index)
    for k, ix, LL in res:
        for nm in H23_SPECS:
            if nm in LL:
                ll[nm].loc[ix] = LL[nm]
        fold_of.loc[ix] = k
    pw["ll_R0"], pw["ll_C1"], pw["fold"] = ll["R0"], ll["C1"], fold_of
    te = pw[pw.fold >= 0].copy()
    mid = te[(te.d_prev >= 120) & (te.d_prev < 420)].copy()
    split_thr = float(Wk.loc[Wk.imu_ok_share >= 0.5, "imu_active_share"].median())
    Wk = Wk.copy()
    Wk["kind_imu"] = np.where(Wk.imu_ok_share >= 0.5, np.where(Wk.imu_active_share <= split_thr, "IMU quiet", "IMU active"), "IMU unknown")
    Wk["kind_wiser"] = np.where(Wk.wiser_excursion_in.notna(), np.where(Wk.wiser_excursion_in >= DISP_IN, "WISER moved", "WISER stayed"), "WISER unknown")
    mid = mid.merge(Wk[["record_id", "bout_start", "kind_imu", "kind_wiser"]], on=["record_id", "bout_start"], how="left")
    kinds = {"all 2-7-min wakes": np.ones(len(mid), bool)}
    for c in ("kind_imu", "kind_wiser"):
        for v in sorted(mid[c].dropna().unique()):
            kinds[v] = (mid[c] == v).to_numpy()

    def tables(mask) -> tuple[pd.DataFrame, pd.DataFrame]:
        g = mid[mask]
        F = g.groupby("fold").agg(n=("y", "size"), n_rem=("y", lambda v: int((v == 1).sum())), ll_R0=("ll_R0", "mean"), ll_C1=("ll_C1", "mean")).reset_index()
        FA = g.groupby(["fold", "animal"]).agg(n=("y", "size"), ll_R0=("ll_R0", "mean"), ll_C1=("ll_C1", "mean")).reset_index()
        return F, FA

    rows = []
    Fpw = te.groupby("fold").agg(n=("y", "size"), n_rem=("y", lambda v: int((v == 1).sum())), ll_R0=("ll_R0", "mean"), ll_C1=("ll_C1", "mean")).reset_index()
    FApw = te.groupby(["fold", "animal"]).agg(n=("y", "size"), ll_R0=("ll_R0", "mean"), ll_C1=("ll_C1", "mean")).reset_index()
    r = compare(Fpw, FApw, "R0", "C1", "all post-wake steps (Phase 2 B1 reproduction)")
    r.update(scores=S["label"], kind="all post-wake", wakes=np.nan)
    rows.append(r)
    for kn, m in kinds.items():
        F, FA = tables(m)
        r = compare(F, FA, "R0", "C1", kn)
        r.update(scores=S["label"], kind=kn, wakes=int(mid[m].drop_duplicates(["record_id", "bout_start"]).shape[0]))
        rows.append(r)
    G = pd.DataFrame(rows)
    base = float(mid.ll_R0.mean())
    diffs = []
    for a_, b_ in (("IMU active", "IMU quiet"), ("WISER moved", "WISER stayed")):
        Fa, _ = tables((mid.kind_imu == a_).to_numpy() | (mid.kind_wiser == a_).to_numpy())
        Fb, _ = tables((mid.kind_imu == b_).to_numpy() | (mid.kind_wiser == b_).to_numpy())
        Fd = Fa[["fold", "n"]].rename(columns={"n": "n_a"}).assign(d_a=Fa.ll_C1 - Fa.ll_R0).merge(
            Fb[["fold", "n"]].rename(columns={"n": "n_b"}).assign(d_b=Fb.ll_C1 - Fb.ll_R0), on="fold", how="inner")
        dd = fold_diff_ci(Fd, "d_a", "d_b", base)
        diffs.append({"scores": S["label"], "split": f"{a_} minus {b_}", **dd})
    info = {"imu_split_threshold": split_thr, "steps_2_7": len(mid), "rem_ends_2_7": int((mid.y == 1).sum())}
    return G, pd.DataFrame(diffs), info | {"wakes": Wk}


# ================================================================== figures
def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def fig_coefs(df: pd.DataFrame, path: Path, title: str, xlabel: str, label_col: str = "label") -> None:
    from sleep_quant import save_fig
    plt = _plt()
    labs = list(dict.fromkeys(df[label_col]))
    fig, ax = plt.subplots(figsize=(8, 0.6 * len(labs) + 1.6))
    for j, (sc, off) in enumerate((("FINAL", -0.12), ("pass2med", 0.12))):
        g = df[df.scores == sc]
        for i, lb in enumerate(labs):
            r = g[g[label_col] == lb]
            if not len(r):
                continue
            r = r.iloc[0]
            ax.errorbar(r.coef, i + off, xerr=[[r.coef - r.ci_lo], [r.ci_hi - r.coef]], fmt="o", color=COLORS[sc], capsize=0, lw=2,
                        label=sc if i == 0 else None)
    ax.axvline(0, color=COLORS["ink"], lw=0.8)
    ax.set_yticks(range(len(labs)), labs, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel(xlabel)
    ax.set_title(title, fontsize=9, color=COLORS["ink"])
    ax.legend(fontsize=8, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    save_fig(fig, path)
    plt.close(fig)


def fig_lines(df: pd.DataFrame, xcol: str, ycol: str, path: Path, title: str, xlabel: str, ylabel: str, by="scores") -> None:
    from sleep_quant import save_fig
    plt = _plt()
    scs = list(dict.fromkeys(df[by]))
    fig, axs = plt.subplots(1, len(scs), figsize=(5.5 * len(scs), 4), sharey=True)
    axs = np.atleast_1d(axs)
    for ax, sc in zip(axs, scs):
        g = df[df[by] == sc]
        for ph in ("light", "dark"):
            q = g[g.phase == ph]
            ax.plot(q[xcol].astype(str), q[ycol], "o-", color=COLORS[ph], label=ph)
        ax.set_title(sc, fontsize=9, color=COLORS["ink"])
        ax.set_xlabel(xlabel)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(axis="x", labelsize=7)
    axs[0].set_ylabel(ylabel)
    axs[0].legend(fontsize=8, frameon=False)
    fig.suptitle(title, fontsize=9, color=COLORS["ink"])
    fig.tight_layout()
    save_fig(fig, path)
    plt.close(fig)


# ================================================================== report text
DEFINITIONS = [
    "## Definitions", "",
    r"Time is field-PC local time. States per second $s_t \in \{0\ \text{unknown}, 1\ \text{WAKE}, 3\ \text{NREM}, 5\ \text{REM}\}$. "
    r"Records (sessions of an animal joined across splits ≤ 60 s; FINAL exclusions; cut at 2026-09-11 19:40), the two scorings, "
    r"the day-half blocks (22; block of the record start) and light are those of Steps A–C. **FINAL** = `states_1s_final` "
    r"(per-session thresholds); **pass2med** = `states_1s_pass2med` (fixed per-animal thresholds).",
    "",
    "### Shared",
    r"- **Bout.** A maximal run of one state value $[a, b)$ (s); length $b - a$.",
    r"- **Dark.** $\text{dark}(t) = \neg[\text{sunrise}(t) \le t < \text{sunset}(t)]$, NOAA times at the field site "
    r"(`sleep_quant.sun_times`); never clock hours. **Harmonics** $(\sin, \cos)(2\pi j h/24)$, $j = 1, 2$, $h$ = clock hour.",
    r"- **Counter P** (min; Step B's `P_tw600_k0`, the grid point chosen most often and used in Steps C–E). Along a record's "
    r"bouts: NREM of length $n$: $P \leftarrow P + n/60$; WAKE of length $d$ (any, MAs included): $P \leftarrow P\,e^{-d/600\,\text{s}}$; "
    r"REM: $P \leftarrow 0$ (κ = 0, full discharge); unknown: $P$ frozen; $P = 0$ at the record start. At a 10-s NREM step "
    r"with elapsed $e$ s in its bout: $P_t = P_{\text{bout start}} + e/60$. *P at onset* of a bout = $P$ just before it.",
    r"- **MA.** A WAKE bout with $d < 40$ s whose neighbours are both NREM (Watson 2016). **Brief wake** = any WAKE bout "
    r"$< 40$ s (MAs, and the brief arousals between REM and NREM or before REM).",
    r"- **Post-round exclusion** (plan §3, day/night contrasts). Units whose time (stated per part) lies in $[g_{end}, g_{end} + 3\,\text{h})$ "
    r"of a Phase-0 gap of the same animal with cause `round_logged` / `round_inferred` are dropped. Applied in H7, H8, H10, "
    r"H11, H20 (all contain a phase contrast); H5 uses Step A2's data unchanged (sensitivity with the exclusion); H9 and "
    r"H23 use Step B's / Phase 2's held-out set-up unchanged (no exclusion).",
    r"- **Cluster-robust CI.** Coefficients from OLS / logistic GLMs / multinomial fits with SEs clustered by day-half "
    r"block ($\hat V = H^{-1}(\sum_g U_g U_g^\top)H^{-1}$ with the small-sample factor; statsmodels' cluster option for OLS / "
    r"GLM, `sleep_explore_c.mnl_fit` for multinomials); 95 % CI $= \hat\beta \pm 1.96\,\widehat{se}$. Animal fixed effects "
    r"(intercepts) unless stated. Per-animal estimates refit the model on the animal alone (no fixed effects).",
    r"- **Held-out Δ (H9, H23).** Forward chaining over the day-half blocks (train on all earlier blocks, test the next; the "
    r"first 6 blocks only train); per-step log loss $\ell = -\ln \hat p(y)$; $\Delta = 100\,(\bar\ell_{hi} - \bar\ell_{lo})/\bar\ell_{lo}$ "
    r"(step-weighted over folds); 95 % CI by bootstrap over folds (2000); animals better = per-animal pooled Δ < 0; "
    r"**holds** = CI < 0 and ≥ 5/6 animals (`sleep_schedule_phase2.compare`).",
    r"- **Verdict.** HOLDS = the plan's pass rule is met on both scorings; DOES NOT HOLD = met on neither; INCONCLUSIVE = "
    r"met on one only (or, H7, a predictor is significant somewhere without meeting 'holds'). The verdict is against the "
    r"table's pass rule as written; what a met rule means is stated per hypothesis.",
    "",
    "### H5",
    r"- **Long wake, T, N_pre** — Step A1 / A2 unchanged (`sleep_explore.post_wake_table`): a WAKE bout $[a_w, b_w)$ with "
    r"$d \ge 420$ s followed by NREM; $T$ = NREM + MA seconds from $b_w$ to the first REM onset (event), censored at an unknown "
    r"epoch, the next wake ≥ 7 min or the record end; dark at $b_w$; range dark $7\,\text{min} \le d < 4$ h (A2).",
    r"- **P at onset** $P_{on}$ = the counter at $b_w$ (the post-wake NREM bout start): $P_{\text{before}}\,e^{-d/600}$.",
    r"- **Hours since sunset** $h_{ss} = (b_w - \text{sunset}_{\text{last}})/3600$, the most recent NOAA sunset before $b_w$.",
    r"- **Model (pass rule).** Events only: $\ln T = \alpha_a + \beta_d \ln d + \beta_h h_{ss} + \beta_P \ln(1+P_{on}) + \varepsilon$; "
    r"$\beta_d > 0$ = more NREM needed before REM after longer wakes at the same time of night and the same count. Supporting: "
    r"the censored Cox $h(T) = h_{0,a}(T)\exp(\beta^\top x)$ with the same $x$ (negative = REM later), Step A2's model "
    r"reproduced, $+h_{ss}^2$, $+\ln(1+N_{pre})$ + anchor, and the post-round-excluded subset.",
    "",
    "### H7",
    r"- **Complete REM bout.** A REM bout $[a, b)$ with known states on both sides inside its record; duration $r = b - a$ (s).",
    r"- **Prior wake** $d$ (s): the most recent WAKE bout > 120 s before $a$ (the wake that started the current SLEEP stretch); "
    r"undefined (bout dropped from models with $\ln d$) if an unknown epoch or the record start comes first.",
    r"- **Temperature anomaly** (°C, Phase 4): outdoor temperature minus its 2-harmonic daily fit over the cohort, nearest "
    r"5-min sample within 15 min of $a$ (`sleep_schedule_temp.weather_anomaly` / `join_weather`); missing before 08-31.",
    r"- **Group size** $n_{coloc}$: other tagged animals in the same WISER house at second $a$ (0 if not in a house; Step C's "
    r"per-second zones = ROI + 14 in, re-read from Step C's cache); nuisance dummies field / unknown location (vs house).",
    r"- **Model (pass rule).** $\ln r = \alpha_a + \beta_P \ln(1+P_{on}) + \beta_D\,\text{dark}(a) + \beta_d \ln(1+d) + "
    r"\beta_T\,\text{temp\_anom} + \beta_n n_{coloc} + \gamma_1 \text{field} + \gamma_2 \text{unknown} + \varepsilon$; "
    r"$100(e^{\beta} - 1)$ = % change of the bout duration per unit. Per predictor: **holds** = pooled CI excludes 0 with the "
    r"same sign on both scorings and ≥ 5/6 rats (per-animal fits, ≥ 30 bouts) share that sign on both; **n.s.** = CI includes "
    r"0 on both; else **partial**. Post-round exclusion by $a$.",
    "",
    "### H8",
    r"- **Exit.** For a complete REM bout followed by NREM or WAKE: exitW = 1 if the next bout is WAKE (brief: < 40 s). "
    r"Duration bins (s): " + ", ".join(DUR_LABELS) + r"; phase = dark at $a$.",
    r"- **Mantel–Haenszel odds ratio** over strata $k$ (animal × duration bin): $OR_{MH} = \sum_k (a_k d_k/n_k) / \sum_k (b_k c_k/n_k)$, "
    r"$a$ = dark & WAKE exit, $b$ = dark & NREM exit, $c$ = light & WAKE, $d$ = light & NREM; > 1 = REM ends in WAKE more often "
    r"at night at matched REM duration. CI: 2.5–97.5 % over 1000 block bootstrap resamples. Logistic exitW ~ dark + "
    r"duration-bin dummies + animal (SEs by block) alongside. Per animal: MH over duration bins (≥ 5 bouts per phase), with "
    r"0.5 added to the four cells of a stratum that has both phases and a zero cell (an animal whose dark REM bouts all end in "
    r"WAKE has an infinite raw OR; `MH_OR_raw` is shown uncorrected).",
    r"- **Pass rule as applied:** ≥ 5 of the 6 rats' per-animal $\ln OR_{MH}$ share one sign, on both scorings, the same sign.",
    "",
    "### H9",
    r"- **REM minutes since sunrise** $R_{sr}(t)$ = REM seconds / 60 recorded for the animal in $[\text{sunrise}_{\text{last}}, t)$ "
    r"on its whole timeline (all records; unknown seconds contribute 0); **recorded hours since sunrise** $K_{sr}(t)$ = known "
    r"seconds / 3600 in the same span.",
    r"- **REM minutes since the last long wake** $R_{lw}(t)$ = REM minutes since the end of the last WAKE run ≥ 7 min or "
    r"unknown run ≥ 10 min (a gap) on the timeline; $K_{lw}(t)$ = recorded hours since then.",
    r"- **Models.** Step B's B-full at `P_tw600_k0` (spline $\ln(e+5)$, spline $\ln(1+P_t)$, 2-harmonic clock, day, anchor, "
    r"dark, L1, animal; sklearn multinomial, C = 1e4) + the column(s) (z-scored), forward chaining over all 16 test folds "
    r"(the key is fixed, no nested choice). Pass rule: Δ (B-full + $R$) vs B-full has a CI that includes 0 (or lies above 0) "
    r"for both $R_{sr}$ and $R_{lw}$. Sensitivity: with $K$ in both models. Full-data multinomial coefficients per SD "
    r"(REM vs stay; a negative coefficient = less REM entry after more REM, the direction a quota predicts).",
    "",
    "### H10",
    r"- **REM ends.** A REM bout ending at $e$ followed by NREM or a WAKE bout < 40 s, with $[e, e + 135]$ known and inside "
    r"the record; phase = dark at $e$; post-round exclusion by $e$.",
    r"- **Second REM** $Y = 1$ if a REM onset falls in $(e, e + 135]$ s. **Interval** $[e, w)$, $w$ = that onset if $Y = 1$, "
    r"else $e + 135$. **Brief-wake count** $n_{bw}$ = WAKE bouts < 40 s starting in $[e, w)$ (incl. an arousal right "
    r"after the REM); $n_{MA}$ = those flanked by NREM (Watson MAs); $n_{W40}$ = WAKE bouts ≥ 40 s starting in $[e, w)$.",
    r"- **Models.** Logistic $\Pr(Y=1) = \text{logit}^{-1}(\alpha_a + \beta\,\text{dark} [+ \gamma n_{bw}])$, SEs by block. "
    r"Pass rule as applied: the dark coefficient with $n_{bw}$ in the model has a CI excluding 0 with the same sign as "
    r"without it, on both scorings. Landmark sensitivity (fixed exposure): among REM ends without a REM onset in "
    r"$(e, e + 45]$, $Y$ = onset in $(e + 45, e + 135]$ ~ dark + 1[a brief wake starts in $[e, e + 45)$].",
    "",
    "### H11",
    r"- **MA step outcome.** Per 10-s NREM step (Step B's steps): $y_{MA} = 1$ if the NREM bout ends in this step with an "
    r"MA (WAKE < 40 s followed by NREM). Reference outcome $y_{pre}$: ends in a brief wake < 40 s followed by REM.",
    r"- **Model (pass rule).** Per phase (dark at the step): logistic $\Pr(y_{MA}=1) = \text{logit}^{-1}(\alpha_a + \beta \ln(1+P_t))$, "
    r"SEs by block; $\beta > 0$ = more MAs per NREM minute at a higher count. Pass: $\beta$ CI > 0 and ≥ 5/6 per-animal "
    r"slopes > 0, in each phase, on both scorings. Sensitivity: + spline of elapsed time in the bout + day + 2-harmonic clock. "
    r"Description: MAs per NREM minute $= \#\text{MA} / (\#\text{steps} \times 10/60)$ per $P$ bin (min: " + ", ".join(P_LABELS) + "), "
    r"mean of animals (cells ≥ 30 steps). Post-round exclusion by the step time.",
    "",
    "### H20",
    r"- **SLEEP episode** (Watson 2016, `episodes_of`): split at WAKE > 120 s and unknown epochs, trimmed to sleep, ≥ 20 min; "
    r"episodes starting in a post-round 3 h are dropped. REM bouts $R_1..R_m$ in order.",
    r"- **k-th interval** ($k = 1..m-1$): from the end of $R_k$ to the onset of $R_{k+1}$; $I_k$ = NREM seconds in it (the "
    r"count's units; under `P_tw600_k0` the count is 0 at every interval start, so every interval starts at the same P). "
    r"The last interval (after $R_m$, to the episode end) is censored. Phase = dark at the end of $R_k$.",
    r"- **Model (pass rule).** Completed intervals with $I_k > 0$: $\ln I_k = \alpha_a + \beta_k k + \beta_D\,\text{dark} + \varepsilon$, "
    r"SEs by block; $\beta_k < 0$ = shorter in later cycles. Pass: $\beta_k$ CI < 0 and ≥ 5/6 per-animal slopes < 0 (animals with "
    r"≥ 15 intervals), both scorings. Supporting: episode fixed effects; + $\ln r_k$ + clock; wall-clock interval; episodes "
    r"with ≥ 4 REM bouts; Cox on $I_k$ censored at the episode end; and the step model: B-full + $k$ (number of REM onsets "
    r"since the episode start) on NREM steps after the episode's first REM — the REM-vs-stay coefficient of $k$ at the same "
    r"$P_t$ and clock (+ = REM entry more likely in later cycles).",
    "",
    "### H23",
    r"- **Post-wake steps and the carry-over gain** (Phase 2 B1 unchanged): NREM steps whose bout follows a WAKE bout "
    r"($d > 0$). R0 = elapsed spline + 2-harmonic clock + day + [ln(1+d), fW10] + animal; C1 = R0 + spline $\ln(1+N_{since})$ "
    r"+ $\ln(1 + W_{pre})$ + [ln REM_pre, anchor] (pre-wake history). Fitted per fold on ALL post-wake steps (forward "
    r"chaining); the gain = Δ C1 vs R0 evaluated on the test steps after 2–7-min wakes ($120 \le d < 420$ s), per kind.",
    r"- **IMU active share** of a wake $[a_w, b_w)$: share of IMU-ok seconds in state active / locomoting (IMU seconds cache, "
    r"field-PC second = UTC − 4 h); known if ≥ 50 % of the wake's seconds are IMU-ok. **IMU quiet / active** = share ≤ / > "
    r"its median over the 2–7-min wakes of the scoring (outcome-blind split).",
    r"- **WISER excursion** (in): reference = median default-track position over the 30 s before the wake (≥ 10 s with "
    r"positions); excursion = max over 5-s blocks in the wake of the distance of the block median from the reference; known if "
    r"≥ 50 % of the wake's seconds have a position. **WISER moved / stayed** = excursion ≥ / < 14 in (the minimum resolvable "
    r"distance). Net displacement (30 s after vs before) reported.",
    r"- **Gain difference.** Per fold, $g_{kind} = \overline{\ell_{C1} - \ell_{R0}}$ over the kind's steps (nats); "
    r"difference $g_{active} - g_{quiet}$ (and moved − stayed), step-weighted over folds with both kinds, in % of the mean "
    r"R0 loss of the 2–7-min steps; 95 % CI by bootstrap over folds. Negative = pre-wake history helps more after the "
    r"active / moved kind. Pass rule as applied: the CI excludes 0 for a split, on both scorings (two splits are tested; "
    r"multiplicity is stated).",
    "",
]


# ================================================================== the parts (each: report lines, verdict row, CSVs)
def part_h5(ctx, rd, save):
    rows, pa_all, lines_v, met, rd_parts = [], [], [], [], []
    for sk, S in ctx["S"].items():
        tab = h5_table(S["recs"])
        M, PA, info = h5_fit(tab, ctx["gaps"])
        M.insert(0, "scores", S["label"])
        PA.insert(0, "scores", S["label"])
        rows.append(M)
        pa_all.append(PA)
        m = M[(M.model == H5_MAIN) & (M.term == "l_d") & M.method.str.startswith("OLS") & M.subset.str.contains(r"\(A2")].iloc[0]
        h = M[(M.model == H5_MAIN) & (M.term == "hss") & M.method.str.startswith("OLS") & M.subset.str.contains(r"\(A2")].iloc[0]
        r0 = M[M.model.str.startswith("A2 repro") & (M.term == "l_d") & M.subset.str.contains(r"\(A2")].iloc[0]
        cx = M[(M.term == "l_d") & M.method.str.startswith("Cox") & M.subset.str.contains(r"\(A2")].iloc[0]
        ok = bool(m.ci_lo > 0)
        met.append(ok)
        npos = int((PA.ln_d > 0).sum())
        inf = info["dark, 7 min-4 h (A2 range)"]
        mpr = M[(M.model == H5_MAIN) & (M.term == "l_d") & M.method.str.startswith("OLS") & M.subset.str.contains("post-round")]
        mnp = M[(M.model == "ln d + ln(1+P) (no time of night)") & (M.term == "l_d") & M.subset.str.contains(r"\(A2")].iloc[0]
        rd_parts.append(f"{S['label']}: ln d {ci_txt(m.coef, m.ci_lo, m.ci_hi, 2)} with time of night and P (A2 alone "
                        f"{ci_txt(r0.coef, r0.ci_lo, r0.ci_hi, 2)}; with P but no time of night {ci_txt(mnp.coef, mnp.ci_lo, mnp.ci_hi, 2)}; "
                        f"post-round sleeps excluded {ci_txt(mpr.coef.iloc[0], mpr.ci_lo.iloc[0], mpr.ci_hi.iloc[0], 2) if len(mpr) else 'n/a'}); "
                        f"hours since sunset {ci_txt(h.coef, h.ci_lo, h.ci_hi, 3)} per h")
        lines_v.append(f"- **{S['label']}:** ln d {m.coef:+.3f} [{m.ci_lo:+.3f}, {m.ci_hi:+.3f}] with hours since sunset "
                       f"{h.coef:+.3f} [{h.ci_lo:+.3f}, {h.ci_hi:+.3f}] per h and ln(1+P) in the model (n {int(m.n)} events of "
                       f"{inf['sleeps']} sleeps; r(ln d, h_ss) = {inf['r_lnd_hss']:+.2f}); Step A2's slope reproduced "
                       f"{r0.coef:+.3f} [{r0.ci_lo:+.3f}, {r0.ci_hi:+.3f}]; {npos}/{len(PA)} rats with ln d > 0; censored Cox ln d "
                       f"{cx.coef:+.3f} [{cx.ci_lo:+.3f}, {cx.ci_hi:+.3f}] (negative = REM later) → rule "
                       f"{'met' if ok else 'NOT met'}.")
    M, PA = pd.concat(rows, ignore_index=True), pd.concat(pa_all, ignore_index=True)
    save(M, "h5_models")
    save(PA, "h5_per_animal")
    v = verdict_of(met)
    F = M[(M.term == "l_d") & M.method.str.startswith("OLS") & M.subset.str.contains(r"\(A2")].rename(columns={"model": "label"})
    fig_coefs(F, ctx["fd"] / "ephys_spikes_sleep_explore_F1_h5_2026c.png",
              f"H5: ln d slope on ln(NREM before the first REM), dark 7 min-4 h, events (OLS, SEs by block)  {ctx['gc']}",
              "ln d coefficient (+ = more NREM before REM after longer wakes)")
    L = ["## H5 — the night ramp: time of night or wake length?", "",
         "**Hypothesis (plan):** \"The night ramp (#6b) is time of night, not wake length.\" **Test:** \"within dark: latency ~ ln d + "
         "hours since sunset, P at onset.\" **Pass rule (quoted):** \"ln d stays with CI > 0\". A met rule means the wake length keeps "
         "its own association at the same time of night and the same count (i.e. the ramp is not explained by time of night alone); "
         "a rule not met means ln d no longer carries the ramp once time of night is in.", "",
         *_tbl(M.drop(columns=["se"]), 3), "", "Per animal (OLS of the H5 model, ≥ 10 events):", "", *_tbl(PA, 3), "",
         "![](../figures/ephys_spikes_sleep_explore_F1_h5_2026c.png)", "", *lines_v, "",
         f"**H5 verdict: {v}** (pass rule {'met' if v == 'HOLDS' else 'not met on every scoring'}).", ""]
    labs = [S["label"] for S in ctx["S"].values()]
    yes = [lb for lb, m_ in zip(labs, met) if m_]
    head = ("ln d keeps CI > 0 at the same hours since sunset and P on every scoring (wake length is not replaced by time of night)"
            if v == "HOLDS" else (f"ln d keeps CI > 0 at the same hours since sunset and P on {', '.join(yes)} only" if yes
                                  else "ln d loses its CI > 0 once hours since sunset and P are in, on every scoring"))
    reading = head + ". " + "; ".join(rd_parts) + "."
    L[-1:-1] = ["", f"Reading: {reading}"]
    key = " | ".join(x.split(":** ", 1)[1].split(";")[0] for x in lines_v)
    return L, {"H": "H5", "hypothesis": "night ramp is time of night, not wake length", "pass_rule": "ln d stays with CI > 0",
               **key_lines(ctx, lines_v, 200), **met_by(ctx, met),
               "met": ", ".join(f"{S['label']} {'yes' if m_ else 'no'}" for S, m_ in zip(ctx["S"].values(), met)), "verdict": v,
               "reading": head, "key": key}


def _tbl(df: pd.DataFrame, nd: int = 3) -> list[str]:
    from sleep_explore import tbl
    return tbl(df, nd)


def part_h7(ctx, rd, save):
    co, pa, infos, alls = {}, {}, {}, []
    for sk, S in ctx["S"].items():
        T = h7_table(S["recs"], ctx["gaps"], ctx["weather"], ctx["zone"], ctx["mates"][sk])
        C, PA, info = h7_fit(T)
        C.insert(0, "scores", S["label"])
        PA.insert(0, "scores", S["label"])
        co[S["label"]], pa[S["label"]], infos[S["label"]] = C, PA, info
        alls.append(T.assign(scores=S["label"]))
        T.to_csv(ctx["out"] / f"h7_rem_bouts_{sk}.csv.gz", index=False)
    C = pd.concat(co.values(), ignore_index=True)
    PA = pd.concat(pa.values(), ignore_index=True)
    ST = h7_status(co, pa)
    save(C, "h7_coef")
    save(PA, "h7_per_animal")
    save(ST, "h7_status")
    holds = ST[ST.status == "holds"]
    if (ST.status == "n.s.").all():
        v, reading = "HOLDS", "scoped negative: none of the five predictors is associated with REM bout duration"
    elif len(holds):
        v, reading = "HOLDS", "named predictor(s): " + ", ".join(holds.label)
    else:
        v, reading = "INCONCLUSIVE", "a predictor is significant somewhere without meeting 'holds'"
    desc = []
    for lab, T in zip(co, alls):
        u = T[~T.post_round]
        desc.append({"scores": lab, "complete_rem_bouts": len(T), "post_round_dropped": int(T.post_round.sum()),
                     "median_dur_s_light": float(u[~u.dark].dur_s.median()), "median_dur_s_dark": float(u[u.dark].dur_s.median()),
                     "prior_wake_known_share": float(u.d_prior.notna().mean()), "temp_known_share": float(u.temp_anom.notna().mean()),
                     "entered_from_wake_share": float(u.from_wake.mean()), "in_house_share": float((u.zone.isin([1, 2])).mean())})
    DS = pd.DataFrame(desc)
    save(DS, "h7_descriptives")
    F = C[C.model.str.startswith("H7 (plan)")]
    fig_coefs(F, ctx["fd"] / "ephys_spikes_sleep_explore_F1_h7_2026c.png",
              f"H7: ln REM bout duration, pooled OLS coefficients (animal FE, SEs by block)  {ctx['gc']}", "coefficient on ln(duration)")
    L = ["## H7 — is REM bout duration related to the count, phase, prior wake, temperature or group size?", "",
         "**Hypothesis (plan):** \"REM bout duration is unregulated (the planned C3 never run).\" **Test:** \"ln REM duration ~ P at "
         "onset + dark + ln d + temperature + group size.\" **Pass rule (quoted):** \"all n.s. (scoped negative) or a named predictor "
         "holds\".", "",
         "Bouts:", "", *_tbl(DS, 3), "", "Bouts per model: " + "; ".join(f"{lab}: " + ", ".join(f"{k} {v_}" for k, v_ in inf["bouts_used"].items())
                                                                         for lab, inf in infos.items()), "",
         "Pooled coefficients (OLS on ln duration; % per unit = 100(e^β − 1)):", "", *_tbl(C.drop(columns=["se"]), 4), "",
         "Per animal (≥ 30 bouts; the plan model):", "", *_tbl(PA, 3), "",
         "Status per predictor (holds / n.s. / partial, both scorings):", "", *_tbl(ST, 3), "",
         "![](../figures/ephys_spikes_sleep_explore_F1_h7_2026c.png)", "",
         "Caveat: the scorer requires REM ≥ 7 s and turns REM with ≥ 3 of 5 s of head movement into WAKE (`imu_remclean`, both "
         "scorings), so a REM bout's end can be set by head movement; group size is WISER same-house (ROI + 14 in), not contact.", "",
         f"**H7 verdict: {v}** — {reading}.", ""]
    sig = {}
    for lab, C_ in co.items():
        c_ = C_[C_.model.str.startswith("H7 (plan)")]
        sig[lab] = [r.term for r in c_.itertuples() if r.ci_lo > 0 or r.ci_hi < 0]
    det = []
    for r in ST.itertuples():
        if r.status == "holds":
            det.append(f"{r.label}: holds, " + ", ".join(f"{lab} {getattr(r, lab + '_pct_per_unit'):+.1f} % per unit "
                                                       f"({getattr(r, lab + '_rats_same_sign')} rats)" for lab in co))
        elif r.status == "partial":
            det.append(f"{r.label}: partial (CI excludes 0 on {', '.join(l_ for l_ in co if r.term in sig[l_]) or 'neither scoring'}"
                       + "; " + ", ".join(f"{lab} {getattr(r, lab + '_coef'):+.3f} {getattr(r, lab + '_ci')}" for lab in co) + ")")
        else:
            det.append(f"{r.label}: n.s.")
    pr = C[C.model.str.startswith("POST HOC") & (C.term == "l_P")]
    if len(pr):
        det.append("post hoc, bouts with P at onset >= 1 min: ln(1+P) " + ", ".join(f"{r.scores} {ci_txt(r.coef, r.ci_lo, r.ci_hi, 3)}" for r in pr.itertuples()))
    L[-1:-1] = ["", "Reading: " + "; ".join(det) + "."]
    return L, {"H": "H7", "hypothesis": "REM bout duration is unregulated", "pass_rule": "all n.s. (scoped negative) or a named predictor holds",
               "FINAL rule met": "CI excludes 0: " + (", ".join(sig.get("FINAL", [])) or "none"),
               "pass2med rule met": "CI excludes 0: " + (", ".join(sig.get("pass2med", [])) or "none"),
               "FINAL": "; ".join(f"{r.term} {r.FINAL_coef:+.3f} {r.FINAL_ci}" for r in ST.itertuples()) if "FINAL_coef" in ST else "",
               "pass2med": "; ".join(f"{r.term} {r.pass2med_coef:+.3f} {r.pass2med_ci}" for r in ST.itertuples()) if "pass2med_coef" in ST else "",
               "met": ", ".join(f"{r.term}: {r.status}" for r in ST.itertuples()), "verdict": v, "reading": reading,
               "key": "; ".join(f"{r.term} {r.status}" for r in ST.itertuples())}


def part_h8(ctx, rd, save):
    M_all, B_all, P_all, met, signs, lines, rd8 = [], [], [], [], [], [], []
    rng = np.random.default_rng(8)
    for sk, S in ctx["S"].items():
        T = h8_table(S["recs"], ctx["gaps"])
        M, B, PA, info = h8_fit(T, rng)
        for df in (M, B, PA):
            df.insert(0, "scores", S["label"])
        M_all.append(M)
        B_all.append(B)
        P_all.append(PA)
        ok = max(info["n_pos"], info["n_neg"]) >= 5
        met.append(ok)
        signs.append(np.sign(info["n_pos"] - info["n_neg"]))
        mh = M.iloc[0]
        lg = M.iloc[1]
        u_ = T[~T.post_round]
        inf_raw = PA[PA.MH_OR_raw.isna() & PA.ln_OR.notna()]
        rd8.append(f"{S['label']}: WAKE exits light {u_[~u_.dark].exitW.mean():.2f} vs dark {u_[u_.dark].exitW.mean():.2f}, pooled MH OR "
                   f"{np.exp(mh.coef):.2f} [{np.exp(mh.ci_lo):.2f}, {np.exp(mh.ci_hi):.2f}]"
                   + (" (CI includes 1)" if mh.ci_lo <= 0 <= mh.ci_hi else "")
                   + f", rats > 1: {info['n_pos']}/{info['qualifying']}"
                   + (f" (incl. {', '.join(inf_raw.animal)}: every dark REM bout ended in WAKE, infinite raw OR, counted through the "
                      f"continuity correction)" if len(inf_raw) else ""))
        lines.append(f"- **{S['label']}:** per-animal MH ln OR > 0 (more WAKE exits at night) in {info['n_pos']}/{info['qualifying']}, "
                     f"< 0 in {info['n_neg']}/{info['qualifying']}; pooled MH OR {np.exp(mh.coef):.2f} [{np.exp(mh.ci_lo):.2f}, "
                     f"{np.exp(mh.ci_hi):.2f}], logistic OR {np.exp(lg.coef):.2f} [{np.exp(lg.ci_lo):.2f}, {np.exp(lg.ci_hi):.2f}] "
                     f"({int(mh.n_bouts)} bouts) → rule {'met' if ok else 'NOT met'}.")
    M, B, PA = (pd.concat(x, ignore_index=True) for x in (M_all, B_all, P_all))
    save(M, "h8_models")
    save(B, "h8_bins")
    save(PA, "h8_per_animal")
    v = verdict_of(met)
    if v == "HOLDS" and len(set(signs)) > 1:
        v = "INCONCLUSIVE"
    fig_lines(B.assign(x=B.dur_bin.astype(str)), "x", "share_wake", ctx["fd"] / "ephys_spikes_sleep_explore_F1_h8_2026c.png",
              f"H8: share of REM bouts ending in WAKE, by REM bout duration and phase  {ctx['gc']}", "REM bout duration", "share ending in WAKE")
    direction = "more WAKE exits at night" if signs and signs[0] > 0 else "fewer WAKE exits at night"
    L = ["## H8 — do REM exits differ by phase at matched REM duration?", "",
         "**Hypothesis (plan):** \"REM exits differ by phase.\" **Test:** \"share of REM bouts ending in WAKE vs NREM, night vs day, "
         "matched duration.\" **Pass rule (quoted):** \"≥ 5/6 same sign\".", "",
         *_tbl(M.drop(columns=["se"]), 3), "", "Share ending in WAKE by duration bin and phase:", "", *_tbl(B, 3), "",
         "Per animal (MH over duration bins):", "", *_tbl(PA, 3), "", "![](../figures/ephys_spikes_sleep_explore_F1_h8_2026c.png)", "",
         *lines, "", "Caveat: an exit to WAKE can be produced by the scorer's REM-clean rule (≥ 3 of 5 s of head movement → WAKE).", "",
         f"**H8 verdict: {v}**" + (f" ({direction})." if v == "HOLDS" else "."), ""]
    head = (f"at matched REM duration, REM bouts end in WAKE more often at night in >= 5/6 rats on every scoring" if v == "HOLDS" and signs[0] > 0
            else (f"at matched REM duration, REM bouts end in WAKE less often at night in >= 5/6 rats on every scoring" if v == "HOLDS"
                  else ("the same-sign rule is met on " + ", ".join(S["label"] for S, m_ in zip(ctx["S"].values(), met) if m_) + " only"
                        if any(met) else "the same-sign rule is met on no scoring")))
    L[-1:-1] = ["", "Reading: " + head + "; " + "; ".join(rd8) + "."]
    return L, {"H": "H8", "hypothesis": "REM exits differ by phase", "pass_rule": "≥ 5/6 same sign",
               **key_lines(ctx, lines, 170), **met_by(ctx, met),
               "met": ", ".join(f"{S['label']} {'yes' if m_ else 'no'}" for S, m_ in zip(ctx["S"].values(), met)), "verdict": v,
               "reading": head, "key": " | ".join(l_.split(":** ", 1)[1].split(";")[0] for l_ in lines)}


def part_h9(ctx, rd, save):
    T_all, C_all, met, lines, desc = [], [], [], [], {}
    for sk, S in ctx["S"].items():
        t0 = time.time()
        T, C = h9_run(S, ctx["workers"])
        desc[S["label"]] = C.attrs.get("desc", {})
        T_all.append(T)
        C_all.append(C)
        main = T[T.subset.str.contains("pass rule")]
        ok = bool((main.ci_hi_pct >= 0).all())
        met.append(ok)
        lines.append(f"- **{S['label']}:** " + "; ".join(f"{r.subset.split(' (')[0]} Δ {r.delta_pct:+.3f} % [{r.ci_lo_pct:+.3f}, {r.ci_hi_pct:+.3f}], "
                                                         f"{r.folds_better}/{r.folds} folds, {r.animals_better}/{r.animals} rats" for r in main.itertuples())
                     + f" → rule {'met' if ok else 'NOT met'} ({time.time() - t0:.0f} s).")
        print(lines[-1], flush=True)
    T, C = pd.concat(T_all, ignore_index=True), pd.concat(C_all, ignore_index=True)
    cols = ["scores", "subset", "comparison", "n_steps", "n_rem", "delta_pct", "ci_lo_pct", "ci_hi_pct", "folds_better", "folds", "animals_better", "animals", "holds"]
    T = T[[c for c in cols if c in T]]
    save(T, "h9_heldout")
    save(C, "h9_coef")
    v = verdict_of(met)
    fig_coefs(T.rename(columns={"delta_pct": "coef", "ci_lo_pct": "ci_lo", "ci_hi_pct": "ci_hi", "subset": "label"}),
              ctx["fd"] / "ephys_spikes_sleep_explore_F1_h9_2026c.png",
              f"H9: held-out log-loss change when REM obtained since sunrise / since the last long wake is added to B-full  {ctx['gc']}",
              "Δ held-out log-loss (%), negative = better")
    dl = [f"{lab}: " + ", ".join(f"{k} median {a:.1f} (90 % {b:.1f})" for k, (a, b) in d.items()) for lab, d in desc.items()]
    L = ["## H9 — a daily REM quota?", "",
         "**Hypothesis (plan):** \"There is no daily REM quota.\" **Test:** \"add 'REM minutes since sunrise' (and since the last long "
         "wake) to step B.\" **Pass rule (quoted):** \"adds nothing (CI includes 0)\". Applied to both terms, on both scorings; a CI "
         "entirely above 0 (worse) also counts as adding nothing.", "",
         "Distribution over NREM steps (min / h): " + " | ".join(dl), "",
         *_tbl(T, 3), "", "Full-data multinomial coefficients (per SD of the added column; cluster-robust CI by block):", "",
         *_tbl(C.drop(columns=["se"]), 4), "", "![](../figures/ephys_spikes_sleep_explore_F1_h9_2026c.png)", "", *lines, "",
         f"**H9 verdict: {v}**" + (" — REM obtained since sunrise or since the last long wake adds nothing to the count model held out."
                                   if v == "HOLDS" else "."), ""]
    cr = C[(C.equation == "REM vs stay") & C.model.isin(["B+rem_sr", "B+rem_lw"])]
    gain = T[T.subset.str.contains("pass rule") & (T.ci_hi_pct < 0)]
    head = ("neither term improves held-out prediction on either scoring" if v == "HOLDS" else
            "improves held-out prediction: " + "; ".join(f"{r.scores} {r.subset.split(' (')[0]} {ci_txt(r.delta_pct, r.ci_lo_pct, r.ci_hi_pct, 3)} %"
                                                         for r in gain.itertuples()))
    L[-1:-1] = ["", "Reading: " + head + "; full-data REM-vs-stay coefficients per SD (negative = the direction a quota predicts): "
                + "; ".join(f"{r.scores} {r.term} {ci_txt(r.coef, r.ci_lo, r.ci_hi, 3)}" for r in cr.itertuples()) + "."]
    return L, {"H": "H9", "hypothesis": "no daily REM quota", "pass_rule": "adds nothing (CI includes 0)",
               **key_lines(ctx, lines, 200), **met_by(ctx, met),
               "met": ", ".join(f"{S['label']} {'yes' if m_ else 'no'}" for S, m_ in zip(ctx["S"].values(), met)), "verdict": v,
               "reading": head,
               "key": " | ".join(l_.split(":** ", 1)[1].split(" → ")[0] for l_ in lines)}


def part_h10(ctx, rd, save):
    M_all, R_all, P_all, met, lines, rd10 = [], [], [], [], [], []
    for sk, S in ctx["S"].items():
        T = h10_table(S["recs"], ctx["gaps"])
        M, Rt, PA = h10_fit(T)
        for df in (M, Rt, PA):
            df.insert(0, "scores", S["label"])
        M_all.append(M)
        R_all.append(Rt)
        P_all.append(PA)
        m0 = M[(M.model.str.startswith("M0")) & (M.term == "darkf")].iloc[0]
        m1 = M[(M.model.str.startswith("M1 (pass")) & (M.term == "darkf")].iloc[0]
        nb = M[(M.model.str.startswith("M1 (pass")) & (M.term == "n_brief")].iloc[0]
        ok = bool((m1.ci_lo > 0 or m1.ci_hi < 0) and np.sign(m1.coef) == np.sign(m0.coef))
        met.append(ok)
        lm = M[(M.model.str.startswith("L1 landmark")) & (M.term == "darkf")].iloc[0]
        rd10.append(f"{S['label']}: dark {ci_txt(m0.coef, m0.ci_lo, m0.ci_hi, 2)} → {ci_txt(m1.coef, m1.ci_lo, m1.ci_hi, 2)} with the count "
                    f"(landmark {ci_txt(lm.coef, lm.ci_lo, lm.ci_hi, 2)})")
        u = T[~T.post_round]
        lines.append(f"- **{S['label']}:** second REM within 135 s: light {u[~u.dark].y.mean():.3f} vs dark {u[u.dark].y.mean():.3f} "
                     f"({len(u)} REM ends, {int(u.dark.sum())} dark); brief wakes per interval light {u[~u.dark].n_brief.mean():.2f} vs dark "
                     f"{u[u.dark].n_brief.mean():.2f}; dark log-odds {m0.coef:+.3f} [{m0.ci_lo:+.3f}, {m0.ci_hi:+.3f}] → with the "
                     f"brief-wake count {m1.coef:+.3f} [{m1.ci_lo:+.3f}, {m1.ci_hi:+.3f}] (count {nb.coef:+.3f} per wake); "
                     f"per-animal dark < 0 with the count: {int((PA.dark_M1 < 0).sum())}/{int(PA.dark_M1.notna().sum())} → rule "
                     f"{'met' if ok else 'NOT met'}.")
    M, Rt, PA = (pd.concat(x, ignore_index=True) for x in (M_all, R_all, P_all))
    save(M, "h10_models")
    save(Rt, "h10_rates")
    save(PA, "h10_per_animal")
    v = verdict_of(met)
    fig_lines(Rt.rename(columns={"brief_wakes_in_interval (3 = 3+)": "nb"}), "nb", "p_second_rem", ctx["fd"] / "ephys_spikes_sleep_explore_F1_h10_2026c.png",
              f"H10: P(second REM within 135 s of a REM end) by brief wakes in the interval and phase  {ctx['gc']}",
              "brief wakes (< 40 s) in the interval (3 = 3+)", "P(second REM within 135 s)")
    L = ["## H10 — are sequential REMs rarer at night beyond the interruptions?", "",
         "**Hypothesis (plan):** \"Sequential cycles are rarer at night through the gain, not through interruptions.\" **Test:** "
         "\"second REM within 135 s vs MA count in the interval, by phase.\" **Pass rule (quoted):** \"phase effect survives the MA "
         "count\".", "", *_tbl(M.drop(columns=["se"]), 3), "", "Rates by phase and brief-wake count:", "", *_tbl(Rt, 3), "",
         "Per animal (logistic, no FE):", "", *_tbl(PA, 3), "", "![](../figures/ephys_spikes_sleep_explore_F1_h10_2026c.png)", "",
         *lines, "", "Caveat: the scorer does not allow REM after a wake > 10 s, so a brief wake of 11–39 s forces NREM before the "
         "next REM; the count's coefficient is partly built in. The count is measured over an interval that ends at the second REM, "
         "so longer exposure accompanies Y = 0 (the landmark rows fix the exposure).", "",
         f"**H10 verdict: {v}**" + (" — the night's lower rate of a second REM within 135 s remains with the brief-wake count in the model." if v == "HOLDS" else "."), ""]
    head = ("a second REM within 135 s is less likely at night also at the same number of brief wakes in the interval" if v == "HOLDS"
            else "the phase effect does not keep its CI with the brief-wake count on every scoring")
    L[-1:-1] = ["", "Reading: " + head + " (log-odds; " + "; ".join(rd10) + ")."]
    return L, {"H": "H10", "hypothesis": "sequential REMs rarer at night beyond interruptions", "pass_rule": "phase effect survives the MA count",
               **key_lines(ctx, lines, 200), **met_by(ctx, met),
               "met": ", ".join(f"{S['label']} {'yes' if m_ else 'no'}" for S, m_ in zip(ctx["S"].values(), met)), "verdict": v,
               "reading": head,
               "key": " | ".join(l_.split(":** ", 1)[1].split("; per-animal")[0][-90:] for l_ in lines)}


def part_h11(ctx, rd, save):
    M_all, R_all, P_all, lines = [], [], [], []
    metp = {"light": [], "dark": []}
    for sk, S in ctx["S"].items():
        df = h11_arrays(S)
        M, Rt, PA = h11_fit(df)
        for x in (M, Rt, PA):
            x.insert(0, "scores", S["label"])
        M_all.append(M)
        R_all.append(Rt)
        P_all.append(PA)
        parts = []
        for ph in ("light", "dark"):
            r = M[(M.phase == ph) & M.outcome.str.startswith("MA") & M.model.str.contains("pass rule")].iloc[0]
            pp = PA[PA.phase == ph]
            npos = int((pp.slope_l_P > 0).sum())
            ok = bool(r.ci_lo > 0 and npos >= 5)
            metp[ph].append(ok)
            parts.append(f"{ph} slope {r.coef:+.3f} [{r.ci_lo:+.3f}, {r.ci_hi:+.3f}] per ln(1+P), {npos}/{pp.slope_l_P.notna().sum()} rats > 0 "
                         f"({int(r.events)} MAs) → {'met' if ok else 'not met'}")
        lines.append(f"- **{S['label']}:** " + "; ".join(parts) + ".")
    M, Rt, PA = (pd.concat(x, ignore_index=True) for x in (M_all, R_all, P_all))
    save(M, "h11_models")
    save(Rt, "h11_rates")
    save(PA, "h11_per_animal")
    both = {ph: all(v_) for ph, v_ in metp.items()}
    if all(both.values()):
        v = "HOLDS"
    elif any(both.values()):
        v = f"HOLDS ({[ph for ph, b in both.items() if b][0]} only)"
    elif any(any(v_) for v_ in metp.values()):
        v = "INCONCLUSIVE"
    else:
        v = "DOES NOT HOLD"
    fig_lines(Rt.assign(x=Rt.P_bin.astype(str)), "x", "ma_per_nrem_min", ctx["fd"] / "ephys_spikes_sleep_explore_F1_h11_2026c.png",
              f"H11: MAs per NREM minute by the count P (min) and phase (mean of animals)  {ctx['gc']}", "P at the step (min)", "MAs per NREM minute")
    L = ["## H11 — does the MA rate rise with the count P?", "",
         "**Hypothesis (plan):** \"MA rate rises with P (pre-REM fragility).\" **Test:** \"MAs per NREM min ~ P, by phase.\" **Pass rule "
         "(quoted):** \"slope > 0, ≥ 5/6\" — applied per phase: pooled slope CI > 0 and ≥ 5/6 per-animal slopes > 0, on both scorings.", "",
         *_tbl(M.drop(columns=["se"]), 4), "", "MAs per NREM minute by P bin:", "", *_tbl(Rt, 4), "", "Per animal:", "", *_tbl(PA, 4), "",
         "![](../figures/ephys_spikes_sleep_explore_F1_h11_2026c.png)", "", *lines, "",
         "Note: P grows with the elapsed time inside a bout; the sensitivity row adds a spline of the elapsed time, day and the clock. "
         "Brief wakes followed by REM are not MAs (Watson) and are shown as a reference outcome.", "", f"**H11 verdict: {v}.**", ""]
    mm = M[M.outcome.str.startswith("MA")]
    main_ = mm[mm.model.str.contains("pass rule")]
    sens_ = mm[~mm.model.str.contains("pass rule")]
    if (main_.ci_hi < 0).all():
        head = "the MA rate per NREM minute falls with P in both phases on both scorings (highest at a low count)"
        head += (", also with elapsed time in the bout, day and clock in the model" if (sens_.ci_hi < 0).all()
                 else "; with elapsed time, day and clock in the model the decline is " + ", ".join(
                     f"{r.scores} {r.phase} {ci_txt(r.coef, r.ci_lo, r.ci_hi, 3)}" for r in sens_.itertuples()))
    else:
        head = "slopes per ln(1+P): " + "; ".join(f"{r.scores} {r.phase} {ci_txt(r.coef, r.ci_lo, r.ci_hi, 3)}" for r in main_.itertuples())
    L[-1:-1] = ["", "Reading: " + head + "; " + "; ".join(f"{r.scores} {r.phase} {ci_txt(r.coef, r.ci_lo, r.ci_hi, 3)} → "
                                                          f"{ci_txt(q.coef, q.ci_lo, q.ci_hi, 3)} with the covariates"
                                                          for r, q in zip(main_.itertuples(), sens_.itertuples())) + "."]
    return L, {"H": "H11", "hypothesis": "MA rate rises with P", "pass_rule": "slope > 0, ≥ 5/6 (per phase)",
               **key_lines(ctx, lines, 220),
               **met_by(ctx, [", ".join(f"{ph} {'yes' if metp[ph][i] else 'no'}" for ph in metp) for i in range(len(ctx["S"]))]),
               "met": "; ".join(f"{ph}: " + ", ".join(f"{S['label']} {'yes' if m_ else 'no'}" for S, m_ in zip(ctx["S"].values(), metp[ph])) for ph in metp),
               "verdict": v, "reading": head, "key": " | ".join(l_.split(":** ", 1)[1][:200] for l_ in lines)}


def part_h20(ctx, rd, save):
    M_all, K_all, P_all, H_all, met, lines = [], [], [], [], [], []
    for sk, S in ctx["S"].items():
        T = h20_intervals(S["recs"], ctx["gaps"])
        M, K, PA = h20_fit(T)
        hz = h20_hazard(S)
        for x in (M, K, PA):
            x.insert(0, "scores", S["label"])
        M_all.append(M)
        K_all.append(K)
        P_all.append(PA)
        hp = pd.Series(hz["per_animal"])
        H_all.append({"scores": S["label"], "n_steps": hz["n_steps"], "n_rem": hz["n_rem"], "k_REM_vs_stay": hz["rem"]["coef"],
                      "ci_lo": hz["rem"]["ci_lo"], "ci_hi": hz["rem"]["ci_hi"], "k_WAKE_vs_stay": hz["wake"]["coef"],
                      "wake_ci_lo": hz["wake"]["ci_lo"], "wake_ci_hi": hz["wake"]["ci_hi"], "animals_pos": int((hp > 0).sum()), "animals": len(hp)})
        m = M.iloc[0]
        nneg = int((PA.slope_k < 0).sum())
        ok = bool(m.ci_hi < 0 and nneg >= 5)
        met.append(ok)
        u = T[~T.post_round]
        lines.append(f"- **{S['label']}:** k slope on ln NREM interval {m.coef:+.4f} [{m.ci_lo:+.4f}, {m.ci_hi:+.4f}] per cycle "
                     f"({int(m.n)} completed intervals in {u.episode.nunique()} episodes), {nneg}/{len(PA)} rats < 0; within-episode "
                     f"{M.iloc[1].coef:+.4f} [{M.iloc[1].ci_lo:+.4f}, {M.iloc[1].ci_hi:+.4f}]; Cox k {M.iloc[5].coef:+.3f} "
                     f"[{M.iloc[5].ci_lo:+.3f}, {M.iloc[5].ci_hi:+.3f}]; step model at matched P and clock: k on REM entry "
                     f"{hz['rem']['coef']:+.3f} [{hz['rem']['ci_lo']:+.3f}, {hz['rem']['ci_hi']:+.3f}] → rule {'met' if ok else 'NOT met'}.")
    M, K, PA = (pd.concat(x, ignore_index=True) for x in (M_all, K_all, P_all))
    HZ = pd.DataFrame(H_all)
    save(M, "h20_models")
    save(K, "h20_by_k")
    save(PA, "h20_per_animal")
    save(HZ, "h20_step_model")
    v = verdict_of(met)
    fig_lines(K.rename(columns={"k (6 = 6+)": "k"}), "k", "median_nrem_s", ctx["fd"] / "ephys_spikes_sleep_explore_F1_h20_2026c.png",
              f"H20: median NREM seconds of the k-th inter-REM interval in a SLEEP episode, by phase  {ctx['gc']}", "k (6 = 6+)", "median NREM s in the interval")
    L = ["## H20 — do inter-REM intervals shorten within a SLEEP episode?", "",
         "**Hypothesis (plan):** \"Inter-REM intervals shorten within a sleep episode (ultradian progression).\" **Test:** \"k-th interval "
         "~ k at matched P and phase.\" **Pass rule (quoted):** \"slope < 0, ≥ 5/6\" — applied as pooled k slope CI < 0 and ≥ 5/6 per-animal "
         "slopes < 0, on both scorings. Matched P: every interval starts at P = 0 (κ = 0) and is measured in NREM seconds, the count's units.", "",
         *_tbl(M.drop(columns=["se"]), 4), "", "By k and phase (completed intervals):", "", *_tbl(K, 1), "", "Per animal:", "", *_tbl(PA, 4), "",
         "Step model (B-full + k on NREM steps after the episode's first REM; multinomial, SEs by block; per SD-free unit = one cycle):", "",
         *_tbl(HZ, 4), "", "![](../figures/ephys_spikes_sleep_explore_F1_h20_2026c.png)", "", *lines, "", f"**H20 verdict: {v}.**", ""]
    we = M[M.model.str.startswith("OLS, episode fixed")]
    we_null = bool(((we.ci_lo <= 0) & (we.ci_hi >= 0)).all())
    hz_null = bool(((HZ.ci_lo <= 0) & (HZ.ci_hi >= 0)).all())
    if v == "HOLDS" and we_null and hz_null:
        head = ("the pooled slope meets the rule, but within episodes (episode fixed effects) and at the same count and clock "
                "(step model) k has no detectable association: the shorter intervals at high k come from episodes with many REM "
                "bouts having shorter intervals, not from a shortening inside an episode")
    else:
        head = "pooled slope rule " + ("met" if v == "HOLDS" else "not met on every scoring") + (
            "; within-episode estimate " + ("covers 0" if we_null else "excludes 0") + "; step model " + ("covers 0" if hz_null else "excludes 0"))
    L[-1:-1] = ["", "Reading: " + head + " (within episode: " + "; ".join(f"{r.scores} {ci_txt(r.coef, r.ci_lo, r.ci_hi, 4)}" for r in we.itertuples())
                + "; step model k on REM entry: " + "; ".join(f"{r.scores} {ci_txt(r.k_REM_vs_stay, r.ci_lo, r.ci_hi, 4)}" for r in HZ.itertuples()) + ")."]
    return L, {"H": "H20", "hypothesis": "inter-REM intervals shorten within an episode", "pass_rule": "slope < 0, ≥ 5/6",
               **key_lines(ctx, lines, 200), **met_by(ctx, met),
               "met": ", ".join(f"{S['label']} {'yes' if m_ else 'no'}" for S, m_ in zip(ctx["S"].values(), met)), "verdict": v,
               "reading": head, "key": " | ".join(l_.split(":** ", 1)[1].split(";")[0] for l_ in lines)}


def part_h23(ctx, rd, save):
    G_all, Dd_all, W_all, lines, met_imu, met_w = [], [], [], [], [], []
    for sk, S in ctx["S"].items():
        t0 = time.time()
        Wk = h23_wakes(S, ctx["imu"], ctx["pos"])
        G, Dd, info = h23_run(S, Wk, ctx["workers"])
        Wk2 = info["wakes"]
        Wk2.insert(0, "scores", S["label"])
        W_all.append(Wk2)
        G_all.append(G)
        Dd_all.append(Dd)
        di = Dd.set_index("split")
        ri = di.loc["IMU active minus IMU quiet"]
        rw = di.loc["WISER moved minus WISER stayed"]
        oi = bool(ri.ci_lo_pct > 0 or ri.ci_hi_pct < 0)
        ow = bool(rw.ci_lo_pct > 0 or rw.ci_hi_pct < 0)
        met_imu.append(oi)
        met_w.append(ow)
        g = G.set_index("kind")
        lines.append(f"- **{S['label']}:** {info['steps_2_7']} steps after 2–7-min wakes ({info['rem_ends_2_7']} REM ends); gain all "
                     f"{g.loc['all 2-7-min wakes'].delta_pct:+.2f} % [{g.loc['all 2-7-min wakes'].ci_lo_pct:+.2f}, {g.loc['all 2-7-min wakes'].ci_hi_pct:+.2f}]; "
                     f"IMU active − quiet {ri.diff_pct:+.2f} % [{ri.ci_lo_pct:+.2f}, {ri.ci_hi_pct:+.2f}] (split at active share "
                     f"{info['imu_split_threshold']:.2f}); WISER moved − stayed {rw.diff_pct:+.2f} % [{rw.ci_lo_pct:+.2f}, {rw.ci_hi_pct:+.2f}] "
                     f"→ IMU split {'differs' if oi else 'no difference'}, WISER split {'differs' if ow else 'no difference'} ({time.time() - t0:.0f} s).")
        print(lines[-1], flush=True)
    G, Dd, Wk = (pd.concat(x, ignore_index=True) for x in (G_all, Dd_all, W_all))
    cols = ["scores", "kind", "wakes", "n_steps", "n_rem", "delta_pct", "ci_lo_pct", "ci_hi_pct", "folds_better", "folds", "animals_better", "animals", "holds"]
    G = G[[c for c in cols if c in G]]
    save(G, "h23_gain")
    save(Dd, "h23_difference")
    Wk.to_csv(ctx["out"] / "h23_wakes.csv.gz", index=False)
    WS = Wk.groupby(["scores", "kind_imu", "kind_wiser"]).agg(wakes=("d_s", "size"), median_d_s=("d_s", "median"),
                                                             median_active_share=("imu_active_share", "median"),
                                                             median_excursion_in=("wiser_excursion_in", "median"),
                                                             median_net_in=("wiser_net_in", "median"), dark_share=("dark", "mean")).reset_index()
    save(WS, "h23_wakes")
    imu_both, w_both = all(met_imu), all(met_w)
    if imu_both or w_both:
        v = "HOLDS"
    elif any(met_imu) or any(met_w):
        v = "INCONCLUSIVE"
    else:
        v = "DOES NOT HOLD"
    fig_coefs(Dd.rename(columns={"diff_pct": "coef", "ci_lo_pct": "ci_lo", "ci_hi_pct": "ci_hi", "split": "label"}),
              ctx["fd"] / "ephys_spikes_sleep_explore_F1_h23_2026c.png",
              f"H23: difference of the held-out carry-over gain (C1 vs R0) between kinds of 2-7-min wakes  {ctx['gc']}",
              "gain difference (% of R0 loss), negative = history helps more after the first kind")
    L = ["## H23 — are the 2–7-min wakes two kinds for the carry-over of history?", "",
         "**Hypothesis (plan):** \"The 2–7-min wakes are two kinds (quiet vs active).\" **Test:** \"split by WISER displacement / IMU "
         "activity during the wake; carry-over gain per kind.\" **Pass rule (quoted):** \"carry-over differs, CI excludes 0\".", "",
         "Wakes per kind (2–7-min wakes followed by NREM):", "", *_tbl(WS, 2), "",
         "Carry-over gain (C1 vs R0, held out) per kind (Δ < 0 = pre-wake history helps):", "", *_tbl(G, 3), "",
         "Gain difference between kinds:", "", *_tbl(Dd, 3), "", "![](../figures/ephys_spikes_sleep_explore_F1_h23_2026c.png)", "", *lines, "",
         "Caveats: WISER default tracks (V3 for the implanted animals; ~4–7 in jitter; 14 in = the minimum resolvable distance; "
         "the WISER frame is an unverified offset frame — only distances are used); the IMU is the scorer's EMG, so a WAKE second "
         "with a still head was scored WAKE by its LFP rule; two splits were tested.", "",
         f"**H23 verdict: {v}**" + (" (" + ", ".join(n for n, b in (("IMU split", imu_both), ("WISER split", w_both)) if b) + ")." if v == "HOLDS" else "."), ""]
    head = ("the carry-over gain differs between the kinds on every scoring for the " + ", ".join(n for n, b in (("IMU split", imu_both), ("WISER split", w_both)) if b)
            if v == "HOLDS" else ("no split shows a gain difference with a CI excluding 0 on every scoring" if v == "INCONCLUSIVE"
                                  else "no gain difference between quiet and active (IMU) or moved and stayed (WISER) 2–7-min wakes on either scoring"))
    q = Wk[Wk.imu_ok_share >= 0.5].groupby("scores").imu_active_share.quantile([0.25, 0.5, 0.75]).unstack()
    L[-1:-1] = ["", "Reading: " + head + "; IMU active share of these wakes, quartiles " + "; ".join(
        f"{lab} {r[0.25]:.2f} / {r[0.5]:.2f} / {r[0.75]:.2f}" for lab, r in q.iterrows()) + "; the gain after all 2–7-min wakes is "
        + "; ".join(f"{r.scores} {ci_txt(r.delta_pct, r.ci_lo_pct, r.ci_hi_pct, 2)} %" for r in G[G.kind == "all 2-7-min wakes"].itertuples()) + "."]
    return L, {"H": "H23", "hypothesis": "2-7-min wakes are two kinds (quiet vs active)", "pass_rule": "carry-over differs, CI excludes 0",
               **key_lines(ctx, lines, 220),
               **met_by(ctx, [f"IMU {'yes' if a_ else 'no'}, WISER {'yes' if b_ else 'no'}" for a_, b_ in zip(met_imu, met_w)]),
               "met": f"IMU: {', '.join('yes' if x else 'no' for x in met_imu)}; WISER: {', '.join('yes' if x else 'no' for x in met_w)}",
               "verdict": v, "reading": head, "key": " | ".join(l_.split(":** ", 1)[1].split(" → ")[0][-120:] for l_ in lines)}


# ================================================================== run
def run(a) -> None:
    from _common import git_commit, write_json
    from output_paths import figure_dir, report_dir, run_dir
    t_all = time.time()
    parts = [p for p in PARTS if p in set(a.parts)]
    out = run_dir("sleep_explore_F1" + ("_scratch" if a.scratch else ""), "2026c")
    rd, fd = (out, out / "figures") if a.scratch else (report_dir("2026c", "ephys_spikes"), figure_dir("2026c", "ephys_spikes"))
    gc = git_commit()
    times, csvs = {}, []

    def save(df: pd.DataFrame, name: str) -> None:
        p = rd / f"ephys_spikes_sleep_explore_F1_{name}_2026c.csv"
        df.to_csv(p, index=False)
        csvs.append(p.name)

    gaps = gaps_table()
    ctx = {"gaps": gaps, "out": out, "fd": fd, "gc": gc, "workers": a.workers, "S": {}}
    t0 = time.time()
    for sk in a.scorings:
        ctx["S"][sk] = load_scoring(sk, gaps)
    times["load"] = time.time() - t0
    inputs = {"states_FINAL": str(STATES), "states_pass2med": str(PASS2MED), "gaps": str(Path(json.load(open(ROOT / "results/2026c/ephys_spikes/reports/run_manifest_sleep_schedule_phase0_2026c.json"))["run_dir"]) / "gaps.csv")}
    if "h7" in parts:
        from sleep_explore_c import mates_arrays, zone_arrays
        from sleep_schedule_temp import weather_anomaly
        t0 = time.time()
        zc = Path(json.load(open(C_MANIFEST))["run_dir"]) / "zone_per_second.npz" if C_MANIFEST.exists() else None
        if zc is None or not zc.exists():
            zc = out / "zone_per_second.npz"
        ctx["zone"] = zone_arrays(zc)
        ctx["mates"] = {sk: mates_arrays(ctx["zone"], timelines(S["recs"])) for sk, S in ctx["S"].items()}
        ctx["weather"] = weather_anomaly()
        inputs.update(zone_cache=str(zc), weather="sleep_schedule_temp.weather_anomaly (field2026-sync from-field)")
        times["h7_inputs"] = time.time() - t0
    if "h23" in parts:
        t0 = time.time()
        ctx["imu"] = imu_grid()
        ctx["pos"] = wiser_grid()
        inputs.update(imu_seconds_cache=str(OUT / "imu_seconds_cache"), wiser_default_tracks=str(OUT / "wiser_default_tracks"))
        times["h23_inputs"] = time.time() - t0
        print(f"H23 inputs {times['h23_inputs']:.0f} s", flush=True)
    sections, verdicts = [], []
    fns = {"h5": part_h5, "h7": part_h7, "h8": part_h8, "h9": part_h9, "h10": part_h10, "h11": part_h11, "h20": part_h20, "h23": part_h23}
    for p in parts:
        t0 = time.time()
        L, vrow = fns[p](ctx, rd, save)
        iv = next(i for i, ln in enumerate(L) if ln.startswith(f"**{p.upper()} verdict"))
        L[iv:iv] = [f"*Implementation notes and deviations (stated before the run unless marked):* {DEV[p]}", ""]
        times[p] = time.time() - t0
        vrow["runtime_s"] = round(times[p], 1)
        print(f"{p} done in {times[p]:.0f} s: {vrow['verdict']}", flush=True)
        sections.append(L)
        verdicts.append(vrow)
    VT = pd.DataFrame(verdicts)
    save(VT, "verdicts")
    times["total"] = time.time() - t_all
    data_lines = [f"- {S['label']}: {len(S['recs'])} records, {len(S['D']['y'])} NREM steps (post-round 3 h: {int(S['D']['post_round'].sum())}), "
                  f"{int((S['D']['y'] == 1).sum())} REM ends, {int((S['D']['y'] == 2).sum())} WAKE ends." for S in ctx["S"].values()]
    hdr = ["# Sleep behaviour explore — Step F, sequence-only batch (F1): H5, H7, H8, H9, H10, H11, H20, H23 (cohort 2026c)"
           + (" — SCRATCH" if a.scratch else ""), "",
           f"Plan: [{PLAN}](../../../../{PLAN}) (section 5, the Step F table — hypothesis, test and pass rule written before results "
           f"and used unchanged; section 9 Amendment 1, the batch split). Builds on Steps A–E "
           f"([A](ephys_spikes_sleep_explore_A_2026c.md), [B](ephys_spikes_sleep_explore_B_2026c.md), [C](ephys_spikes_sleep_explore_C_2026c.md), "
           f"[E](ephys_spikes_sleep_explore_E_2026c.md)) and the [claim audit](ephys_spikes_sleep_schedule_claim_audit_2026c.md) (#32–#43). "
           f"Driver `ephys/sleep_explore_f1.py run` (commit {gc}; file uncommitted at run time); bulk `{out}`; parts {', '.join(parts)}; "
           f"runtime {times['total'] / 60:.1f} min.", "",
           "**Status: exploration step (technical ledger); claim numbers and statuses belong in the claim audit, not here.** Inputs: the "
           "scored 1-s states (FINAL and pass2med), NOAA light, the Phase-0 gap table; H7 also the weather console and Step C's WISER "
           "zones; H23 also the WISER default tracks and the head-IMU seconds cache. No LFP features. Everything from 2026-09-11 19:40 "
           "is cut. The scorer's EMG is the head IMU; a claim that links IMU movement to a scored state carries that caveat.", "",
           "## Verdicts at a glance", "", *_tbl(VT[["H", "hypothesis", "verdict"]], 2), "",
           "The full verdict table (pass rule, both scorings, key numbers, reading) is at the end of the report.", "",
           "## Data", "", *data_lines, ""]
    cols = ["H", "hypothesis", "pass_rule", "FINAL", "FINAL rule met", "pass2med", "pass2med rule met", "verdict", "reading"]
    fin = ["## Final verdict table (both scorings)", "",
           "Pass rules quoted from the plan's Step F table; 'rule met' per scoring as operationalised in each section; HOLDS = met on "
           "both scorings, DOES NOT HOLD = met on neither, INCONCLUSIVE = met on one only (H7: a predictor significant somewhere "
           "without meeting 'holds'). A HOLDS verdict is not a claim status; claim numbers are assigned in the claim audit.", "",
           *_tbl(VT[[c for c in cols if c in VT]], 3), "",
           "## Deviations and notes, summary", "",
           "Each section states its own implementation notes and deviations in place, just above its verdict line. Common to all: "
           "the post-round 3 h exclusion is applied in H7, H8, H10, H11 and H20 (phase contrasts), not in H5 (Step A2's data, "
           "sensitivity row), H9 or H23 (Step B / Phase 2 set-ups unchanged). Two changes were made after the first scratch run, "
           "both marked in their sections: the H8 per-animal continuity correction (a defect fix) and the H7 'P at onset ≥ 1 min' "
           "sensitivity row (not in the verdict).", ""]
    flat = [ln for blk in [hdr, DEFINITIONS] + sections + [fin] for ln in blk]
    rpt = rd / "ephys_spikes_sleep_explore_F1_2026c.md"
    rpt.write_text("\n".join(flat) + "\n", encoding="utf-8")
    write_json(rd / "run_manifest_sleep_explore_F1_2026c.json",
               {"run_dir": str(out), "git_commit": gc, "parts": parts, "scorings": [ctx["S"][s]["label"] for s in a.scorings], "p_key": KEY,
                "inputs": inputs, "runtime_s": {k: round(v_, 1) for k, v_ in times.items()}, "verdicts": verdicts, "csvs": csvs,
                "plan": PLAN, "scratch": bool(a.scratch)})
    print("written", rpt, f"({times['total'] / 60:.1f} min)", flush=True)


# ================================================================== selftest
def selftest() -> None:
    t_start = time.time()
    ok_all = True
    rng = np.random.default_rng(1)

    def check(name: str, cond: bool) -> None:
        nonlocal ok_all
        print(("PASS " if cond else "FAIL ") + name, flush=True)
        ok_all &= bool(cond)

    # 1. counter at every bout = sleep_model.counter_starts on NREM bouts; REM onset values by hand
    seq = [(N, 120), (W, 60), (N, 60), (R, 30), (N, 30), (W, 500), (N, 90), (W, 8), (R, 40), (0, 20), (N, 30)]
    st = np.concatenate([np.full(d, s, np.int8) for s, d in seq])
    ct = counter_trace(st, 600.0, 0.0)
    cs = counter_starts(st, "disc", 600.0, 0.0)
    check("counter_trace equals sleep_model.counter_starts at every NREM bout start", all(abs(ct[k] - v) < 1e-12 for k, v in cs.items()))
    p_r1 = 2.0 * np.exp(-60 / 600) + 1.0
    p_r2 = (0.5 * np.exp(-500 / 600) + 1.5) * np.exp(-8 / 600)
    check(f"P at REM onsets by hand ({ct[240]:.4f} = {p_r1:.4f}; {ct[898]:.4f} = {p_r2:.4f}); frozen over unknown",
          abs(ct[240] - p_r1) < 1e-9 and abs(ct[898] - p_r2) < 1e-9 and abs(ct[938]) < 1e-12 and abs(ct[958]) < 1e-12)
    rc = {"animal": "SF07", "start": pd.Timestamp("2026-09-03 10:00"), "state": st, "record_id": 0, "block": "2026-09-03D"}
    rb = rem_bout_table([rc])
    check("rem_bout_table: first REM prior wake unknown (record start), second REM prior wake 500 s, entered from a wake",
          np.isnan(rb.d_prior.iloc[0]) and rb.d_prior.iloc[1] == 500 and rb.from_wake.iloc[1] == 1 and rb.complete.iloc[0]
          and not rb.complete.iloc[1])

    # 2. hours since sunset
    from sleep_quant import sun_times
    ss = pd.Timestamp(sun_times(pd.Timestamp("2026-09-03").date())[1])
    h = hours_since_sunset([ss + pd.Timedelta(hours=2), pd.Timestamp("2026-09-04 01:00")])
    check(f"hours since sunset: +2 h -> {h[0]:.3f}; 01:00 next day -> {h[1]:.2f} (from 09-03 sunset)",
          abs(h[0] - 2) < 1e-9 and abs(h[1] - (pd.Timestamp("2026-09-04 01:00") - ss).total_seconds() / 3600) < 1e-9)

    # 3. H5 estimator: latency driven by ln d only (truth +0.3) vs by hours since sunset only, with ln d and h_ss correlated
    n = 600
    an = rng.choice(["SF07", "SF08", "SF09", "SF10"], n)
    hss = rng.uniform(0.5, 10, n)
    l_d = np.log(420) + 0.25 * hss + rng.normal(0, 0.8, n)
    base = pd.DataFrame({"animal": an, "block": rng.choice([f"b{i}" for i in range(16)], n), "hss": hss, "l_d": l_d,
                         "l_P": rng.uniform(0, 1, n), "l_npre": 0.0, "anchor": 0, "dark": True, "d_s": np.exp(l_d).clip(420, 14000),
                         "event": 1, "t_wake_end": pd.Timestamp("2026-09-03 23:00")})
    for c in ("sin1", "cos1", "sin2", "cos2"):
        base[c] = rng.normal(0, 1, n)
    wd = base.assign(T_s=np.exp(6 + 0.3 * l_d + rng.normal(0, 0.5, n)))
    wd["l_T"] = np.log(wd.T_s)
    wh = base.assign(T_s=np.exp(6 + 0.15 * hss + rng.normal(0, 0.5, n)))
    wh["l_T"] = np.log(wh.T_s)
    md, _, _ = h5_fit(wd, None)
    mh, _, _ = h5_fit(wh, None)
    gd = md[(md.model == H5_MAIN) & (md.term == "l_d") & md.method.str.startswith("OLS")].iloc[0]
    gh = mh[(mh.model == H5_MAIN) & (mh.term == "l_d") & mh.method.str.startswith("OLS")].iloc[0]
    gh0 = mh[(mh.model == "ln d + ln(1+P) (no time of night)") & (mh.term == "l_d")].iloc[0]
    check(f"H5: ln-d world slope {gd.coef:+.3f} [{gd.ci_lo:+.3f}, {gd.ci_hi:+.3f}] > 0 (truth 0.30); time-of-night world: "
          f"without h_ss {gh0.coef:+.3f} (spurious), with h_ss {gh.coef:+.3f} [{gh.ci_lo:+.3f}, {gh.ci_hi:+.3f}] covers 0",
          gd.ci_lo > 0 and abs(gd.coef - 0.3) < 0.1 and gh0.ci_lo > 0 and gh.ci_lo <= 0 <= gh.ci_hi)

    # 4. H7 classification: duration depends on dark only (truth +0.3), both 'scorings'
    m = 3000
    T = pd.DataFrame({"animal": rng.choice(["SF07", "SF08", "SF09", "SF10", "SF11", "SF12"], m), "block": rng.choice([f"b{i}" for i in range(22)], m),
                      "darkf": rng.integers(0, 2, m).astype(float), "l_P": rng.uniform(0, 3, m), "l_dprior": rng.uniform(4, 9, m),
                      "temp_anom": rng.normal(0, 3, m), "n_coloc": rng.integers(0, 4, m).astype(float), "loc_field": 0.0, "loc_unknown": 0.0,
                      "post_round": False, "from_wake": 0, "T_day": rng.uniform(0, 12, m)})
    for c in ("sin1", "cos1", "sin2", "cos2"):
        T[c] = rng.normal(0, 1, m)
    T["l_dur"] = 3.8 + 0.3 * T.darkf + rng.normal(0, 0.6, m)
    co, pa = {}, {}
    for lab, seed in (("FINAL", 0), ("pass2med", 1)):
        Tl = T.assign(l_dur=T.l_dur + np.random.default_rng(seed).normal(0, 0.05, m))
        c_, p_, _ = h7_fit(Tl)
        co[lab], pa[lab] = c_, p_
    stt = h7_status(co, pa).set_index("term").status
    check(f"H7: only dark holds when only dark matters ({dict(stt)})", stt["darkf"] == "holds" and (stt.drop("darkf") != "holds").all())

    # 5. H8: Mantel-Haenszel removes duration confounding (night bouts shorter; exit depends on duration only)
    k = 8000
    dark = rng.integers(0, 2, k)
    dur = np.where(dark == 1, rng.lognormal(3.5, 0.6, k), rng.lognormal(4.2, 0.6, k))
    pW = 1 / (1 + np.exp(-(-1.5 + 0.02 * (60 - np.minimum(dur, 200)))))
    df = pd.DataFrame({"darkf": dark, "exitW": (rng.random(k) < pW).astype(int), "dur_bin": pd.cut(dur, DUR_EDGES, right=False, labels=DUR_LABELS),
                       "animal": "SF07"})
    crude = (df[df.darkf == 1].exitW.mean() / (1 - df[df.darkf == 1].exitW.mean())) / (df[df.darkf == 0].exitW.mean() / (1 - df[df.darkf == 0].exitW.mean()))
    o = mh_or(df, ["dur_bin"])
    check(f"H8: crude OR {crude:.2f} (confounded by duration) vs MH OR {o:.2f} (truth 1; within-bin residual confounding small)",
          crude > 1.3 and 0.8 < o < 1.25)
    zc = pd.DataFrame({"darkf": [1] * 10 + [0] * 20, "exitW": [1] * 10 + [1] * 12 + [0] * 8, "dur_bin": "a"})
    o_raw, o_cc = mh_or(zc, ["dur_bin"]), mh_or(zc, ["dur_bin"], cc=0.5)
    check(f"H8: all dark bouts end in WAKE -> raw OR undefined ({o_raw}), corrected OR {o_cc:.2f} = (10.5 x 8.5) / (0.5 x 12.5) > 1",
          np.isnan(o_raw) and abs(o_cc - (10.5 * 8.5) / (0.5 * 12.5)) < 1e-9)

    # 6. H9 features by hand: REM since sunrise / since the last long wake on a tiny timeline
    sr = int((pd.Timestamp(sun_times(pd.Timestamp("2026-09-03").date())[0]) - G0).total_seconds())
    s_tl = np.zeros(SPAN, np.int8)
    s_tl[sr - 600:sr + 3000] = N
    s_tl[sr - 300:sr - 200] = R                      # 100 s REM before sunrise
    s_tl[sr + 100:sr + 160] = R                      # 60 s REM after sunrise
    s_tl[sr + 300:sr + 800] = W                      # 500-s long wake
    s_tl[sr + 900:sr + 960] = R                      # 60 s REM after the long wake
    t_step = sr + 2000
    Dh = {"y": np.zeros(1, np.int8), "animal": np.array(["SF07"]), "t_s": np.array([t_step])}
    h9_features(Dh, [], {a_: (s_tl if a_ == "SF07" else np.zeros(SPAN, np.int8)) for a_ in ANIMALS})
    check(f"H9 features: REM since sunrise {Dh['rem_sr'][0]:.3f} min (2.0), since the long wake {Dh['rem_lw'][0]:.3f} min (1.0), "
          f"recorded since sunrise {Dh['rec_sr'][0]:.4f} h ({2000 / 3600:.4f})",
          abs(Dh["rem_sr"][0] - 2.0) < 1e-9 and abs(Dh["rem_lw"][0] - 1.0) < 1e-9 and abs(Dh["rec_sr"][0] - 2000 / 3600) < 1e-9)

    # 7. H9 held-out machinery: an informative column gives a CI < 0, a noise column a CI covering 0
    nS = 24000
    blocks = np.repeat([f"2026-09-{1 + i // 2:02d}{'D' if i % 2 == 0 else 'N'}" for i in range(12)], nS // 12)
    Ds = {"animal": rng.choice(["SF07", "SF08", "SF09"], nS), "block": blocks}
    for c in ("l_elapsed", "T_day", "has_anchor", "dark", "l_dprev", "prev_rem", "prev_unk", "fW10", f"lP_{KEY}", "sin1", "cos1", "sin2", "cos2"):
        Ds[c] = rng.normal(0, 1, nS)
    Ds["good"], Ds["noise"] = rng.normal(0, 1, nS), rng.normal(0, 1, nS)
    eta_r = -3.5 + 0.6 * Ds[f"lP_{KEY}"] - 0.5 * Ds["good"]
    eta_w = -3.0 + 0.3 * Ds["fW10"]
    pr = np.column_stack([np.ones(nS), np.exp(eta_r), np.exp(eta_w)])
    pr /= pr.sum(1, keepdims=True)
    Ds["y"] = np.array([rng.choice(3, p=p_) for p_ in pr]).astype(np.int8)
    specs = {"B": {"L1": True, "hist": KEY}, "B+good": {"L1": True, "hist": KEY, "extra": ("good",)},
             "B+noise": {"L1": True, "hist": KEY, "extra": ("noise",)}}
    from sleep_model import cmp
    res = run_folds(Ds, specs, 3, folds_of(Ds))
    F, FA = fixed_tables(res, specs)
    rg, rn = cmp(F, FA, "B", "B+good", "good"), cmp(F, FA, "B", "B+noise", "noise")
    check(f"H9 held-out: informative column Δ {rg['delta_pct']:+.3f} % [{rg['ci_lo_pct']:+.3f}, {rg['ci_hi_pct']:+.3f}] < 0; noise "
          f"{rn['delta_pct']:+.3f} % [{rn['ci_lo_pct']:+.3f}, {rn['ci_hi_pct']:+.3f}] covers / above 0",
          rg["ci_hi_pct"] < 0 and rn["ci_hi_pct"] >= 0)

    # 8. H10 window extraction by hand + the 'survives' estimator in two worlds
    seq = [(N, 300), (R, 60), (W, 10), (N, 40), (W, 20), (N, 30), (R, 50), (N, 300), (R, 40), (W, 100), (N, 400)]
    st = np.concatenate([np.full(d, s, np.int8) for s, d in seq])
    t10 = h10_table([{"animal": "SF07", "start": pd.Timestamp("2026-09-03 10:00"), "state": st, "record_id": 0, "block": "2026-09-03D"}],
                    pd.DataFrame(columns=["animal", "gap_start", "gap_end", "cause"]))
    r1 = t10.iloc[0]
    check(f"H10 table: first REM end -> second REM after 100 s (y 1, brief wakes 2, Watson MA 1, exit arousal), second REM end "
          f"-> none within 135 s; third REM (next wake 100 s) excluded ({len(t10)} rows)",
          len(t10) == 2 and (r1.y, r1.n_brief, r1.n_ma, r1.exit_brief, r1.lat_s) == (1, 2, 1, 1, 100.0) and t10.iloc[1].y == 0)
    q = 6000
    dk = rng.integers(0, 2, q)
    nb = rng.poisson(np.where(dk == 1, 1.5, 0.5))
    y_gain = (rng.random(q) < 1 / (1 + np.exp(-(-0.5 - 1.0 * dk)))).astype(int)
    y_int = (rng.random(q) < 1 / (1 + np.exp(-(0.0 - 0.9 * nb)))).astype(int)
    out = []
    for yy in (y_gain, y_int):
        Tq = pd.DataFrame({"animal": rng.choice(["SF07", "SF08", "SF09", "SF10"], q), "block": rng.choice([f"b{i}" for i in range(20)], q),
                           "y": yy, "darkf": dk.astype(float), "dark": dk.astype(bool), "n_brief": nb, "n_ma": nb, "exit_brief": 0, "n_w40": 0,
                           "l_rem": rng.normal(4, 0.5, q), "post_round": False, "rem_in_45": 0, "brief_45": (nb > 0).astype(int)})
        M_, _, _ = h10_fit(Tq)
        out.append(M_[(M_.model.str.startswith("M1 (pass")) & (M_.term == "darkf")].iloc[0])
    check(f"H10: gain world dark with the count {out[0].coef:+.3f} [{out[0].ci_lo:+.3f}, {out[0].ci_hi:+.3f}] survives; interruption world "
          f"{out[1].coef:+.3f} [{out[1].ci_lo:+.3f}, {out[1].ci_hi:+.3f}] covers 0", out[0].ci_hi < 0 and out[1].ci_lo <= 0 <= out[1].ci_hi)

    # 9. H11: MA flags by hand; slope recovered in a P-dependent world, null world covers 0
    seq = [(N, 100), (W, 20), (N, 100), (W, 8), (R, 30), (N, 50), (W, 200), (N, 60)]
    st = np.concatenate([np.full(d, s, np.int8) for s, d in seq])
    fl = ma_flags([{"record_id": 0, "state": st}])
    check(f"H11 flags: MA, brief wake before REM, long wake, record end ({[fl[(0, a_)] for a_ in (0, 120, 258, 508)]})",
          [fl[(0, a_)] for a_ in (0, 120, 258, 508)] == [1, 2, 3, 0])
    z = 60000
    lP = rng.uniform(0, 4, z)
    res11 = []
    for slope in (0.4, 0.0):
        y = (rng.random(z) < 1 / (1 + np.exp(-(-4.5 + slope * lP)))).astype(int)
        df = pd.DataFrame({"animal": rng.choice(["SF07", "SF08", "SF09", "SF10", "SF11", "SF12"], z), "block": rng.choice([f"b{i}" for i in range(20)], z),
                           "dark": rng.integers(0, 2, z).astype(bool), "post_round": False, "y_ma": y, "y_pre": 0, "P": np.expm1(lP), "l_P": lP,
                           "l_elapsed": rng.normal(4, 1, z), "T_day": rng.uniform(0, 12, z)})
        for c in ("sin1", "cos1", "sin2", "cos2"):
            df[c] = rng.normal(0, 1, z)
        df["P_bin"] = pd.cut(df.P, P_EDGES, right=False, labels=P_LABELS)
        M_, _, _ = h11_fit(df)
        res11.append(M_[(M_.phase == "light") & M_.outcome.str.startswith("MA") & M_.model.str.contains("pass rule")].iloc[0])
    check(f"H11: slope {res11[0].coef:+.3f} [{res11[0].ci_lo:+.3f}, {res11[0].ci_hi:+.3f}] (truth 0.4); null {res11[1].coef:+.3f} "
          f"[{res11[1].ci_lo:+.3f}, {res11[1].ci_hi:+.3f}] covers 0",
          res11[0].ci_lo > 0 and abs(res11[0].coef - 0.4) < 0.15 and res11[1].ci_lo <= 0 <= res11[1].ci_hi)

    # 10. H20: intervals by hand; slope recovered (intervals x 0.85 per cycle) and null
    seq = [(W, 200), (N, 600), (R, 60), (N, 400), (W, 20), (N, 100), (R, 50), (N, 300), (R, 40), (N, 500), (W, 300)]
    st = np.concatenate([np.full(d, s, np.int8) for s, d in seq])
    t20 = h20_intervals([{"animal": "SF07", "start": pd.Timestamp("2026-09-03 10:00"), "state": st, "record_id": 0, "block": "2026-09-03D"}],
                        pd.DataFrame(columns=["animal", "gap_start", "gap_end", "cause"]))
    check(f"H20 intervals: k 1, 2 completed with NREM 500 / 300 s (wall 520 / 300), k 3 censored with 500 s ({t20[['k', 'event', 'nrem_s', 'wall_s']].values.tolist()})",
          t20[["k", "event", "nrem_s", "wall_s"]].values.tolist() == [[1, 1, 500, 520], [2, 1, 300, 300], [3, 0, 500, 500]])
    rows = []
    for e in range(900):
        a_ = ["SF07", "SF08", "SF09", "SF10", "SF11", "SF12"][e % 6]
        m_rem = int(rng.integers(2, 7))
        for k in range(1, m_rem):
            for world, f_ in (("shrink", 0.85), ("null", 1.0)):
                rows.append({"world": world, "animal": a_, "block": f"b{e % 20}", "episode": f"e{e}", "k": k, "event": 1,
                             "nrem_s": float(np.exp(np.log(600) + np.log(f_) * (k - 1) + rng.normal(0, 0.4))), "darkf": float(e % 2), "dark": bool(e % 2),
                             "post_round": False, "m_rem": m_rem, "wall_s": 1.0, "rem_k_s": 60.0})
    TT = pd.DataFrame(rows)
    TT["l_nrem"], TT["l_wall"], TT["l_remk"] = np.log(TT.nrem_s), rng.normal(6, 0.4, len(TT)), np.log(60.0)
    for c in ("sin1", "cos1", "sin2", "cos2"):
        TT[c] = rng.normal(0, 1, len(TT))
    ms, _, ps = h20_fit(TT[TT.world == "shrink"])
    mn, _, _ = h20_fit(TT[TT.world == "null"])
    check(f"H20: shrink world slope {ms.iloc[0].coef:+.4f} [{ms.iloc[0].ci_lo:+.4f}, {ms.iloc[0].ci_hi:+.4f}] (truth {np.log(0.85):+.4f}), "
          f"{int((ps.slope_k < 0).sum())}/{len(ps)} rats < 0; null {mn.iloc[0].coef:+.4f} [{mn.iloc[0].ci_lo:+.4f}, {mn.iloc[0].ci_hi:+.4f}]",
          ms.iloc[0].ci_hi < 0 and abs(ms.iloc[0].coef - np.log(0.85)) < 0.03 and (ps.slope_k < 0).sum() >= 5 and mn.iloc[0].ci_lo <= 0 <= mn.iloc[0].ci_hi)

    # 11. H23: wake kinds by hand; the gain-difference bootstrap
    imu = np.zeros(400, np.int8)
    imu[100:200] = 1
    imu[200:300] = np.r_[np.full(30, 1), np.full(70, 2)]
    x = np.full(400, np.nan, np.float32)
    y = np.full(400, np.nan, np.float32)
    x[50:300], y[50:300] = 10.0, 10.0
    x[220:260] = 40.0
    k1 = wake_kinds(100, 200, imu, (x, y))
    k2 = wake_kinds(200, 300, imu, (x, y))
    check(f"H23 kinds: still wake active share {k1['imu_active_share']:.2f} excursion {k1['wiser_excursion_in']:.1f}; moving wake "
          f"{k2['imu_active_share']:.2f} / {k2['wiser_excursion_in']:.1f} in",
          k1["imu_active_share"] == 0 and k1["wiser_excursion_in"] == 0 and abs(k2["imu_active_share"] - 0.7) < 1e-9 and abs(k2["wiser_excursion_in"] - 30) < 1e-6)
    Fd = pd.DataFrame({"fold": range(16), "n_a": 300, "n_b": 300, "d_a": -0.004 + rng.normal(0, 0.002, 16), "d_b": rng.normal(0, 0.002, 16)})
    dd = fold_diff_ci(Fd, "d_a", "d_b", base=0.4)
    Fn = Fd.assign(d_a=rng.normal(0, 0.002, 16))
    dn = fold_diff_ci(Fn, "d_a", "d_b", base=0.4)
    check(f"H23 difference: {dd['diff_pct']:+.2f} % [{dd['ci_lo_pct']:+.2f}, {dd['ci_hi_pct']:+.2f}] (truth -1.0) excludes 0; null "
          f"[{dn['ci_lo_pct']:+.2f}, {dn['ci_hi_pct']:+.2f}] covers 0", dd["ci_hi_pct"] < 0 and dn["ci_lo_pct"] <= 0 <= dn["ci_hi_pct"])
    print(f"selftest {'PASS' if ok_all else 'FAIL'} ({time.time() - t_start:.0f} s)", flush=True)
    if not ok_all:
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["run"])
    ap.add_argument("--parts", nargs="+", default=list(PARTS), choices=list(PARTS))
    ap.add_argument("--scorings", nargs="+", default=["final", "pass2med"], choices=list(SCORINGS))
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--scratch", action="store_true", help="write everything into the run folder only")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.workers > 6:
        a.workers = 6
    if a.selftest:
        selftest()
    elif a.cmd == "run":
        run(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
