r"""Sleep-state quantification for cohort 2026c: NREM / REM time per animal-day and the circadian (hour-of-day) profile.

Two steps:
  export    (run where the scorer outputs are; the server for the full run): one compact file per session,
            <out>/<SFxx>/<session>.states.npz = 1-s epochs ts (s since Record Start, epoch centre), state (1 WAKE, 3 NREM,
            5 REM), and the scorer's metrics on the same grid (sw = broadband slow wave, th = theta ratio, emg; all
            min-max normalised per session) + the thresholds and channels.
  quantify  (local): per animal-day and per hour of day, from those files + the reviewed session table
            (results/<c>/ephys_spikes/reports/ephys_spikes_sleep_review_<c>.csv, from sleep_review.py --merge).

Definitions (quantify):
  t(k)        wallclock of epoch k = session start (logger RTC at Record Start, the folder name; field-PC time within ~1 s)
              + ts(k) seconds. Hours are field-PC local time (EDT).
  included    a session counts unless: the user marked it `noise` (logger noise), it carries the tag SF12_contact_failing
              (ephys.quality_flags), it is shorter than MIN_SESSION_H (its per-session thresholds rest on too little data),
              or it was not scored; epochs after a session's valid_until and after the paddock end (PADDOCK_END) drop out.
              Sessions marked `bad` (the user's suspect-REM flag) are kept; a sensitivity number drops them.
  phases      light = [sunrise, sunset), dark = the rest of the calendar day; sunrise / sunset for the paddock
              (LAT, LON) from the NOAA solar equations, in EDT.
  f_X,p(a,d)  = seconds of state X / included seconds, animal a, calendar day d, phase p (light / dark).
  X per 24 h  M_X(a,d) = sum_p f_X,p(a,d) * L_p(d), L_p = phase length (min): minutes of X per 24 h, weighting each phase by
              its true length so unequal coverage of day and night does not bias it. An animal-day counts only if both
              phases are covered >= MIN_PHASE_COVER.
  hourly      f_X(a,h) = seconds of X / included seconds over all window epochs with local hour h (0-23).
  mean +- SEM across animals: SEM = sd / sqrt(N), N = animals contributing (one value per animal: its mean over days).

Usage:
  python ephys/sleep_quant.py export --src <sleep root> [--variant imu_remclean] --out <dir>
  python ephys/sleep_quant.py quantify --cohort 2026c --states D:/3rd_rat_spikes/analysis/sleep_server/states_1s
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

LAT, LON, UTC_OFFSET_H = 42.45, -76.47, -4          # paddock near Ithaca NY; EDT for the whole cohort (Aug 30 - Sep 12)
MIN_SESSION_H = 0.5
MIN_PHASE_COVER = 0.5
PADDOCK_END = pd.Timestamp("2026-09-12 10:10:00")
WINDOW = (pd.Timestamp("2026-08-31 00:00"), pd.Timestamp("2026-09-07 00:00"))   # to SF11's last day (implant off 09-07 06:10)
STATES = {"WAKE": 1, "NREM": 3, "REM": 5}


# ---------------------------------------------------------------- export (no repo imports: runs on the server as is)
def export(src: Path, variant: str, out: Path) -> None:
    from scipy.io import loadmat
    n = 0
    for mat in sorted((src / variant).glob("*/*/*.SleepState.states.mat")):
        animal, session = mat.parent.parent.name, mat.parent.name
        st = loadmat(mat, simplify_cells=True)["SleepState"]
        m = st["detectorinfo"]["detectionparms"]["SleepScoreMetrics"]
        h = m["histsandthreshs"]
        ts = np.asarray(st["idx"]["timestamps"], dtype=np.float64).reshape(-1)
        t = np.asarray(m["t_clus"], dtype=np.float64).reshape(-1)
        k = np.clip(np.searchsorted(t, ts), 0, len(t) - 1)
        dest = out / animal / f"{session}.states.npz"
        dest.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(dest, ts=ts.astype(np.int32), state=np.asarray(st["idx"]["states"]).reshape(-1).astype(np.uint8),
                            sw=np.asarray(m["broadbandSlowWave"]).reshape(-1)[k].astype(np.float32),
                            th=np.asarray(m["thratio"]).reshape(-1)[k].astype(np.float32),
                            emg=np.asarray(m["EMG"]).reshape(-1)[k].astype(np.float32),
                            thresholds=np.asarray([h["swthresh"], h["EMGthresh"], h["THthresh"]], dtype=np.float64),
                            channels=np.asarray([m["SWchanID"], m["THchanID"]], dtype=np.int32))
        n += 1
    print(f"{n} sessions -> {out}")


# ---------------------------------------------------------------- solar (NOAA equations)
def sun_times(d: date) -> tuple[datetime, datetime]:
    """Sunrise and sunset (naive local EDT) at (LAT, LON) on date d; zenith 90.833 deg (standard sunrise)."""
    n = d.timetuple().tm_yday
    g = 2 * math.pi / 365 * (n - 1)
    eqt = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g) - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
            - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    lat = math.radians(LAT)
    ha = math.degrees(math.acos(math.cos(math.radians(90.833)) / (math.cos(lat) * math.cos(decl)) - math.tan(lat) * math.tan(decl)))
    noon = 720 - 4 * LON - eqt + UTC_OFFSET_H * 60          # minutes after local midnight
    base = datetime(d.year, d.month, d.day)
    return base + timedelta(minutes=noon - 4 * ha), base + timedelta(minutes=noon + 4 * ha)


# ---------------------------------------------------------------- quantify
def load_epochs(cohort: str, states_dir: Path, review_csv: Path, drop_bad: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """All included epochs (animal, t, state) + the per-session inclusion table."""
    rv = pd.read_csv(review_csv)
    rv["start"] = pd.to_datetime(rv.start_local)
    rows, parts = [], []
    for r in rv.itertuples():
        f = states_dir / r.animal / f"{r.session}.states.npz"
        tags = str(r.tags) if isinstance(r.tags, str) else ""
        reason = ("not scored" if not f.exists() else "noise (user)" if r.verdict == "noise"
                  else "SF12_contact_failing" if "SF12_contact_failing" in tags
                  else f"< {MIN_SESSION_H} h" if (r.duration_h or 0) < MIN_SESSION_H
                  else "bad (user), sensitivity" if drop_bad and r.verdict == "bad" else "")
        rows.append({"animal": r.animal, "session": r.session, "start": r.start, "duration_h": r.duration_h,
                     "verdict": r.verdict, "tags": tags, "excluded": reason})
        if reason:
            continue
        with np.load(f) as z:
            ts, st = z["ts"].astype(np.int64), z["state"]
        t = r.start + pd.to_timedelta(ts, unit="s")
        keep = np.asarray(t < PADDOCK_END)
        for tag in tags.split(";"):
            if tag.startswith("valid_until "):
                keep &= np.asarray(t < pd.Timestamp(tag[len("valid_until "):]))
        parts.append(pd.DataFrame({"animal": r.animal, "t": t[keep], "state": st[keep]}))
    ep = pd.concat(parts, ignore_index=True)
    return ep[ep.state > 0], pd.DataFrame(rows)


def per_day(ep: pd.DataFrame) -> pd.DataFrame:
    ep = ep.assign(date=ep.t.dt.date)
    out = []
    for (an, d), g in ep.groupby(["animal", "date"]):
        sr, ss = sun_times(d)
        light = (g.t >= sr) & (g.t < ss)
        L = {"light": (ss - sr).total_seconds() / 60, "dark": 1440 - (ss - sr).total_seconds() / 60}
        row = {"animal": an, "date": d, "sunrise": sr.strftime("%H:%M"), "sunset": ss.strftime("%H:%M")}
        ok = True
        for ph, m in (("light", light), ("dark", ~light)):
            sec = int(m.sum())
            row[f"{ph}_cover"] = round(sec / 60 / L[ph], 3)
            ok &= sec / 60 / L[ph] >= MIN_PHASE_COVER
            for X, code in STATES.items():
                row[f"f_{X}_{ph}"] = round(float((g.state[m] == code).mean()), 4) if sec else np.nan
        for X in STATES:
            row[f"{X}_min_24h"] = round(row[f"f_{X}_light"] * L["light"] + row[f"f_{X}_dark"] * L["dark"], 1)
        row["included_day"] = bool(ok)
        out.append(row)
    return pd.DataFrame(out)


def hourly(ep: pd.DataFrame) -> pd.DataFrame:
    e = ep.assign(hour=ep.t.dt.hour)
    rows = []
    for (an, h), g in e.groupby(["animal", "hour"]):
        r = {"animal": an, "hour": h, "seconds": len(g)}
        for X, code in STATES.items():
            r[f"f_{X}"] = float((g.state == code).mean())
        r["rem_share_of_sleep"] = r["f_REM"] / max(1e-9, r["f_REM"] + r["f_NREM"])
        rows.append(r)
    return pd.DataFrame(rows)


def load_weather(sync_root: Path) -> pd.DataFrame:
    """5-min weather for cohort 3 from field2026-sync from-field/ (coverage note: 2026-09-10_cohort3-weather.md): the on-site
    console's cloud export for 08-31 -> 09-10 21:50, the field PC's local listener after that, and the NWS Ithaca-airport
    series (KITH, off-site substitute) only inside the console's uplink hole 09-02 21:10 -> 09-03 15:16. Columns: t (EDT),
    temp_C, rh_pct, rain_rate_mmh, daily_rain_mm (the console's accumulator, resets at local midnight; NaN on NWS rows), source."""
    F = sync_root / "from-field"

    def awn(paths, source):
        d = pd.concat([pd.read_csv(p, encoding="utf-8", encoding_errors="replace") for p in paths], ignore_index=True)
        c = lambda key: next(x for x in d.columns if key in x)  # noqa: E731 - headers differ only in the degree sign's encoding
        return pd.DataFrame({"t": pd.to_datetime(d["Simple Date"]), "temp_C": d[c("Outdoor Temperature")], "rh_pct": d[c("Humidity (%)")],
                             "rain_rate_mmh": d[c("Rain Rate")], "daily_rain_mm": d[c("Daily Rain")], "source": source})
    cloud = awn([F / "AWN-F8B3B78DEAC9-20260831-20260910.csv"], "on-site cloud").sort_values("t")
    local = awn(sorted(F.glob("AWN-F8B3B78DEAC9_2026-09-*.csv")), "on-site listener")
    local = local[local.t > cloud.t.max()]
    n = pd.read_csv(F / "NWS-KITH-20260902-20260903_gapfill.csv")
    nws = pd.DataFrame({"t": pd.to_datetime(n.timestamp_utc).dt.tz_convert("America/New_York").dt.tz_localize(None),
                        "temp_C": n.temp_C, "rh_pct": n.rh_pct, "rain_rate_mmh": np.nan, "daily_rain_mm": np.nan, "source": "NWS KITH"})
    gaps = np.flatnonzero((cloud.t.diff() > pd.Timedelta(minutes=15)).to_numpy())
    inside = np.zeros(len(nws), bool)
    for i in gaps:
        inside |= ((nws.t > cloud.t.iloc[i - 1]) & (nws.t < cloud.t.iloc[i])).to_numpy()
    return pd.concat([cloud, nws[inside], local], ignore_index=True).sort_values("t").reset_index(drop=True)


def daily_weather(w: pd.DataFrame) -> pd.DataFrame:
    """Per local calendar day: mean temperature (degC) and humidity (%) over all samples; rain_mm = the day's maximum of the
    console accumulator; rain_complete = the console reported until >= 23:30 (else rain_mm is a lower bound: 09-02)."""
    g = w.groupby(w.t.dt.date)
    con = w[w.source.str.startswith("on-site")]
    gc = con.groupby(con.t.dt.date)
    d = pd.DataFrame({"temp_C": g.temp_C.mean().round(2), "rh_pct": g.rh_pct.mean().round(1),
                      "rain_mm": gc.daily_rain_mm.max(),
                      "rain_complete": gc.t.max().apply(lambda t: t.hour * 60 + t.minute >= 23 * 60 + 30),
                      "weather_cover": g.t.apply(lambda t: round(min(1.0, t.dt.floor("5min").nunique() / 288), 3)),
                      "nws_share": g.source.apply(lambda s: round(float(s.str.startswith("NWS").mean()), 3))})
    d.index.name = "date"
    return d


def glm_logit(df: pd.DataFrame, y: str, xs: list[str]):
    """Quasi-binomial GLM, logit link, one intercept per animal (no common constant), cluster-robust SEs by date with the
    small-sample correction and t(G-1) inference (the weather is one value per day, so days are the independent units)."""
    import statsmodels.api as sm
    X = pd.concat([pd.get_dummies(df.animal, prefix="an", dtype=float), df[xs].astype(float)], axis=1)
    groups = pd.factorize(df.date)[0]
    return sm.GLM(df[y].astype(float), X, family=sm.families.Binomial()).fit(
        scale="X2", cov_type="cluster", cov_kwds={"groups": groups, "use_correction": True, "df_correction": True}, use_t=True)


def weather_and_trend_stats(day: pd.DataFrame, wd: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[str]]:
    """Returns (model table, per-animal slopes, the analysed animal-day table, notes). Unit = included animal-day.
      p_X(a,d)  = M_X(a,d) / 1440                       (share of the 24 h in state X, phase-weighted)
      z(v)      = (v - mean_d v) / sd_d v over the analysed days (one value per day)
      weather   logit E[p_X] = alpha_a + beta_v z(v_d)          (one model per weather variable v, then all three jointly)
      trend     logit E[p_X] = alpha_a + gamma * day            (day = days since 09-01); per animal: OLS p_X = a + s_a day,
                across animals: one-sample t-test and Wilcoxon of s_a vs 0, count of s_a < 0
      effect    pp per SD ~ beta * pbar (1 - pbar) * 100 at the mean share pbar
    """
    from scipy import stats
    d = day[day.included_day].copy()
    d["date"] = pd.to_datetime(d.date)
    d = d.merge(wd.reset_index().assign(date=lambda x: pd.to_datetime(x.date)), on="date", how="left")
    d["day"] = (d.date - pd.Timestamp("2026-09-01")).dt.days
    for X in ("NREM", "REM"):
        d[f"p_{X}"] = d[f"{X}_min_24h"] / 1440
    dd = d.drop_duplicates("date").set_index("date")
    for v in ("temp_C", "rh_pct", "rain_mm"):
        d[f"z_{v}"] = (d[v] - dd[v].mean()) / dd[v].std(ddof=1)
    notes = [f"analysed: {len(d)} animal-days, {d.date.nunique()} days ({d.date.min():%m-%d}..{d.date.max():%m-%d}), "
             f"{d.animal.nunique()} animals"]
    cors = dd[["temp_C", "rh_pct", "rain_mm"]].assign(day=(dd.index - pd.Timestamp("2026-09-01")).days).corr().round(2)
    notes.append("correlation across days: " + "; ".join(f"{a}~{b} {cors.loc[a, b]:+.2f}" for i, a in enumerate(cors.columns)
                                                          for b in cors.columns[i + 1:]))
    rows = []
    for X in ("NREM", "REM"):
        pbar = d[f"p_{X}"].mean()
        specs = [("temp_C",), ("rh_pct",), ("rain_mm",), ("temp_C", "rh_pct", "rain_mm"), ("day",), ("day", "rh_pct")]
        for spec in specs:
            xs = ["day" if v == "day" else f"z_{v}" for v in spec]
            r = glm_logit(d, f"p_{X}", xs)
            for x in xs:
                unit = "per day" if x == "day" else "per SD"
                rows.append({"outcome": X, "model": " + ".join(spec), "term": x.replace("z_", ""), "beta_logit": round(r.params[x], 4),
                             "se": round(r.bse[x], 4), "p": round(float(r.pvalues[x]), 4),
                             f"pp_{unit.replace(' ', '_')}": round(r.params[x] * pbar * (1 - pbar) * 100, 2),
                             "n_animal_days": int(r.nobs), "n_days": d.date.nunique()})
        # day-level cross-check: across-animal mean per day vs each weather variable (N = days)
        m = d.groupby("date")[f"p_{X}"].mean()
        for v in ("temp_C", "rh_pct", "rain_mm"):
            lr = stats.linregress(dd.loc[m.index, v], m * 100)
            rows.append({"outcome": X, "model": f"day means ~ {v}", "term": v, "beta_logit": np.nan, "se": round(lr.stderr, 4),
                         "p": round(lr.pvalue, 4), "pp_per_SD": round(lr.slope * dd[v].std(ddof=1), 2), "r": round(lr.rvalue, 2),
                         "n_animal_days": np.nan, "n_days": len(m)})
    tab = pd.DataFrame(rows)
    sl = []
    for X in ("NREM", "REM"):
        for an, g in d.groupby("animal"):
            if len(g) >= 4:
                lr = stats.linregress(g.day, g[f"p_{X}"] * 100)
                sl.append({"outcome": X, "animal": an, "n_days": len(g), "slope_pp_per_day": round(lr.slope, 3), "p_within": round(lr.pvalue, 3),
                           "first_day": f"{g.date.min():%m-%d}", "last_day": f"{g.date.max():%m-%d}"})
    slopes = pd.DataFrame(sl)
    for X in ("NREM", "REM"):
        s = slopes[slopes.outcome == X].slope_pp_per_day
        t = stats.ttest_1samp(s, 0.0)
        w = stats.wilcoxon(s) if len(s) >= 2 else None
        notes.append(f"{X} slope across animals: mean {s.mean():+.3f} pp/day (SEM {s.std(ddof=1) / np.sqrt(len(s)):.3f}), "
                     f"{int((s < 0).sum())}/{len(s)} negative; t({len(s) - 1}) = {t.statistic:.2f}, p = {t.pvalue:.4f}; "
                     f"Wilcoxon p = {w.pvalue:.4f}" if w is not None else "")
    return tab, slopes, d, notes


def save_fig(fig, path: Path) -> Path:
    """Save; if the target is locked (e.g. open in a viewer on Windows), write <name>.new.png next to it instead of failing."""
    try:
        fig.savefig(path, dpi=140)
        return path
    except OSError as e:
        alt = path.with_name(path.stem + ".new.png")
        fig.savefig(alt, dpi=140)
        print(f"WARNING: {path.name} is locked ({e.strerror}); wrote {alt.name} - close the viewer and rerun to replace it")
        return alt


def md_table(df: pd.DataFrame) -> list[str]:
    return (["| " + " | ".join(map(str, df.columns)) + " |", "|" + "---|" * len(df.columns)]
            + ["| " + " | ".join(map(str, r)) + " |" for r in df.itertuples(index=False)])


def mean_sem(x: pd.Series) -> tuple[float, float, int]:
    x = x.dropna()
    n = len(x)
    return float(x.mean()), float(x.std(ddof=1) / math.sqrt(n)) if n > 1 else float("nan"), n


def quantify(cohort: str, states_dir: Path, review_csv: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from _common import figure_dir, git_commit, report_dir, utc_now_iso

    ep, sess = load_epochs(cohort, states_dir, review_csv)
    rd, fd = report_dir(cohort), figure_dir(cohort)
    sess.to_csv(rd / f"ephys_spikes_sleep_quant_sessions_{cohort}.csv", index=False)
    day = per_day(ep)
    day.to_csv(rd / f"ephys_spikes_sleep_quant_days_{cohort}.csv", index=False)
    win = ep[(ep.t >= WINDOW[0]) & (ep.t < WINDOW[1])]
    hr = hourly(win)
    hr.to_csv(rd / f"ephys_spikes_sleep_quant_hourly_{cohort}.csv", index=False)

    # window summary: one value per animal (mean over its included days), then mean +- SEM across animals
    dw = day[day.included_day & (pd.to_datetime(day.date) >= WINDOW[0]) & (pd.to_datetime(day.date) < WINDOW[1])]
    per_an = dw.groupby("animal")[["NREM_min_24h", "REM_min_24h", "WAKE_min_24h", "f_NREM_light", "f_NREM_dark", "f_REM_light", "f_REM_dark"]].mean()
    per_an["n_days"] = dw.groupby("animal").size()
    per_an["rem_share_of_sleep"] = per_an.REM_min_24h / (per_an.REM_min_24h + per_an.NREM_min_24h)
    per_an.round(4).to_csv(rd / f"ephys_spikes_sleep_quant_window_per_animal_{cohort}.csv")
    ep_b, _ = load_epochs(cohort, states_dir, review_csv, drop_bad=True)
    day_b = per_day(ep_b)
    dwb = day_b[day_b.included_day & (pd.to_datetime(day_b.date) >= WINDOW[0]) & (pd.to_datetime(day_b.date) < WINDOW[1])]
    per_an_b = dwb.groupby("animal")[["NREM_min_24h", "REM_min_24h"]].mean()

    # ---- weather + statistics
    from _common import sibling_repo
    wx = load_weather(sibling_repo("field2026-sync"))
    wd = daily_weather(wx)
    wd.to_csv(rd / f"ephys_spikes_sleep_quant_weather_daily_{cohort}.csv")
    tab, slopes, dan, notes = weather_and_trend_stats(day, wd)
    tab.to_csv(rd / f"ephys_spikes_sleep_quant_glm_{cohort}.csv", index=False)
    slopes.to_csv(rd / f"ephys_spikes_sleep_quant_slopes_{cohort}.csv", index=False)
    win_days = day[(pd.to_datetime(day.date) >= WINDOW[0]) & (pd.to_datetime(day.date) < WINDOW[1])]
    _, slopes_w, _, notes_w = weather_and_trend_stats(win_days, wd)

    # ---- figures
    days_all = sorted(day.date.unique())
    fig, axes = plt.subplots(3, 1, figsize=(11, 10), sharex=True, gridspec_kw={"height_ratios": [3, 3, 2]})
    for ax, X, col in ((axes[0], "NREM", "#1f5fa8"), (axes[1], "REM", "#b8322a")):
        di = day[day.included_day]
        for an, g in di.groupby("animal"):
            ax.plot(pd.to_datetime(g.date), g[f"{X}_min_24h"] / 60, "-", color="0.7", lw=0.8)
            ax.text(pd.to_datetime(g.date.iloc[-1]), g[f"{X}_min_24h"].iloc[-1] / 60, f" {an}", fontsize=6, color="0.5", va="center")
        stats = [(pd.Timestamp(d),) + mean_sem(di[di.date == d][f"{X}_min_24h"] / 60) for d in days_all]
        xs, ms, ss, ns = zip(*stats)
        ax.errorbar(xs, ms, yerr=ss, fmt="o-", color=col, capsize=3, lw=1.6, label="mean ± SEM across animals")
        for x, m, s, n in stats:
            if n:
                ax.annotate(f"N={n}", (x, m + (s if s == s else 0)), textcoords="offset points", xytext=(0, 5), ha="center", fontsize=7)
        ax.axvspan(WINDOW[0], WINDOW[1] - pd.Timedelta(hours=12), color=col, alpha=0.06, label="window (all 6 animals)")
        ax.set_ylabel(f"{X} (h per 24 h)")
        ax.set_title(f"{X} per day (phase-weighted, days with both phases >= {MIN_PHASE_COVER:.0%} recorded)", fontsize=9)
        ax.legend(fontsize=7, loc="upper right")
    axw = axes[2]
    wdp = wd[(pd.to_datetime(wd.index) >= pd.Timestamp(min(days_all))) & (pd.to_datetime(wd.index) <= pd.Timestamp(max(days_all)))]
    xd = pd.to_datetime(wdp.index)
    axw.bar(xd, wdp.rain_mm, width=0.6, color="#4a90c2", alpha=0.6, label="rain (mm/day, console)")
    for x, r, ok in zip(xd, wdp.rain_mm, wdp.rain_complete):
        if not ok and r == r:
            axw.annotate(">=", (x, r), textcoords="offset points", xytext=(0, 2), ha="center", fontsize=7, color="#4a90c2")
    axw.set_ylabel("rain (mm/day)", color="#4a90c2")
    axh = axw.twinx()
    axh.plot(xd, wdp.rh_pct, "s-", color="0.35", ms=4, lw=1.2, label="humidity (% mean)")
    axh.plot(xd, wdp.temp_C * 4, "^-", color="#d98c1f", ms=4, lw=1.2, label="temperature (°C x 4)")
    axh.set_ylabel("humidity % / temperature °C x 4")
    h1, l1 = axw.get_legend_handles_labels()
    h2, l2 = axh.get_legend_handles_labels()
    axw.legend(h1 + h2, l1 + l2, fontsize=7, loc="upper right")
    axw.set_title("on-site weather (console; NWS airport inside the 09-02 21:10 - 09-03 15:16 uplink hole; '>=' = rain lower bound)", fontsize=8)
    axw.tick_params(axis="x", labelrotation=45, labelsize=7)
    fig.suptitle(f"Cohort 2026c sleep per day (imu_remclean; git {git_commit()}, {utc_now_iso()})", fontsize=9)
    fig.tight_layout()
    f1 = save_fig(fig, fd / f"ephys_spikes_sleep_quant_per_day_{cohort}.png")

    srs = [sun_times(d) for d in sorted(win.t.dt.date.unique())]
    sr_h = np.mean([s.hour + s.minute / 60 for s, _ in srs])
    ss_h = np.mean([e.hour + e.minute / 60 for _, e in srs])
    fig, axes = plt.subplots(1, 3, figsize=(14, 3.8))
    for ax, key, lab, col in ((axes[0], "f_NREM", "NREM (% of recorded time)", "#1f5fa8"),
                              (axes[1], "f_REM", "REM (% of recorded time)", "#b8322a"),
                              (axes[2], "rem_share_of_sleep", "REM share of sleep (%)", "#6a3d9a")):
        piv = hr.pivot(index="hour", columns="animal", values=key) * 100
        for an in piv.columns:
            ax.plot(piv.index + 0.5, piv[an], color="0.75", lw=0.7)
        m = piv.mean(axis=1)
        s = piv.std(axis=1, ddof=1) / np.sqrt(piv.notna().sum(axis=1))
        ax.plot(piv.index + 0.5, m, color=col, lw=2, label=f"mean ± SEM, N={piv.shape[1]}")
        ax.fill_between(piv.index + 0.5, m - s, m + s, color=col, alpha=0.25)
        ax.axvspan(0, sr_h, color="0.2", alpha=0.08)
        ax.axvspan(ss_h, 24, color="0.2", alpha=0.08, label="dark (mean sunset-sunrise)")
        ax.set_xlim(0, 24)
        ax.set_xticks(range(0, 25, 3))
        ax.set_xlabel("hour of day (EDT, field-PC time)")
        ax.set_ylabel(lab)
        ax.legend(fontsize=7)
    fig.suptitle(f"Circadian profile, {WINDOW[0]:%m-%d} - {WINDOW[1] - pd.Timedelta(days=1):%m-%d} (all 6 animals); "
                 f"grey = single animals (git {git_commit()})", fontsize=9)
    fig.tight_layout()
    f2 = save_fig(fig, fd / f"ephys_spikes_sleep_quant_circadian_{cohort}.png")

    # ---- report
    def ms(col, df=per_an, scale=1.0):
        m, s, n = mean_sem(df[col] * scale)
        return f"{m:.1f} ± {s:.1f} (N={n})"
    excl = sess[sess.excluded != ""].groupby("excluded").agg(sessions=("session", "size"), hours=("duration_h", "sum")).round(1)
    lines = [
        f"# Sleep quantification, cohort {cohort} (imu_remclean)", "",
        f"Generated by `ephys/sleep_quant.py quantify` (git {git_commit()}, {utc_now_iso()}). Definitions: the module docstring; "
        "summary below.", "",
        "## Inclusion",
        f"- Included epochs: {len(ep) / 3600:.0f} h over {ep.animal.nunique()} animals.",
        "- Sessions excluded:", "",
        "| Reason | Sessions | Hours |", "|---|---|---|",
        *[f"| {k} | {int(v.sessions)} | {v.hours:.1f} |" for k, v in excl.iterrows()], "",
        f"- Window for the across-animal summary: {WINDOW[0]:%Y-%m-%d} to {WINDOW[1] - pd.Timedelta(days=1):%Y-%m-%d}, "
        "the last days with all 6 animals (SF11's implant came off on 09-07 at 06:10).",
        f"- An animal-day counts if both its light and its dark phase are at least {MIN_PHASE_COVER:.0%} recorded.", "",
        "## Window summary (one value per animal = its mean over included days; mean ± SEM across animals)", "",
        "| Quantity | Mean ± SEM |", "|---|---|",
        f"| NREM, h per 24 h | {ms('NREM_min_24h', scale=1 / 60)} |",
        f"| REM, h per 24 h | {ms('REM_min_24h', scale=1 / 60)} |",
        f"| WAKE, h per 24 h | {ms('WAKE_min_24h', scale=1 / 60)} |",
        f"| REM share of sleep, % | {ms('rem_share_of_sleep', scale=100)} |",
        f"| NREM, % of light phase | {ms('f_NREM_light', scale=100)} |",
        f"| NREM, % of dark phase | {ms('f_NREM_dark', scale=100)} |",
        f"| REM, % of light phase | {ms('f_REM_light', scale=100)} |",
        f"| REM, % of dark phase | {ms('f_REM_dark', scale=100)} |", "",
        f"Sensitivity, dropping the 3 sessions the user flagged `bad` (SF07, suspect REM): NREM "
        f"{ms('NREM_min_24h', per_an_b, 1 / 60)} h, REM {ms('REM_min_24h', per_an_b, 1 / 60)} h per 24 h.", "",
        "Per animal:", "", *md_table(per_an.round(3).reset_index()), "",
        "## Weather (per calendar day)", "",
        "Sources and rules: `load_weather` / `daily_weather` docstrings.",
        "- `rain_mm` is the on-site console's daily accumulator (its maximum over the day).",
        "- `rain_complete = False` makes `rain_mm` a lower bound.",
        "- `nws_share` = the share of samples from the NWS airport substitute.", "",
        *md_table(wd.reset_index()), "",
        "## Does the weather go with NREM / REM? (GLM)", "",
        "**Unit:** one included animal-day.",
        "**Outcome:** $p_X = M_X / 1440$, the share of the 24 h spent in state X, phase-weighted as in the per-day figure.",
        "**Model:** a quasi-binomial GLM with a logit link and one intercept per animal:",
        "$$\\operatorname{logit} E[p_X(a,d)] = \\alpha_a + \\beta\\, z(v_d)$$",
        "- $z(v)$ = the weather variable standardised across the analysed days.",
        "- Standard errors are cluster-robust by day, with the small-sample correction and $t(G-1)$ inference, $G$ = number of "
        "days. The weather is one value per day, so **days, not animal-days, are the independent units**.",
        "- `pp_per_SD` ≈ $\\beta\\,\\bar p(1-\\bar p) \\times 100$ = the change in percentage points of the 24 h per 1 SD of "
        "the variable.",
        "- The `day means ~ v` rows are the plain cross-check: across-animal mean per day regressed on $v$ (N = days).", "",
        "Notes:", "", *[f"- {n}" for n in notes if n], "",
        *md_table(tab.fillna("")), "",
        "## Is the REM (and NREM) change over days consistent across animals?", "",
        "- **Per animal:** an OLS slope $s_a$ of $100\\,p_X$ on day (days since 09-01), for animals with ≥ 4 analysed days.",
        "- **Across animals:** a one-sample $t$-test and a Wilcoxon signed-rank test of $s_a$ against 0, plus the count of "
        "negative slopes. With N = 6 the smallest two-sided Wilcoxon p is 0.031.",
        "- **Pooled:** the GLM rows `day` above (animal intercepts, cluster by day).", "",
        *md_table(slopes), "",
        f"Window only ({WINDOW[0]:%m-%d}..{WINDOW[1] - pd.Timedelta(days=1):%m-%d}, all 6 animals, no drop-outs):", "",
        *[f"- {n}" for n in notes_w[2:] if n], "",
        "**Caveats for both tests:**",
        "- There are about 11 days.",
        "- Humidity, rain and day order are correlated (see the correlations above), so a weather effect and a time trend "
        "cannot be separated with these data.",
        "- The REM score depends on the LFP theta. Probe advances (SF08 and SF12 on 09-09; SF12 again on 09-10) and SF12's "
        "shank-1 / contact degradation can shift the score over days without any change in sleep.",
        "- The five females released on 09-11 at 19:40 change the social regime for the last day.", "",
        "## Figures",
        f"- `{f1.relative_to(rd.parent).as_posix()}`: per day, all days (N falls after 09-06: SF11 implant loss; SF12 from 09-10).",
        f"- `{f2.relative_to(rd.parent).as_posix()}`: hour-of-day profile over the window; dark shading = mean "
        f"sunset {int(ss_h)}:{int(ss_h % 1 * 60):02d} to sunrise {int(sr_h)}:{int(sr_h % 1 * 60):02d} EDT.", "",
        "## Caveats",
        "- **Scores are automatic.** The user's review is a strict visual screen, not a manual scoring, so there is no "
        "epoch-level accuracy number yet.",
        "- **Thresholds are per session.** Short sessions are excluded for this reason.",
        "- **The 09-11 19:40 release of five females** (population 5 to 10) lies after the window.",
        "- **The clock is the logger RTC** (≈ field-PC time within ~1 s), which is irrelevant at hour resolution.",
    ]
    out = rd / f"ephys_spikes_sleep_quant_{cohort}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"-> {out}\n   {f1}\n   {f2}")
    print(per_an.round(3).to_string())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--src", required=True)
    e.add_argument("--variant", default="imu_remclean")
    e.add_argument("--out", required=True)
    q = sub.add_parser("quantify")
    q.add_argument("--cohort", default=None)
    q.add_argument("--states", required=True)
    q.add_argument("--review", default=None, help="default reports/ephys_spikes_sleep_review_<c>.csv")
    a = ap.parse_args()
    if a.cmd == "export":
        export(Path(a.src), a.variant, Path(a.out))
        return
    from _common import report_dir, resolve_cohort
    c = resolve_cohort(a.cohort)
    quantify(c, Path(a.states), Path(a.review) if a.review else report_dir(c) / f"ephys_spikes_sleep_review_{c}.csv")


if __name__ == "__main__":
    main()
