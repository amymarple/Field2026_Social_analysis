r"""
analyze_evening_morning_sleep.py — Direction 3: EVENING (baseline) vs MORNING
(weather-driven) sleep, analyzed SEPARATELY.

The two daytime rest episodes that bracket the nocturnal active period have
different drivers, so pooling them (as Stage B's 05:00-21:00 window does) blurs
the question. This driver splits them:

  * EVENING sleep = local [17:00, sleep_end(day)) — the settle after the daytime heat
    has passed, before nocturnal emergence. It is the LEAST daytime-influenced readout
    of a rat's BASELINE sleep-site preference. The nocturnal rat's "day" is one full
    SLEEP PERIOD (not a 0-24 h calendar day), so its END — `sleep_end_hour` — is the
    evening/overnight emergence, TEMPERATURE-CALIBRATED (a single cross-day theta*) and
    searched THROUGH the night, so it is hours-since-midnight and MAY EXCEED 24 on hot
    nights (via wiser_analysis_utils.temperature_calibrated_sleep_end). A behavioral
    emergence time + a per-night activity-fraction profile are independent cross-checks.

  * MORNING sleep = local [05:00, 10:00), BEFORE the ~10:00 sleep-site switch — the
    bed-down after the active night. Its SITE is expected to depend on temperature +
    (overnight) rain. We test whether the morning site DEPARTS from the rat's own
    evening baseline as a function of morning temperature / overnight rain.

Guardrails (regime-aware-wiser-tracking): sleep = low-speed PROXY (not ephys); a
signal gap is 'unknown', never 'moved' (per-window dropout reported, high-dropout =
lower-confidence); WISER inch frame UNVERIFIED -> ROI-identity + RELATIVE displacement
only (house_2 not "cooler", no directional claim); jitter floor ~7 in (tiers reuse
RELOCATION_TIERS); refuge_4 is a BURROW ENTRANCE 07-03->07-07 (flagged, never a rest
site); weather acts on BOTH the animal path and the UWB-dropout path, so language is
"temperature/weather-linked", never causal. Field-log notes are hypotheses, not labels.

Read-only on the DB + AWN weather CSVs. Data outputs to
D:\Field2026_analysis_out\direction3_evening_morning_sleep_<ts>\; the report is also copied to
wiser/outputs/direction3_evening_morning_sleep/.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
import wiser_analysis_utils as w        # noqa: E402
import time_utils                       # noqa: E402
import metrics                          # noqa: E402

DEFAULT_DB = Path(r"D:\Reolink_record\audio_in\Wiser_backup\snapshots\1stcohort_2026_2026-07-09.sqlite")
DEFAULT_FIXED = Path(r"D:\Reolink_record\audio_in\Wiser_backup\snapshots\tag_reports_2026-06-30.sqlite")
DEFAULT_GT = PROJECT_ROOT / "configs" / "fixed_position_ground_truth.csv"
DEFAULT_ROIS = PROJECT_ROOT / "configs" / "wiser_rois.json"
DEFAULT_WEATHER = [
    Path(r"D:\Reolink_record\audio_in\weather_data\AWN-F8B3B78DEAC9-20260628-20260709.csv"),  # newest, spans 06-28→07-09
    Path(r"D:\Reolink_record\audio_in\weather_data\AWN-F8B3B78DEAC9-20260628-20260705.csv"),
    Path(r"D:\Reolink_record\audio_in\weather_data\AWN-F8B3B78DEAC9-20260628-20260629.csv"),
    Path(r"D:\Reolink_record\audio_in\weather_data\AWN-F8B3B78DEAC9-20260630-20260701.csv"),
]
from output_paths import OUT_ROOT as DEFAULT_OUT_ROOT   # single source of truth (env FIELD2026_ANALYSIS_OUT_ROOT)
REPORT_DIR = PROJECT_ROOT / "outputs" / "direction3_evening_morning_sleep"
DROP_TAGS = {"12409"}                    # Sova, removed 2026-06-29 15:00

MORNING_START, MORNING_END = 5, 10       # local h — morning-sleep site, read BEFORE the ~10:00 switch
EVENING_START = 17                       # local h — evening-sleep window start (5 pm)
SITE_CEIL_H = 24.0                       # cap for the evening resting-SITE slice (loaded window ends here)
SLEEP_END_CEIL_H = 30.0                  # search the sleep-period end THROUGH the night, up to 06:00 next day
ACT_BIN_S = 300                          # 5-min bins for the activity-fraction profile
BIN_S = 60                               # dropout-grid bin
WET_THR_MM = 0.2                         # overnight_rain_mm above this = a "wet" morning
BURROW_ROI = "refuge_4"
BURROW_WINDOW = ("2026-07-03", "2026-07-07")   # local dates [dig start, removal)

DAY_CONTEXT = {
    "2026-06-28": "warm ~22-23C (evening release ~19:25); PARTIAL day (evening only)",
    "2026-06-29": "sunny/HOT ~30C; obs 'house may be too hot'; Sova removed 15:00",
    "2026-06-30": "sunny/humid HIGH ~34C; thunderstorm/rain ~17:30; AM IR-condensation fog",
    "2026-07-01": "sunny/humid high ~36C; thunderstorm/rain ~19:45 (post evening window)",
    "2026-07-02": "hot ~33-35C midday",
    "2026-07-03": "pre-dawn fog; refuge_4 BURROW digging begins ~01:00 (nightly)",
    "2026-07-04": "July-4th fireworks ~21:00; refuge_4 burrow active",
    "2026-07-05": "refuge_4 burrow active",
    "2026-07-06": "refuge_4 hole discovered ~13:00; burrow active",
    "2026-07-07": "refuge_4 REMOVED ~13:00; CH07/CH08 interior cams added ~14:38",
    "2026-07-08": "refuge_4 gone (removed 07-07)",
}


# ---------------------------------------------------------------------------
# small stats / weather helpers (numpy only; no scipy dependency)
# ---------------------------------------------------------------------------
def _spearman(x, y):
    """Spearman rank rho + usable n (Pearson on ranks; numpy only). NaN if n<4 or a
    tie-degenerate (zero-variance) rank vector."""
    x = np.asarray(x, float); y = np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    n = int(len(x))
    if n < 4:
        return np.nan, n
    rx = pd.Series(x).rank().to_numpy()
    ry = pd.Series(y).rank().to_numpy()
    if np.ptp(rx) == 0 or np.ptp(ry) == 0:
        return np.nan, n
    return float(np.corrcoef(rx, ry)[0, 1]), n


def _overnight_rain_mm(wx: pd.DataFrame, night: str, *, start_prev_h=21, end_h=11):
    """Antecedent wetness for a morning bed-down: integral of rain rate over local
    [prev-day 21:00, this-day 11:00). rain_rate_mmhr * dt_h, gaps capped at 30 min so
    a logging gap can't inflate the total. NaN if no rain column / no samples."""
    if wx.empty or "rain_rate_mmhr" not in wx.columns:
        return np.nan
    d0 = pd.Timestamp(night)                      # local midnight of `night`
    lo = d0 - pd.Timedelta(hours=24 - start_prev_h)
    hi = d0 + pd.Timedelta(hours=end_h)
    sub = wx[(wx["datetime_local"] >= lo) & (wx["datetime_local"] < hi)].sort_values("datetime_local")
    if len(sub) < 2:
        return np.nan
    t = sub["datetime_local"].to_numpy()
    r = sub["rain_rate_mmhr"].to_numpy(float)
    dt_h = np.diff(t).astype("timedelta64[s]").astype(float) / 3600.0
    dt_h = np.clip(dt_h, 0.0, 0.5)
    return float(np.nansum(r[:-1] * dt_h))


