r"""Phase 4 of the internal-schedule analysis: ambient temperature as a slow REM gate (plan Amendment 6, written before
any result). Called by `python ephys/sleep_schedule.py phase4`.

Definitions:
  weather        sleep_quant.load_weather: on-site console, 5 min, 08-31 -> 09-12 (NWS KITH only inside the console's
                 09-02/03 uplink hole); outdoor temperature temp_C (degC), relative humidity, rain rate.
  temp_anom      temp_C minus its fit on (sin, cos)(2 pi k h / 24), k = 1, 2, over the whole cohort (degC): warmer (+) or
                 colder (-) than usual for that time of day. Joined to a 10-s step / 10-min bin by the nearest weather
                 sample within 15 min.
  T1             held out (forward chaining, as Phase 2): M2t vs M2t + z(temp_anom); full-fit multinomial coefficients
                 (REM vs stay, Wake vs stay) per SD, and per-animal signs of the REM-vs-stay coefficient.
  T2             1-h bins with >= 20 min of sleep: REM share of sleep ~ temp_anom + phase + day + animal (binomial GLM,
                 var weights = sleep s; SEs clustered by date); and sleep share of recorded time (>= 30 min recorded).
  T3             night -> next-day sleep deviations (Phase 3b) with the night and day mean temp_anom as covariates.
  T4             empirical REM hazard per 10-s step against the total NREM since the last REM, per temp_anom tertile.
Prediction (before results): warmer than usual -> REM entry more likely, REM share higher.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from sleep_schedule import ROOT, included_sessions  # noqa: E402
from sleep_schedule_phase2 import build_steps, compare, fit2, forward_folds, run_cv  # noqa: E402
from sleep_schedule_phase2b import records_with_metrics  # noqa: E402


def weather_anomaly() -> pd.DataFrame:
    import statsmodels.api as sm
    from _common import sibling_repo
    from sleep_quant import load_weather
    w = load_weather(sibling_repo("field2026-sync")).dropna(subset=["temp_C"]).copy()
    h = w.t.dt.hour + w.t.dt.minute / 60
    X = sm.add_constant(pd.DataFrame({f"{f}{k}": fn(2 * np.pi * k * h / 24) for k in (1, 2) for f, fn in (("s", np.sin), ("c", np.cos))}))
    w["temp_anom"] = sm.OLS(w.temp_C, X).fit().resid
    return w.sort_values("t").reset_index(drop=True)


def join_weather(df: pd.DataFrame, tcol: str, w: pd.DataFrame) -> pd.DataFrame:
    left = df[[tcol]].copy()
    left["_i"] = np.arange(len(df))
    m = pd.merge_asof(left.sort_values(tcol), w[["t", "temp_C", "temp_anom", "rh_pct", "rain_rate_mmh"]].rename(columns={"t": tcol}),
                      on=tcol, direction="nearest", tolerance=pd.Timedelta(minutes=15)).sort_values("_i")
    for c in ("temp_C", "temp_anom", "rh_pct", "rain_rate_mmh"):
        df[c] = m[c].to_numpy()
    return df


def phase4(a) -> None:
    import statsmodels.api as sm
    from _common import git_commit, write_json
    from output_paths import report_dir, run_dir
    from sleep_quant import md_table
    from sleep_schedule_phase2 import baselines, bins10
    from sleep_schedule_phase3 import light_flags
    out = run_dir("sleep_schedule_phase4" + ("_smoke" if a.smoke else ""), "2026c")
    rd = out if a.smoke else report_dir("2026c", "ephys_spikes")
    gc = git_commit()
    w = weather_anomaly()
    w.to_csv(out / "weather_anomaly.csv.gz", index=False)
    wsum = pd.DataFrame([{"samples": len(w), "from": w.t.min(), "to": w.t.max(), "temp_min": w.temp_C.min(), "temp_max": w.temp_C.max(),
                          "anom_sd": w.temp_anom.std(), "anom_min": w.temp_anom.min(), "anom_max": w.temp_anom.max()}])
    rv = included_sessions(Path(a.review), Path(a.states))
    recs = records_with_metrics(rv, Path(a.states))
    steps = build_steps(recs)
    steps = join_weather(steps, "t", w)
    st = steps.dropna(subset=["temp_anom"]).copy()
    st["dark"] = (~light_flags(st.t)).astype(float)
    print(f"steps with weather {len(st)} of {len(steps)}", flush=True)
    base = ["L1", "ntspl", "wsince", "rem"]
    F, _, FA, _ = run_cv(st, {"M2t": base, "M2t_temp": base + ["col:temp_anom"]}, forward_folds(st))
    T1 = pd.DataFrame([compare(F, FA, "M2t", "M2t_temp", "NREM steps with weather")])
    levels = sorted(st.animal.unique())
    m, s_ = fit2(st, base + ["col:temp_anom"], levels)
    cls = list(m.classes_)
    k_col = None
    # the temp column is the last column before the animal dummies: locate it by refitting the design width
    from sleep_schedule_phase2 import design2, feats2
    X0, _ = design2(feats2(st.iloc[:50]), st.animal.iloc[:50], base, s_, levels)
    X1, _ = design2(feats2(st.iloc[:50]), st.animal.iloc[:50], base + ["col:temp_anom"], s_, levels)
    k_col = X0.shape[1] - (len(levels) - 1)
    coef = {lab: float(m.coef_[cls.index(c)][k_col] - m.coef_[cls.index(0)][k_col]) for lab, c in (("REM vs stay", 1), ("Wake vs stay", 2)) if c in cls}
    sg = []
    for an, g in st.groupby("animal"):
        ma, _ = fit2(g, base + ["col:temp_anom"], [an])
        ca = list(ma.classes_)
        if 1 in ca and 0 in ca:
            sg.append(np.sign(ma.coef_[ca.index(1)][k_col] - ma.coef_[ca.index(0)][k_col]))
    T1["full_fit_REM_vs_stay_per_SD"] = coef.get("REM vs stay")
    T1["full_fit_Wake_vs_stay_per_SD"] = coef.get("Wake vs stay")
    T1["animals_REM_coef_positive"] = int(np.sum(np.array(sg) > 0))
    T1["animals_fit"] = len(sg)
    T1.to_csv(rd / "ephys_spikes_sleep_schedule_phase4_t1_2026c.csv", index=False)
    print(T1.round(4).to_string(index=False), flush=True)

    # T2 hourly shares
    Bn, RB = bins10(recs)
    Bn["hbin"] = Bn.t.dt.floor("1h")
    H = Bn.groupby(["animal", "hbin"]).agg(rec_s=("rec_s", "sum"), rem_s=("rem_s", "sum"), nrem_s=("nrem_s", "sum"), block=("block", "first")).reset_index()
    H["t"] = H.hbin + pd.Timedelta(minutes=30)
    H = join_weather(H, "t", w).dropna(subset=["temp_anom"])
    H["hour"] = H.t.dt.hour + 0.5
    H["day"] = (H.t - pd.Timestamp("2026-08-30 19:00")).dt.total_seconds() / 86400
    H["date"] = H.t.dt.date

    def design_h(g):
        X = pd.DataFrame({"temp_anom": g.temp_anom, "day": g.day}, index=g.index)
        for k in (1, 2):
            X[f"s{k}"], X[f"c{k}"] = np.sin(2 * np.pi * k * g.hour / 24), np.cos(2 * np.pi * k * g.hour / 24)
        return sm.add_constant(pd.concat([X, pd.get_dummies(g.animal, drop_first=True, dtype=float)], axis=1))
    rows = []
    for lab, g, y, wts in (("REM share of sleep (hours with >= 20 min sleep)", H[(H.rem_s + H.nrem_s) >= 1200], lambda g: g.rem_s / (g.rem_s + g.nrem_s), lambda g: g.rem_s + g.nrem_s),
                           ("sleep share of recorded time (hours >= 30 min recorded)", H[H.rec_s >= 1800], lambda g: (g.rem_s + g.nrem_s) / g.rec_s, lambda g: g.rec_s)):
        fit = sm.GLM(y(g), design_h(g), family=sm.families.Binomial(), var_weights=wts(g)).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(g.date)[0]})
        sga = []
        for an, ga in g.groupby("animal"):
            Xa = design_h(ga).drop(columns=[c for c in design_h(ga).columns if c.startswith("SF")], errors="ignore")
            try:
                sga.append(np.sign(sm.GLM(y(ga), Xa, family=sm.families.Binomial(), var_weights=wts(ga)).fit().params["temp_anom"]))
            except Exception:  # noqa: BLE001
                pass
        rows.append({"outcome": lab, "n_animal_hours": len(g), "logit_coef_per_degC": fit.params["temp_anom"],
                     "ci_lo": fit.conf_int().loc["temp_anom", 0], "ci_hi": fit.conf_int().loc["temp_anom", 1], "p": fit.pvalues["temp_anom"],
                     "odds_ratio_per_degC": float(np.exp(fit.params["temp_anom"])), "animals_positive": int(np.sum(np.array(sga) > 0)), "animals": len(sga)})
    T2 = pd.DataFrame(rows)
    T2.to_csv(rd / "ephys_spikes_sleep_schedule_phase4_t2_2026c.csv", index=False)
    print(T2.round(4).to_string(index=False), flush=True)

    # T3 night -> day trade-off with temperature
    rows = []
    p3b = Path(json.load(open(ROOT / "results/2026c/ephys_spikes/reports/run_manifest_sleep_schedule_phase3b_2026c.json"))["run_dir"])
    from sleep_quant import sun_times
    for lab in ("FINAL", "pass2med_remclean"):
        D = pd.read_csv(p3b / f"budget_days_{lab}.csv", parse_dates=["night_of"])
        for k in ("night", "day"):
            vals = []
            for r in D.itertuples():
                d = pd.Timestamp(r.night_of)
                ss0 = pd.Timestamp(sun_times(d.date())[1])
                sr1, ss1 = (pd.Timestamp(x) for x in sun_times((d + pd.Timedelta(days=1)).date()))
                t0, t1 = (ss0, sr1) if k == "night" else (sr1, ss1)
                ww = w[(w.t >= t0) & (w.t < t1)]
                vals.append(ww.temp_anom.mean() if len(ww) > 20 else np.nan)
            D[f"{k}_temp_anom"] = vals
        for q in ("REM", "NREM"):
            x, y = f"night_{q}_dev_min", f"day_{q}_dev_min"
            g = D[(D.night_cov >= 0.5) & (D.day_cov >= 0.5)].dropna(subset=[x, y, "night_temp_anom", "day_temp_anom"])
            for spec, cols in (("without temperature", [x]), ("with night + day temp anomaly", [x, "night_temp_anom", "day_temp_anom"])):
                Xf = sm.add_constant(pd.concat([g[cols], pd.get_dummies(g.animal, drop_first=True, dtype=float)], axis=1))
                fe = sm.OLS(g[y], Xf).fit(cov_type="HC3")
                rows.append({"scores": lab, "quantity": q, "model": spec, "n": len(g), "within_animal_slope": fe.params[x],
                             "ci_lo": fe.conf_int().loc[x, 0], "ci_hi": fe.conf_int().loc[x, 1], "p": fe.pvalues[x],
                             "day_temp_coef": fe.params.get("day_temp_anom", np.nan), "night_temp_coef": fe.params.get("night_temp_anom", np.nan)})
    T3 = pd.DataFrame(rows)
    T3.to_csv(rd / "ephys_spikes_sleep_schedule_phase4_t3_2026c.csv", index=False)
    print(T3.round(3).to_string(index=False), flush=True)

    # T4 hazard by temperature tertile
    s4 = st[st.has_anchor == 1].copy()
    s4["n_tot"] = s4.n_since + s4.elapsed
    s4["tert"] = pd.qcut(s4.temp_anom, 3, labels=["colder", "usual", "warmer"])
    edges = np.r_[0, 60, 240, 480, 720, 1200, 1800, 3600]
    s4["nb"] = pd.cut(s4.n_tot, edges, right=False)
    T4 = s4.groupby(["tert", "nb"], observed=True).agg(n=("y", "size"), hR=("y", lambda v: (v == 1).mean()), hW=("y", lambda v: (v == 2).mean())).reset_index()
    T4["nb"] = T4.nb.astype(str)
    T4.to_csv(rd / "ephys_spikes_sleep_schedule_phase4_t4_2026c.csv", index=False)
    L = ["# Internal sleep schedule — Phase 4: ambient temperature as a slow REM gate (cohort 2026c)", "",
         f"Plan Amendment 6 (written before results). Driver `ephys/sleep_schedule.py phase4` → `ephys/sleep_schedule_temp.py` "
         f"(commit {gc}); bulk `{out}`. **Technical ledger; no claim audit yet.**", "", "## Definitions", "", "```",
         (sys.modules[__name__].__doc__ or "").strip(), "```", "", "## Weather", "", md_table(wsum.round(2)), "",
         "## T1 Held out: does the temperature anomaly add to REM-entry prediction?", "", md_table(T1.round(4)), "",
         "## T2 Hourly shares vs the temperature anomaly", "", md_table(T2.round(4)), "",
         "## T3 Night -> next-day trade-off with temperature as a covariate", "", md_table(T3.round(3)), "",
         "## T4 Empirical hazards by temperature-anomaly tertile", "", md_table(T4.round(4)), ""]
    flat = [ln for x in L for ln in (x if isinstance(x, list) else [x])]
    (rd / "ephys_spikes_sleep_schedule_phase4_2026c.md").write_text("\n".join(flat) + "\n", encoding="utf-8")
    write_json(rd / "run_manifest_sleep_schedule_phase4_2026c.json", {"run_dir": str(out), "git_commit": gc})
    print("written", rd / "ephys_spikes_sleep_schedule_phase4_2026c.md")
