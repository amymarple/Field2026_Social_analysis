"""NREM depth (the sleep scorer's spectral slope) by time of day, day vs night, and whether it explains the NREM ripple
rate (cohort 2026c). Plan: implementation_plan/2026-10-08-swr-temperature.md, Part 2 (written before computing).

Depth: s_t = the raw slow-wave metric of the scorer (negative IRASA slope 4-90 Hz, per second) of variant imu_fixch (fixed
per-animal channels; `<session>.SleepScoreRaw.npz`, before the per-session min-max rescaling; storage
3rd_rat/analysis/sleep/imu_fixch/, read-only). Per 30-min bin D_k = mean s_t over the bin's NREM seconds (final 1-s states),
same sessions / exclusions as the ripple bins of swr_temperature.py (its saved bins_30min); pooled as z within animal x block.
  S1  day vs night depth, per animal x biological date (day period - night period), animal-level t(n-1)
  S2  circadian profiles of depth and ripple rate (block-demeaned), mean +- SEM over animals
  S3  does depth explain the rate: r ~ block + z(D); the hour profile, the night - day difference and the night trend
      across days, each with and without z(D)

  python ephys/swr_depth.py run [--sleep-root …]
  python ephys/swr_depth.py --selftest
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
from _common import figure_dir, git_commit, report_dir, write_json  # noqa: E402
import swr_temperature as st  # noqa: E402

COHORT = st.COHORT
HARM = ["hs1", "hc1", "hs2", "hc2"]


def depth_bins(a) -> pd.DataFrame:
    """Per animal x block x 30-min bin: mean raw slope over the NREM seconds that survive the ripple analysis' exclusions."""
    q = st.sessions(Path(a.quality), Path(a.review), ["validated", "good"])
    win = st.settle_windows(Path(a.cohort_yaml))
    parts, missing = [], []
    for row in q.itertuples():
        sf = Path(a.states_root) / row.animal / f"{row.session}.states.npz"
        rf = Path(a.sleep_root) / row.animal / row.session / f"{row.session}.SleepScoreRaw.npz"
        if not sf.exists() or not rf.exists():
            missing.append(f"{row.animal} {row.session}")
            continue
        with np.load(sf) as s_, np.load(rf) as r_:
            ts, state = s_["ts"].astype(int), s_["state"]
            raw = pd.Series(r_["sw"].astype(float), index=r_["t_clus"].astype(int))
        sec = ts[state == 3]
        sw = raw.reindex(sec).to_numpy()
        t = pd.Series(row.start_t + pd.to_timedelta(sec, unit="s"))
        k = st.keep_mask(t, row, st.FEMALES, win) & np.isfinite(sw)
        parts.append(pd.DataFrame({"animal": row.animal, "block": row.block_from, "b0": t[k].dt.floor("30min").values, "sw": sw[k]}))
    d = pd.concat(parts, ignore_index=True)
    out = d.groupby(["animal", "block", "b0"]).agg(D=("sw", "mean"), D_s=("sw", "size")).reset_index()
    out.attrs["missing"] = missing
    return out


def wls(d: pd.DataFrame, formula: str, terms: list[str]) -> dict:
    """WLS (weights N) with SEs clustered by date (CR1), t(G-1) CIs for the named terms."""
    import statsmodels.formula.api as smf
    from scipy import stats
    G = d.date.nunique()
    m = smf.wls(formula, data=d, weights=d.N).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d.date)[0], "use_correction": True})
    tq = stats.t.ppf(0.975, G - 1)
    out = {"n": len(d), "dates": G, "_m": m}
    for t in terms:
        if t in m.params:
            e, se = float(m.params[t]), float(m.bse[t])
            out.update({t: e, f"{t}_lo": e - tq * se, f"{t}_hi": e + tq * se, f"{t}_p": float(2 * stats.t.sf(abs(e / se), G - 1))})
    return out


def hour_amp(m) -> tuple[float, float]:
    """Peak-to-trough amplitude and peak hour of the fitted hour-harmonic profile of a fitted model."""
    h = np.linspace(0, 24, 241)
    f = sum(m.params.get(f"h{t}{k}", 0.0) * fn(2 * np.pi * k * h / 24) for k in (1, 2) for t, fn in (("s", np.sin), ("c", np.cos)))
    return float(f.max() - f.min()), float(h[int(np.argmax(f))])