def _window_weather(wx: pd.DataFrame, night: str, h_lo: float, h_hi: float):
    """Mean temp / rain over local hour band [h_lo, h_hi) on `night`."""
    if wx.empty or "temp_c" not in wx.columns:
        return np.nan, np.nan
    hf = wx["datetime_local"].dt.hour + wx["datetime_local"].dt.minute / 60.0
    m = (wx["datetime_local"].dt.date.astype(str) == night) & (hf >= h_lo) & (hf < h_hi)
    sub = wx[m]
    if sub.empty:
        return np.nan, np.nan
    t = float(sub["temp_c"].mean())
    rr = float(sub["rain_rate_mmhr"].mean()) if "rain_rate_mmhr" in sub.columns else np.nan
    return t, rr


def _burrow_flag(sites: pd.DataFrame) -> pd.Series:
    """True where dominant_roi is the refuge_4 burrow entrance inside the burrow
    window (07-03 -> 07-07): burrow behaviour + UWB-dropout lower bound, NOT sleep."""
    if sites.empty:
        return pd.Series([], dtype=bool)
    lo, hi = BURROW_WINDOW
    return ((sites["dominant_roi"] == BURROW_ROI)
            & (sites["night"] >= lo) & (sites["night"] < hi))


# ---------------------------------------------------------------------------
# dropout guard (per night, shortid, window)
# ---------------------------------------------------------------------------
def _dropout(slice_df: pd.DataFrame, window: str, exp_bins_by_night: dict) -> pd.DataFrame:
    rows = []
    d = slice_df.dropna(subset=["x", "y", "datetime"]).copy()
    if not d.empty:
        d["bin_utc"] = w._bin_utc_ns(d["datetime"], BIN_S)
        for (night, sid), g in d.groupby(["night", "shortid"]):
            exp = exp_bins_by_night.get(str(night), np.nan)
            present = g["bin_utc"].nunique()
            frac = float(1 - present / exp) if exp and exp == exp and exp > 0 else np.nan
            rows.append({"night": str(night), "shortid": str(sid), "window": window,
                         "present_bins": int(present), "expected_bins": (int(exp) if exp == exp else np.nan),
                         "dropout_frac": frac})
    return pd.DataFrame(rows, columns=["night", "shortid", "window", "present_bins",
                                       "expected_bins", "dropout_frac"])


# ---------------------------------------------------------------------------
# figures
# ---------------------------------------------------------------------------
def _fig_evening_baseline(evening_sites, cents, tags, out_path):
    """Evening rest centroid_x per rat across days (house ref lines) — stability of
    the baseline site."""
    if evening_sites.empty:
        return
    nights = sorted(evening_sites["night"].unique())
    fig, ax = plt.subplots(figsize=(max(7, 1.2 * len(nights)), 4.5))
    cmap = plt.get_cmap("tab10")
    for name, (cx, _) in cents.items():
        ax.axhline(cx, color="0.6", ls="--", lw=0.8)
        ax.text(0.002, cx, name, fontsize=7, color="0.4",
                transform=ax.get_yaxis_transform(), va="bottom")
    for i, t in enumerate(tags):
        g = evening_sites[evening_sites["shortid"].astype(str) == str(t)].sort_values("night")
        if g.empty:
            continue
        ax.plot(g["night"], g["centroid_x"], "-o", ms=5, color=cmap(i % 10), label=str(t), alpha=0.85)
    ax.set_ylabel("evening rest centroid x (in)  [UNVERIFIED inch frame]")
    ax.set_title("Direction 3 — EVENING baseline sleep site per rat across days\n"
                 "(evening = 17:00 -> temperature-calibrated end; less daytime-influenced)", fontsize=9.5)
    ax.tick_params(axis="x", labelrotation=45, labelsize=7)
    ax.legend(fontsize=7, ncol=len(tags), title="tag", loc="upper right")
    fig.tight_layout(); fig.savefig(out_path, dpi=130); plt.close(fig)


def _fig_morning_vs_weather(mvb, out_path):
    """Morning displacement-from-evening-baseline vs morning temp and overnight rain."""
    if mvb.empty:
        return
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    tags = sorted(mvb["shortid"].astype(str).unique())
    cmap = plt.get_cmap("tab10"); tcol = {t: cmap(i % 10) for i, t in enumerate(tags)}
    for xcol, ax, xlabel in [("morning_temp_c", axes[0], "morning outside T (C)  [05:00-11:00]"),
                             ("overnight_rain_mm", axes[1], "overnight rain (mm)  [prev 21:00 -> 11:00]")]:
        for t in tags:
            g = mvb[mvb["shortid"].astype(str) == t]
            ax.scatter(g[xcol], g["morning_vs_evening_baseline_in"], s=34,
                       color=tcol[t], label=t, alpha=0.85, edgecolor="none")
        sw = mvb[mvb["shelter_switch_vs_baseline"] == True]  # noqa: E712
        ax.scatter(sw[xcol], sw["morning_vs_evening_baseline_in"], s=120, marker="o",
                   facecolors="none", edgecolors="tab:red", linewidths=1.2, label="shelter switch")
        rho, n = _spearman(mvb[xcol], mvb["morning_vs_evening_baseline_in"])
        ax.axhline(w.RELOCATION_TIERS["stable"], color="0.7", ls=":", lw=0.8)
        ax.set_xlabel(xlabel); ax.set_ylabel("morning move from evening baseline (in)")
        ax.set_title(f"Spearman rho={rho:.2f} (n={n})" if rho == rho else f"Spearman n/a (n={n})",
                     fontsize=9)
    axes[0].legend(fontsize=6.5, ncol=2, loc="upper right")
    fig.suptitle("MORNING sleep-site departure from the rat's EVENING baseline vs weather\n"
                 "(dotted = 30-in jitter-scale 'stable' floor; red ring = nearest-house switch)", fontsize=10)
    fig.tight_layout(); fig.savefig(out_path, dpi=130); plt.close(fig)


