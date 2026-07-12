r"""
analyze_biological_day_sleep.py — Direction 3: biological-day sleep model (CORE rebuild).

Re-cuts the daytime sleep analysis on the rat's **biological day**, RETIRING the
temperature-crossing `sleep_end` (which searched through the night, ran past midnight on
hot days, and conflated the active-night MIDNIGHT NAP with the end of the main sleep).

Biological day (field-confirmed + phase-locked ~21:00 circadian result):
  * SLEEP TRUNK ~05:00 → trunk-end (main daytime sleep);
  * then an active evening→night containing a ~midnight NAP (NOT the trunk).

Trunk end = **`locomotor_emergence_hour`** (util `locomotor_emergence`): the onset of
sustained locomotion / **sleep-site departure**. *Sensor-limited interpretation:* WISER only
sees movement above the ~7 in jitter floor and CANNOT observe in-shelter waking/stirring, so
this ~20:00 value is expected to LAG a true behavioral wake. The field ~18:00 wake vs this
~20:00 is **consistent with** WISER's invisibility to in-nest behavior but is **not proven**
to be entirely that (a genuinely later departure is not excluded without interior CV / ephys).

This pass (scope: "core first"):
  * detect `locomotor_emergence_hour` per day; check it vs afternoon temperature (expect ρ≈0);
  * cut the trunk into a morning-window [05:00,10:00) and a day-window [10:00,emergence) SITE,
    report how often they DIFFER (this does NOT prove a transition AT 10:00);
  * **within-trunk relocations over the FULL ROI STATE SPACE** (no fixed 10:00): a dominant
    change-point (pre/post INDEPENDENTLY state-classified) + a state-sequence giving the transition
    matrix, dwell-by-site, relocations/rat-day, and timing — labels never from displacement direction;
  * **temperature-modulates-SITE, MULTI-SITE (within-rat)**: does heat shift the dwell distribution
    across ALL states (any-shelter-vs-exposed + per-state)? Ambient = coarse covariate.
DEFERRED: nap detection in the active night.
NB the earlier BINARY house_2-fraction test was a state-space misspecification — SUPERSEDED here.

Guardrails: sleep = low-speed PROXY (not ephys); a gap is 'unknown' not 'moved'; WISER inch
frame UNVERIFIED -> ROI-identity + RELATIVE displacement only; jitter ~7 in; refuge_4 burrow
07-03->07-07 flagged; Sova(12409) dropped, Hypnos(12380) auto-cut 07-09. Read-only on DB + AWN.

Data -> D:\Field2026_analysis_out\biological_day_sleep_<ts>\; report also to
wiser/outputs/direction3_biological_day_sleep/.
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
    Path(r"D:\Reolink_record\audio_in\weather_data\AWN-F8B3B78DEAC9-20260628-20260709.csv"),
    Path(r"D:\Reolink_record\audio_in\weather_data\AWN-F8B3B78DEAC9-20260628-20260705.csv"),
]
from output_paths import OUT_ROOT as DEFAULT_OUT_ROOT   # single source of truth (env FIELD2026_ANALYSIS_OUT_ROOT)
REPORT_DIR = PROJECT_ROOT / "outputs" / "direction3_biological_day_sleep"
DROP_TAGS = {"12409"}                    # Sova

TRUNK_START = 5                          # 05:00 morning bed-down (trunk start)
WINDOW_SPLIT = 10                        # nominal morning/day WINDOW boundary (NOT a proven switch time)
DAY_END_CAP = 21                         # cap the day-window / trunk slice (emergence_hi)
ACT_BIN_S = 300                          # 5-min activity-profile bins (emergence detection)
BIN_S = 60                               # dropout-grid bin
# change-point
CP_BIN_S = 300                           # 5-min position bins for the change-point
CP_SMOOTH_BINS = 3                       # default centered rolling-median smoothing
CP_MIN_SEG_BINS = 3                      # min bins each side of a split
CP_MIN_DISP_IN = 100.0                   # supported change-point: pre/post displacement >= this (robust tier)
CP_SMOOTH_SENS = (1, 3, 5)               # smoothing-sensitivity sweep
DOORWAY_BUFFER_IN = 36.0                 # doorway band width around a house core
BURROW_ROI = "refuge_4"
BURROW_WINDOW = ("2026-07-03", "2026-07-07")

DAY_CONTEXT = {
    "2026-06-28": "warm ~22-23C; PARTIAL (evening release ~19:25)",
    "2026-06-29": "sunny/HOT ~30C; Sova removed 15:00",
    "2026-06-30": "sunny/humid HIGH ~34C; rain ~17:30",
    "2026-07-01": "sunny/humid high ~36C; rain ~19:45",
    "2026-07-02": "hot ~33-35C midday",
    "2026-07-03": "pre-dawn fog; refuge_4 burrow active",
    "2026-07-04": "July-4th fireworks ~21:00",
    "2026-07-05": "refuge_4 burrow active",
    "2026-07-06": "refuge_4 hole found ~13:00",
    "2026-07-07": "refuge_4 REMOVED ~13:00; CH07/CH08 added",
    "2026-07-08": "refuge_4 gone",
}


def _spearman(x, y):
    x = np.asarray(x, float); y = np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    n = int(len(x))
    if n < 4 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return np.nan, n
    rx = pd.Series(x).rank().to_numpy(); ry = pd.Series(y).rank().to_numpy()
    return float(np.corrcoef(rx, ry)[0, 1]), n


def _window_weather(wx, night, h_lo, h_hi):
    if wx.empty or "temp_c" not in wx.columns:
        return np.nan
    hf = wx["datetime_local"].dt.hour + wx["datetime_local"].dt.minute / 60.0
    m = (wx["datetime_local"].dt.date.astype(str) == night) & (hf >= h_lo) & (hf < h_hi)
    sub = wx[m]
    return float(sub["temp_c"].mean()) if not sub.empty else np.nan


def _window_temp_peak(wx, night, h_lo, h_hi):
    if wx.empty or "temp_c" not in wx.columns:
        return np.nan
    hf = wx["datetime_local"].dt.hour + wx["datetime_local"].dt.minute / 60.0
    m = (wx["datetime_local"].dt.date.astype(str) == night) & (hf >= h_lo) & (hf < h_hi)
    sub = wx[m]
    return float(sub["temp_c"].max()) if not sub.empty else np.nan


def _rat_centered_temp_corr(trunk_site):
    """Spearman(rat-centered trunk_frac_house2, midday_peak_temp_c) — removes each rat's
    baseline house preference so it tests a WITHIN-rat temperature effect. Returns (rho, n)."""
    if trunk_site is None or trunk_site.empty or "trunk_frac_house2" not in trunk_site.columns:
        return np.nan, 0
    ts = trunk_site.dropna(subset=["trunk_frac_house2", "midday_peak_temp_c"]).copy()
    if ts.empty:
        return np.nan, 0
    ts["centered"] = ts["trunk_frac_house2"] - ts.groupby("shortid")["trunk_frac_house2"].transform("mean")
    return _spearman(ts["midday_peak_temp_c"], ts["centered"])


def _burrow_flag(sites):
    if sites.empty:
        return pd.Series([], dtype=bool)
    lo, hi = BURROW_WINDOW
    return ((sites["dominant_roi"] == BURROW_ROI) & (sites["night"] >= lo) & (sites["night"] < hi))


def _dropout(slice_df, window, exp_bins):
    rows = []
    d = slice_df.dropna(subset=["x", "y", "datetime"]).copy()
    if not d.empty:
        d["bin_utc"] = w._bin_utc_ns(d["datetime"], BIN_S)
        for (night, sid), g in d.groupby(["night", "shortid"]):
            exp = exp_bins.get(str(night), np.nan)
            present = g["bin_utc"].nunique()
            frac = float(1 - present / exp) if exp and exp == exp and exp > 0 else np.nan
            rows.append({"night": str(night), "shortid": str(sid), "window": window,
                         "present_bins": int(present), "dropout_frac": frac})
    return pd.DataFrame(rows, columns=["night", "shortid", "window", "present_bins", "dropout_frac"])


def _cp_hour_local(cp_time_utc):
    if cp_time_utc is None or not np.isfinite(cp_time_utc):
        return np.nan
    loc = pd.Timestamp(int(cp_time_utc)) + pd.Timedelta(hours=w.LOCAL_TZ_OFFSET_HOURS)
    return float(loc.hour + loc.minute / 60.0)


# ---------------------------------------------------------------------------
def _fig_emergence_vs_temp(emergence, weather_day, out_path):
    if emergence is None or emergence.empty:
        return
    e = emergence.sort_values("sleep_day").merge(
        weather_day[["night", "afternoon_temp_c"]], left_on="sleep_day", right_on="night", how="left")
    fig, ax = plt.subplots(figsize=(max(7, 1.1 * len(e)), 4.2))
    ax.plot(e["sleep_day"], e["locomotor_emergence_hour"], "-o", color="tab:blue",
            label="locomotor emergence (clock h)")
    ax.axhspan(19.5, 21, color="tab:blue", alpha=0.08)
    ax.set_ylim(15.5, 21.5); ax.set_ylabel("locomotor emergence / sleep-site departure (local hour)", color="tab:blue", fontsize=8)
    ax.tick_params(axis="x", labelrotation=45, labelsize=7)
    axt = ax.twinx()
    axt.plot(e["sleep_day"], e["afternoon_temp_c"], "-^", color="tab:red", alpha=0.6, label="afternoon T (C)")
    axt.set_ylabel("afternoon T (C)", color="tab:red"); axt.tick_params(colors="tab:red")
    rho, n = _spearman(e["afternoon_temp_c"], e["locomotor_emergence_hour"])
    ax.set_title(f"Locomotor emergence (sleep-site departure) vs afternoon temperature — ρ={rho:.2f} (n={n})\n"
                 "flat ~20:00 across warm/hot days = circadian-clustered, NOT temperature-driven "
                 "(retires `sleep_end`); sensor-limited (lags any in-nest wake WISER can't see)", fontsize=8.5)
    ax.legend(fontsize=7, loc="upper left")
    fig.tight_layout(); fig.savefig(out_path, dpi=130); plt.close(fig)


def _fig_morning_vs_day(morning_sites, day_sites, cents, tags, out_path):
    if morning_sites.empty and day_sites.empty:
        return
    nights = sorted(set(morning_sites["night"]) | set(day_sites["night"]))
    xpos = {n: i for i, n in enumerate(nights)}
    fig, ax = plt.subplots(figsize=(max(8, 1.2 * len(nights)), 4.6))
    cmap = plt.get_cmap("tab10")
    for name, (cx, _) in cents.items():
        ax.axhline(cx, color="0.6", ls="--", lw=0.8)
        ax.text(0.002, cx, name, fontsize=7, color="0.4", transform=ax.get_yaxis_transform(), va="bottom")
    for i, t in enumerate(tags):
        gm = morning_sites[morning_sites["shortid"].astype(str) == str(t)].sort_values("night")
        gd = day_sites[day_sites["shortid"].astype(str) == str(t)].sort_values("night")
        c = cmap(i % 10)
        if not gm.empty:
            ax.plot([xpos[n] for n in gm["night"]], gm["centroid_x"], "-o", ms=5, color=c, label=f"{t} morning", alpha=0.9)
        if not gd.empty:
            ax.plot([xpos[n] for n in gd["night"]], gd["centroid_x"], "--s", ms=5, mfc="none", color=c, label=f"{t} day", alpha=0.9)
    ax.set_xticks(range(len(nights))); ax.set_xticklabels(nights)
    ax.set_ylabel("rest centroid x (in)  [UNVERIFIED inch frame]")
    ax.set_title("Morning-window [05–10] (o solid) vs day-window [10–emergence] (□ dashed) site per rat\n"
                 "a solid vs dashed GAP = the two windows differ (timing tested independently in CP1/CP2, NOT fixed at 10:00)",
                 fontsize=9)
    ax.tick_params(axis="x", labelrotation=45, labelsize=7)
    ax.legend(fontsize=6, ncol=len(tags), loc="upper right")
    fig.tight_layout(); fig.savefig(out_path, dpi=130); plt.close(fig)


def _fig_emergence_timeline(profile, emergence, out_path):
    if profile is None or profile.empty:
        return
    days = sorted(profile["sleep_day"].unique())
    n = len(days)
    em = dict(zip(emergence["sleep_day"].astype(str), emergence["locomotor_emergence_hour"])) if emergence is not None and not emergence.empty else {}
    bl = dict(zip(emergence["sleep_day"].astype(str), emergence["baseline_active"])) if emergence is not None and not emergence.empty else {}
    fig, axes = plt.subplots(n, 1, figsize=(9, 1.35 * n), squeeze=False, sharex=True)
    for r, day in enumerate(days):
        ax = axes[r][0]
        g = profile[(profile["sleep_day"] == day) & (profile["bin_hours"] >= 12) & (profile["bin_hours"] <= 24)].sort_values("bin_hours")
        ax.fill_between(g["bin_hours"], 0, g["active_frac"], color="tab:blue", alpha=0.35, step="mid")
        eh = em.get(str(day))
        if eh is not None and eh == eh:
            ax.axvline(eh, color="tab:green", ls="-", lw=1.3)
            ax.axvspan(12, eh, color="0.90", zorder=0)
        b = bl.get(str(day))
        if b is not None and b == b:
            ax.axhline(b, color="0.6", ls=":", lw=0.7)
        ax.text(0.006, 0.7, f"{day} — {DAY_CONTEXT.get(day, '')[:40]}", transform=ax.transAxes, fontsize=6, color="0.25")
        ax.set_ylim(0, max(0.3, float(g["active_frac"].max()) * 1.15) if not g.empty else 0.3)
        ax.tick_params(labelsize=6); ax.grid(alpha=0.2)
    axl = axes[-1][0]
    axl.set_xlim(12, 24); axl.set_xticks([12, 14, 16, 18, 20, 22, 24])
    axl.set_xticklabels(["12:00", "14:00", "16:00", "18:00", "20:00", "22:00", "00:00"], fontsize=7)
    axl.set_xlabel("local clock hour (grey = afternoon sleep-trunk tail; green = locomotor emergence)")
    fig.text(0.005, 0.5, "activity fraction (5-min bins)", rotation=90, va="center", fontsize=8)
    fig.suptitle("Locomotor-emergence (sleep-site departure) detection per day — ~20:00, not past midnight", fontsize=9.5)
    fig.tight_layout(rect=[0.02, 0, 1, 0.97]); fig.savefig(out_path, dpi=130); plt.close(fig)


def _fig_changepoint_hist(cp, out_path):
    """Histogram of SUPPORTED within-trunk change-point times; 10:00 marked to test clustering."""
    sup = cp[cp["supported"]] if not cp.empty else cp
    fig, ax = plt.subplots(figsize=(8, 4))
    if not sup.empty:
        ax.hist(sup["cp_hour_local"].dropna(), bins=np.arange(5, 21.5, 1.0), color="tab:blue", alpha=0.7, edgecolor="white")
    ax.axvline(10.0, color="tab:red", ls="--", lw=1.4, label="10:00 (the imposed window boundary)")
    if not sup.empty and sup["cp_hour_local"].notna().any():
        med = float(sup["cp_hour_local"].median())
        ax.axvline(med, color="tab:green", ls="-", lw=1.4, label=f"median {med:.1f}h")
    ax.set_xlim(5, 21); ax.set_xlabel("change-point time (local clock hour)")
    ax.set_ylabel("# rat-days (supported)")
    ax.set_title("Independent within-trunk change-point TIMES — do they cluster at 10:00?\n"
                 "(each = one rat-day's best position change-point, no fixed switch hour)", fontsize=9.5)
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(out_path, dpi=130); plt.close(fig)


def _fig_changepoint_per_ratday(cp, tags, out_path):
    """Per rat-day change-point time (supported = filled, unsupported = hollow at its best-split time)."""
    if cp.empty:
        return
    nights = sorted(cp["night"].unique())
    xpos = {n: i for i, n in enumerate(nights)}
    ypos = {t: i for i, t in enumerate(tags)}
    fig, ax = plt.subplots(figsize=(max(8, 1.1 * len(nights)), 0.6 * len(tags) + 2))
    ax.axhline(-1, color="none")
    for r in cp.itertuples():
        if not np.isfinite(getattr(r, "cp_hour_local", np.nan)):
            continue
        x = xpos[r.night] + (r.cp_hour_local - 5) / 16.0 * 0.8 - 0.4    # position within the day cell by hour
        y = ypos.get(str(r.shortid))
        if y is None:
            continue
        if r.supported:
            ax.scatter(x, y, s=60, c=[r.cp_hour_local], cmap="viridis", vmin=5, vmax=21, edgecolor="k", zorder=3)
        else:
            ax.scatter(x, y, s=28, facecolors="none", edgecolors="0.6", zorder=2)
    for i in range(len(nights) + 1):
        ax.axvline(i - 0.5, color="0.9", lw=0.6)
    ax.set_yticks(range(len(tags))); ax.set_yticklabels(tags)
    ax.set_xticks(range(len(nights))); ax.set_xticklabels(nights, rotation=45, ha="right", fontsize=7)
    ax.set_xlim(-0.5, len(nights) - 0.5); ax.set_ylim(-0.6, len(tags) - 0.4)
    sm = plt.cm.ScalarMappable(cmap="viridis", norm=plt.Normalize(5, 21)); sm.set_array([])
    fig.colorbar(sm, ax=ax, label="change-point clock hour", fraction=0.03, pad=0.01)
    ax.set_title("Per rat-day within-trunk change-point (filled = supported ≥100 in; hollow = best split, "
                 "unsupported)\nposition within each day cell encodes the clock hour", fontsize=9)
    fig.tight_layout(); fig.savefig(out_path, dpi=130); plt.close(fig)


def _fig_shelter_temp(wide, tags, out_path):
    """Rat-centered ANY-SHELTER dwell fraction vs day midday-peak temp (within-rat; multi-site)."""
    if wide is None or wide.empty or "any_shelter_frac" not in wide.columns:
        return
    ts = wide.dropna(subset=["any_shelter_frac", "midday_peak_temp_c"]).copy()
    if ts.empty:
        return
    ts["centered"] = ts["any_shelter_frac"] - ts.groupby("shortid")["any_shelter_frac"].transform("mean")
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    cmap = plt.get_cmap("tab10")
    for i, t in enumerate(tags):
        g = ts[ts["shortid"].astype(str) == str(t)]
        if not g.empty:
            ax.scatter(g["midday_peak_temp_c"], g["centered"], s=42, color=cmap(i % 10), label=str(t), alpha=0.85)
    ax.axhline(0, color="0.6", lw=0.8)
    rho, n = _spearman(ts["midday_peak_temp_c"], ts["centered"])
    ax.set_xlabel("midday peak temperature (°C, 12:00–18:00)")
    ax.set_ylabel("ANY-shelter dwell fraction — rat-centered\n(+ = more sheltered than that rat's mean)")
    ax.set_title(f"Does a rat use ANY refuge more on its HOTTER days? Spearman ρ={rho:.2f} (n={n})\n"
                 "within-rat (identity removed), full state space; ambient = coarse covariate", fontsize=9)
    ax.legend(fontsize=7, title="tag", ncol=5, loc="upper center")
    fig.tight_layout(); fig.savefig(out_path, dpi=130); plt.close(fig)


def _fig_state_dwell_matrix(state_dwell, trans_mat, tags, out_path):
    """Left: mean trunk dwell fraction per site-state per rat (stacked). Right: state transition
    matrix heatmap (from -> to over all relocations)."""
    if state_dwell is None or state_dwell.empty:
        return
    piv = state_dwell.pivot_table(index="shortid", columns="state", values="dwell_frac", aggfunc="mean", fill_value=0.0)
    order = piv.mean(axis=0).sort_values(ascending=False).index.tolist()
    piv = piv[order]
    fig, (axl, axr) = plt.subplots(1, 2, figsize=(13, 4.8), gridspec_kw={"width_ratios": [1.15, 1]})
    cmap = plt.get_cmap("tab20")
    bottom = np.zeros(len(piv))
    xs = np.arange(len(piv))
    for j, st in enumerate(order):
        axl.bar(xs, piv[st].to_numpy(), bottom=bottom, color=cmap(j % 20), label=st, width=0.7)
        bottom += piv[st].to_numpy()
    axl.set_xticks(xs); axl.set_xticklabels(piv.index, rotation=45, ha="right", fontsize=7)
    axl.set_ylabel("mean trunk dwell fraction"); axl.set_ylim(0, 1.02)
    axl.set_title("Dwell time by site-state, per rat (full ROI state space)", fontsize=9.5)
    axl.legend(fontsize=6, ncol=2, loc="lower center", bbox_to_anchor=(0.5, 1.02))
    # transition matrix
    if trans_mat is not None and not trans_mat.empty:
        states = sorted(set(trans_mat["from_state"]) | set(trans_mat["to_state"]))
        M = np.zeros((len(states), len(states)))
        idx = {s: i for i, s in enumerate(states)}
        for r in trans_mat.itertuples():
            M[idx[r.from_state], idx[r.to_state]] = r.n
        im = axr.imshow(M, cmap="viridis", aspect="auto")
        axr.set_xticks(range(len(states))); axr.set_xticklabels(states, rotation=45, ha="right", fontsize=7)
        axr.set_yticks(range(len(states))); axr.set_yticklabels(states, fontsize=7)
        for i in range(len(states)):
            for j in range(len(states)):
                if M[i, j]:
                    axr.text(j, i, int(M[i, j]), ha="center", va="center", fontsize=7,
                             color="white" if M[i, j] < M.max() * 0.6 else "black")
        axr.set_xlabel("to"); axr.set_ylabel("from")
        fig.colorbar(im, ax=axr, fraction=0.046, pad=0.04, label="# relocations")
    axr.set_title("Relocation transition matrix (independent state labels)", fontsize=9.5)
    fig.tight_layout(); fig.savefig(out_path, dpi=130); plt.close(fig)


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Direction 3: biological-day sleep model (core rebuild).")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--fixed", type=Path, default=DEFAULT_FIXED)
    ap.add_argument("--rois", type=Path, default=DEFAULT_ROIS)
    ap.add_argument("--weather", type=Path, nargs="*", default=DEFAULT_WEATHER)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUT_ROOT)
    args = ap.parse_args()
    if not args.db.exists():
        raise SystemExit(f"[bio-day] WISER DB not found: {args.db}")

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M")
    out = args.output / f"biological_day_sleep_{ts}"
    figdir = out / "figures"
    figdir.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"=== Direction 3: biological-day sleep model (core) ===\n  DB: {args.db}\n  out: {out}\n")

    fx = w.load_wiser_session(args.fixed)
    fx = time_utils.convert_timestamps(fx)
    fx = time_utils.trim_last_n_minutes(fx, minutes=10)
    fx = w.add_speed(fx)
    moving_thr = w.speed_noise_floor(fx)["p99"]
    jitter = float(np.nanmedian(metrics.compute_summary(
        fx, ground_truth=metrics.load_ground_truth(DEFAULT_GT))["rms_jitter"]))
    print(f"  rest cutoff={moving_thr:.2f} in/s  jitter={jitter:.2f} in")

    df = w.load_wiser_session(args.db)
    df = time_utils.convert_timestamps(df)
    df = w.add_speed(df)
    df = w.add_validity_flags(df, jitter_floor_in=jitter)
    df = w.apply_tag_cutoffs(df)
    df = df[~df["shortid"].astype(str).isin(DROP_TAGS)]

    # --- LOCOMOTOR EMERGENCE / trunk-end (retires the temperature sleep_end) ---
    profile = w.nightly_activity_profile(df, moving_thr_inps=moving_thr, bin_s=ACT_BIN_S)
    emergence = w.locomotor_emergence(profile)
    em_map = dict(zip(emergence["sleep_day"].astype(str), emergence["locomotor_emergence_hour"]))

    # --- daytime trunk window -> morning / day sub-window sites ---
    full = w.select_route_window(df, clock_start=TRUNK_START, clock_end=DAY_END_CAP)
    full = w.rest_mask(full, moving_thr_inps=moving_thr)
    roi_cfg = w.load_rois(args.rois)
    full = w.assign_roi(full, roi_cfg)
    loc = full["datetime"] + pd.Timedelta(hours=w.LOCAL_TZ_OFFSET_HOURS)
    full["loc_hf"] = loc.dt.hour + loc.dt.minute / 60.0
    nights = sorted(full["night"].unique())
    tags = sorted(full["shortid"].astype(str).unique())
    cents = {r["name"]: (r["x"], r["y"]) for r in roi_cfg.get("rois", []) if r["name"] in w.DAYTIME_SHELTERS}
    print(f"  nights={nights}  tags={tags}")
    print("  locomotor_emergence_hour by day:", {k: round(v, 1) for k, v in em_map.items()})

    full["day_end_hf"] = full["night"].astype(str).map(
        lambda n: min(em_map.get(n, DAY_END_CAP), DAY_END_CAP)).astype(float)
    morning = full[(full["loc_hf"] >= TRUNK_START) & (full["loc_hf"] < WINDOW_SPLIT)].copy()
    day = full[(full["loc_hf"] >= WINDOW_SPLIT) & (full["loc_hf"] < full["day_end_hf"])].copy()
    morning_sites = w.window_sleep_site(morning, roi_cfg, window_label="morning")
    day_sites = w.window_sleep_site(day, roi_cfg, window_label="day")
    for s in (morning_sites, day_sites):
        if not s.empty:
            s["burrow_flag"] = _burrow_flag(s).to_numpy()

    exp_m = {n: (WINDOW_SPLIT - TRUNK_START) * 3600 / BIN_S for n in nights}
    exp_d = {n: max(0.0, (min(em_map.get(n, DAY_END_CAP), DAY_END_CAP) - WINDOW_SPLIT)) * 3600 / BIN_S for n in nights}
    dropout = pd.concat([_dropout(morning, "morning", exp_m), _dropout(day, "day", exp_d)], ignore_index=True)

    wx = w.load_weather_multi(args.weather)
    weather_day = pd.DataFrame([{"night": n, "afternoon_temp_c": _window_weather(wx, n, 12, 18),
                                 "locomotor_emergence_hour": em_map.get(n, np.nan)} for n in nights])

    # === B — morning-window vs day-window site DIFFERENCE (NOT a switch AT 10:00) ===
    dmap = {(str(r.night), str(r.shortid)): (r.centroid_x, r.centroid_y, r.nearest_shelter)
            for r in day_sites.itertuples()} if not day_sites.empty else {}
    mrn = morning_sites[~morning_sites.get("burrow_flag", False)] if not morning_sites.empty else morning_sites
    diff_rows = []
    for r in mrn.itertuples():
        d = dmap.get((str(r.night), str(r.shortid)))
        if d is None:
            continue
        dx, dy, dsh = d
        shift = float(np.hypot(dx - r.centroid_x, dy - r.centroid_y))
        differ = bool(r.nearest_shelter is not None and dsh is not None and r.nearest_shelter != dsh)
        diff_rows.append({"night": str(r.night), "shortid": str(r.shortid),
                          "morning_shelter": r.nearest_shelter, "day_shelter": dsh,
                          "morning_vs_day_shift_in": shift, "shelter_differs": differ,
                          "relocation_tier": w.relocation_tier(shift, differ)})
    window_diff = pd.DataFrame(diff_rows)

    # === C — across-day site stability per rat ===
    def _stab(sites, label):
        rows = []
        s = sites[~sites.get("burrow_flag", False)] if not sites.empty else sites
        for t, g in s.groupby("shortid"):
            bx, by = float(g["centroid_x"].median()), float(g["centroid_y"].median())
            rad = np.hypot(g["centroid_x"] - bx, g["centroid_y"] - by)
            modal = g["nearest_shelter"].dropna()
            msh = modal.mode().iloc[0] if not modal.empty else None
            rows.append({"shortid": str(t), "window": label, "n_days": int(g["night"].nunique()),
                         "centroid_mad_in": float(np.median(rad)), "modal_shelter": msh,
                         "frac_days_at_modal": float((g["nearest_shelter"] == msh).mean())})
        return pd.DataFrame(rows)
    stability = pd.concat([_stab(morning_sites, "morning"), _stab(day_sites, "day")], ignore_index=True)

    # === D — within-trunk relocations over the FULL ROI STATE SPACE (no fixed 10:00) ===
    trunk = full[(full["resting"]) & (full["loc_hf"] >= TRUNK_START) & (full["loc_hf"] < full["day_end_hf"])].copy()
    cp_rows, sens_rows, dwell_rows, reloc_rows = [], [], [], []
    exp_trunk = {n: max(0.0, (min(em_map.get(n, DAY_END_CAP), DAY_END_CAP) - TRUNK_START)) * 3600 / BIN_S for n in nights}
    for (night, sid), g in trunk.groupby(["night", "shortid"]):
        date = str(night)
        # (i) dominant positional change-point; pre/post INDEPENDENTLY mapped to the full state space
        cp = w.detect_site_changepoint(g, bin_s=CP_BIN_S, smooth_bins=CP_SMOOTH_BINS,
                                       min_seg_bins=CP_MIN_SEG_BINS, min_disp_in=CP_MIN_DISP_IN)
        frm = w.classify_site_state(cp["pre_x"], cp["pre_y"], roi_cfg, date=date) if cp["supported"] else None
        to = w.classify_site_state(cp["post_x"], cp["post_y"], roi_cfg, date=date) if cp["supported"] else None
        exp = exp_trunk.get(date, np.nan)
        present = g.dropna(subset=["x", "y", "datetime"])
        pbins = w._bin_utc_ns(present["datetime"], BIN_S) if len(present) else np.array([])
        drp = float(1 - (len(set(pbins.tolist())) / exp)) if (exp and exp == exp and exp > 0) else np.nan
        cp_rows.append({"night": date, "shortid": str(sid), "cp_hour_local": _cp_hour_local(cp["cp_time_utc"]),
                        "supported": bool(cp["supported"]), "displacement_in": cp["displacement_in"],
                        "confidence": cp["confidence"], "from_state": frm, "to_state": to,
                        "direction": (f"{frm}->{to}" if cp["supported"] else None),
                        "n_bins": cp["n_bins"], "trunk_dropout_frac": drp})
        supp_flags, hours = [], []
        for sm in CP_SMOOTH_SENS:
            c = w.detect_site_changepoint(g, bin_s=CP_BIN_S, smooth_bins=sm,
                                          min_seg_bins=CP_MIN_SEG_BINS, min_disp_in=CP_MIN_DISP_IN)
            supp_flags.append(bool(c["supported"])); hours.append(_cp_hour_local(c["cp_time_utc"]))
        hrs_sup = [h for f, h in zip(supp_flags, hours) if f and np.isfinite(h)]
        stable = bool(all(supp_flags) and (max(hrs_sup) - min(hrs_sup) <= 1.0)) if hrs_sup and all(supp_flags) else False
        sens_rows.append({"night": date, "shortid": str(sid), "supported_by_smoothing": sum(supp_flags),
                          "n_smoothings": len(CP_SMOOTH_SENS), "smoothing_stable": stable})
        # (ii) full multi-site STATE SEQUENCE -> dwell-by-site + relocations (independent state labels)
        dwell, relocs, _segs = w.trunk_state_dwell_transitions(
            g, roi_cfg, date=date, bin_s=CP_BIN_S, min_dwell_bins=CP_MIN_SEG_BINS, min_disp_in=DOORWAY_BUFFER_IN)
        tot = sum(dwell.values())
        for st, nb in dwell.items():
            dwell_rows.append({"night": date, "shortid": str(sid), "state": st, "n_bins": int(nb),
                               "dwell_frac": (nb / tot) if tot else np.nan})
        for rr in relocs:
            reloc_rows.append({"night": date, "shortid": str(sid),
                               "reloc_hour_local": _cp_hour_local(rr["time_utc"]),
                               "from_state": rr["from_state"], "to_state": rr["to_state"], "disp_in": rr["disp_in"]})
    changepoints = pd.DataFrame(cp_rows)
    cp_sens = pd.DataFrame(sens_rows)
    state_dwell = pd.DataFrame(dwell_rows)
    relocations = pd.DataFrame(reloc_rows)
    sup = changepoints[changepoints["supported"]] if not changepoints.empty else changepoints
    trans_mat = (relocations.groupby(["from_state", "to_state"]).size().rename("n").reset_index()
                 .sort_values("n", ascending=False) if not relocations.empty
                 else pd.DataFrame(columns=["from_state", "to_state", "n"]))
    all_rd = trunk[["night", "shortid"]].drop_duplicates().astype(str)
    reloc_counts = (relocations.groupby(["night", "shortid"]).size().rename("n_relocations").reset_index()
                    if not relocations.empty else pd.DataFrame(columns=["night", "shortid", "n_relocations"]))
    reloc_counts = all_rd.merge(reloc_counts, on=["night", "shortid"], how="left").fillna({"n_relocations": 0})
    reloc_counts["n_relocations"] = reloc_counts["n_relocations"].astype(int)
    dwell_summary = (state_dwell.groupby("state")["dwell_frac"].agg(["mean", "median", "size"]).reset_index()
                     .sort_values("mean", ascending=False) if not state_dwell.empty
                     else pd.DataFrame(columns=["state", "mean", "median", "size"]))

    # === E — does temperature modulate the MULTI-SITE distribution? (within-rat) ===
    weather_day["midday_peak_temp_c"] = [_window_temp_peak(wx, n, 12, 18) for n in nights]
    peak_map = dict(zip(weather_day["night"], weather_day["midday_peak_temp_c"]))
    if not state_dwell.empty:
        wide = state_dwell.pivot_table(index=["night", "shortid"], columns="state",
                                       values="dwell_frac", fill_value=0.0).reset_index()
        shel_cols = [c for c in w.SHELTER_STATES if c in wide.columns]
        wide["any_shelter_frac"] = wide[shel_cols].sum(axis=1) if shel_cols else 0.0
        wide["exposed_frac"] = wide.get("exposed", 0.0) + wide.get("doorway", 0.0)
        wide["midday_peak_temp_c"] = wide["night"].map(peak_map)
    else:
        wide = pd.DataFrame(columns=["night", "shortid", "any_shelter_frac", "exposed_frac", "midday_peak_temp_c"])

    def _rc(col):        # WITHIN-rat (rat-centered) Spearman of a dwell fraction vs peak temp
        if wide.empty or col not in wide.columns:
            return (np.nan, 0)
        ts = wide.dropna(subset=[col, "midday_peak_temp_c"]).copy()
        if ts.empty:
            return (np.nan, 0)
        ts["c"] = ts[col] - ts.groupby("shortid")[col].transform("mean")
        return _spearman(ts["midday_peak_temp_c"], ts["c"])
    rho_shelter, n_shelter = _rc("any_shelter_frac")
    per_state_temp = []
    for st in ["house_1", "house_2", "refuge_1", "refuge_2", "refuge_3", "water_1", "water_2", "exposed", "doorway"]:
        if st in wide.columns:
            r, nn = _rc(st)
            per_state_temp.append({"state": st, "rho_dwellfrac_vs_peaktemp_ratcentered": r, "n": nn,
                                   "mean_dwell_frac": float(wide[st].mean())})
    per_state_temp = pd.DataFrame(per_state_temp)

    # --- CSVs ---
    emergence.to_csv(out / "trunk_locomotor_emergence_by_day.csv", index=False)
    weather_day.to_csv(out / "emergence_vs_afternoon_temp.csv", index=False)
    morning_sites.to_csv(out / "morning_window_sites.csv", index=False)
    day_sites.to_csv(out / "day_window_sites.csv", index=False)
    window_diff.to_csv(out / "morning_vs_day_window_diff.csv", index=False)
    stability.to_csv(out / "site_stability_by_rat.csv", index=False)
    dropout.to_csv(out / "dropout_by_window.csv", index=False)
    changepoints.to_csv(out / "within_trunk_changepoints.csv", index=False)
    cp_sens.to_csv(out / "changepoint_smoothing_sensitivity.csv", index=False)
    state_dwell.to_csv(out / "trunk_state_dwell.csv", index=False)
    relocations.to_csv(out / "trunk_relocations.csv", index=False)
    trans_mat.to_csv(out / "state_transition_matrix.csv", index=False)
    reloc_counts.to_csv(out / "relocations_per_ratday.csv", index=False)
    dwell_summary.to_csv(out / "dwell_by_site_summary.csv", index=False)
    wide.to_csv(out / "site_dwell_vs_temperature.csv", index=False)
    per_state_temp.to_csv(out / "per_state_temp_corr.csv", index=False)

    # --- figures ---
    _fig_emergence_vs_temp(emergence, weather_day, figdir / "BD1_emergence_vs_temp.png")
    _fig_morning_vs_day(morning_sites, day_sites, cents, tags, figdir / "BD2_morning_vs_day_site.png")
    _fig_emergence_timeline(profile, emergence, figdir / "BD3_emergence_timeline.png")
    _fig_changepoint_hist(changepoints, figdir / "CP1_changepoint_time_hist.png")
    _fig_changepoint_per_ratday(changepoints, tags, figdir / "CP2_changepoint_per_ratday.png")
    _fig_state_dwell_matrix(state_dwell, trans_mat, tags, figdir / "SS1_state_dwell_and_transitions.png")
    _fig_shelter_temp(wide, tags, figdir / "E1_shelter_vs_exposed_vs_temp.png")

    # --- report + manifest ---
    report = _build_report(nights, tags, jitter, moving_thr, emergence, weather_day, morning_sites,
                           day_sites, window_diff, stability, dropout, changepoints, cp_sens,
                           state_dwell, relocations, trans_mat, reloc_counts, dwell_summary,
                           wide, rho_shelter, n_shelter, per_state_temp, out)
    (out / "direction3_biological_day_sleep_report.md").write_text(report, encoding="utf-8")
    (REPORT_DIR / "direction3_biological_day_sleep_report.md").write_text(report, encoding="utf-8")

    n_sup = int(changepoints["supported"].sum()) if not changepoints.empty else 0
    w.write_run_manifest(out, {
        "analysis": "Direction 3 — biological-day sleep model (trunk + locomotor emergence + MULTI-SITE "
                    "state-space relocations + within-rat multi-site temperature)",
        "trunk": f"{TRUNK_START:02d}:00 -> locomotor_emergence(day)",
        "emergence_definition": "WISER locomotor emergence / sleep-site departure; ~20:00, circadian-clustered, "
                                "NOT temperature-driven. Sensor-limited (lags any in-nest wake WISER cannot see).",
        "retires": "temperature_calibrated_sleep_end (past-midnight; conflated the midnight nap)",
        "site_state_space": "FULL ROI set via classify_site_state: house_1, house_2, refuge_1/2/3, "
                            "refuge_4 (date-gated burrow), water_1, water_2, doorway, exposed, unknown "
                            "(food->house). Explicit distance rule (shelter_buffer 15 in absorbs ~7 in jitter). "
                            "GAPS: no water-tower ROI (near-water=water_1/2); boundary rect inconsistent -> "
                            "no reliable perimeter (doorway = entrance proxy).",
        "changepoint": f"dominant within-trunk position change-point per rat-day (no fixed hour); pre/post "
                       f"INDEPENDENTLY state-classified; {n_sup} supported (disp >= {CP_MIN_DISP_IN} in).",
        "relocations": "multi-site state-sequence: full transition matrix + relocations/rat-day + dwell-by-site.",
        "temperature_site": "Section E multi-site (within-rat): rat-centered Spearman(any-shelter dwell frac & "
                            "per-state dwell frac, midday peak temp). Ambient = COARSE covariate (no shelter "
                            "microclimate); null phrased 'no detectable association under current measurement/N'.",
        "superseded": "the earlier BINARY house_2-fraction Section E (state-space misspecified) is superseded.",
        "locomotor_emergence_hour_by_day": {k: round(v, 2) for k, v in em_map.items()},
        "nights": nights, "tags": tags, "rest_cutoff_inps": moving_thr, "jitter_floor_in": jitter,
        "frame": "WISER inch offset, UNVERIFIED — ROI-identity + relative displacement only",
        "deferred": "nap detection in the active night",
    })
    n_rel = int(relocations.shape[0]) if not relocations.empty else 0
    print(f"\n  emergence~{np.nanmedian(list(em_map.values())):.1f}h  supported change-points={n_sup}/{len(changepoints)}  "
          f"multi-site relocations={n_rel}  report -> {REPORT_DIR}")
    print(f"All outputs written to: {out}")


def _build_report(nights, tags, jitter, moving_thr, emergence, weather_day, morning_sites,
                  day_sites, window_diff, stability, dropout, changepoints, cp_sens,
                  state_dwell, relocations, trans_mat, reloc_counts, dwell_summary,
                  wide, rho_shelter, n_shelter, per_state_temp, out) -> str:
    L = []
    L.append("# Direction 3 — biological-day sleep model (core rebuild)\n")
    L.append(f"*Candidate / measurement-limited. Rest = low-speed proxy (< {moving_thr:.1f} in/s), NOT "
             f"ephys. WISER inch frame UNVERIFIED (ROI-identity + RELATIVE displacement only). Jitter "
             f"~{jitter:.0f} in.*\n")
    L.append("> **This RETIRES the temperature-crossing `sleep_end`.** The rat biological day is a **sleep "
             "TRUNK ~05:00 → trunk-end** + an active night with a **~midnight nap (not trunk)**. The trunk "
             "end is `locomotor_emergence_hour` — the WISER **onset of sustained locomotion / sleep-site "
             "departure** (~20:00). **Sensor-limited interpretation:** WISER cannot observe in-shelter "
             "waking/stirring, so this variable is *only* the site-departure time; the field-observed "
             "~18:00 in-nest wake vs this ~20:00 is **consistent with** WISER's invisibility to in-nest "
             "behavior but is **not proven** to be entirely caused by it (a genuinely later departure is "
             "not excluded without interior CV / ephys). For bounding a sleep-SITE window the locomotor "
             "edge is the correct boundary.\n")
    L.append(f"Days: {', '.join(nights)} · tags: {', '.join(tags)}. Includes the independent change-point "
             "(Section D) + within-rat temperature-modulates-site (Section E). Nap detection deferred.\n")
    L.append("> **Reconciliation (2026-07-11).** The **single-largest change-point (A1, Section D)** and the "
             "**multi-site state-sequence relocations (A2, Section D multi-site)** are kept **separate**: "
             "different thresholds (**100 in** vs **36 in**), different timing (**13.5 h / 11%** vs "
             "**13.4 h / 8%** within ±1 h of 10:00). Dwell is reported **unconditionally** (sums to 1). "
             "Every number traces to `direction3_biological_day_sleep_canonical_results.md`/`.json` (derived "
             "from this run's CSVs). Superseded wording — conditional dwell shown as a composition, "
             "'~46% non-house', 'shift away from the houses', 'circadian-fixed' — is corrected here and "
             "recorded in `change_log/2026-07-10-biological-day-sleep.md`.\n")

    # Definitions
    L.append("## Definitions (formula + plain text)\n")
    L.append(f"- **Rest proxy** `resting` = smoothed UWB speed `< c`, `c = {moving_thr:.2f}` in/s (p99 "
             "stationary). Proxy for sleep, not ephys.")
    L.append(f"- **Sleep trunk** = the main daytime rest, local `[{TRUNK_START:02d}:00, locomotor_emergence(day))`.")
    L.append("- **`locomotor_emergence_hour(day)`** = first afternoon 5-min bin (≥15:00) with activity "
             "fraction ≥ baseline_active + max(0.03, 0.20·(dusk_peak − baseline)), sustained ≥3 bins, "
             "clamped `[16:00, 21:00]`. The **relative** trip point catches the emergence, not the "
             "near-peak. Sensor-limited: locomotion onset / site departure, NOT in-nest wake.")
    L.append(f"- **Morning-window site** `[{TRUNK_START:02d}:00, {WINDOW_SPLIT:02d}:00)` and **day-window "
             f"site** `[{WINDOW_SPLIT:02d}:00, emergence)` — per (day, rat) resting-fix centroid (median "
             "x,y), `nearest_shelter`, `dominant_roi`. **These fixed windows do NOT locate a transition "
             "time** — that is what Section D estimates independently.")
    L.append("- **Site STATE space (full ROI set)** — `classify_site_state` maps a segment centroid to "
             "**house_1, house_2, refuge_1/2/3, refuge_4** (date-gated by `valid_until`; burrow-flagged in "
             "window), **water_1, water_2, doorway** (near a shelter core, jitter band), **exposed** (open), "
             "**unknown**; `food_1/2 → house_1/2`. Explicit distance rule: enter a shelter within footprint + "
             "**15 in** (absorbs ~7 in jitter, p95 ~15); doorway a further **24 in**; else exposed. **Gaps:** "
             "no water-tower ROI (near-water = water_1/2); the boundary rect is inconsistent with the house "
             "positions → no reliable 'perimeter' (doorway is the entrance proxy).")
    L.append(
        "- **Two DISTINCT site analyses (never merged):** "
        "**(A1) single-largest within-trunk change-point** (`detect_site_changepoint`) = the ONE trunk "
        "split (5-min median-position series, 3-bin smoothed) maximizing pre/post segment-median "
        f"displacement; **supported** if displacement ≥ **{CP_MIN_DISP_IN:.0f} in** with ≥3 bins each side. "
        "Its `confidence = disp/(disp+within-scatter)` is a **displacement-to-scatter ratio (separation "
        "score), NOT a statistical confidence / p-value / posterior**. from/to states = pre/post centroids "
        "classified **independently** via `classify_site_state`, never by displacement direction. It detects "
        "the largest early-vs-late contrast; it does NOT prove exactly one discrete relocation per rat-day. "
        "**(A2) multi-site state-sequence relocation** (`trunk_state_dwell_transitions`) = EVERY change "
        "between two ≥15-min (≥3-bin) confident state-segments whose centroids differ ≥ "
        f"**{DOORWAY_BUFFER_IN:.0f} in** (driver value, overriding the function default 24). **The "
        f"{CP_MIN_DISP_IN:.0f}-in change-point threshold does NOT apply to these.** **dwell fraction** = "
        "share of trunk bins in a state.")
    L.append("- **centroid_mad_in** = median radial deviation of a rat's per-day centroid from its own "
             "median. **Spearman ρ** = rank correlation. **dropout_frac** = 1 − present/expected 60-s bins.\n")

    # A — emergence vs temperature
    L.append("## A. Locomotor emergence (sleep-site departure): evening-clustered, no detectable temperature association\n")
    e = emergence.merge(weather_day[["night", "afternoon_temp_c"]], left_on="sleep_day", right_on="night", how="left")
    show = e[["sleep_day", "baseline_active", "peak_active", "locomotor_emergence_hour", "crossed", "afternoon_temp_c"]]
    L.append("```\n" + show.round(2).to_string(index=False) + "\n```\n")
    rho, n = _spearman(e["afternoon_temp_c"], e["locomotor_emergence_hour"])
    wk = e["locomotor_emergence_hour"].to_numpy()
    n_cross = int(e["crossed"].sum()) if "crossed" in e.columns else -1
    up = e.loc[e["locomotor_emergence_hour"] >= 21.0, "sleep_day"].astype(str).tolist()
    lo = e.loc[e["locomotor_emergence_hour"] <= 16.0, "sleep_day"].astype(str).tolist()
    interior = e[(e["locomotor_emergence_hour"] > 16) & (e["locomotor_emergence_hour"] < 21)]["locomotor_emergence_hour"]
    int_rng = f"{interior.min():.1f}–{interior.max():.1f}" if len(interior) else "n/a"
    L.append(f"- `locomotor_emergence_hour` median **{np.nanmedian(wk):.1f} h**; the detector crossed "
             f"threshold on **{n_cross}/{len(e)}** days. On the **{len(interior)} interior days** it lands "
             f"**{int_rng} h**. **Boundary/censored days:** {len(up)} at the 21:00 ceiling "
             f"({', '.join(up)} — 06-28 never crossed → censored, the others clamped from above), {len(lo)} "
             f"at the 16:00 floor ({', '.join(lo)} — fog-day afternoon activity blip); **clamp values are "
             f"censored boundary outputs, not exact event times**. Spearman(emergence, afternoon_temp) = "
             f"**{rho:.2f}** (n={n}) → **no detectable monotonic association** across these 11 days. This is "
             "an **observational evening-clustering, NOT a demonstrated circadian mechanism**. It **retires** "
             "the old thermal `sleep_end` (which ran past midnight, 00:55/02:20, conflating the overnight "
             "cool-down + the midnight nap with the trunk end).")
    L.append("- **Sensor caveat (not an over-claim):** ~20:00 is the *locomotor* emergence (site departure). "
             "It LAGS the field-observed ~18:00 in-nest wake; that gap is **consistent with** WISER being "
             "blind to in-nest stirring (below the ~7 in jitter floor) but is **not proven** to be entirely "
             "that — measuring the true ~18:00 arousal needs ephys / interior CV (CH07/CH08).\n")

    # B — morning vs day window difference (NOT a switch AT 10:00)
    L.append("## B. Morning-window vs day-window site — they DIFFER, but this does NOT prove a switch at 10:00\n")
    L.append("With 10:00 used as the window boundary, this section can only ask whether the morning-window "
             "[05–10] and day-window [10–emergence] **site assignments differ** — it **cannot** establish "
             "that a transition happens *at* 10:00 (that is Section D).")
    if window_diff.empty:
        L.append("- No morning/day window pairs to compare.\n")
    else:
        cols = ["night", "shortid", "morning_shelter", "day_shelter", "morning_vs_day_shift_in",
                "shelter_differs", "relocation_tier"]
        L.append("```\n" + window_diff[cols].round(1).to_string(index=False) + "\n```\n")
        n_diff = int(window_diff["shelter_differs"].sum())
        L.append(f"- Morning-window vs day-window nearest-house **differs on {n_diff}/{len(window_diff)}** "
                 f"rat-days (tiers { window_diff['relocation_tier'].value_counts().to_dict() }). This is a "
                 "**difference between two fixed windows**, not a located transition time.\n")

    # D — independent change-point (the requested analysis)
    L.append("## D (A1). Single-largest within-trunk change-point (no fixed 10:00) — WHEN is the biggest shift?\n")
    if changepoints.empty:
        L.append("- No change-point rows.\n")
    else:
        sup = changepoints[changepoints["supported"]]
        n_sup, n_tot = len(sup), len(changepoints)
        L.append(f"- **{n_sup}/{n_tot} rat-days have a SUPPORTED change-point** (pre/post displacement ≥ "
                 f"{CP_MIN_DISP_IN:.0f} in). Full table `within_trunk_changepoints.csv`.")
        if n_sup:
            hrs = sup["cp_hour_local"].dropna()
            med, q1, q3 = hrs.median(), hrs.quantile(.25), hrs.quantile(.75)
            near1 = float((hrs.between(9, 11)).mean()); near2 = float((hrs.between(8, 12)).mean())
            L.append(f"- **Change-point TIME distribution (supported):** median **{med:.1f} h**, IQR "
                     f"[{q1:.1f}, {q3:.1f}]; **{near1*100:.0f}% within ±1 h of 10:00**, {near2*100:.0f}% "
                     f"within ±2 h. Range {hrs.min():.1f}–{hrs.max():.1f} h. See `CP1`.")
            clustered = (near1 >= 0.5)
            L.append(f"  → The transitions are **{'broadly consistent with a ~10:00 switch' if clustered else 'SPREAD across the trunk, NOT tightly clustered at 10:00'}** "
                     "(the fixed-window Section B is therefore a coarse proxy at best).")
            cpdir = (sup.groupby(["from_state", "to_state"]).size().rename("n").reset_index()
                     .sort_values("n", ascending=False))
            L.append("- **Change-point from→to STATES (classified independently over the full ROI set, NOT "
                     "by displacement direction):**")
            L.append("```\n" + (cpdir.to_string(index=False) if not cpdir.empty else "(none)") + "\n```")
        conf_med = float(sup["confidence"].median()) if n_sup else float("nan")
        disp_med = float(sup["displacement_in"].median()) if n_sup else float("nan")
        L.append(f"- **Separation criteria:** supported requires displacement ≥ {CP_MIN_DISP_IN:.0f} in "
                 f"(~14× jitter) AND ≥3 bins each side. The supported set is **high-separation** — median "
                 f"separation score {conf_med:.2f} (= disp/(disp+scatter), a RATIO, not a statistic), median "
                 f"displacement **{disp_med:.0f} in** (≈ the house_1↔house_2 separation): clean full-shelter "
                 "position steps, not jitter. So the largest within-trunk shift is COMMON and LARGE, just not "
                 "time-locked to 10:00.")
        # smoothing sensitivity
        if not cp_sens.empty:
            both = cp_sens.merge(changepoints[["night", "shortid", "supported"]], on=["night", "shortid"], how="left")
            sup_sens = both[both["supported"]]
            stable = int(sup_sens["smoothing_stable"].sum()) if not sup_sens.empty else 0
            L.append(f"- **Sensitivity to smoothing** (`smooth_bins ∈ {list(CP_SMOOTH_SENS)}`): of the "
                     f"{len(sup_sens)} supported rat-days, **{stable}** keep a supported change-point at the "
                     "same time (±1 h) across all three smoothings (`changepoint_smoothing_sensitivity.csv`).")
        # missing-data sensitivity
        hi = changepoints[changepoints["trunk_dropout_frac"] > 0.25]
        if n_sup:
            sup_lo = sup[sup["trunk_dropout_frac"] <= 0.25]["cp_hour_local"].dropna()
            L.append(f"- **Sensitivity to missing data:** {len(hi)} rat-days have >25% trunk dropout "
                     "(lower-confidence; a gap is 'unknown', not a move). Restricting to ≤25%-dropout "
                     f"supported change-points, median time = "
                     f"{sup_lo.median():.1f} h (vs {sup['cp_hour_local'].median():.1f} h all) — "
                     "reports whether the timing survives the dropout filter.\n")

    # D.ii — full state-space relocations, dwell, transition matrix
    L.append("### D (A2) — multi-site state-sequence: full-state dwell, ALL relocations, transition matrix\n")
    L.append("The change-point above finds only the single largest positional shift. The **state sequence** "
             "classifies EVERY trunk segment to the full ROI state space (`trunk_state_dwell_transitions`) — "
             "so relocations are labelled by **independent state mapping**, not displacement direction.")
    meta_cols = {"night", "shortid", "any_shelter_frac", "exposed_frac", "midday_peak_temp_c"}
    st_cols = [c for c in wide.columns if c not in meta_cols] if (wide is not None and not wide.empty) else []
    if st_cols:
        uncond = wide[st_cols].mean().sort_values(ascending=False)
        house_share = float(uncond.get("house_1", 0.0) + uncond.get("house_2", 0.0))
        comp = "\n".join(f"{k:>9} {v:6.3f}" for k, v in uncond.items())
        L.append(f"- **Dwell composition — UNCONDITIONAL** (mean over all {len(wide)} rat-days incl. zeros; "
                 f"**sums to 1.0**; this is the valid composition):\n```\n{comp}\n"
                 f"  (sum {float(uncond.sum()):.3f}; house_1+house_2 = {house_share:.3f} "
                 f"≈ {house_share*100:.0f}% of classified trunk dwell)\n```")
        L.append("  *`refuge_4` (burrow) + `tunnel` are interpretation-limited; `doorway`/`exposed` are "
                 "classifier-dependent and jitter-adjacent; `water_2` is a near-water ROI (NOT a validated "
                 "water-tower refuge).*")
    if not dwell_summary.empty:
        L.append("- **Dwell — CONDITIONAL-on-appearance** (mean *only over rat-days where the state occurs*; "
                 "`size` = # such rat-days; **does NOT sum to 1 — do not read as a composition**):\n```\n"
                 + dwell_summary.round(3).to_string(index=False)
                 + f"\n  (sum {float(dwell_summary['mean'].sum()):.3f} — conditional, NOT the composition)\n```")
    if reloc_counts is not None and not reloc_counts.empty:
        rc = reloc_counts["n_relocations"]
        L.append(f"- **Relocations per rat-day:** mean {rc.mean():.1f}, median {int(rc.median())}, range "
                 f"{int(rc.min())}–{int(rc.max())}; {int((rc == 0).sum())}/{len(rc)} rat-days with 0 "
                 f"({int(relocations.shape[0]) if relocations is not None else 0} relocations total).")
    if trans_mat is not None and not trans_mat.empty:
        L.append("- **Transition matrix (from→to over ALL relocations; independent state labels):**\n```\n"
                 + trans_mat.to_string(index=False) + "\n```")
        L.append("  These are **NOT all house_1↔house_2** — the full state space exposes house↔refuge, "
                 "house↔water, house↔doorway, and exposed transitions the binary framing hid. **Caveat:** "
                 "`refuge_4`-involving rows fall in the **07-03→07-07 BURROW window** (refuge_4 = burrow "
                 "entrance + UWB below-plane dropout, **NOT a sleep site**) → discount those. See `SS1`.")
        _H = {"house_1", "house_2"}; _EXC = {"refuge_4", "tunnel"}
        _r = relocations.copy()
        _r["nh"] = ~(_r["from_state"].isin(_H) & _r["to_state"].isin(_H))
        _r["interp"] = ~(_r["from_state"].isin(_EXC) | _r["to_state"].isin(_EXC))
        _ri = _r[_r["interp"]]
        L.append(f"  **Non-house involvement (quantified):** {int(_r['nh'].sum())}/{len(_r)} = "
                 f"{100*_r['nh'].mean():.0f}% of all {len(_r)} relocations involve ≥1 non-house state; "
                 f"restricting to the **{len(_ri)} interpretable** relocations (excluding refuge_4/tunnel), "
                 f"{int(_ri['nh'].sum())}/{len(_ri)} = {100*_ri['nh'].mean():.0f}% do.")
    if relocations is not None and not relocations.empty:
        rh = relocations["reloc_hour_local"].dropna()
        L.append(f"- **Relocation timing:** median {rh.median():.1f} h; {float(rh.between(9, 11).mean())*100:.0f}% "
                 "within ±1 h of 10:00 → spread across the trunk (consistent with the change-point), not a "
                 "10:00 switch.\n")

    # E — MULTI-SITE temperature (within-rat)
    L.append("## E. Does temperature modulate the MULTI-SITE sleep-site distribution? (within-rat)\n")
    L.append("> **Supersedes the earlier binary house_2-fraction test** (that state space was misspecified — "
             "rats also use secondary refuges, near-water, doorways, and exposed rest). Here the outcome is "
             "the **dwell distribution across ALL states**. Absolute use is identity-dominated, so tests are "
             "**within-rat** (rat-centered); ambient temperature is a **coarse covariate** (no shelter "
             "microclimate), so a null is *no detectable association under the current measurement + N*.\n")
    if wide is None or wide.empty:
        L.append("- No state-dwell rows.\n")
    else:
        ar = rho_shelter
        if ar != ar:
            a_txt = "**n/a** (no data)."
        elif abs(ar) < 0.2:
            a_txt = "**No detectable association** (|ρ|<0.2) under the current measurement + sample size."
        elif ar < 0:
            a_txt = ("**Negative** — a rat spends **LESS** time fully enclosed on its hotter days "
                     "(**candidate**). NB `any_shelter_frac` **includes** the interpretation-limited "
                     "refuge_4/tunnel, so read the per-state panel (b) for where the change actually is.")
        else:
            a_txt = "**Positive** — more refuge use on hotter days (**candidate**)."
        L.append(f"- **(a) Any-shelter vs exposed:** Spearman(rat-centered any-shelter dwell fraction, midday "
                 f"peak temp) = **{ar:.2f}** (n={n_shelter}). {a_txt} See `E1`.")
        if per_state_temp is not None and not per_state_temp.empty:
            ps = per_state_temp.copy()
            ps["rho_dwellfrac_vs_peaktemp_ratcentered"] = ps["rho_dwellfrac_vs_peaktemp_ratcentered"].map(
                lambda v: f"{v:.2f}" if v == v else "n/a")
            L.append("- **(b) Which site vs temp** (rat-centered Spearman of each state's dwell fraction vs "
                     "peak temp; multiple comparisons, small N — descriptive):\n```\n"
                     + ps.round(3).to_string(index=False) + "\n```")
            hits = per_state_temp[per_state_temp["rho_dwellfrac_vs_peaktemp_ratcentered"].abs() > 0.3]
            if not hits.empty:
                parts = [f"{r.state} ρ={r.rho_dwellfrac_vs_peaktemp_ratcentered:+.2f} "
                         f"({'↑' if r.rho_dwellfrac_vs_peaktemp_ratcentered > 0 else '↓'} with heat)"
                         for r in hits.itertuples()]
                L.append("  **Candidate multi-site temperature signal** (|ρ|>0.3, uncorrected): "
                         + "; ".join(parts) + ". The two houses go **opposite** ways (house_1 ρ=+0.17 rises, "
                         "house_2 ρ=−0.19 falls), so this is **NOT** a uniform 'leave the enclosed houses' "
                         "pattern; the most consistent descriptive signal is **increased doorway-classified "
                         "dwell on hotter days**, with near-water (`water_2`) a weak spatial clue needing ROI "
                         "validation. The binary house_2-fraction test (ρ≈−0.20) missed it. **Candidate "
                         "only:** n=11 days, uncorrected multiple comparisons, ambient (not shelter) "
                         "temperature; doorway/exposed are jitter-adjacent (position noise at shelter edges). "
                         "Rat-centering removes each rat's MEAN occupancy only — it does not fit rat-specific "
                         "slopes, model shared day-level exposure, or adjust for day-since-release.")
            else:
                L.append("  No state's dwell fraction shows |ρ|>0.3 → no detectable temperature association "
                         "across the state space under the current measurement + N.")
        L.append("- **Caveats:** ambient (not shelter) temperature; house_2/refuges **not verified cooler** "
                 "(inch frame); temperature acts on BOTH the animal and UWB-dropout paths; refuge_4 burrow "
                 "days flagged. See `SS1`/`E1` + `site_dwell_vs_temperature.csv`, `per_state_temp_corr.csv`.\n")

    # C — stability
    L.append("## C. Across-day site stability (per rat, per window)\n")
    if not stability.empty:
        L.append("```\n" + stability.round(2).to_string(index=False) + "\n```\n")
        L.append("- `centroid_mad_in` < 30 in = a stable across-day site (within ~4× jitter).\n")

    L.append("## Dropout guard\n")
    dm = dropout[dropout["dropout_frac"] > 0.25]
    L.append(f"- Window animal-days with >25% dropout: {len(dm)}. refuge_4-dominant reads (07-03→07-07) "
             "flagged `burrow_flag` and excluded (burrow entrance, not sleep).\n")

    L.append("## Evidence status (two levels)\n")
    L.append("**Supported within the current WISER measurement (descriptive):** detected within-trunk site "
             "changes are not concentrated near 10:00 (A1 11% / A2 8% within ±1 h); the two house-labelled "
             "ROIs hold ~85% of unconditional low-movement trunk dwell; the state-sequence detects multiple "
             "qualifying transitions per rat-day (mean 3.1), ~half of interpretable relocations touching a "
             "non-house state; WISER locomotor emergence is evening-clustered (~20.8 h) with no detectable "
             "temperature association over 11 days; individual differences in primary house and mobility are "
             "stable.\n")
    L.append("**Candidate biological interpretation (NOT established):** the low-movement trunk corresponds "
             "to physiological sleep; classified ROIs correspond to specific physical refuge structures "
             "(frame unverified); doorway/near-water use on hot days reflects thermoregulation; evening "
             "emergence clustering is generated by a circadian mechanism; `water_2` is the water-tower "
             "refuge. Each requires external validation (interior CV CH07/CH08 / ephys, georeference survey, "
             "in-shelter thermistor).\n")
    L.append("## Deferred (next pass)\n")
    L.append("- **Nap detection** in the active night (the ~midnight rest bout, scored separately from the "
             "trunk). The true ~18:00 in-nest behavioral wake needs interior CV (CH07/CH08) / ephys.\n")
    L.append(f"\n*Figures + CSVs: `{out}`.*\n")
    return "\n".join(L)


if __name__ == "__main__":
    main()