def bio_date(c: pd.Series) -> pd.Series:
    from sleep_quant import sun_times
    out = []
    for t in c:
        sr, _ = sun_times(t.date())
        out.append((t.normalize() - pd.Timedelta(days=1)) if t < pd.Timestamp(sr) else t.normalize())
    return pd.Series(pd.to_datetime(out), index=c.index)


def run(a):
    from scipy import stats
    rd = report_dir(COHORT)
    man = json.loads((rd / f"run_manifest_swr_temperature_{COHORT}.json").read_text())
    run_dir = Path(man["run_dir"])
    b = pd.read_csv(run_dir / "bins_30min.csv.gz", parse_dates=["b0"])
    db = depth_bins(a)
    db.to_csv(run_dir / "depth_bins_30min.csv.gz", index=False)
    b["block"] = b.block.astype(str)
    db["block"] = db.block.astype(str)
    x = b.merge(db, on=["animal", "block", "b0"], how="inner")
    x["Dz"] = (x.D - x.groupby("ab").D.transform("mean")) / x.groupby("ab").D.transform("std")
    mu = x.groupby("ab").apply(lambda g: np.average(g.r, weights=g.N))
    x["r_dm"] = x.r - x.ab.map(mu)
    x["bio"] = bio_date(x.b0 + pd.Timedelta(minutes=15)).dt.strftime("%m-%d")
    x["h"] = x.hour.astype(int)
    print(f"bins with depth {len(x)} of {len(b)} ripple bins ({x.animal.nunique()} animals); sessions without a raw slope file: "
          f"{len(db.attrs.get('missing', []))}", flush=True)
    # S1: day vs night depth, per animal x biological date
    pp = x.groupby(["animal", "bio", "phase"]).apply(lambda g: pd.Series({"Dz": np.average(g.Dz, weights=g.N),
                                                                         "r": g.n.sum() / g.N.sum(), "N": g.N.sum()})).reset_index()
    pv = pp[pp.N >= 30].pivot_table(index=["animal", "bio"], columns="phase", values=["Dz", "r"]).dropna()
    pv.columns = [f"{u}_{v}" for u, v in pv.columns]
    pv = pv.reset_index()
    pv["dD"] = pv.Dz_day - pv.Dz_night
    pv["dr"] = pv.r_night - pv.r_day
    s1 = pv.groupby("animal").agg(pairs=("dD", "size"), day_minus_night_depth=("dD", "mean"), night_minus_day_rate=("dr", "mean"),
                                  day_deeper=("dD", lambda v: int((v > 0).sum())))
    am = s1.day_minus_night_depth
    t1 = stats.ttest_1samp(am, 0)
    ci1 = (am.mean() - stats.t.ppf(0.975, len(am) - 1) * am.std(ddof=1) / np.sqrt(len(am)),
           am.mean() + stats.t.ppf(0.975, len(am) - 1) * am.std(ddof=1) / np.sqrt(len(am)))
    # S2: hour profiles (per animal weighted by NREM minutes, then mean +- SEM over animals)
    prof = x.groupby(["animal", "h"]).apply(lambda g: pd.Series({"r_dm": np.average(g.r_dm, weights=g.N),
                                                                "Dz": np.average(g.Dz, weights=g.N), "T": g.temp_C.mean()})).reset_index()
    hp = prof.groupby("h").agg(animals=("animal", "nunique"), r_dm=("r_dm", "mean"), r_sem=("r_dm", lambda v: v.std(ddof=1) / np.sqrt(len(v))),
                               Dz=("Dz", "mean"), Dz_sem=("Dz", lambda v: v.std(ddof=1) / np.sqrt(len(v))), T=("T", "mean")).reset_index()
    hp = hp[hp.animals >= 3]
    # S3: does depth explain the rate
    base = "r ~ C(ab)"
    s3 = {}
    s3["rate_on_depth"] = wls(x, base + " + Dz", ["Dz"])
    per_an = []
    for an, g in x.groupby("animal"):
        f = wls(g, ("r ~ C(ab) + Dz" if g.ab.nunique() > 1 else "r ~ Dz"), ["Dz"]) if g.date.nunique() >= 3 else {}
        per_an.append({"animal": an, "beta_Dz": f.get("Dz"), "lo": f.get("Dz_lo"), "hi": f.get("Dz_hi"), "bins": len(g)})
    per_an = pd.DataFrame(per_an)
    h0 = wls(x, base + " + " + " + ".join(HARM), HARM)
    h1 = wls(x, base + " + " + " + ".join(HARM) + " + Dz", HARM + ["Dz"])
    a0, pk0 = hour_amp(h0["_m"])
    a1, pk1 = hour_amp(h1["_m"])
    n0 = wls(x, base + " + night", ["night"])
    n1 = wls(x, base + " + night + Dz", ["night", "Dz"])
    xn = x[x.phase == "night"]
    tr0 = wls(xn, base + " + day", ["day"])
    tr1 = wls(xn, base + " + day + Dz", ["day", "Dz"])
    # depth across days (night and day), for the night-trend question
    dtr = {ph: wls(x[x.phase == ph], "Dz ~ C(ab) + day", ["day"]) for ph in ("day", "night")}
    res = dict(S1=dict(animal_mean=float(am.mean()), lo=float(ci1[0]), hi=float(ci1[1]), p=float(t1.pvalue), animals=len(am),
                       day_deeper_animals=int((am > 0).sum())),
               S3=dict(beta_Dz=s3["rate_on_depth"]["Dz"], beta_lo=s3["rate_on_depth"]["Dz_lo"], beta_hi=s3["rate_on_depth"]["Dz_hi"],
                       beta_pos_animals=int((per_an.beta_Dz > 0).sum()), animals=int(per_an.beta_Dz.notna().sum()),
                       hour_amp_without=a0, hour_amp_with=a1, hour_peak_without=pk0, hour_peak_with=pk1,
                       hour_share_explained=1 - a1 / a0,
                       night_without=n0["night"], night_without_lo=n0["night_lo"], night_without_hi=n0["night_hi"],
                       night_with=n1["night"], night_with_lo=n1["night_lo"], night_with_hi=n1["night_hi"],
                       trend_without=tr0["day"], trend_without_lo=tr0["day_lo"], trend_without_hi=tr0["day_hi"],
                       trend_with=tr1["day"], trend_with_lo=tr1["day_lo"], trend_with_hi=tr1["day_hi"],
                       depth_trend_night=dtr["night"]["day"], depth_trend_night_lo=dtr["night"]["day_lo"], depth_trend_night_hi=dtr["night"]["day_hi"],
                       depth_trend_day=dtr["day"]["day"], depth_trend_day_lo=dtr["day"]["day_lo"], depth_trend_day_hi=dtr["day"]["day_hi"]))
    s1.to_csv(rd / f"ephys_spikes_swr_depth_day_night_{COHORT}.csv")
    hp.to_csv(rd / f"ephys_spikes_swr_depth_hour_profile_{COHORT}.csv", index=False)
    per_an.to_csv(rd / f"ephys_spikes_swr_depth_rate_per_animal_{COHORT}.csv", index=False)
    write_json(rd / f"ephys_spikes_swr_depth_tests_{COHORT}.json", res)
    fig = figure(x, hp, pv)
    report(x, s1, hp, per_an, res, fig, rd, run_dir, db.attrs.get("missing", []))
    write_json(rd / f"run_manifest_swr_depth_{COHORT}.json", dict(name="swr_depth", run_dir=str(run_dir), git=git_commit(),
                                                                   bins=len(x), plan="implementation_plan/2026-10-08-swr-temperature.md (Part 2)"))
    print(json.dumps(res, indent=1))