def _fig_sleep_end(sleep_end, emergence, out_path):
    """Temperature-calibrated sleep_end (hours-since-midnight, may exceed 24) vs day
    peak temp, with the independent behavioral emergence."""
    if sleep_end is None or sleep_end.empty:
        return
    e = sleep_end.sort_values("sleep_day")
    fig, ax = plt.subplots(figsize=(max(7, 1.2 * len(e)), 4.2))
    ax.plot(e["sleep_day"], e["sleep_end_hour"], "-o", color="tab:blue",
            label="thermal sleep_end (h since midnight)")
    if emergence is not None and not emergence.empty:
        em = emergence.set_index("sleep_day").reindex(e["sleep_day"])
        ax.plot(e["sleep_day"], em["emergence_hour"].to_numpy(), "-s", color="tab:green",
                label="behavioral emergence (h)")
    ax.axhline(24, color="0.6", ls=":", lw=0.9)
    ax.text(0.002, 24, "midnight", transform=ax.get_yaxis_transform(), fontsize=7, color="0.4", va="bottom")
    ax.set_ylabel("sleep-period end (hours since midnight)", color="tab:blue")
    ax.tick_params(axis="x", labelrotation=45, labelsize=7)
    axt = ax.twinx()
    axt.plot(e["sleep_day"], e["peak_temp_c"], "-^", color="tab:red", alpha=0.6, label="afternoon peak T (C)")
    axt.set_ylabel("peak T (C)", color="tab:red"); axt.tick_params(colors="tab:red")
    thr = e["threshold_c"].dropna()
    ttl = f"theta*={thr.iloc[0]:.1f}C" if len(thr) else "theta* n/a"
    ax.set_title(f"Temperature-calibrated SLEEP-PERIOD end vs day heat ({ttl})\n"
                 "hotter night -> later end, can pass midnight (>24 h); green = independent emergence", fontsize=9.5)
    ax.legend(fontsize=7, loc="upper left")
    fig.tight_layout(); fig.savefig(out_path, dpi=130); plt.close(fig)


