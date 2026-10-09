"""NREM sharp-wave ripples vs ambient temperature, day vs night (cohort 2026c). Plan, definitions and tests fixed before any
result: implementation_plan/2026-10-08-swr-temperature.md.

Data: the SWR production (storage 3rd_rat/analysis/swr/, sessions of tier validated + good from
reports/ephys_spikes_swr_quality_2026c.csv), events with excluded == False and state == NREM; the final 1-s sleep states;
on-site weather (sleep_quant.load_weather) and its anomaly (sleep_schedule_temp.weather_anomaly); day = [sunrise, sunset).
Exclusions: after use_until; after 09-11 19:40 (females; sensitivity to the paddock end); the first 30 min of every session
(handling); probe-advance settle windows; bins with < 5 min NREM; bins straddling sunrise / sunset.
Per animal x block x 30-min bin: rate r = events / NREM min, frequency f = median Hz, duration d = median ms, relative
amplitude A = median amplitude / the block reference's NREM median.
Model per outcome (WLS, weights = NREM minutes, SEs clustered by date, t(G-1)):
    y = alpha_{animal x block} + bT*T + bN*night + bTN*T*night + g*day
-> day slope bT, night slope bT + bTN, night - day difference at the mean T; per animal; T = temp_C (T1, T3) or temp_anom (T2).
Amendment 1 (after a Fable audit): model H = the same + hour-of-day harmonics (k = 1, 2); animal-level inference;
leave-one-animal-out; hour profile; verdict = Established / Candidate / No (see the plan).

  python ephys/swr_temperature.py run [--swr-root …] [--states-root …]
  python ephys/swr_temperature.py rate       (Amendment 2: day / night ripple RATE per period, from the saved bins)
  python ephys/swr_temperature.py extremes   (rate at the hottest vs the coldest time of each day)
  python ephys/swr_temperature.py --selftest
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _common import git_commit, report_dir, write_json  # noqa: E402

COHORT = "2026c"
FEMALES = pd.Timestamp("2026-09-11 19:40")
PADDOCK_END = pd.Timestamp("2026-09-12 10:10")
DAY0 = pd.Timestamp("2026-08-31")
HANDLING = pd.Timedelta(minutes=30)
MIN_NREM_MIN = 5.0
OUTCOMES = {"f": ("ripple frequency", "Hz"), "r": ("NREM ripple rate", "/NREM min"), "d": ("duration", "ms"),
            "A": ("relative amplitude", "x block reference")}


# ------------------------------------------------------------------ data
def sessions(quality_csv: Path, review_csv: Path, tiers) -> pd.DataFrame:
    q = pd.read_csv(quality_csv)
    q = q[q.tier.isin(tiers)].copy()
    rv = pd.read_csv(review_csv)[["animal", "session", "start_local"]]
    q = q.merge(rv, on=["animal", "session"], how="left")
    q["start_t"] = pd.to_datetime(q.start_local.fillna(q.start))
    q["use_until_t"] = pd.to_datetime(q.use_until.fillna("").str.slice(0, 19), errors="coerce")
    # a first block (valid_from null) is read back as NaN, and groupby drops NaN keys: name it
    q["block_from"] = q.block_from.fillna("start").astype(str).replace({"None": "start", "nan": "start"})
    return q.reset_index(drop=True)


def settle_windows(cohort_yaml: Path) -> list:
    import yaml
    eph = yaml.safe_load(open(cohort_yaml))["ephys"]
    return [(m["animal"], pd.Timestamp(m["time"]), pd.Timestamp(m["time"]) + pd.Timedelta(hours=float(m.get("settle_h", 4))))
            for m in eph.get("probe_moves", [])]


def keep_mask(t: pd.Series, row, end: pd.Timestamp, windows) -> np.ndarray:
    k = (t >= row.start_t + HANDLING) & (t < end)
    if pd.notna(row.use_until_t):
        k &= t < row.use_until_t
    for an, a0, a1 in windows:
        if an == row.animal:
            k &= ~((t >= a0) & (t < a1))
    return np.asarray(k)


def load_session(row, swr_root: Path, states_root: Path, end: pd.Timestamp, windows):
    """(NREM events, NREM seconds) of one session after the exclusions, on the start_local clock."""
    sf = states_root / row.animal / f"{row.session}.states.npz"
    if not sf.exists():  # no sleep states (tier check): NREM undefined, the session cannot enter
        return pd.DataFrame(columns=["t", "f", "d", "amp", "animal", "session", "block", "tier"]), \
            pd.DataFrame(columns=["t", "animal", "block"])
    z = np.load(swr_root / row.animal / row.session / f"{row.session}.swr_events.npz", allow_pickle=True)
    m = (~z["excluded"].astype(bool)) & (z["state"] == "NREM")
    ev = pd.DataFrame({"t": row.start_t + pd.to_timedelta(z["peak_s"][m], unit="s"), "f": z["frequency_hz"][m],
                       "d": z["duration_ms"][m], "amp": z["amplitude"][m]})
    with np.load(states_root / row.animal / f"{row.session}.states.npz") as s:
        ts = s["ts"][s["state"] == 3].astype(float)
    nrem = pd.Series(row.start_t + pd.to_timedelta(ts, unit="s"))
    ev = ev[keep_mask(ev.t, row, end, windows)]
    nrem = nrem[keep_mask(nrem, row, end, windows)]
    for c, v in (("animal", row.animal), ("session", row.session), ("block", row.block_from), ("tier", row.tier)):
        ev[c] = v
    return ev, pd.DataFrame({"t": nrem.values, "animal": row.animal, "block": row.block_from})


def ref_amplitudes(q: pd.DataFrame, swr_root: Path) -> dict:
    out = {}
    for (an, bf), g in q.groupby(["animal", "block_from"]):
        ref = g.reference.iloc[0]
        f = swr_root / an / ref / f"{ref}.swr_events.npz"
        if not f.exists():
            continue
        z = np.load(f, allow_pickle=True)
        m = (~z["excluded"].astype(bool)) & (z["state"] == "NREM")
        out[(an, bf)] = float(np.median(z["amplitude"][m]))
    return out


def phase_of_bins(b0: pd.Series, width: pd.Timedelta) -> pd.Series:
    """'day' / 'night' by the bin centre; None for bins that contain sunrise or sunset."""
    from sleep_quant import sun_times
    out = []
    for t0 in b0:
        t1, c = t0 + width, t0 + width / 2
        sr, ss = (pd.Timestamp(x) for x in sun_times(c.date()))
        if (t0 < sr < t1) or (t0 < ss < t1):
            out.append(None)
        else:
            out.append("day" if sr <= c < ss else "night")
    return pd.Series(out, index=b0.index)


def build_bins(ev: pd.DataFrame, nrem: pd.DataFrame, refamp: dict, w: pd.DataFrame, width: str) -> pd.DataFrame:
    W = pd.Timedelta(width)
    ev = ev.assign(b0=ev.t.dt.floor(width))
    nrem = nrem.assign(b0=nrem.t.dt.floor(width))
    nb = nrem.groupby(["animal", "block", "b0"]).size().rename("nrem_s")
    g = ev.groupby(["animal", "block", "b0"])
    eb = pd.DataFrame({"n": g.size(), "f": g.f.median(), "d": g.d.median(), "amp": g.amp.median()})
    b = pd.concat([nb, eb], axis=1).reset_index()
    b["n"] = b.n.fillna(0)
    b["N"] = b.nrem_s.fillna(0) / 60
    b = b[b.N >= MIN_NREM_MIN].copy()
    b["r"] = b.n / b.N
    b["A"] = [a / refamp.get((an, bf), np.nan) for a, an, bf in zip(b.amp, b.animal, b.block)]
    b["phase"] = phase_of_bins(b.b0, W).values
    b = b[b.phase.notna()].copy()
    ws = w.set_index("t")[["temp_C", "temp_anom"]]
    tm = ws.groupby(ws.index.floor(width)).mean()
    b = b.join(tm, on="b0")
    b["night"] = (b.phase == "night").astype(float)
    c = b.b0 + W / 2
    b["hour"] = c.dt.hour + c.dt.minute / 60
    for k in (1, 2):  # Amendment 1: time-of-day harmonics
        b[f"hs{k}"] = np.sin(2 * np.pi * k * b.hour / 24)
        b[f"hc{k}"] = np.cos(2 * np.pi * k * b.hour / 24)
    b["day"] = (b.b0 - DAY0) / pd.Timedelta(days=1)
    b["date"] = b.b0.dt.strftime("%Y-%m-%d")
    b["ab"] = b.animal + "|" + b.block.astype(str)
    return b.dropna(subset=["temp_C"]).reset_index(drop=True)


# ------------------------------------------------------------------ statistics
def fit(b: pd.DataFrame, y: str, tcol: str, trend: bool = True, hour: bool = False) -> dict:
    """WLS y ~ C(ab) + T + night + T:night [+ day] [+ hour harmonics k=1,2 (model H, Amendment 1)], weights N, SE clustered by
    date (CR1, t(G-1))."""
    import statsmodels.formula.api as smf
    from scipy import stats
    d = b.dropna(subset=[y, tcol]).copy()
    d = d.rename(columns={tcol: "T"})
    if d.ab.nunique() > 1:
        rhs = "C(ab) + T + night + T:night" + (" + day" if trend else "")
    else:
        rhs = "T + night + T:night" + (" + day" if trend else "")
    if hour:
        rhs += " + hs1 + hc1 + hs2 + hc2"
    if d.phase.nunique() < 2:
        rhs = rhs.replace(" + night + T:night", "")
    G = d.date.nunique()
    if G < 3 or len(d) < 8:
        return dict(outcome=y, temp=tcol, n_bins=len(d), n_dates=G)
    m = smf.wls(f"{y} ~ {rhs}", data=d, weights=d.N).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d.date)[0],
                                                                                        "use_correction": True})
    V, p_ = m.cov_params(), m.params
    tq = stats.t.ppf(0.975, G - 1)

    def lin(c: dict):
        est = sum(p_[k] * v for k, v in c.items())
        se = float(np.sqrt(sum(V.loc[i, j] * c[i] * c[j] for i in c for j in c)))
        pv = float(2 * stats.t.sf(abs(est / se), G - 1)) if se > 0 else np.nan
        return est, se, est - tq * se, est + tq * se, pv

    out = dict(outcome=y, temp=tcol, n_bins=len(d), n_dates=G, n_units=d.ab.nunique())
    if "T:night" in p_:
        for nm, c in (("day", {"T": 1}), ("night", {"T": 1, "T:night": 1}), ("diff", {"T:night": 1})):
            e, s, lo, hi, pv = lin(c)
            out.update({f"slope_{nm}": e, f"se_{nm}": s, f"lo_{nm}": lo, f"hi_{nm}": hi, f"p_{nm}": pv})
        e, s, lo, hi, pv = lin({"night": 1, "T:night": float(d["T"].mean())})
        out.update(night_minus_day=e, nmd_lo=lo, nmd_hi=hi, nmd_p=pv)
    else:
        e, s, lo, hi, pv = lin({"T": 1})
        out.update(slope_all=e, lo_all=lo, hi_all=hi, p_all=pv)
    return out


def per_animal(b: pd.DataFrame, y: str, tcol: str, trend: bool = True, hour: bool = False) -> pd.DataFrame:
    rows = []
    for an, g in b.groupby("animal"):
        r = fit(g, y, tcol, trend, hour)
        r["animal"] = an
        rows.append(r)
    return pd.DataFrame(rows)


def animal_level(pa: pd.DataFrame) -> dict:
    """Amendment 1: mean of the per-animal slopes with a t(n-1) 95 % CI, per phase."""
    from scipy import stats
    out = {}
    for ph in ("day", "night"):
        s = pa[f"slope_{ph}"].dropna() if f"slope_{ph}" in pa else pd.Series(dtype=float)
        n = len(s)
        if n >= 3:
            m, se = float(s.mean()), float(s.std(ddof=1) / np.sqrt(n))
            tq = stats.t.ppf(0.975, n - 1)
            out.update({f"al_{ph}": m, f"al_lo_{ph}": m - tq * se, f"al_hi_{ph}": m + tq * se,
                        f"al_p_{ph}": float(2 * stats.t.sf(abs(m / se), n - 1)) if se > 0 else np.nan, f"al_n_{ph}": n})
    return out


def loao(b: pd.DataFrame, y: str, tcol: str, hour: bool) -> pd.DataFrame:
    """Amendment 1: the pooled model refitted without each animal in turn."""
    return pd.DataFrame([dict(fit(b[b.animal != an], y, tcol, hour=hour), left_out=an) for an in sorted(b.animal.unique())])


def hour_profile(b: pd.DataFrame) -> pd.DataFrame:
    """Amendment 1 (descriptive): outcomes minus their animal x block mean (NREM-minute weighted), averaged per clock hour,
    with the mean outdoor temperature of those bins."""
    d = b.copy()
    for y in OUTCOMES:
        mu = d.dropna(subset=[y]).groupby("ab").apply(lambda g: np.average(g[y], weights=g.N))
        d[f"{y}_dm"] = d[y] - d.ab.map(mu)
    d["h"] = d.hour.astype(int)
    rows = []
    for h, g in d.groupby("h"):
        row = {"hour": h, "bins": len(g), "animals": g.animal.nunique(), "share_night": float(g.night.mean()),
               "temp_C": float(g.temp_C.mean())}
        for y in OUTCOMES:
            gg = g.dropna(subset=[f"{y}_dm"])
            row[f"{y}_dm"] = float(np.average(gg[f"{y}_dm"], weights=gg.N)) if len(gg) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def day_night(b: pd.DataFrame) -> pd.DataFrame:
    """Per animal: NREM-minute-weighted means by phase, and the paired per-date difference night(D) - day(D), where night(D)
    = [sunset D, sunrise D+1)."""
    from sleep_quant import sun_times
    rows = []
    for an, g in b.groupby("animal"):
        row = {"animal": an, "bins_day": int((g.phase == "day").sum()), "bins_night": int((g.phase == "night").sum()),
               "nrem_h_day": g[g.phase == "day"].N.sum() / 60, "nrem_h_night": g[g.phase == "night"].N.sum() / 60}
        c = g.b0 + pd.Timedelta(minutes=15)
        biod = []
        for t in c:
            sr, _ = sun_times(t.date())
            biod.append((t.normalize() - pd.Timedelta(days=1)) if t < pd.Timestamp(sr) else t.normalize())
        g = g.assign(bio=biod)
        for y in OUTCOMES:
            for ph in ("day", "night"):
                h = g[(g.phase == ph) & g[y].notna()]
                row[f"{y}_{ph}"] = float(np.average(h[y], weights=h.N)) if len(h) else np.nan
            per = g.dropna(subset=[y]).groupby(["bio", "phase"]).apply(lambda h: np.average(h[y], weights=h.N)).unstack()
            if {"day", "night"} <= set(per.columns):
                dd = (per.night - per.day).dropna()
                row[f"{y}_night_minus_day"] = float(dd.mean()) if len(dd) else np.nan
                row[f"{y}_nmd_sem"] = float(dd.std(ddof=1) / np.sqrt(len(dd))) if len(dd) > 1 else np.nan
                row[f"{y}_nmd_ndays"] = int(len(dd))
        rows.append(row)
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ run
def assemble(a, tiers, end):
    from sleep_schedule_temp import weather_anomaly
    q = sessions(Path(a.quality), Path(a.review), tiers)
    win = settle_windows(Path(a.cohort_yaml))
    evs, nrs = [], []
    for row in q.itertuples():
        e, n = load_session(row, Path(a.swr_root), Path(a.states_root), end, win)
        evs.append(e)
        nrs.append(n)
    ev, nr = pd.concat(evs, ignore_index=True), pd.concat(nrs, ignore_index=True)
    return q, ev, nr, ref_amplitudes(q, Path(a.swr_root)), weather_anomaly()


TEMPS = ("temp_C", "temp_anom")


def run(a):
    from output_paths import run_dir
    out = run_dir("swr_temperature", COHORT)
    rd = report_dir(COHORT)
    q, ev, nr, refamp, w = assemble(a, ["validated", "good"], FEMALES)
    ev.to_csv(out / "nrem_events.csv.gz", index=False)
    w.to_csv(out / "weather_anomaly.csv.gz", index=False)
    b = build_bins(ev, nr, refamp, w, "30min")
    b.to_csv(out / "bins_30min.csv.gz", index=False)
    print(f"primary: {len(q)} sessions, {len(ev)} NREM events loaded, {int(b.n.sum())} in {len(b)} bins "
          f"({b.animal.nunique()} animals, {b.date.nunique()} dates)", flush=True)
    vab = (q[q.tier == "validated"].animal + "|" + q[q.tier == "validated"].block_from.astype(str)).unique()
    bv = b[b.ab.isin(vab)]
    res, pas = [], []
    for model, hr in (("P", False), ("H", True)):
        for y in OUTCOMES:
            for tc in TEMPS:
                r = fit(b, y, tc, hour=hr)
                pa_ = per_animal(b, y, tc, hour=hr)
                r.update(animal_level(pa_))
                rv = fit(bv, y, tc, hour=hr)
                r.update({f"val_{k}": rv.get(k) for k in ("slope_day", "lo_day", "hi_day", "slope_night", "lo_night", "hi_night")})
                res.append(dict(r, model=model))
                pas.append(pa_.assign(model=model))
    R, PA = pd.DataFrame(res), pd.concat(pas, ignore_index=True)
    V = verdict(R, PA)
    dn = day_night(b)
    hp = hour_profile(b)
    _, ev_c, nr_c, ref_c, _ = assemble(a, ["validated", "good", "check"], FEMALES)
    bc = build_bins(ev_c, nr_c, ref_c, w, "30min")
    _, ev_p, nr_p, ref_p, _ = assemble(a, ["validated", "good"], PADDOCK_END)
    bp = build_bins(ev_p, nr_p, ref_p, w, "30min")
    b60 = build_bins(ev, nr, refamp, w, "60min")
    evb = ev.assign(b0=ev.t.dt.floor("30min")).merge(
        b[["animal", "block", "b0", "temp_C", "temp_anom", "night", "day", "date", "ab", "phase", "hs1", "hc1", "hs2", "hc2"]],
        on=["animal", "block", "b0"])
    evb = evb.sample(min(len(evb), 400_000), random_state=0).assign(N=1.0)
    sens = []
    for model, hr in (("P", False), ("H", True)):
        for tc in TEMPS:
            sens.append(dict(fit(b, "f", tc, trend=False, hour=hr), analysis="no day trend", model=model))
            for nm, bb in (("+ check sessions", bc), ("to the paddock end (females)", bp), ("validated blocks only", bv),
                           ("1-h bins", b60), ("event level (400k events)", evb)):
                sens.append(dict(fit(bb, "f", tc, hour=hr), analysis=nm, model=model))
    S = pd.DataFrame(sens)
    LO = pd.concat([loao(b, y, tc, True).assign(outcome=y, temp=tc) for y in ("f", "r") for tc in TEMPS], ignore_index=True)
    for df_, nm in ((R, "tests"), (PA, "per_animal"), (V, "verdict"), (dn, "day_night"), (S, "sensitivity"), (LO, "loao"),
                    (hp, "hour_profile")):
        df_.to_csv(rd / f"ephys_spikes_swr_temperature_{nm}_{COHORT}.csv", index=False)
    figs = figures(b, R, rd) + [hour_figure(hp)]
    write_report(a, q, ev, b, R, PA, V, dn, S, LO, hp, figs, rd, out)
    write_json(rd / f"run_manifest_swr_temperature_{COHORT}.json",
               dict(name="swr_temperature", run_dir=str(out), git=git_commit(), sessions=len(q), events_loaded=len(ev),
                    events_in_bins=int(b.n.sum()), bins=len(b), plan="implementation_plan/2026-10-08-swr-temperature.md (+ Amendment 1)"))
    print(f"wrote {rd / f'ephys_spikes_swr_temperature_{COHORT}.md'}; run folder {out}")


def verdict(R: pd.DataFrame, PA: pd.DataFrame) -> pd.DataFrame:
    """Amendment 1 rule on model H: Established = H CI excludes 0 + animal-level CI excludes 0 + >= 4 animals share the sign +
    validated blocks only the same sign with a CI excluding 0; Candidate = the H CI excludes 0, another criterion fails."""
    rows = []
    for r in R[R.model == "H"].itertuples():
        g = PA[(PA.model == "H") & (PA.outcome == r.outcome) & (PA.temp == r.temp)]
        for ph in ("day", "night"):
            s, lo, hi = (getattr(r, f"{k}_{ph}", np.nan) for k in ("slope", "lo", "hi"))
            an = g[f"slope_{ph}"].dropna() if f"slope_{ph}" in g else pd.Series(dtype=float)
            agree = int((np.sign(an) == np.sign(s)).sum())
            c1 = bool(np.isfinite(lo) and (lo > 0 or hi < 0))
            al, alo, ahi = (getattr(r, f"{k}_{ph}", np.nan) for k in ("al", "al_lo", "al_hi"))
            c2 = bool(np.isfinite(alo) and (alo > 0 or ahi < 0) and np.sign(al) == np.sign(s))
            c3 = agree >= min(4, len(an))
            vs, vlo, vhi = (getattr(r, f"val_{k}_{ph}", np.nan) for k in ("slope", "lo", "hi"))
            c4 = bool(vlo is not None and np.isfinite(vlo) and (vlo > 0 or vhi < 0) and np.sign(vs) == np.sign(s))
            v = "Established" if c1 and c2 and c3 and c4 else "Candidate" if c1 else "No"
            rows.append(dict(outcome=r.outcome, temp=r.temp, phase=ph, slope=s, lo=lo, hi=hi, animal_mean=al, animal_lo=alo,
                             animal_hi=ahi, animals_same_sign=agree, animals=len(an), validated_slope=vs, validated_lo=vlo,
                             validated_hi=vhi, c_pooled=c1, c_animal=c2, c_sign=c3, c_validated=c4, verdict=v))
    return pd.DataFrame(rows)


def hour_figure(hp: pd.DataFrame) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from _common import figure_dir
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.2))
    for ax, (y, lab) in zip(axes, (("f_dm", "frequency - block mean (Hz)"), ("r_dm", "rate - block mean (/NREM min)"))):
        ax.bar(hp.hour, hp[y], color=["#2b4f8a" if s > 0.5 else "#d98c00" for s in hp.share_night])
        ax.axhline(0, color="0.5", lw=0.6)
        ax.set_xlabel("clock hour (bin centre)", fontsize=8)
        ax.set_ylabel(lab, fontsize=8)
    axes[2].plot(hp.hour, hp.temp_C, "o-", color="0.4", ms=3)
    axes[2].set_xlabel("clock hour", fontsize=8)
    axes[2].set_ylabel("outdoor temperature of these bins (degC)", fontsize=8)
    for ax in axes:
        ax.tick_params(labelsize=7)
    fig.suptitle("NREM ripples by time of day (bins of all animals, within-block deviations; blue = mostly night bins)", fontsize=9)
    fig.tight_layout()
    p = figure_dir(COHORT) / f"ephys_spikes_swr_temperature_hour_profile_{COHORT}.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    return p


def figures(b: pd.DataFrame, R: pd.DataFrame, rd: Path) -> list:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from _common import figure_dir
    fd = figure_dir(COHORT)
    col = {"day": "#d98c00", "night": "#2b4f8a"}
    animals = sorted(b.animal.unique())
    out = []
    fig, axes = plt.subplots(len(OUTCOMES), len(animals), figsize=(2.6 * len(animals), 2.3 * len(OUTCOMES)), squeeze=False)
    for i, y in enumerate(OUTCOMES):
        for j, an in enumerate(animals):
            ax = axes[i, j]
            g = b[b.animal == an]
            for ph in ("day", "night"):
                h = g[(g.phase == ph) & g[y].notna()]
                ax.scatter(h.temp_C, h[y], s=6, alpha=0.5, color=col[ph], label=ph)
                if len(h) > 5:
                    k = np.polyfit(h.temp_C, h[y], 1, w=np.sqrt(h.N))
                    xs = np.linspace(h.temp_C.min(), h.temp_C.max(), 10)
                    ax.plot(xs, np.polyval(k, xs), color=col[ph], lw=1.2)
            if i == 0:
                ax.set_title(an, fontsize=9)
            if j == 0:
                ax.set_ylabel(f"{OUTCOMES[y][0]}\n({OUTCOMES[y][1]})", fontsize=8)
            if i == len(OUTCOMES) - 1:
                ax.set_xlabel("outdoor temperature (degC)", fontsize=8)
            ax.tick_params(labelsize=7)
    axes[0, 0].legend(fontsize=7, frameon=False)
    fig.suptitle("NREM ripples per 30-min bin vs outdoor temperature (raw scatter; lines = within-animal WLS fits, "
                 "blocks pooled - the model uses block intercepts + day trend)", fontsize=9)
    fig.tight_layout()
    p = fd / f"ephys_spikes_swr_temperature_scatter_{COHORT}.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    out.append(p)
    fig, axes = plt.subplots(len(animals), 1, figsize=(12, 1.9 * len(animals)), sharex=True, squeeze=False)
    for j, an in enumerate(animals):
        ax = axes[j, 0]
        g = b[b.animal == an]
        for ph in ("day", "night"):
            h = g[g.phase == ph]
            ax.scatter(h.b0, h.f, s=5, color=col[ph])
        ax.set_ylabel(f"{an}\nf (Hz)", fontsize=8)
        ax2 = ax.twinx()
        t = b.drop_duplicates("b0").sort_values("b0")
        ax2.plot(t.b0, t.temp_C, color="0.6", lw=0.7)
        ax2.set_ylabel("degC", fontsize=7, color="0.5")
        ax.tick_params(labelsize=7)
        ax2.tick_params(labelsize=7)
    fig.suptitle("NREM ripple frequency per 30-min bin (day orange, night blue) and outdoor temperature (grey)", fontsize=9)
    fig.tight_layout()
    p = fd / f"ephys_spikes_swr_temperature_timeline_{COHORT}.png"
    fig.savefig(p, dpi=110)
    plt.close(fig)
    out.append(p)
    return out


def fmt(x, nd=2):
    return "" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{nd}f}"


def write_report(a, q, ev, b, R, PA, V, dn, S, LO, hp, figs, rd, out):
    L = []
    w = L.append
    TN = {"temp_C": "outdoor T", "temp_anom": "T anomaly (vs the usual for the hour)"}
    w(f"# NREM sharp-wave ripples vs ambient temperature, day vs night ({COHORT})")
    w("")
    w(f"Generated by `ephys/swr_temperature.py run` (repo `{git_commit()}`). Plan with the original definitions and tests fixed "
      f"before any result, plus **Amendment 1** (written after the first result and a Fable audit): "
      f"[`implementation_plan/2026-10-08-swr-temperature.md`](../../../../implementation_plan/2026-10-08-swr-temperature.md). "
      f"Run folder (event / bin tables): `{out}`.")
    w("")
    w("## Summary")
    w("")
    hpf = hp.dropna(subset=["f_dm"])
    hr = hp.dropna(subset=["r_dm"])
    est = V[V.verdict == "Established"]
    cand = V[V.verdict == "Candidate"]
    w(f"- **Time of day dominates.** Within animal x block, NREM ripple frequency runs from {hpf.f_dm.max():+.1f} Hz "
      f"(hour {int(hpf.loc[hpf.f_dm.idxmax(), 'hour'])}) to {hpf.f_dm.min():+.1f} Hz (hour {int(hpf.loc[hpf.f_dm.idxmin(), 'hour'])}) "
      f"around its block mean, and the NREM ripple rate from {hr.r_dm.max():+.1f} to {hr.r_dm.min():+.1f} /NREM min "
      f"(hour profile below). Outdoor temperature follows the same clock, so the original model (no hour term) read part "
      f"of this as a temperature slope.")
    w("- **Ambient temperature effects (Amendment 1 rule, model H = hour of day held fixed): "
      + ("; ".join(f"{OUTCOMES[x.outcome][0]} vs {TN[x.temp]}, {x.phase}: {x.slope:+.3f} per degC" for x in est.itertuples())
         if len(est) else "none Established") + "."
      + (" Candidates (pooled CI excludes 0, another criterion fails): "
         + "; ".join(f"{OUTCOMES[x.outcome][0]} vs {TN[x.temp]}, {x.phase} ({x.slope:+.3f}; fails: "
                     + ", ".join(k for k, c in (("animal-level", x.c_animal), ("sign agreement", x.c_sign),
                                               ("validated blocks", x.c_validated)) if not c) + ")" for x in cand.itertuples())
         if len(cand) else "") + "**")
    dnf = dn.dropna(subset=["f_night", "f_day"])
    w(f"- **Night vs day (descriptive):** night NREM ripples are faster than day NREM ripples in "
      f"{int((dnf.f_night > dnf.f_day).sum())} / {len(dnf)} animals (paired per date "
      f"{dn.f_night_minus_day.min():+.1f} to {dn.f_night_minus_day.max():+.1f} Hz) and more frequent in "
      f"{int((dn.r_night > dn.r_day).sum())} / {len(dn)}. Night is colder, so this is the opposite of a direct "
      f"warm-outside -> warm-brain -> faster-ripple effect; a brain temperature set by the activity cycle (highest at the end "
      f"of the active phase) or sleep pressure fits better - neither is measured here (no head / brain temperature).")
    w("")
    w("## Verdict (Amendment 1 rule; model H)")
    w("")
    w("Established = the pooled model-H CI excludes 0 AND the animal-level CI (mean of per-animal slopes, t(n-1)) excludes 0 AND "
      ">= 4 animals share the sign AND validated blocks only give the same sign with a CI excluding 0; Candidate = the pooled CI "
      "excludes 0 but another criterion fails.")
    w("")
    w("| Outcome | Temperature | Phase | Pooled slope /degC [95 % CI] | Animal-level mean [CI] | Same sign | Validated blocks [CI] | Verdict |")
    w("|---|---|---|---|---|---|---|---|")
    for x in V.itertuples():
        w(f"| {OUTCOMES[x.outcome][0]} | {x.temp} | {x.phase} | {fmt(x.slope, 3)} [{fmt(x.lo, 3)}, {fmt(x.hi, 3)}] | "
          f"{fmt(x.animal_mean, 3)} [{fmt(x.animal_lo, 3)}, {fmt(x.animal_hi, 3)}] | {x.animals_same_sign} / {x.animals} | "
          f"{fmt(x.validated_slope, 3)} [{fmt(x.validated_lo, 3)}, {fmt(x.validated_hi, 3)}] | **{x.verdict}** |")
    w("")
    w("### Leave one animal out (model H)")
    w("")
    w("| Outcome | Temperature | Left out | Day slope [CI] | Night slope [CI] |")
    w("|---|---|---|---|---|")
    for x in LO.itertuples():
        w(f"| {OUTCOMES[x.outcome][0]} | {x.temp} | {x.left_out} | {fmt(x.slope_day, 3)} [{fmt(x.lo_day, 3)}, {fmt(x.hi_day, 3)}] | "
          f"{fmt(x.slope_night, 3)} [{fmt(x.lo_night, 3)}, {fmt(x.hi_night, 3)}] |")
    w("")
    w("## Time-of-day profile (descriptive, Amendment 1)")
    w("")
    w("| Hour | Bins | Animals | Night share | Outdoor T (degC) | f - block mean (Hz) | r - block mean (/min) | d - block mean (ms) | A - block mean |")
    w("|---|---|---|---|---|---|---|---|---|")
    for x in hp.itertuples():
        w(f"| {x.hour:02d} | {x.bins} | {x.animals} | {x.share_night:.2f} | {x.temp_C:.1f} | {fmt(x.f_dm, 2)} | {fmt(x.r_dm, 1)} | "
          f"{fmt(x.d_dm, 2)} | {fmt(x.A_dm, 3)} |")
    w("")
    w("## Data")
    w("")
    per = b.groupby("animal").agg(bins=("N", "size"), nrem_h=("N", lambda x: x.sum() / 60), dates=("date", "nunique"),
                                  events=("n", "sum"), T_min=("temp_C", "min"), T_max=("temp_C", "max"))
    w(f"- {len(q)} sessions of tier validated / good (quality guide); {len(ev):,} kept NREM events loaded after the exclusions, "
      f"{int(b.n.sum()):,} of them in the {len(b)} 30-min bins with >= {MIN_NREM_MIN:.0f} min NREM that are not crossed by "
      f"sunrise / sunset and have weather; {b.date.nunique()} dates, to 09-11 19:40.")
    w("")
    w("| Animal | Bins | NREM h | Dates | Events in bins | Outdoor T range (degC) |")
    w("|---|---|---|---|---|---|")
    for an, r in per.iterrows():
        w(f"| {an} | {int(r.bins)} | {r.nrem_h:.1f} | {int(r.dates)} | {int(r.events):,} | {r.T_min:.1f} - {r.T_max:.1f} |")
    w("")
    w("## All slopes: original pre-registered model P (no hour term) and model H")
    w("")
    w("Slopes per degC (95 % CI, SEs clustered by date, t(G-1)); weights = NREM minutes; animal x block intercepts + day trend.")
    w("")
    w("| Model | Outcome | Temperature | Day slope | Night slope | Night - day at mean T (model P only) | Animal-level day / night |")
    w("|---|---|---|---|---|---|---|")
    for r in R.itertuples():
        nmd = f"{fmt(r.night_minus_day, 2)} [{fmt(r.nmd_lo, 2)}, {fmt(r.nmd_hi, 2)}]" if r.model == "P" else ""
        w(f"| {r.model} | {OUTCOMES[r.outcome][0]} | {r.temp} | {fmt(r.slope_day, 3)} [{fmt(r.lo_day, 3)}, {fmt(r.hi_day, 3)}] | "
          f"{fmt(r.slope_night, 3)} [{fmt(r.lo_night, 3)}, {fmt(r.hi_night, 3)}] | {nmd} | "
          f"{fmt(getattr(r, 'al_day', np.nan), 3)} / {fmt(getattr(r, 'al_night', np.nan), 3)} |")
    w("")
    w("The original verdict rule (CI excludes 0 + >= 4 animals share the sign) applied to model P passed frequency day / night "
      "and night anomaly; the audit showed these are time of day and two non-validated animals - see the verdict above.")
    w("")
    w("### Per animal (model H)")
    w("")
    animals = sorted(PA.animal.unique())
    w("| Outcome | Temperature | " + " | ".join(animals) + " |")
    w("|---|---|" + "---|" * len(animals))
    for (y, tc), g in PA[PA.model == "H"].groupby(["outcome", "temp"], sort=False):
        g = g.set_index("animal")
        w(f"| {OUTCOMES[y][0]} | {tc} | " + " | ".join(
            f"d {fmt(g.loc[an].get('slope_day'), 2)} / n {fmt(g.loc[an].get('slope_night'), 2)}" if an in g.index else "" for an in animals) + " |")
    w("")
    w("## Day vs night (descriptive; per animal, NREM-minute-weighted bin means; paired = night(D) - day(D) over dates)")
    w("")
    w("| Animal | NREM h day / night | f day / night (Hz) | night - day f (SEM, days) | r day / night | night - day r | d day / night (ms) | A day / night |")
    w("|---|---|---|---|---|---|---|---|")
    for r in dn.itertuples():
        w(f"| {r.animal} | {r.nrem_h_day:.1f} / {r.nrem_h_night:.1f} | {fmt(r.f_day, 1)} / {fmt(r.f_night, 1)} | "
          f"{fmt(getattr(r, 'f_night_minus_day', np.nan), 2)} ({fmt(getattr(r, 'f_nmd_sem', np.nan), 2)}, {getattr(r, 'f_nmd_ndays', '')}) | "
          f"{fmt(r.r_day, 1)} / {fmt(r.r_night, 1)} | {fmt(getattr(r, 'r_night_minus_day', np.nan), 2)} | "
          f"{fmt(r.d_day, 1)} / {fmt(r.d_night, 1)} | {fmt(r.A_day, 2)} / {fmt(r.A_night, 2)} |")
    w("")
    w("## Sensitivity (ripple frequency; models P and H)")
    w("")
    w("| Model | Analysis | Temperature | Day slope [CI] | Night slope [CI] | Bins |")
    w("|---|---|---|---|---|---|")
    for r in S.itertuples():
        w(f"| {r.model} | {r.analysis} | {r.temp} | {fmt(getattr(r, 'slope_day', np.nan), 3)} [{fmt(getattr(r, 'lo_day', np.nan), 3)}, "
          f"{fmt(getattr(r, 'hi_day', np.nan), 3)}] | {fmt(getattr(r, 'slope_night', np.nan), 3)} [{fmt(getattr(r, 'lo_night', np.nan), 3)}, "
          f"{fmt(getattr(r, 'hi_night', np.nan), 3)}] | {r.n_bins} |")
    w("")
    for p in figs:
        w(f"![{p.stem}](../figures/{p.name})")
        w("")
    w("## Definitions")
    w("")
    w("Bins: animal $a$, channel block $b$, 30-min clock bin $k$; $N_k$ = NREM minutes (final 1-s states) after the exclusions; "
      "$E_k$ = the bin's kept NREM events.")
    w("")
    w("- **NREM ripple rate** $r_k = |E_k|/N_k$ (events per NREM minute).")
    w("- **Ripple frequency** $f_k = \\operatorname{median}_{e\\in E_k} f_e$ (Hz); $f_e$ = DetectSWR's frequency at the event's peak "
      "trough = the Hilbert phase derivative of the 80-250 Hz filtered ripple channel (`swr_detect.troughs`). Single values are "
      "unbounded (about 10 % below 100 Hz), hence the median per bin.")
    w("- **Duration** $d_k = \\operatorname{median}_{e\\in E_k} \\mathrm{duration}_e$ (ms).")
    w("- **Relative amplitude** $A_k = \\operatorname{median}_{e\\in E_k}\\mathrm{amp}_e / \\operatorname{median}_{e\\in\\mathrm{NREM(ref}_b)}\\mathrm{amp}_e$ "
      "(amplitude relative to the block's reference session; raw uV depend on channel and probe).")
    w("- **Temperature** $T_k$ = mean outdoor `temp_C` of the bin's 5-min weather samples (degC); $T^{anom}_k$ = mean `temp_anom` = "
      "temp_C minus its fit on (sin, cos)(2 pi k h / 24), k = 1, 2, over the cohort (warmer + / colder - than usual for the hour).")
    w("- **Phase** day = the bin centre in [sunrise, sunset) at the paddock; night = otherwise; bins containing sunrise or sunset dropped.")
    w("- **Model P** (pre-registered) $y_k = \\alpha_{a,b} + \\beta_T T_k + \\beta_N\\,\\mathrm{night}_k + \\beta_{TN} T_k\\,\\mathrm{night}_k + "
      "\\gamma\\,\\mathrm{day}_k + \\varepsilon_k$, WLS weights $N_k$, day slope $\\beta_T$, night slope $\\beta_T+\\beta_{TN}$, SEs clustered "
      "by calendar date (CR1), CI / p from $t(G-1)$.")
    w("- **Model H** (Amendment 1) = model P $+ \\sum_{k=1,2}[a_k\\sin(2\\pi k h_k/24) + b_k\\cos(2\\pi k h_k/24)]$, $h_k$ = clock hour of "
      "the bin centre. Text: the temperature slope at a fixed time of day; with $T^{anom}$, warmer vs colder days at the same hour.")
    w("- **Animal-level CI**: mean of the per-animal model slopes $\\bar s$, $\\bar s \\pm t_{0.975}(n-1)\\,\\mathrm{SD}/\\sqrt n$.")
    w("- **Hour profile**: $y_k - \\bar y_{a,b}$ (NREM-minute-weighted block mean), averaged (weights $N_k$) over bins of the same clock hour.")
    w("- **Exclusions**: after use_until; after 09-11 19:40 (females); the first 30 min of each session file (handling; also file "
      "splits - conservative); probe-advance settle windows; bins with < 5 min NREM.")
    w("")
    w("## Reading rules and limits")
    w("")
    w("- Day and night differ in temperature, and so do the hours within a phase: only model H and the anomaly speak to "
      "temperature, and even they cannot separate ambient temperature from anything that varies with the weather from day to day.")
    w("- Outdoor temperature is not brain temperature: the rats sleep huddled in insulated houses; no logger / head temperature exists.")
    w("- SF08 block 1 (over-selection, late reference) and SF12 block 1 (shank-1 degradation) are the least trustworthy blocks "
      "(quality guide); results carried by them are flagged by the validated-blocks criterion.")
    w("- The frequency estimator correlates weakly with amplitude (r about 0.2 within bins), but amplitude has no temperature "
      "slope and the slopes survive conditioning on amplitude, duration and rate (audit): event composition explains <= ~0.3 Hz.")
    (rd / f"ephys_spikes_swr_temperature_{COHORT}.md").write_text("\n".join(L) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ Amendment 2: day / night ripple RATE per period
def periods(b: pd.DataFrame, hp: pd.DataFrame, split_day: bool = False) -> pd.DataFrame:
    """One row per animal x block x period (day of biological date D = [sunrise D, sunset D); night of D = [sunset D,
    sunrise D+1)), from the 30-min bins: R = sum n / sum N, T = NREM-minute-weighted temperature, hour-adjusted rate."""
    from sleep_quant import sun_times
    d = b.copy()
    c = d.b0 + pd.Timedelta(minutes=15)
    bio = []
    for t in c:
        sr, _ = sun_times(t.date())
        bio.append((t.normalize() - pd.Timedelta(days=1)) if t < pd.Timestamp(sr) else t.normalize())
    d["bio"] = pd.to_datetime(bio).strftime("%m-%d")
    if split_day:  # the user (10-09): day = sunrise -> solar noon (morning) + solar noon -> sunset (afternoon), by bin centre
        st = [tuple(pd.Timestamp(x) for x in sun_times(t.date())) for t in c]
        am = np.asarray([t < sr_ + (ss_ - sr_) / 2 for t, (sr_, ss_) in zip(c, st)])
        isday = (d.phase == "day").to_numpy()
        d.loc[isday & am, "phase"] = "morning"
        d.loc[isday & ~am, "phase"] = "afternoon"
    prof = hp.set_index("hour").r_dm
    d["r_adj"] = d.r - d.hour.astype(int).map(prof).fillna(0)
    rows = []
    for (an, blk, ab, bi, ph), g in d.groupby(["animal", "block", "ab", "bio", "phase"]):
        N = g.N.sum()
        rows.append(dict(animal=an, block=blk, ab=ab, bio=bi, phase=ph, nrem_min=N, n=g.n.sum(), R=g.n.sum() / N,
                         R_adj=float(np.average(g.r_adj, weights=g.N)), T=float(np.average(g.temp_C, weights=g.N)),
                         T_anom=float(np.average(g.temp_anom, weights=g.N)),
                         A=float(np.average(g.A.dropna(), weights=g.N[g.A.notna()])) if g.A.notna().any() else np.nan,
                         day=float(np.average(g.day, weights=g.N)), date=bi, bins=len(g)))
    p = pd.DataFrame(rows)
    return p[p.nrem_min >= 30].reset_index(drop=True)


def fit_period(p: pd.DataFrame, y: str, tcol: str, trend: bool = True) -> dict:
    """WLS y ~ C(ab) + T [+ day], weights = NREM minutes, SEs clustered by biological date, t(G-1)."""
    import statsmodels.formula.api as smf
    from scipy import stats
    d = p.dropna(subset=[y, tcol]).rename(columns={tcol: "TT"})
    G = d.date.nunique()
    if G < 3 or len(d) < 5:
        return dict(n=len(d), dates=G)
    rhs = ("C(ab) + " if d.ab.nunique() > 1 else "") + "TT" + (" + day" if trend else "")
    m = smf.wls(f"{y} ~ {rhs}", data=d, weights=d.nrem_min).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d.date)[0],
                                                                                             "use_correction": True})
    s, se = float(m.params["TT"]), float(m.bse["TT"])
    tq = stats.t.ppf(0.975, G - 1)
    return dict(slope=s, lo=s - tq * se, hi=s + tq * se, p=float(2 * stats.t.sf(abs(s / se), G - 1)), n=len(d), dates=G)


def per_animal_period(p: pd.DataFrame, y: str, tcol: str) -> pd.DataFrame:
    """Per animal across its periods: WLS slope (block intercepts, no trend: few dates per animal), Pearson / Spearman r of the
    block-demeaned y vs T."""
    from scipy import stats
    rows = []
    for an, g in p.dropna(subset=[y, tcol]).groupby("animal"):
        r = dict(animal=an, periods=len(g))
        if len(g) >= 3:
            f = fit_period(g.assign(date=g.date), y, tcol, trend=False) if g.date.nunique() >= 3 else {}
            yd = g[y] - g.groupby("ab")[y].transform("mean")
            r.update(slope=f.get("slope", np.nan), pearson=float(stats.pearsonr(g[tcol], yd)[0]),
                     spearman=float(stats.spearmanr(g[tcol], yd)[0]))
        rows.append(r)
    return pd.DataFrame(rows)


def rate_analysis(a):
    split = bool(getattr(a, "split_day", False))
    sfx = "_daysplit" if split else ""
    from scipy import stats
    rd = report_dir(COHORT)
    man = json.loads((rd / f"run_manifest_swr_temperature_{COHORT}.json").read_text())
    b = pd.read_csv(Path(man["run_dir"]) / "bins_30min.csv.gz", parse_dates=["b0"])
    hp = pd.read_csv(rd / f"ephys_spikes_swr_temperature_hour_profile_{COHORT}.csv")
    q = pd.read_csv(a.quality)
    vab = set((q[q.tier == "validated"].animal + "|" + q[q.tier == "validated"].block_from.astype(str)))
    p = periods(b, hp, split)
    p.to_csv(Path(man["run_dir"]) / f"periods_day_night{sfx}.csv.gz", index=False)
    PH = [x for x in ("day", "morning", "afternoon", "night") if x in set(p.phase)]
    rows, pas = [], []
    for y, ylab in (("R", "rate"), ("R_adj", "hour-adjusted rate"), ("A", "relative amplitude (check)")):
        for tcol in ("T", "T_anom"):
            for ph in PH:
                d = p[p.phase == ph]
                f = fit_period(d, y, tcol)
                pa_ = per_animal_period(d, y, tcol)
                s_ = pa_.slope.dropna() if "slope" in pa_ else pd.Series(dtype=float)
                al = {}
                if len(s_) >= 3:
                    m_, se_ = float(s_.mean()), float(s_.std(ddof=1) / np.sqrt(len(s_)))
                    tq = stats.t.ppf(0.975, len(s_) - 1)
                    al = dict(al=m_, al_lo=m_ - tq * se_, al_hi=m_ + tq * se_)
                fv = fit_period(d[d.ab.isin(vab)], y, tcol)
                fn = fit_period(d, y, tcol, trend=False)
                agree = int((np.sign(s_) == np.sign(f.get("slope", np.nan))).sum())
                c1 = np.isfinite(f.get("lo", np.nan)) and (f["lo"] > 0 or f["hi"] < 0)
                c2 = bool(al) and (al["al_lo"] > 0 or al["al_hi"] < 0) and np.sign(al["al"]) == np.sign(f.get("slope"))
                c3 = agree >= min(4, len(s_))
                c4 = np.isfinite(fv.get("lo", np.nan)) and (fv["lo"] > 0 or fv["hi"] < 0) and np.sign(fv["slope"]) == np.sign(f.get("slope"))
                v = "Established" if c1 and c2 and c3 and c4 else "Candidate" if c1 else "No"
                rows.append(dict(outcome=y, label=ylab, temp=tcol, phase=ph, **{k: f.get(k) for k in ("slope", "lo", "hi", "p", "n", "dates")},
                                 **al, same_sign=agree, animals=len(s_), val_slope=fv.get("slope"), val_lo=fv.get("lo"),
                                 val_hi=fv.get("hi"), notrend_slope=fn.get("slope"), notrend_lo=fn.get("lo"), notrend_hi=fn.get("hi"),
                                 verdict=v))
                pas.append(pa_.assign(outcome=y, temp=tcol, phase=ph))
    R, PA = pd.DataFrame(rows), pd.concat(pas, ignore_index=True)
    R.to_csv(rd / f"ephys_spikes_swr_temperature_rate{sfx}_tests_{COHORT}.csv", index=False)
    PA.to_csv(rd / f"ephys_spikes_swr_temperature_rate{sfx}_per_animal_{COHORT}.csv", index=False)
    p.to_csv(rd / f"ephys_spikes_swr_temperature_rate{sfx}_periods_{COHORT}.csv", index=False)
    fig = rate_figure(p, PH, sfx)
    rate_report(p, R, PA, fig, rd, man["run_dir"], PH, sfx)
    print(f"wrote {rd / f'ephys_spikes_swr_temperature_rate{sfx}_{COHORT}.md'} ({len(p)} periods)")


def rate_figure(p: pd.DataFrame, PH=("day", "night"), sfx: str = "") -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from _common import figure_dir
    animals = sorted(p.animal.unique())
    fig, axes = plt.subplots(len(PH), len(animals) + 1, figsize=(2.7 * (len(animals) + 1), 2.7 * len(PH)), squeeze=False)
    col = {"day": "#d98c00", "morning": "#e6a817", "afternoon": "#c0392b", "night": "#2b4f8a"}
    for i, ph in enumerate(PH):
        d = p[p.phase == ph].copy()
        d["Rd"] = d.R - d.groupby("ab").R.transform("mean")
        for j, an in enumerate(animals + ["all (block-demeaned)"]):
            ax = axes[i, j]
            g = d if j == len(animals) else d[d.animal == an]
            yv = g.Rd if j == len(animals) else g.R
            for ab_, gg in g.groupby("ab"):
                ax.scatter(gg["T"], (gg.R - gg.R.mean()) if j == len(animals) else gg.R, s=18, color=col[ph], alpha=0.8,
                           marker="o" if ab_.endswith("start") else "s")
            if len(g) >= 3:
                k = np.polyfit(g["T"], yv, 1)
                xs = np.linspace(g["T"].min(), g["T"].max(), 10)
                ax.plot(xs, np.polyval(k, xs), color=col[ph], lw=1)
            ax.set_title(f"{an} - {ph}" if j < len(animals) else f"all animals - {ph}", fontsize=8)
            ax.tick_params(labelsize=7)
            if j == 0:
                ax.set_ylabel("NREM ripple rate (/NREM min)", fontsize=8)
            if i == len(PH) - 1:
                ax.set_xlabel("outdoor T during NREM (degC)", fontsize=8)
    fig.suptitle("Day and night NREM ripple rate vs temperature, one point per animal x period (circle = first block, "
                 "square = later block; 'all' = rate minus its block mean)", fontsize=9)
    fig.tight_layout()
    out = figure_dir(COHORT) / f"ephys_spikes_swr_temperature_rate{sfx}_{COHORT}.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


def rate_report(p, R, PA, fig, rd, run_dir, PH=("day", "night"), sfx=""):
    L = []
    w = L.append
    w(f"# Day and night NREM ripple RATE vs temperature ({COHORT})" + (" - day split at solar noon" if sfx else ""))
    if sfx:
        w("")
        w("Day split as the user asked (10-09): morning = sunrise -> solar noon (the midpoint of sunrise and sunset, about 13:00 "
          "EDT), afternoon = solar noon -> sunset; a 30-min bin goes by its centre. The night is unchanged.")
    w("")
    w(f"Generated by `ephys/swr_temperature.py rate` (repo `{git_commit()}`) from the 30-min bins of `{run_dir}`. "
      "Plan Amendment 2 ([plan](../../../../implementation_plan/2026-10-08-swr-temperature.md)): written after the bin-level "
      "rate slopes were seen, at the user's correction ('day / night ripple RATE vs temperature'). Bin-level analysis and its "
      f"audit: [`ephys_spikes_swr_temperature_{COHORT}.md`](ephys_spikes_swr_temperature_{COHORT}.md).")
    w("")
    w("## Answer")
    w("")
    for ph in PH:
        r = R[(R.outcome == "R") & (R.temp == "T") & (R.phase == ph)].iloc[0]
        ra = R[(R.outcome == "R") & (R.temp == "T_anom") & (R.phase == ph)].iloc[0]
        rj = R[(R.outcome == "R_adj") & (R.temp == "T") & (R.phase == ph)].iloc[0]
        am = R[(R.outcome == "A") & (R.temp == "T") & (R.phase == ph)].iloc[0]
        pp = PA[(PA.outcome == "R") & (PA.temp == "T") & (PA.phase == ph)]
        w(f"- **{ph.capitalize()} ripple rate:** {fmt(r.slope, 2)} events/NREM min per degC [{fmt(r.lo, 2)}, {fmt(r.hi, 2)}] "
          f"({r.n} animal-periods, {r.dates} dates); per animal {r.same_sign} / {r.animals} with that sign "
          f"(Pearson r: " + ", ".join(f"{x.animal} {fmt(x.pearson, 2)}" for x in pp.itertuples()) + f"); animal-level mean "
          f"{fmt(getattr(r, 'al', np.nan), 2)} [{fmt(getattr(r, 'al_lo', np.nan), 2)}, {fmt(getattr(r, 'al_hi', np.nan), 2)}]; "
          f"validated blocks {fmt(r.val_slope, 2)} [{fmt(r.val_lo, 2)}, {fmt(r.val_hi, 2)}]; hour-adjusted {fmt(rj.slope, 2)} "
          f"[{fmt(rj.lo, 2)}, {fmt(rj.hi, 2)}]; vs the anomaly {fmt(ra.slope, 2)} [{fmt(ra.lo, 2)}, {fmt(ra.hi, 2)}]. "
          f"Amplitude check {fmt(am.slope, 3)} per degC [{fmt(am.lo, 3)}, {fmt(am.hi, 3)}]. **Verdict: {r.verdict}.**")
    w("")
    w("## All tests")
    w("")
    w("Per phase: WLS y = animal x block intercepts + beta T + gamma day, weights NREM minutes, SEs clustered by date, t(G-1). "
      "Verdict = the Amendment 1 rule (pooled CI excludes 0, animal-level CI excludes 0, >= 4 animals same sign, validated "
      "blocks agree).")
    w("")
    w("| Outcome | Temperature | Phase | Slope /degC [95 % CI] | p | Animal-level [CI] | Same sign | Validated blocks [CI] | No trend [CI] | Verdict |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for r in R.itertuples():
        w(f"| {r.label} | {r.temp} | {r.phase} | {fmt(r.slope, 3)} [{fmt(r.lo, 3)}, {fmt(r.hi, 3)}] | {fmt(r.p, 3)} | "
          f"{fmt(getattr(r, 'al', np.nan), 3)} [{fmt(getattr(r, 'al_lo', np.nan), 3)}, {fmt(getattr(r, 'al_hi', np.nan), 3)}] | "
          f"{r.same_sign} / {r.animals} | {fmt(r.val_slope, 3)} [{fmt(r.val_lo, 3)}, {fmt(r.val_hi, 3)}] | "
          f"{fmt(r.notrend_slope, 3)} [{fmt(r.notrend_lo, 3)}, {fmt(r.notrend_hi, 3)}] | **{r.verdict}** |")
    w("")
    w("## Per animal (rate vs outdoor T)")
    w("")
    w("| Animal | Phase | Periods | Slope /degC | Pearson r | Spearman rho |")
    w("|---|---|---|---|---|---|")
    for x in PA[(PA.outcome == "R") & (PA.temp == "T")].itertuples():
        w(f"| {x.animal} | {x.phase} | {x.periods} | {fmt(getattr(x, 'slope', np.nan), 2)} | {fmt(getattr(x, 'pearson', np.nan), 2)} | "
          f"{fmt(getattr(x, 'spearman', np.nan), 2)} |")
    w("")
    w("## The periods")
    w("")
    w("| Animal | Block | Date | Phase | NREM min | Rate /min | Outdoor T (degC) | T anomaly | Rel. amplitude |")
    w("|---|---|---|---|---|---|---|---|---|")
    for x in p.sort_values(["animal", "date", "phase"]).itertuples():
        w(f"| {x.animal} | {x.block} | {x.date} | {x.phase} | {x.nrem_min:.0f} | {x.R:.1f} | {x.T:.1f} | {x.T_anom:+.1f} | {fmt(x.A, 2)} |")
    w("")
    w(f"![rate vs temperature](../figures/{fig.name})")
    w("")
    w("## Definitions")
    w("")
    w("- **Period**: for biological date D, day = [sunrise D, sunset D), night = [sunset D, sunrise D+1); the 30-min bins of "
      "the bin-level analysis (same exclusions: tiers validated / good, after use_until, to 09-11 19:40, first 30 min of each "
      "file, probe-advance settle windows, bins with >= 5 min NREM not crossed by sunrise / sunset).")
    w("- **Period rate** $R_p = \\sum_{k\\in p} n_k / \\sum_{k\\in p} N_k$ (kept NREM SWR events per NREM minute); periods with "
      ">= 30 NREM minutes. Text: how often ripples occur during that day's / night's NREM.")
    w("- **Period temperature** $T_p = \\sum_k N_k T_k / \\sum_k N_k$ (degC): outdoor temperature while the animal was in NREM; "
      "$T^{anom}_p$ the same for the anomaly (vs the usual for the hour).")
    w("- **Hour-adjusted rate** $R^{adj}_p = \\sum_k N_k (r_k - \\bar r_{h(k)}) / \\sum_k N_k$, $\\bar r_h$ = the cohort hour profile "
      "(within-block deviation by clock hour): removes differences in when within the period the NREM fell.")
    w("- **Model** per phase: $R_p = \\alpha_{a,b} + \\beta T_p + \\gamma\\,\\mathrm{day}_p$, WLS weights = NREM minutes, SEs clustered by "
      "biological date, $t(G-1)$; per animal the same without the trend (few dates); animal-level CI = mean of the per-animal "
      "slopes, $t(n-1)$.")
    w("- **Relative amplitude** (check): NREM-minute-weighted mean of the bins' median amplitude / the block reference's NREM "
      "median: if the rate slope came with an amplitude slope, a fixed detection boundary could produce it.")
    w("")
    w("## Limits")
    w("")
    w("- Outdoor air, not the house or the brain; the rats sleep huddled in insulated houses.")
    w("- Rate depends on the detection boundary (fixed per block in raw units); the amplitude check tests the obvious route. "
      "SF08 block 1 and SF12 block 1 are the least trustworthy blocks (quality guide).")
    w("- One value per animal per period and 12 dates: weather varies little between dates within a phase; a slope across "
      "dates can also carry anything else that changed from day to day (handling, disturbance, the probe).")
    (rd / f"ephys_spikes_swr_temperature_rate{sfx}_{COHORT}.md").write_text("\n".join(L) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ hottest vs coldest time of each day (user 10-09)
def extremes(a):
    """Per biological date D (sunrise D -> sunrise D+1): the hottest window = +-1 h around the time of the maximum outdoor
    temperature between sunrise and sunset of D; the coldest window = +-1 h around the minimum between sunset D and sunrise
    D+1. Per animal x block: R = sum n / sum N over the 30-min bins whose centre falls in the window (>= 10 NREM min);
    paired difference R_cold - R_hot per animal x date (same block)."""
    import statsmodels.api as sm
    from scipy import stats
    from sleep_quant import sun_times
    rd = report_dir(COHORT)
    man = json.loads((rd / f"run_manifest_swr_temperature_{COHORT}.json").read_text())
    run = Path(man["run_dir"])
    b = pd.read_csv(run / "bins_30min.csv.gz", parse_dates=["b0"])
    wx = pd.read_csv(run / "weather_anomaly.csv.gz", parse_dates=["t"]).dropna(subset=["temp_C"])
    b["c"] = b.b0 + pd.Timedelta(minutes=15)
    rows = []
    for D in pd.date_range("2026-08-31", "2026-09-11"):
        sr, ss = (pd.Timestamp(x) for x in sun_times(D.date()))
        sr2, _ = (pd.Timestamp(x) for x in sun_times((D + pd.Timedelta(days=1)).date()))
        day = wx[(wx.t >= sr) & (wx.t < ss)]
        night = wx[(wx.t >= ss) & (wx.t < sr2)]
        if len(day) < 100 or len(night) < 100:
            continue
        th, tc = day.loc[day.temp_C.idxmax()], night.loc[night.temp_C.idxmin()]
        for nm, w0 in (("hot", th), ("cold", tc)):
            g = b[(b.c >= w0.t - pd.Timedelta(hours=1)) & (b.c <= w0.t + pd.Timedelta(hours=1))]
            for (an, ab), gg in g.groupby(["animal", "ab"]):
                N = gg.N.sum()
                if N >= 10:
                    rows.append(dict(date=D.strftime("%m-%d"), window=nm, t_extreme=w0.t.strftime("%H:%M"), T=w0.temp_C,
                                     animal=an, ab=ab, nrem_min=N, R=gg.n.sum() / N, T_bins=float(np.average(gg.temp_C, weights=gg.N))))
    e = pd.DataFrame(rows)
    pr = e.pivot_table(index=["date", "animal", "ab"], columns="window", values=["R", "T", "nrem_min"]).dropna()
    pr.columns = [f"{x}_{y}" for x, y in pr.columns]
    pr = pr.reset_index()
    pr["diff"] = pr.R_cold - pr.R_hot
    pr["dT"] = pr.T_cold - pr.T_hot
    pa = pr.groupby("animal").agg(pairs=("diff", "size"), R_hot=("R_hot", "mean"), R_cold=("R_cold", "mean"),
                                  diff=("diff", "mean"), diff_sem=("diff", lambda x: x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else np.nan),
                                  cold_higher=("diff", lambda x: int((x > 0).sum())), T_hot=("T_hot", "mean"), T_cold=("T_cold", "mean"))
    m = sm.OLS(pr["diff"], np.ones(len(pr))).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(pr.date)[0], "use_correction": True})
    G = pr.date.nunique()
    tq = stats.t.ppf(0.975, G - 1)
    est, se = float(m.params.iloc[0]), float(m.bse.iloc[0])
    am = pa["diff"]
    ta = stats.ttest_1samp(am, 0)
    e.to_csv(rd / f"ephys_spikes_swr_temperature_extremes_windows_{COHORT}.csv", index=False)
    pr.to_csv(rd / f"ephys_spikes_swr_temperature_extremes_pairs_{COHORT}.csv", index=False)
    times = e.drop_duplicates(["date", "window"]).pivot(index="date", columns="window", values=["t_extreme", "T"])
    L = []
    w = L.append
    w(f"# NREM ripple rate at the hottest vs the coldest time of the day ({COHORT})")
    w("")
    w(f"Generated by `ephys/swr_temperature.py extremes` (repo `{git_commit()}`) from the 30-min bins of `{run}` (same events "
      "and exclusions as the temperature analysis: tiers validated / good, kept NREM events, to 09-11 19:40). The user asked "
      "(10-09): at the hottest time around midday and the coldest time at night, which ripple rate is higher?")
    w("")
    w("## Answer")
    w("")
    w(f"- **The coldest time has the higher NREM ripple rate.** Paired per animal x date (same block): cold - hot = "
      f"{est:+.1f} events/NREM min [95 % CI {est - tq * se:+.1f}, {est + tq * se:+.1f}] (SEs clustered by date, t({G - 1})), "
      f"{len(pr)} pairs, {int((pr['diff'] > 0).sum())} / {len(pr)} with the cold window higher; per animal "
      f"{int((pa['diff'] > 0).sum())} / {len(pa)} animals higher in the cold window (animal-level mean {am.mean():+.1f}, "
      f"t({len(am) - 1}) p {ta.pvalue:.3f}).")
    w(f"- Mean rates: hottest window {pr.R_hot.mean():.1f}, coldest window {pr.R_cold.mean():.1f} events/NREM min; the "
      f"temperature difference averages {pr.dT.mean():+.1f} degC.")
    w("- This is a time-of-day contrast (midday rest vs the end of the night), not a temperature effect: the per-period "
      "analysis ([rate report](ephys_spikes_swr_temperature_rate_2026c.md)) found no temperature relation in the day and only a "
      "Candidate one at night.")
    w("")
    w("## Per animal")
    w("")
    w("| Animal | Pairs (dates) | Rate hottest | Rate coldest | Cold - hot (SEM) | Dates cold higher | T hottest / coldest (degC) |")
    w("|---|---|---|---|---|---|---|")
    for an, r in pa.iterrows():
        w(f"| {an} | {int(r.pairs)} | {r.R_hot:.1f} | {r.R_cold:.1f} | {r['diff']:+.1f} ({fmt(r.diff_sem, 1)}) | "
          f"{int(r.cold_higher)} / {int(r.pairs)} | {r.T_hot:.1f} / {r.T_cold:.1f} |")
    w("")
    w("## The windows")
    w("")
    w("| Date | Hottest at | T max | Coldest at (that night) | T min |")
    w("|---|---|---|---|---|")
    for d_, r in times.iterrows():
        w(f"| {d_} | {r[('t_extreme', 'hot')] if ('t_extreme', 'hot') in r else ''} | {fmt(r.get(('T', 'hot')), 1)} | "
          f"{r[('t_extreme', 'cold')] if ('t_extreme', 'cold') in r else ''} | {fmt(r.get(('T', 'cold')), 1)} |")
    w("")
    w("## Definitions")
    w("")
    w("- **Hottest window** of biological date D: +-1 h around the 5-min weather sample with the highest outdoor temperature "
      "between sunrise and sunset of D. **Coldest window**: +-1 h around the lowest between sunset D and sunrise D+1.")
    w("- **Window rate** $R = \\sum n_k / \\sum N_k$ over the 30-min bins whose centre lies in the window (kept NREM SWR events "
      "per NREM minute); >= 10 NREM minutes required.")
    w("- **Paired difference** $\\Delta = R_{cold} - R_{hot}$ per animal x date x block; pooled mean with SEs clustered by date "
      "(CR1, $t(G-1)$); animal-level = the per-animal mean differences, one-sample t.")
    (rd / f"ephys_spikes_swr_temperature_extremes_{COHORT}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[L.index("## Answer"):L.index("## Definitions")]))


# ------------------------------------------------------------------ selftest
def selftest():
    rng = np.random.default_rng(1)
    rows = []
    for an in ("A1", "A2", "A3", "A4"):
        off = rng.normal(150, 5)
        for dd in range(10):
            for k in range(30):
                night = float(k >= 15)
                T = 15 + 6 * np.sin(2 * np.pi * k / 30) + rng.normal(0, 2) + 0.3 * dd
                f = off + 0.8 * T + 0.5 * T * night - 3 * night + rng.normal(0, 1.5)
                rows.append(dict(animal=an, ab=an + "|b1", T_=T, f=f, night=night, phase="night" if night else "day",
                                 day=dd + k / 30, date=f"d{dd:02d}", N=rng.uniform(5, 30)))
    b = pd.DataFrame(rows).rename(columns={"T_": "temp_C"})
    r = fit(b, "f", "temp_C")
    ok = abs(r["slope_day"] - 0.8) < 0.15 and abs(r["slope_night"] - 1.3) < 0.15 and r["lo_diff"] > 0
    print(f"{'PASS' if ok else 'FAIL'} synthetic slopes: day {r['slope_day']:.3f} (0.8), night {r['slope_night']:.3f} (1.3), "
          f"diff CI [{r['lo_diff']:.3f}, {r['hi_diff']:.3f}]")
    # Amendment 1: an outcome driven by the hour only, with temperature following the hour -> model P shows a spurious
    # slope, model H removes it
    rows = []
    for an in ("A1", "A2", "A3", "A4"):
        for dd in range(10):
            for k in range(48):
                h = k / 2
                T = 15 + 6 * np.sin(2 * np.pi * (h - 9) / 24) + rng.normal(0, 1.5) + rng.normal(0, 2) * 0
                rows.append(dict(animal=an, ab=an + "|b1", temp_C=T, f=150 + 3 * np.sin(2 * np.pi * (h - 9) / 24) + rng.normal(0, 1),
                                 night=float(h < 7 or h >= 19), phase="night" if (h < 7 or h >= 19) else "day", day=dd + h / 24,
                                 date=f"d{dd:02d}", N=10.0, hour=h,
                                 **{f"h{t}{q_}": fn(2 * np.pi * q_ * h / 24) for q_ in (1, 2) for t, fn in (("s", np.sin), ("c", np.cos))}))
    bh = pd.DataFrame(rows)
    rp, rh = fit(bh, "f", "temp_C"), fit(bh, "f", "temp_C", hour=True)
    ok3 = rp["slope_day"] > 0.2 and abs(rh["slope_day"]) < 0.1 and abs(rh["slope_night"]) < 0.1
    print(f"{'PASS' if ok3 else 'FAIL'} hour confound: model P day slope {rp['slope_day']:.3f} (spurious), model H "
          f"{rh['slope_day']:.3f} / {rh['slope_night']:.3f} (~0)")
    ok = ok and ok3
    b0 = pd.Series(pd.to_datetime(["2026-09-05 12:00", "2026-09-05 23:00", "2026-09-05 06:30"]))
    ph = list(phase_of_bins(b0, pd.Timedelta("30min")))
    ok2 = ph[0] == "day" and ph[1] == "night" and ph[2] is None
    print(f"{'PASS' if ok2 else 'FAIL'} phases {ph} (12:00 day, 23:00 night, 06:30-07:00 contains sunrise)")
    print("SELFTEST " + ("PASS" if ok and ok2 else "FAIL"))
    sys.exit(0 if ok and ok2 else 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["run", "rate", "extremes"])
    ap.add_argument("--swr-root", default="Q:/hc997/SocialFieldRat2026/3rd_rat/analysis/swr")
    ap.add_argument("--states-root", default="D:/3rd_rat_spikes/analysis/sleep_server/states_1s_final")
    ap.add_argument("--quality", default=str(report_dir(COHORT) / f"ephys_spikes_swr_quality_{COHORT}.csv"))
    ap.add_argument("--review", default=str(report_dir(COHORT) / f"ephys_spikes_sleep_review_{COHORT}.csv"))
    ap.add_argument("--cohort-yaml", default=str(HERE.parent / f"cohorts/{COHORT}.yaml"))
    ap.add_argument("--split-day", action="store_true", help="rate: split the day at solar noon (morning / afternoon)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    if a.cmd == "run":
        run(a)
    if a.cmd == "rate":
        rate_analysis(a)
    if a.cmd == "extremes":
        extremes(a)


if __name__ == "__main__":
    main()