def figure(x, hp, pv) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sleep_quant import sun_times
    srs = [sun_times(d.date()) for d in pd.date_range("2026-08-31", "2026-09-11")]
    sr_h = np.mean([s.hour + s.minute / 60 for s, _ in srs])
    ss_h = np.mean([e.hour + e.minute / 60 for _, e in srs])
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    ax = axes[0, 0]
    ax.errorbar(hp.h + 0.5, hp.Dz, yerr=hp.Dz_sem, fmt="-o", color="#6a3d9a", ms=4, capsize=2, label="NREM depth (z of the slope)")
    ax.set_ylabel("NREM depth, z within animal x block", fontsize=9, color="#6a3d9a")
    ax2 = ax.twinx()
    ax2.errorbar(hp.h + 0.5, hp.r_dm, yerr=hp.r_sem, fmt="-s", color="#2b7a2b", ms=4, capsize=2, label="ripple rate")
    ax2.set_ylabel("NREM ripple rate - block mean (/NREM min)", fontsize=9, color="#2b7a2b")
    for a_ in (ax,):
        a_.axvspan(0, sr_h, color="0.88", lw=0)
        a_.axvspan(ss_h, 24, color="0.88", lw=0)
        a_.set_xlim(0, 24)
        a_.set_xticks(range(0, 25, 3))
        a_.set_xlabel("clock hour (EDT)", fontsize=9)
    ax.set_title("A  Circadian: NREM depth (purple) and NREM ripple rate (green), mean +- SEM over animals (grey = night)",
                 fontsize=9, loc="left")
    ax = axes[0, 1]
    for an, g in pv.groupby("animal"):
        ax.plot([0, 1], [g.Dz_day.mean(), g.Dz_night.mean()], "-o", label=an)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["day (sunrise-sunset)", "night"])
    ax.set_ylabel("NREM depth, z within animal x block", fontsize=9)
    ax.set_title("B  Day vs night NREM depth per animal (mean over dates)", fontsize=9, loc="left")
    ax.legend(fontsize=7, frameon=False)
    ax = axes[1, 0]
    for ph, c in (("day", "#d98c00"), ("night", "#2b4f8a")):
        g = x[x.phase == ph].copy()
        g["q"] = pd.qcut(g.Dz, 8, duplicates="drop")
        s = g.groupby("q", observed=True).apply(lambda h: pd.Series({"Dz": h.Dz.mean(), "r": np.average(h.r_dm, weights=h.N),
                                                                    "se": h.r_dm.std(ddof=1) / np.sqrt(len(h))}))
        ax.errorbar(s.Dz, s.r, yerr=s.se, fmt="-o", color=c, ms=4, capsize=2, label=ph)
    ax.axhline(0, color="0.5", lw=0.6)
    ax.set_xlabel("NREM depth (z within animal x block), octiles", fontsize=9)
    ax.set_ylabel("NREM ripple rate - block mean (/NREM min)", fontsize=9)
    ax.set_title("C  Ripple rate vs NREM depth (30-min bins, binned by depth; mean +- SEM)", fontsize=9, loc="left")
    ax.legend(fontsize=8, frameon=False)
    ax = axes[1, 1]
    for ph, c in (("day", "#d98c00"), ("night", "#2b4f8a")):
        g = x[x.phase == ph].groupby(["bio", "animal"]).apply(lambda h: np.average(h.Dz, weights=h.N)).rename("Dz").reset_index()
        m = g.groupby("bio").Dz.agg(["mean", "sem", "size"])
        m = m[m["size"] >= 2]
        ax.errorbar(pd.to_datetime("2026-" + m.index) + (pd.Timedelta(hours=13) if ph == "day" else pd.Timedelta(hours=25)), m["mean"],
                    yerr=m["sem"], fmt="-o", color=c, ms=4, capsize=2, label=ph)
    import matplotlib.dates as mdates
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax.set_ylabel("NREM depth, z within animal x block", fontsize=9)
    ax.set_title("D  NREM depth across days, day and night, mean +- SEM over animals", fontsize=9, loc="left")
    ax.legend(fontsize=8, frameon=False)
    for a_ in axes.ravel():
        a_.tick_params(labelsize=8)
    fig.suptitle(f"NREM depth (sleep scorer's spectral slope, fixed channel) and NREM ripple rate, cohort {COHORT}", fontsize=10)
    fig.tight_layout()
    out = figure_dir(COHORT) / f"ephys_spikes_swr_depth_{COHORT}.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def f_(v, nd=2):
    return "" if v is None or not np.isfinite(v) else f"{v:.{nd}f}"