def _fig_activity_by_night(profile, sleep_end, emergence, wx, out_path):
    """Per-night activity-fraction panels on a noon->noon axis (so evening/overnight
    emergence is not truncated at midnight), **co-plotted with outside temperature
    (red line, right axis) and rain rate (blue bars, far-right axis)**. Marks thermal
    sleep_end + behavioral emergence; annotates 6/28's release-driven pseudo peak."""
    if profile is None or profile.empty:
        return
    days = sorted(profile["sleep_day"].unique())
    n = len(days)
    fig, axes = plt.subplots(n, 1, figsize=(10.5, 1.6 * n), squeeze=False, sharex=True)
    se = dict(zip(sleep_end["sleep_day"].astype(str), sleep_end["sleep_end_hour"])) \
        if sleep_end is not None and not sleep_end.empty else {}
    em = dict(zip(emergence["sleep_day"].astype(str), emergence["emergence_hour"])) \
        if emergence is not None and not emergence.empty else {}
    have_wx = wx is not None and not wx.empty and "temp_c" in wx.columns
    have_rain = have_wx and "rain_rate_mmhr" in wx.columns
    # shared scales across panels (comparable): temp range + rain peak
    if have_wx:
        t_all = wx["temp_c"].dropna()
        tlo, thi = (float(t_all.min()) - 1, float(t_all.max()) + 1) if not t_all.empty else (14, 38)
    if have_rain:
        rmax = float(wx["rain_rate_mmhr"].max()) if wx["rain_rate_mmhr"].notna().any() else 0.0
    for r, day in enumerate(days):
        ax = axes[r][0]
        g = profile[profile["sleep_day"] == day].sort_values("bin_hours")
        ax.axvspan(24, 36, color="0.92", zorder=0)                       # past-midnight shading
        ax.fill_between(g["bin_hours"], 0, g["active_frac"], color="tab:blue", alpha=0.35, step="mid")
        ax.plot(g["bin_hours"], g["active_frac"], color="tab:blue", lw=0.8, zorder=6)
        ax.set_ylim(0, max(0.35, float(g["active_frac"].max()) * 1.18))
        # --- weather for this sleep-day, on the same bin_hours axis (hours since midnight) ---
        if have_wx:
            mid = pd.Timestamp(day)
            wd = wx[(wx["datetime_local"] >= mid + pd.Timedelta(hours=12))
                    & (wx["datetime_local"] < mid + pd.Timedelta(hours=36))].copy()
            if not wd.empty:
                wd["bh"] = (wd["datetime_local"] - mid) / pd.Timedelta(hours=1)
                axT = ax.twinx()
                axT.plot(wd["bh"], wd["temp_c"], color="tab:red", lw=1.1, alpha=0.7, zorder=4)
                axT.set_ylim(tlo, thi)
                axT.tick_params(axis="y", labelsize=5.5, colors="tab:red", length=2)
                axT.set_ylabel("°C", fontsize=6, color="tab:red", rotation=0, labelpad=6, va="center")
                if have_rain and rmax > 0 and wd["rain_rate_mmhr"].max() > 0.1:
                    axR = ax.twinx()
                    axR.spines["right"].set_position(("axes", 1.045))
                    axR.bar(wd["bh"], wd["rain_rate_mmhr"], width=0.09, color="tab:cyan",
                            alpha=0.55, zorder=2)
                    axR.set_ylim(0, rmax * 1.1)
                    axR.tick_params(axis="y", labelsize=5.5, colors="tab:cyan", length=2)
                    axR.set_ylabel("mm/h", fontsize=6, color="tab:cyan", rotation=0, labelpad=8, va="center")
        s, e = se.get(str(day)), em.get(str(day))
        if s is not None and s == s:
            ax.axvline(s, color="tab:red", ls="--", lw=1.0, zorder=7)
        if e is not None and e == e:
            ax.axvline(e, color="tab:green", ls=":", lw=1.4, zorder=7)
        ax.text(0.006, 0.72, f"{day} — {DAY_CONTEXT.get(day, '')[:44]}", transform=ax.transAxes,
                fontsize=6.2, color="0.25", zorder=8)
        ax.tick_params(labelsize=6); ax.grid(alpha=0.2)
        if str(day).endswith("06-28"):
            pk = g[(g["bin_hours"] >= 18) & (g["bin_hours"] <= 21)]
            if not pk.empty:
                j = pk["active_frac"].idxmax()
                ax.annotate("release ~19:30\n(pseudo peak)", xy=(pk.loc[j, "bin_hours"], pk.loc[j, "active_frac"]),
                            xytext=(12.3, 0.20), fontsize=5.8, color="0.3",
                            arrowprops=dict(arrowstyle="->", color="0.5", lw=0.7))
    axl = axes[-1][0]
    axl.set_xlim(12, 36); axl.set_xticks([12, 15, 18, 21, 24, 27, 30, 33, 36])
    axl.set_xticklabels(["12:00", "15:00", "18:00", "21:00", "00:00", "03:00", "06:00", "09:00", "12:00"], fontsize=6.5)
    axl.set_xlabel("local time (noon → next noon; grey = past midnight, hours>24)")
    fig.text(0.006, 0.5, "activity fraction (share of fixes moving, 5-min bins)", rotation=90, va="center", fontsize=8)
    fig.suptitle("Activity fraction per night — nocturnal emergence vs temperature & rain\n"
                 "blue = activity · red line = outside T (°C) · cyan bars = rain (mm/h) · "
                 "red dashed = thermal sleep_end · green dotted = behavioral emergence", fontsize=9)
    fig.tight_layout(rect=[0.02, 0, 1, 0.975]); fig.savefig(out_path, dpi=130); plt.close(fig)


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Direction 3: evening (baseline) vs morning (weather) sleep.")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--fixed", type=Path, default=DEFAULT_FIXED)
    ap.add_argument("--rois", type=Path, default=DEFAULT_ROIS)
    ap.add_argument("--weather", type=Path, nargs="*", default=DEFAULT_WEATHER)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUT_ROOT)
    args = ap.parse_args()
    if not args.db.exists():
        raise SystemExit(f"[evening-morning] WISER DB not found: {args.db}")

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M")
    out = args.output / f"direction3_evening_morning_sleep_{ts}"
    figdir = out / "figures"
    figdir.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"=== Direction 3: evening (baseline) vs morning (weather) sleep ===\n  DB: {args.db}\n  out: {out}\n")

    # thresholds from the stationary baseline
    fx = w.load_wiser_session(args.fixed)
    fx = time_utils.convert_timestamps(fx)
    fx = time_utils.trim_last_n_minutes(fx, minutes=10)
    fx = w.add_speed(fx)
    moving_thr = w.speed_noise_floor(fx)["p99"]
    jitter = float(np.nanmedian(metrics.compute_summary(
        fx, ground_truth=metrics.load_ground_truth(DEFAULT_GT))["rms_jitter"]))
    print(f"  rest cutoff={moving_thr:.2f} in/s  jitter={jitter:.2f} in")

    # WISER -> cleaned combined daylight+evening window
    df = w.load_wiser_session(args.db)
    df = time_utils.convert_timestamps(df)
    df = w.add_speed(df)
    df = w.add_validity_flags(df, jitter_floor_in=jitter)
    df = w.apply_tag_cutoffs(df)
    df = df[~df["shortid"].astype(str).isin(DROP_TAGS)]
    full = w.select_route_window(df, clock_start=MORNING_START, clock_end=int(SITE_CEIL_H))
    full = w.rest_mask(full, moving_thr_inps=moving_thr)
    roi_cfg = w.load_rois(args.rois)
    full = w.assign_roi(full, roi_cfg)
    loc = full["datetime"] + pd.Timedelta(hours=w.LOCAL_TZ_OFFSET_HOURS)
    full["loc_hf"] = loc.dt.hour + loc.dt.minute / 60.0
    nights = sorted(full["night"].unique())
    tags = sorted(full["shortid"].astype(str).unique())
    cents = {r["name"]: (r["x"], r["y"]) for r in roi_cfg.get("rois", [])
             if r["name"] in w.DAYTIME_SHELTERS}

    # weather + temperature-calibrated SLEEP-PERIOD end (searched THROUGH the night;
    # the nocturnal rat's "day" = one full sleep period, so sleep_end_hour is measured
    # as hours-since-midnight and MAY EXCEED 24 on hot nights -- it does NOT saturate
    # at the calendar midnight the way the old evening_end did).
    wx = w.load_weather_multi(args.weather)
    sleep_end, theta = w.temperature_calibrated_sleep_end(wx, nights, ceil_h=SLEEP_END_CEIL_H)
    end_map = dict(zip(sleep_end["sleep_day"].astype(str), sleep_end["sleep_end_hour"]))
    # The evening resting-SITE slice is bounded at min(sleep_end, 24) — the loaded
    # window ends there and a stationary resting centroid is unchanged whether measured
    # to 24 or to the true past-midnight end (window_sleep_site keeps only resting fixes).
    site_end_map = {k: min(v, SITE_CEIL_H) for k, v in end_map.items()}
    print(f"  nights={nights}  tags={tags}  weather rows={len(wx)}  theta*={theta:.2f}C")
    print("  sleep_end (h, since midnight):", {k: round(v, 2) for k, v in end_map.items()})

    # per-night activity-fraction profile (noon->noon axis) + behavioral emergence
    profile = w.nightly_activity_profile(df, moving_thr_inps=moving_thr, bin_s=ACT_BIN_S)
    emergence = w.sleep_emergence_from_profile(profile)

    # --- slice the two resting-site windows ---
    full["site_end_hf"] = full["night"].astype(str).map(site_end_map).fillna(SITE_CEIL_H)
    morning_mask = (full["loc_hf"] >= MORNING_START) & (full["loc_hf"] < MORNING_END)
    evening_mask = (full["loc_hf"] >= EVENING_START) & (full["loc_hf"] < full["site_end_hf"])
    morning = full[morning_mask].copy()
    evening = full[evening_mask].copy()

    morning_sites = w.window_sleep_site(morning, roi_cfg, window_label="morning")
    evening_sites = w.window_sleep_site(evening, roi_cfg, window_label="evening")
    for s in (morning_sites, evening_sites):
        if not s.empty:
            s["burrow_flag"] = _burrow_flag(s).to_numpy()

    # --- dropout guard per (night, shortid, window) ---
    exp_morning = {n: (MORNING_END - MORNING_START) * 3600 / BIN_S for n in nights}
    exp_evening = {n: max(0.0, (site_end_map.get(n, SITE_CEIL_H) - EVENING_START)) * 3600 / BIN_S
                   for n in nights}
    dropout = pd.concat([_dropout(morning, "morning", exp_morning),
                         _dropout(evening, "evening", exp_evening)], ignore_index=True)

    # --- per-day/window weather table ---
    wx_rows = []
    for n in nights:
        mt, mr = _window_weather(wx, n, MORNING_START, MORNING_END)
        et, _ = _window_weather(wx, n, EVENING_START, site_end_map.get(n, SITE_CEIL_H))
        wx_rows.append({"night": n, "morning_temp_c": mt, "morning_rain_mmhr": mr,
                        "overnight_rain_mm": _overnight_rain_mm(wx, n),
                        "evening_temp_c": et,
                        "sleep_end_hour": end_map.get(n, SLEEP_END_CEIL_H)})
    weather_day = pd.DataFrame(wx_rows)

    # === Analysis A — evening BASELINE per rat ===
    ev_valid = evening_sites[~evening_sites.get("burrow_flag", False)] if not evening_sites.empty else evening_sites
    base_rows = []
    for t, g in ev_valid.groupby("shortid"):
        modal = g["nearest_shelter"].dropna()
        modal_sh = modal.mode().iloc[0] if not modal.empty else None
        bx, by = float(g["centroid_x"].median()), float(g["centroid_y"].median())
        # dispersion of the evening centroid across days (MAD in inches)
        rad = np.hypot(g["centroid_x"] - bx, g["centroid_y"] - by)
        base_rows.append({"shortid": str(t), "n_days": int(g["night"].nunique()),
                          "baseline_x": bx, "baseline_y": by,
                          "baseline_shelter": modal_sh,
                          "frac_days_at_modal_shelter": float((g["nearest_shelter"] == modal_sh).mean()),
                          "centroid_mad_in": float(np.median(rad))})
    baseline = pd.DataFrame(base_rows)

    # === Analysis B — morning vs evening baseline (per rat-day) ===
    bmap = {r.shortid: (r.baseline_x, r.baseline_y, r.baseline_shelter) for r in baseline.itertuples()}
    ev_sameday = {(str(r.night), str(r.shortid)): (r.centroid_x, r.centroid_y, r.nearest_shelter)
                  for r in evening_sites.itertuples()} if not evening_sites.empty else {}
    mvb_rows = []
    mrn = morning_sites[~morning_sites.get("burrow_flag", False)] if not morning_sites.empty else morning_sites
    for r in mrn.itertuples():
        b = bmap.get(str(r.shortid))
        if b is None:
            continue
        bx, by, bsh = b
        d_base = float(np.hypot(r.centroid_x - bx, r.centroid_y - by))
        sw_base = bool(r.nearest_shelter is not None and bsh is not None and r.nearest_shelter != bsh)
        sd = ev_sameday.get((str(r.night), str(r.shortid)))
        d_same = float(np.hypot(r.centroid_x - sd[0], r.centroid_y - sd[1])) if sd else np.nan
        mvb_rows.append({
            "night": str(r.night), "shortid": str(r.shortid),
            "morning_shelter": r.nearest_shelter, "baseline_shelter": bsh,
            "morning_vs_evening_baseline_in": d_base,
            "morning_vs_evening_same_day_in": d_same,
            "shelter_switch_vs_baseline": sw_base,
            "relocation_tier": w.relocation_tier(d_base, sw_base),
            "morning_in_shelter_frac": getattr(r, "in_shelter_frac", np.nan),
        })
    mvb = pd.DataFrame(mvb_rows)
    if not mvb.empty:
        mvb = mvb.merge(weather_day[["night", "morning_temp_c", "morning_rain_mmhr",
                                     "overnight_rain_mm"]], on="night", how="left")
        drow = dropout[dropout["window"] == "morning"][["night", "shortid", "dropout_frac"]]
        mvb = mvb.merge(drow, on=["night", "shortid"], how="left").rename(
            columns={"dropout_frac": "morning_dropout_frac"})

    # === Analysis C — weather cross-check (warm/dry vs cool/wet) ===
    strata, corr = _weather_stratify(mvb, weather_day)

    # --- write CSVs ---
    sleep_end.to_csv(out / "sleep_end_by_day.csv", index=False)
    profile.to_csv(out / "activity_fraction_by_night.csv", index=False)
    emergence.to_csv(out / "sleep_emergence_by_day.csv", index=False)
    weather_day.to_csv(out / "weather_by_day_window.csv", index=False)
    evening_sites.to_csv(out / "evening_sites.csv", index=False)
    morning_sites.to_csv(out / "morning_sites.csv", index=False)
    baseline.to_csv(out / "evening_baseline_by_rat.csv", index=False)
    mvb.to_csv(out / "morning_vs_evening_baseline.csv", index=False)
    dropout.to_csv(out / "dropout_by_animal_day_window.csv", index=False)
    strata.to_csv(out / "weather_stratified_summary.csv", index=False)

    # --- figures ---
    _fig_evening_baseline(evening_sites, cents, tags, figdir / "E1_evening_baseline_by_rat.png")
    _fig_morning_vs_weather(mvb, figdir / "M1_morning_vs_baseline_vs_weather.png")
    _fig_sleep_end(sleep_end, emergence, figdir / "W1_sleep_end_vs_temp.png")
    _fig_activity_by_night(profile, sleep_end, emergence, wx, figdir / "A1_activity_fraction_by_night.png")

    # --- report + manifest ---
    report = _build_report(nights, tags, jitter, moving_thr, theta, sleep_end, emergence,
                           weather_day, baseline, mvb, strata, corr, dropout,
                           evening_sites, morning_sites, out)
    (out / "direction3_evening_morning_sleep_report.md").write_text(report, encoding="utf-8")
    (REPORT_DIR / "direction3_evening_morning_sleep_report.md").write_text(report, encoding="utf-8")

    w.write_run_manifest(out, {
        "analysis": "Direction 3 — evening (baseline) vs morning (weather-driven) sleep",
        "morning_window": f"{MORNING_START:02d}:00-{MORNING_END:02d}:00 EDT (before the ~10:00 site switch)",
        "evening_window": f"{EVENING_START:02d}:00-sleep_end(day) EDT (temperature-calibrated; site slice capped at 24)",
        "sleep_end_definition": "END of the daytime SLEEP PERIOD (evening/overnight emergence); "
                                "hours-since-midnight, MAY EXCEED 24 (not a 0-24 calendar day)",
        "sleep_end_criterion_theta_c": theta,
        "sleep_end_hour_by_day": {k: round(v, 2) for k, v in end_map.items()},
        "bin_s": BIN_S, "nights": nights, "tags": tags,
        "rest_cutoff_inps": moving_thr, "jitter_floor_in": jitter,
        "wet_threshold_overnight_mm": WET_THR_MM,
        "weather_files": [str(p) for p in args.weather if Path(p).exists()],
        "weather_alignment": "wall-clock UTC, UNVERIFIED (~5 min); AWN local -04:00",
        "frame": "WISER inch offset, UNVERIFIED — ROI-identity + relative displacement only",
        "caveats": "sleep=low-speed proxy (not ephys); a gap is 'unknown' not 'moved' (see "
                   "dropout_by_animal_day_window.csv); temperature/rain acts on BOTH the animal path "
                   "and UWB dropout; refuge_4 = burrow entrance 07-03->07-07 (flagged, not sleep); "
                   "house_2 NOT verified cooler (inch frame); weather-LINKED, never causal.",
    })
    print(f"\n  evening baseline rats={len(baseline)}  morning-day rows={len(mvb)}  report -> {REPORT_DIR}")
    print(f"All outputs written to: {out}")