def report(x, s1, hp, per_an, res, fig, rd, run_dir, missing):
    S1, S3 = res["S1"], res["S3"]
    L = []
    w = L.append
    w(f"# NREM depth and the NREM ripple rate: day vs night, time of day ({COHORT})")
    w("")
    w(f"Generated by `ephys/swr_depth.py run` (repo `{git_commit()}`); plan Part 2 (written before computing) of "
      f"[`implementation_plan/2026-10-08-swr-temperature.md`](../../../../implementation_plan/2026-10-08-swr-temperature.md). "
      f"Ripple bins from `{run_dir}`; depth = the raw spectral slope of the `imu_fixch` sleep scores (storage, read-only).")
    w("")
    w("## Answer")
    w("")
    w(f"- **S1 day vs night depth:** day - night = {S1['animal_mean']:+.2f} SD of the within-block depth [{S1['lo']:+.2f}, "
      f"{S1['hi']:+.2f}] (animal-level, t({S1['animals'] - 1}), p {S1['p']:.3f}); day deeper in {S1['day_deeper_animals']} / "
      f"{S1['animals']} animals.")
    hmax, hmin = hp.loc[hp.Dz.idxmax()], hp.loc[hp.Dz.idxmin()]
    w(f"- **S2 time of day:** depth is highest at hour {int(hmax.h)} ({hmax.Dz:+.2f}) and lowest at hour {int(hmin.h)} "
      f"({hmin.Dz:+.2f}); the ripple rate profile is in the figure and the table below.")
    w(f"- **S3 rate on depth (within block):** {S3['beta_Dz']:+.1f} events/NREM min per SD of depth [{S3['beta_lo']:+.1f}, "
      f"{S3['beta_hi']:+.1f}]; positive in {S3['beta_pos_animals']} / {S3['animals']} animals.")
    w(f"  - Time-of-day profile of the rate: peak-to-trough {S3['hour_amp_without']:.1f} -> {S3['hour_amp_with']:.1f} /NREM min "
      f"with depth in the model (share explained {100 * S3['hour_share_explained']:.0f} %).")
    w(f"  - Night - day rate: {S3['night_without']:+.1f} [{S3['night_without_lo']:+.1f}, {S3['night_without_hi']:+.1f}] -> "
      f"{S3['night_with']:+.1f} [{S3['night_with_lo']:+.1f}, {S3['night_with_hi']:+.1f}] with depth.")
    w(f"  - Night rate trend across days: {S3['trend_without']:+.2f} [{S3['trend_without_lo']:+.2f}, {S3['trend_without_hi']:+.2f}] -> "
      f"{S3['trend_with']:+.2f} [{S3['trend_with_lo']:+.2f}, {S3['trend_with_hi']:+.2f}] /NREM min per day with depth; night depth "
      f"itself changes {S3['depth_trend_night']:+.3f} SD per day [{S3['depth_trend_night_lo']:+.3f}, {S3['depth_trend_night_hi']:+.3f}] "
      f"(day {S3['depth_trend_day']:+.3f} [{S3['depth_trend_day_lo']:+.3f}, {S3['depth_trend_day_hi']:+.3f}]).")
    w("- Reading rule (plan): depth explains a contrast when adding it removes more than half, the contrast's CI then includes "
      "0, and the rate-depth slope is positive in >= 4 animals.")
    w("")
    w(f"![depth and ripple rate](../figures/{fig.name})")
    w("")
    w("## Day vs night depth per animal (S1)")
    w("")
    w("| Animal | Dates paired | Day - night depth (SD) | Day deeper (dates) | Night - day ripple rate (/NREM min) |")
    w("|---|---|---|---|---|")
    for an, r in s1.iterrows():
        w(f"| {an} | {int(r.pairs)} | {r.day_minus_night_depth:+.2f} | {int(r.day_deeper)} / {int(r.pairs)} | {r.night_minus_day_rate:+.1f} |")
    w("")
    w("## Time-of-day profile (S2; hours with >= 3 animals)")
    w("")
    w("| Hour | Animals | Depth (z) | SEM | Ripple rate - block mean | SEM | Outdoor T (degC) |")
    w("|---|---|---|---|---|---|---|")
    for r in hp.itertuples():
        w(f"| {r.h:02d} | {r.animals} | {r.Dz:+.2f} | {f_(r.Dz_sem)} | {r.r_dm:+.1f} | {f_(r.r_sem, 1)} | {r.T:.1f} |")
    w("")
    w("## Rate on depth per animal (S3)")
    w("")
    w("| Animal | Bins | Slope (/NREM min per SD of depth) [95 % CI] |")
    w("|---|---|---|")
    for r in per_an.itertuples():
        w(f"| {r.animal} | {r.bins} | {f_(r.beta_Dz, 1)} [{f_(r.lo, 1)}, {f_(r.hi, 1)}] |")
    w("")
    w("## Definitions")
    w("")
    w("- **Depth** $s_t$ = the sleep scorer's raw slow-wave metric (negative IRASA spectral slope, 4-90 Hz) per second on the "
      "animal's fixed sleep channel (variant `imu_fixch`, before the scorer's per-session min-max rescaling); higher = steeper "
      "spectrum = more slow-wave power = deeper NREM. $D_k$ = mean $s_t$ over the NREM seconds (final 1-s states) of 30-min bin "
      "$k$; $\\tilde D_k = (D_k - \\bar D_{a,b}) / \\mathrm{SD}_{a,b}(D)$ within animal x block (the probe / channel differ "
      "between blocks).")
    w("- **Ripple rate** $r_k$ = kept NREM SWR events / NREM minutes in the bin (as the temperature analysis); block-demeaned "
      "$r_k - \\bar r_{a,b}$ (NREM-minute weighted).")
    w("- **S1** per animal x biological date (day = sunrise -> sunset of D, night = sunset D -> sunrise D+1; >= 30 NREM min in "
      "each): NREM-minute-weighted $\\tilde D$ day - night; animal-level mean of the per-animal means with a $t(n-1)$ CI.")
    w("- **S3** WLS, weights = NREM minutes, SEs clustered by date (CR1, $t(G-1)$): $r_k = \\alpha_{a,b} + \\beta \\tilde D_k$; "
      "hour profile = $\\sum_{k=1,2}[a_k \\sin + b_k \\cos](2\\pi k h/24)$ with / without $\\tilde D_k$, amplitude = "
      "peak-to-trough of the fitted profile; night coefficient in $r_k = \\alpha_{a,b} + \\beta_N \\mathrm{night}_k$ (+ $\\tilde D_k$); "
      "night trend = the coefficient of days in night bins (+ $\\tilde D_k$).")
    w("- Sessions / exclusions = the ripple bins (tiers validated / good, to 09-11 19:40, first 30 min of each file, probe-advance "
      "settle windows, >= 5 NREM min per bin)." + (f" Sessions without a raw slope file: {', '.join(missing)}." if missing else ""))
    w("")
    w("## Limits")
    w("")
    w("- The slope is a broadband spectral measure on one fixed channel per animal; it tracks slow-wave power but is not delta "
      "power itself, and its absolute level depends on the probe position (hence z within block).")
    w("- Depth and ripple rate are measured on the same LFP: a shared recording factor (contact, noise) could couple them.")
    w("- Correlation within a block does not show that depth causes the ripple rate; both may follow sleep pressure.")
    (rd / f"ephys_spikes_swr_depth_{COHORT}.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def selftest():
    rng = np.random.default_rng(3)
    rows = []
    for an in ("A1", "A2", "A3", "A4"):
        for dd in range(8):
            for k in range(48):
                h = k / 2
                Dz = np.cos(2 * np.pi * (h - 6) / 24) + rng.normal(0, 0.3)
                r = 60 + 8 * Dz + rng.normal(0, 2)
                rows.append(dict(ab=an, r=r, Dz=Dz, N=10.0, date=f"d{dd}", night=float(h < 7 or h >= 19),
                                 **{f"h{t}{q}": fn(2 * np.pi * q * h / 24) for q in (1, 2) for t, fn in (("s", np.sin), ("c", np.cos))}))
    x = pd.DataFrame(rows)
    h0 = wls(x, "r ~ C(ab) + " + " + ".join(HARM), HARM)
    h1 = wls(x, "r ~ C(ab) + " + " + ".join(HARM) + " + Dz", HARM + ["Dz"])
    a0, _ = hour_amp(h0["_m"])
    a1, _ = hour_amp(h1["_m"])
    ok = abs(h1["Dz"] - 8) < 0.6 and a1 < 0.2 * a0
    print(f"{'PASS' if ok else 'FAIL'} depth-driven rate: beta {h1['Dz']:.2f} (8), hour amplitude {a0:.1f} -> {a1:.1f} with depth")
    print("SELFTEST " + ("PASS" if ok else "FAIL"))
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["run"])
    ap.add_argument("--sleep-root", default="Q:/hc997/SocialFieldRat2026/3rd_rat/analysis/sleep/imu_fixch")
    ap.add_argument("--states-root", default="D:/3rd_rat_spikes/analysis/sleep_server/states_1s_final")
    ap.add_argument("--quality", default=str(report_dir(COHORT) / f"ephys_spikes_swr_quality_{COHORT}.csv"))
    ap.add_argument("--review", default=str(report_dir(COHORT) / f"ephys_spikes_sleep_review_{COHORT}.csv"))
    ap.add_argument("--cohort-yaml", default=str(HERE.parent / f"cohorts/{COHORT}.yaml"))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    if a.cmd == "run":
        run(a)


if __name__ == "__main__":
    main()