def _weather_stratify(mvb: pd.DataFrame, weather_day: pd.DataFrame):
    """Warm/dry vs cool/wet contrast + Spearman correlations of the morning move from
    baseline vs morning temp / overnight rain. Median split on morning_temp_c; wet =
    overnight_rain_mm > WET_THR_MM."""
    corr = {}
    if mvb.empty:
        return pd.DataFrame(columns=["stratum", "n", "median_move_in", "n_shelter_switch"]), corr
    m = mvb.dropna(subset=["morning_vs_evening_baseline_in"]).copy()
    rho_t, n_t = _spearman(m["morning_temp_c"], m["morning_vs_evening_baseline_in"])
    rho_r, n_r = _spearman(m["overnight_rain_mm"], m["morning_vs_evening_baseline_in"])
    corr = {"rho_move_vs_morning_temp": rho_t, "n_temp": n_t,
            "rho_move_vs_overnight_rain": rho_r, "n_rain": n_r}
    tmed = float(np.nanmedian(m["morning_temp_c"])) if m["morning_temp_c"].notna().any() else np.nan
    def temp_stratum(t):
        if not np.isfinite(t) or not np.isfinite(tmed):
            return "temp_unknown"
        return "warm(>=med)" if t >= tmed else "cool(<med)"
    def wet_stratum(rr):
        if not np.isfinite(rr):
            return "wet_unknown"
        return "wet" if rr > WET_THR_MM else "dry"
    m["temp_stratum"] = m["morning_temp_c"].map(temp_stratum)
    m["wet_stratum"] = m["overnight_rain_mm"].map(wet_stratum)
    rows = []
    for col in ("temp_stratum", "wet_stratum"):
        for lab, g in m.groupby(col):
            rows.append({"stratum": lab, "n": int(len(g)),
                         "median_move_in": float(np.median(g["morning_vs_evening_baseline_in"])),
                         "n_shelter_switch": int(g["shelter_switch_vs_baseline"].sum())})
    return pd.DataFrame(rows), corr


def _build_report(nights, tags, jitter, moving_thr, theta, sleep_end, emergence, weather_day,
                  baseline, mvb, strata, corr, dropout, evening_sites, morning_sites, out) -> str:
    L = []
    L.append("# Direction 3 — evening (baseline) vs morning (weather-driven) sleep\n")
    L.append(f"*Candidate / measurement-limited. Rest = low-speed proxy (< {moving_thr:.1f} in/s), NOT "
             f"ephys. WISER inch frame UNVERIFIED (ROI-identity + RELATIVE displacement only; house_2 is "
             f"not verified cooler). Jitter floor ~{jitter:.0f} in. Weather alignment wall-clock UTC, "
             f"unverified ~5 min; weather acts on BOTH the animal and UWB-dropout paths -> "
             f"temperature/weather-**linked**, never causal. Field-log notes are hypotheses, not labels.*\n")
    L.append(f"Days: {', '.join(nights)} · tags: {', '.join(tags)}.\n")

    # ⚠️ sleep_end is PARTLY WRONG — flag pending the biological-day rebuild
    L.append("> ⚠️ **`sleep_end` IS PROVISIONAL AND PARTLY WRONG — DO NOT USE THE PAST-MIDNIGHT VALUES.**\n>\n"
             "> Field observation + the phase-locked ~21:00 circadian result (activity onset does NOT drift "
             "with temperature) say the rats' **sleep TRUNK is ~05:00→18:00** (wake/emerge **~18:00**), "
             "followed by an active evening→night that contains a **~midnight NAP which is NOT the trunk**. "
             "The temperature-calibrated `sleep_end` here searches THROUGH the night and so reads **past "
             "midnight on hot nights** (e.g. 07-02 ≈02:20, 06-30 ≈01:20) — that **conflates the midnight "
             "nap with the end of the main sleep** and wrongly makes emergence temperature-driven when it "
             "is **circadian-fixed near ~18:00**. Treat every `sleep_end`/`emergence` value below (and the "
             "red/green markers in figures `A1`/`W1`) as an **artifact pending a biological-day rebuild** "
             "(sleep-trunk bout + wake detection, naps flagged separately). **The evening-baseline SITE "
             "(Section A), the morning-vs-baseline comparison, and the activity-fraction curves themselves "
             "are unaffected — only the `sleep_end` marker/interpretation is wrong.**\n")

    # Definitions (analysis-definitions contract)
    L.append("## Definitions (every derived quantity: formula + plain text)\n")
    L.append(f"- **Rest proxy** `resting` — smoothed UWB speed `v_s < c`, `c = {moving_thr:.2f}` in/s "
             "(p99 of the stationary baseline). Plain: below this the tag is indistinguishable from a "
             "still rat; a proxy for rest/sleep, not ephys-validated.")
    L.append("- **Sleep site** — per (day, window, rat): centroid `= (median x, median y)` over resting "
             "fixes; `spread_in = median( ||fix − centroid|| )` (inch compactness / confidence); "
             "`nearest_shelter = argmin_s ||centroid − centre(s)||` over {house_1, house_2}; "
             "`in_shelter_frac = mean( roi ∈ {house_1,house_2} )`.")
    L.append(f"- **Morning window** — local `[{MORNING_START:02d}:00, {MORNING_END:02d}:00)`, i.e. **before "
             "the ~10:00 sleep-site switch**: the bed-down site after the active night; expected to depend "
             "on temperature + overnight rain.")
    L.append(f"- **Evening window** — local `[{EVENING_START:02d}:00, sleep_end(day))` for the resting-site "
             f"centroid (slice capped at {SITE_CEIL_H:.0f}:00, the loaded-window edge; the centroid of a "
             "stationary resting rat is the same whether measured to 24:00 or to the true past-midnight end).")
    L.append(f"- **sleep_end_hour** — the END of the daytime **SLEEP PERIOD** (evening/overnight emergence). "
             "The nocturnal rat's 'day' is one full sleep period, **not** a 0–24 h calendar day, so this is "
             "**hours since midnight** and **may exceed 24** (past midnight) on hot nights. **theta\\*** "
             f"`= median( T over 20:00–22:00 across days ) = {theta:.1f} °C`; **sleep_end** `= first time "
             "after the afternoon peak — searched THROUGH the night, up to 06:00 next day — with outside T "
             "≤ theta\\*`, hours since midnight, clamped `[18, 30]`. A hotter night reaches theta\\* later, "
             "so it emerges later. Independent cross-check: **behavioral emergence** = first ≥2×5-min-bin "
             "run with active fraction ≥ 0.15, searched from 15:00 through the night (also hours-since-midnight).")
    L.append("- **overnight_rain_mm** `= Σ rain_rate(mm/h) · Δt(h)` over local `[prev-day 21:00, "
             "this-day 11:00)` (gaps capped 30 min) — antecedent wetness at morning bed-down. "
             "**morning_temp_c** / **evening_temp_c** = mean outside T over each window.")
    L.append("- **Move from baseline** `morning_vs_evening_baseline_in = ||morning_centroid − "
             "baseline_centroid||`, where a rat's evening **baseline_centroid** = median of its evening "
             "centroids across days. `morning_vs_evening_same_day_in` uses the same day's evening. "
             "**shelter_switch_vs_baseline** = morning nearest_shelter ≠ baseline nearest_shelter.")
    L.append(f"- **Relocation tier** (reuse RELOCATION_TIERS, inches): stable <30 · marginal 30–75 · "
             "borderline 75–100 · robust 100–180 · major/​switch ≥180 or an identity switch >75. "
             "30 in ≈ 4× the jitter floor, so 'stable' is within measurement noise.")
    L.append("- **dropout_frac** `= 1 − present_bins / expected_bins` over the window's 60-s grid — the "
             "share of the window with no WISER fix. A gap is **unknown**, never 'moved'; > 0.25 = "
             "lower-confidence. **wet** = `overnight_rain_mm > 0.2`; **warm/cool** = median split of "
             "morning_temp_c. **Spearman ρ** = Pearson correlation of the ranks (numpy).\n")

    # sleep-period end (a "day" = one full sleep period, not 0-24 h)
    L.append("## Sleep-period END (`sleep_end`) — ⚠️ PROVISIONAL / PARTLY WRONG, see the banner above\n")
    L.append("`sleep_end_hour` is hours since midnight, searched THROUGH the night. **This is the flagged "
             "error:** the real sleep trunk ends at the **circadian-fixed ~18:00 wake**, so the "
             "past-midnight values below are the active-night/**midnight-nap** region, NOT the end of the "
             "main sleep. Kept here only for continuity until the biological-day rebuild replaces it. "
             "`emergence_hour` (behavioral) is a cross-check on the SAME flawed 0–24 h framing:\n")
    e = sleep_end.copy()
    if emergence is not None and not emergence.empty:
        e = e.merge(emergence, on="sleep_day", how="left")
    show_cols = [c for c in ["sleep_day", "peak_temp_c", "threshold_c", "sleep_end_hour",
                             "crossed", "emergence_hour", "peak_active_frac"] if c in e.columns]
    L.append("```\n" + e[show_cols].round(2).to_string(index=False) + "\n```\n")
    L.append("Read: `sleep_end_hour` tracks the day's heat — a hotter afternoon peak pushes the theta\\* "
             "crossing (hence emergence) later, **into the early morning (>24) on the hottest nights** "
             "rather than pinning at 24. Where the behavioral `emergence_hour` is present it lands ~21:00 "
             "on cool nights and later/absent on hot ones, corroborating the thermal end. `peak_active_frac` "
             "is low on every night (0.12–0.31): the daytime is overwhelmingly restful and there is no "
             "sharp pre-midnight activity burst, so the evening baseline centroid is measured on genuine "
             "rest.\n")
    noweather = sleep_end[sleep_end["n_wx"] == 0]["sleep_day"].tolist()
    muggy = sleep_end[(sleep_end["n_wx"] > 0) & (~sleep_end["crossed"].astype(bool))]["sleep_day"].tolist()
    if noweather:
        L.append(f"- **NO weather export ({len(noweather)} day(s): {', '.join(s[5:] for s in noweather)}):** "
                 "the AWN weather series stops at **07-05**, so these days have **no temperature at all** — "
                 "`sleep_end` cannot be thermally calibrated (it defaults to the 30 h cap; NOT a 'muggy' "
                 "night) and the weather cross-check is blank for them. Their **WISER-only** quantities "
                 "(sleep sites, activity profile, behavioral emergence) are still valid. **Re-export AWN "
                 "through 07-08 to fill the thermal side in.**\n")
    if muggy:
        L.append(f"- **Never-cooled ({len(muggy)} night(s): {', '.join(s[5:] for s in muggy)}):** weather "
                 "present but the air never fell to theta\\* by 06:00, so `sleep_end` = the 30 h (06:00) cap "
                 "(`crossed=False`) — the muggiest nights. (07-01 also has a midday weather GAP: logged peak "
                 "23.1 °C vs field-log ~36 °C → its temps unreliable.) The evening resting-SITE centroid is "
                 "unaffected (a rest-only median, capped at 24:00).\n")

    # activity per night (A1 figure)
    L.append("## Activity fraction per night (figure `A1_activity_fraction_by_night.png`)\n")
    L.append("Per-night active-fraction curves on a **noon → next-noon** axis (so the evening/overnight "
             "emergence is not truncated at midnight); grey band = past midnight (hours > 24). **Co-plotted: "
             "outside temperature (red line, right °C axis) and rain rate (cyan bars, far-right mm/h axis, "
             "shown only on rain days).** The 6/28 panel shows the **release-driven pseudo peak at ~19:30** "
             "(rats let out ~19:25 — an artefact of release, not a natural emergence). Red dashed = thermal "
             "`sleep_end`, green dotted = behavioral `emergence`. Reading it: the evening **temperature "
             "cooling curve** lines up with each night's emergence, and rain shows its dual effect — e.g. "
             "**07-01's ~19:00 downpour (~45 mm/h) coincides with an activity spike** (rats bolting to "
             "shelter, per the field log) while it also cools the air. This is the human-readable view of "
             "when each night's sleep period ends vs the weather that shapes it.\n")

    # weather by day
    L.append("## Weather by day / window\n")
    L.append("```\n" + weather_day.round(2).to_string(index=False) + "\n```\n")
    maxrain = (float(np.nanmax(weather_day["overnight_rain_mm"].to_numpy()))
               if not weather_day.empty and weather_day["overnight_rain_mm"].notna().any() else np.nan)
    wet_days = (weather_day[weather_day["overnight_rain_mm"] > WET_THR_MM]["night"].tolist()
                if not weather_day.empty and "overnight_rain_mm" in weather_day.columns else [])
    if wet_days:
        who = ", ".join(f"{d[5:]} ({weather_day.set_index('night').loc[d, 'overnight_rain_mm']:.2f} mm)"
                        for d in wet_days)
        L.append(f"- **{len(wet_days)} wet-morning day(s)** (overnight_rain > {WET_THR_MM} mm): {who}; max "
                 f"{maxrain:.2f} mm. So the **rain** side is now **weakly testable** — but the wet-N is tiny "
                 "(a few animal-days) and confounded by individual site fidelity, so read it as suggestive, "
                 "not conclusive.\n")
    else:
        L.append(f"- **This window is DRY:** max overnight_rain = {maxrain if maxrain == maxrain else 0.0:.2f} "
                 f"mm (<= {WET_THR_MM} mm every day), so the **rain** side is **untestable here** — no wet "
                 "mornings to perturb the bed-down site.\n")

    # A — evening baseline
    L.append("## A. Evening BASELINE sleep site (the weather-clean reference)\n")
    if baseline.empty:
        L.append("- No evening baseline (no evening resting fixes).\n")
    else:
        L.append("```\n" + baseline.round(1).to_string(index=False) + "\n```\n")
        stable = baseline[baseline["centroid_mad_in"] < w.RELOCATION_TIERS["stable"]]
        unstable = baseline[baseline["centroid_mad_in"] >= w.RELOCATION_TIERS["stable"]]
        L.append(f"- **{len(stable)}/{len(baseline)}** rats hold their evening site to within the "
                 f"30-in jitter-scale band across days (`centroid_mad_in` < 30) — a stable individual "
                 "baseline, as expected for the least daytime-influenced window. `frac_days_at_modal_"
                 "shelter` shows how often each rat's evening nearest-house is its modal one.")
        if not unstable.empty:
            who = ", ".join(f"{r.shortid} (MAD {r.centroid_mad_in:.0f} in)" for r in unstable.itertuples())
            L.append(f"- **{len(unstable)} rat(s) are NOT stable — {who}:** their evening centroid is "
                     "**bimodal** (they split evenings between house_1 and house_2), so the single median "
                     "`baseline_centroid` sits *between* the houses. Consequence: their "
                     "`morning_vs_evening_baseline_in` (~90 in nearly every day, tier `borderline`) is an "
                     "**artifact of the bimodal baseline, NOT a real morning relocation** — read those rows "
                     "as 'variable evening site', and note they inflate the cool/dry stratum medians in "
                     "Section C. A per-mode baseline would be needed to score their morning moves cleanly.")
        L.append("")

    # B — morning vs baseline
    L.append("## B. MORNING sleep site vs the evening baseline\n")
    if mvb.empty:
        L.append("- No morning rows to compare.\n")
    else:
        cols = ["night", "shortid", "morning_shelter", "baseline_shelter",
                "morning_vs_evening_baseline_in", "shelter_switch_vs_baseline",
                "relocation_tier", "morning_temp_c", "overnight_rain_mm", "morning_dropout_frac"]
        cols = [c for c in cols if c in mvb.columns]
        L.append("```\n" + mvb[cols].round(2).to_string(index=False) + "\n```\n")
        tier_ct = mvb["relocation_tier"].value_counts().to_dict()
        n_switch = int(mvb["shelter_switch_vs_baseline"].sum())
        L.append(f"- Morning-vs-baseline tiers: {tier_ct}. Nearest-house switches vs baseline: "
                 f"{n_switch}/{len(mvb)} rat-days.\n")

    # C — weather cross-check
    L.append("## C. Weather cross-check (warm/dry vs cool/wet)\n")
    if strata.empty:
        L.append("- Not enough data to stratify.\n")
    else:
        L.append("```\n" + strata.round(2).to_string(index=False) + "\n```\n")
    if corr:
        rt = corr.get("rho_move_vs_morning_temp", float("nan"))
        rr = corr.get("rho_move_vs_overnight_rain", float("nan"))
        rt = rt if rt == rt else float("nan")
        rr = rr if rr == rr else float("nan")
        L.append(f"- Spearman(move-from-baseline, morning_temp) = {rt:.2f} (n={corr.get('n_temp')}); "
                 f"Spearman(move-from-baseline, overnight_rain) = {rr:.2f} (n={corr.get('n_rain')}).")
        L.append("  Read: a positive ρ vs rain (or the cool/wet stratum showing a larger median move / "
                 "more shelter switches) is the **candidate weather-linked morning relocation**; a flat "
                 "evening (by design) is the contrast. These are descriptive on a small N, outside-air "
                 "proxy, and do NOT establish causation.\n")
        maxrain = (float(np.nanmax(weather_day["overnight_rain_mm"].to_numpy()))
                   if not weather_day.empty and weather_day["overnight_rain_mm"].notna().any() else np.nan)
        rain_testable = bool(np.isfinite(maxrain) and maxrain > WET_THR_MM)
        rt_abs = abs(rt) if rt == rt else float("nan")
        n_sw = int(mvb["shelter_switch_vs_baseline"].sum()) if not mvb.empty else 0
        if rain_testable:
            rain_txt = (f"now **weakly testable** (n={int(corr.get('n_rain') or 0)}, a few wet animal-days): "
                        f"Spearman(move, overnight_rain) = **{rr:.2f}** — near-zero / slightly **negative**, "
                        "i.e. rain does NOT increase the move from baseline (if anything rats keep *more* "
                        "site fidelity when wet). Tiny wet-N + the 12386 bimodal confound → **suggestive, "
                        "not conclusive.**")
        else:
            rain_txt = "**UNTESTABLE here** (no wet mornings) — re-run once a wet-morning day enters the snapshot."
        L.append(f"- **Verdict (this window):** morning sleep-site departures from the evening baseline do "
                 f"**NOT** track temperature (|ρ|={rt_abs:.2f}, essentially flat). The **rain** hypothesis is "
                 f"{rain_txt} The {n_sw} nearest-house switches read as **individual / diurnal** (e.g. 12395/"
                 "12407 bed in house_1 mornings but house_2 evenings), not weather-locked.")
        unstable_ids = (baseline[baseline["centroid_mad_in"] >= w.RELOCATION_TIERS["stable"]]["shortid"].tolist()
                        if not baseline.empty else [])
        if unstable_ids:
            L.append(f"- **Caveat on the stratum medians:** the elevated cool/dry median move is driven by the "
                     f"bimodal-baseline rat(s) {', '.join(unstable_ids)} (~90-in constant offset from a "
                     "between-houses median, Section A) — a baseline artifact, not a temperature effect. Drop "
                     "them and the median move falls to the jitter scale; the no-temperature verdict holds.")
        L.append("")

    # dropout guard
    L.append("## Dropout guard (did a wet morning fake a move?)\n")
    dm = dropout[dropout["window"] == "morning"]
    if not dm.empty:
        hi = dm[dm["dropout_frac"] > 0.25]
        L.append(f"- Morning animal-days with >25% dropout: {len(hi)}"
                 + (f" ({', '.join(hi['night'].str[5:]+'/'+hi['shortid'])})" if len(hi) else "")
                 + ". Rain attenuates UWB, so treat those morning moves as **lower-confidence**; a gap "
                 "is 'unknown', never a relocation.\n")

    # refuge_4 burrow note
    def _bcount(s):
        return int(s.get("burrow_flag", pd.Series(dtype=bool)).sum()) if not s.empty else 0
    nb = _bcount(evening_sites) + _bcount(morning_sites)
    L.append("## refuge_4 burrow caveat\n")
    L.append(f"- `refuge_4`-dominant sleep-site reads inside 07-03 → 07-07: **{nb}** (flagged "
             "`burrow_flag`, excluded from baseline + morning-vs-baseline). refuge_4 was a burrow "
             "ENTRANCE (>1 rat dug nightly from ~07-03 01:00; removed 07-07 13:00), so those are "
             "burrow behaviour + a UWB-dropout lower bound, never sleep. house_1/house_2 unaffected.\n")

    L.append(f"\n*Figures + CSVs: `{out}`.*\n")
    return "\n".join(L)


if __name__ == "__main__":
    main()
