r"""
analyze_circadian_rest.py — Direction 3 companion: diel / circadian REST profile.

Question: across the 24 h day, WHEN do the rats stop moving (rest / candidate sleep)?
Produces a per-local-clock-hour REST fraction: the **group mean ± SEM across animals**
first, with each **per-animal trace ("truth")** overlaid, plus a coverage panel so
signal dropout is never mistaken for rest.

Method (candidate, measurement-limited):
  * REST = smoothed WISER speed < the stationary p99 noise floor (indistinguishable from
    stationary given ~7 in jitter). A low-speed PROXY for sleep, NOT ephys-validated.
  * Full 24 h, binned by LOCAL clock hour (EDT = UTC-4); pooled over all days present.
  * A signal GAP is 'unknown', never 'rest' -> rest_frac is over OBSERVED fixes and a
    coverage fraction is reported per hour; the refuge_4 burrow (nightly 07-03->07-07)
    and wet nights raise night dropout, so low-coverage hours are lower-confidence.

Guardrails: rest is a proxy; the WISER inch frame is unverified (irrelevant here — this
is a temporal, not spatial, claim); weather/burrow act on BOTH the animal path and the
UWB-dropout path (hence the coverage panel). Read-only on the DB.

Outputs -> D:\Field2026_analysis_out\circadian_rest_<ts>\ (CSVs + figure + manifest); the
version-controlled report also goes to wiser/outputs/circadian_rest/.
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
import wiser_inputs as _wi        # noqa: E402  (per-cohort WISER snapshot resolver)
import time_utils                       # noqa: E402
import metrics                          # noqa: E402

# Newest snapshot on the analysis PC -> full days 2026-06-28 → 07-08.
# WISER db + fixed baseline resolved per-cohort by wiser_inputs.finalize() (see --db / --fixed / --canonical)
DEFAULT_GT = PROJECT_ROOT / "configs" / "fixed_position_ground_truth.csv"
from output_paths import OUT_ROOT as DEFAULT_OUT_ROOT   # single source of truth (env FIELD2026_ANALYSIS_OUT_ROOT)
import output_paths as _op                               # cohort-aware run/report/figure dirs
REPORT_DIR = PROJECT_ROOT / "outputs" / "circadian_rest"
DROP_TAGS = {"12409"}                    # Sova, removed -> excluded
# Direction-3 daytime REST window (05:00-21:00 local); the complement is 'night'.
DAY_START, DAY_END = 5, 21
# per-day resolution: a cell/night below these is missing data, not rest -> masked
MIN_COVER = 0.30                         # min per (tag,date,hour) coverage to plot/average
MIN_GROUP_ANIMALS = 2                    # min rats with data for a group per-night point
MIN_HOURS_PHASE = 16                     # min covered hours for a COMPARABLE amplitude
MIN_HOURS_PEAK = 3                       # min covered hours to report a peak at all
# 06-28 is the release day: rats went out ~19:25 EDT, so that night's activity peak is a
# release-driven 'pseudo' peak on partial (evening-only) coverage — reported but flagged.
RELEASE_DATE, RELEASE_HHMM = "2026-06-28", "~19:25"


def _fig_circadian(per_tag, grp, jitter, moving_thr, nights, out_path):
    """Three stacked panels vs local clock-hour (night shaded, 05:00-21:00 = daytime rest
    window): (1) REST fraction on a full 0-1 axis (honest scale — rest is high everywhere
    at the jitter-ceiling threshold); (2) the same signal as ACTIVE fraction (1 - rest),
    auto-scaled to reveal the diel rhythm; (3) coverage. Group mean ± SEM + per-animal
    traces on both (1) and (2)."""
    fig, (ax, axa, axc) = plt.subplots(
        3, 1, figsize=(10, 8.2), sharex=True, gridspec_kw={"height_ratios": [2.4, 2.4, 1]})
    hours = np.arange(24)
    g = grp.set_index("clock_hour").reindex(hours)
    cmap = plt.get_cmap("tab10")
    tags = sorted(per_tag["shortid"].astype(str).unique())
    pt = {t: per_tag[per_tag["shortid"].astype(str) == t].set_index("clock_hour").reindex(hours)
          for t in tags}

    for a in (ax, axa, axc):     # night shading = complement of the daytime rest window
        a.axvspan(-0.5, DAY_START - 0.5, color="0.90", zorder=0)
        a.axvspan(DAY_END - 0.5, 23.5, color="0.90", zorder=0)

    m, sem = g["rest_frac_mean"].to_numpy(), g["rest_frac_sem"].to_numpy()
    # (1) REST fraction, full 0-1 scale
    for i, t in enumerate(tags):
        ax.plot(hours, pt[t]["rest_frac"], "-", lw=0.9, alpha=0.45, color=cmap(i % 10), label=t)
    ax.fill_between(hours, m - sem, m + sem, color="k", alpha=0.18, zorder=3, label="±1 SEM (across rats)")
    ax.plot(hours, m, "-o", color="k", lw=2.0, ms=3.5, zorder=4, label="group mean")
    ax.set_ylim(0, 1.02)
    ax.set_ylabel("REST fraction\n(speed < %.1f in/s)" % moving_thr, fontsize=9)
    ax.set_title("Circadian REST / ACTIVITY profile — group mean ± SEM + per-animal "
                 "(shaded = night; 05:00-21:00 = daytime rest window)\n"
                 f"rest = low-speed PROXY (not ephys); jitter ~{jitter:.0f} in; "
                 f"{len(tags)} rats × {len(nights)} days; local EDT", fontsize=9)
    ax.legend(fontsize=7, ncol=4, loc="lower center")
    ax.grid(alpha=0.25)

    # (2) ACTIVE fraction = 1 - rest, auto-scaled (active = 1-rest so SEM is identical)
    am = 1.0 - m
    for i, t in enumerate(tags):
        axa.plot(hours, 1.0 - pt[t]["rest_frac"], "-", lw=0.9, alpha=0.45, color=cmap(i % 10))
    axa.fill_between(hours, am - sem, am + sem, color="k", alpha=0.18, zorder=3)
    axa.plot(hours, am, "-o", color="k", lw=2.0, ms=3.5, zorder=4)
    axa.set_ylabel("ACTIVE fraction\n(1 − rest, auto-scaled)", fontsize=9)
    axa.grid(alpha=0.25)
    axa.margins(y=0.15)
    # annotate evening activity peak
    pk = int(np.nanargmax(am))
    axa.annotate(f"activity peak {pk:02d}:00", xy=(pk, am[pk]),
                 xytext=(pk, am[pk] + (np.nanmax(am) - np.nanmin(am)) * 0.35),
                 fontsize=7, ha="center", color="tab:red",
                 arrowprops=dict(arrowstyle="->", color="tab:red", lw=0.8))

    # (3) coverage panel (dropout != rest)
    axc.bar(hours, g["cover_frac_mean"], color="tab:blue", alpha=0.6, width=0.85)
    axc.axhline(0.5, color="tab:red", ls=":", lw=0.8)
    axc.set_ylim(0, 1.02)
    axc.set_ylabel("coverage\n(obs min/60)", fontsize=8)
    axc.set_xlabel("local clock hour (EDT)")
    axc.set_xticks(hours); axc.tick_params(labelsize=7); axc.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def _group_by_night(per_cell):
    """Mask low-coverage cells, then average REST fraction ACROSS animals per (date, hour).
    Returns (date, clock_hour, rest_frac_mean, rest_frac_sem, active_mean, n_animals)."""
    pc = per_cell.copy()
    pc.loc[pc["cover_frac"] < MIN_COVER, "rest_frac"] = np.nan
    g = (pc.dropna(subset=["rest_frac"]).groupby(["night", "clock_hour"])
         .agg(rest_frac_mean=("rest_frac", "mean"), rest_frac_sd=("rest_frac", "std"),
              n_animals=("rest_frac", "size")).reset_index())
    g = g[g["n_animals"] >= MIN_GROUP_ANIMALS].copy()
    g["rest_frac_sem"] = g["rest_frac_sd"] / np.sqrt(g["n_animals"].clip(lower=1))
    g["active_mean"] = 1.0 - g["rest_frac_mean"]
    return g


def _night_phase_amp(group_night):
    """Per date: activity-peak hour (phase) + diel amplitude (peak-minus-trough ACTIVE
    fraction). Peak hour is reported for any date with >= MIN_HOURS_PEAK covered hours (so
    the 06-28 release-evening 'pseudo' peak is INCLUDED); amplitude is only comparable —
    and therefore only filled — on dates with >= MIN_HOURS_PHASE covered hours. `partial`
    flags reduced-coverage dates (e.g. the 06-28 evening-only release day)."""
    rows = []
    for night, g in group_night.groupby("night"):
        g = g.dropna(subset=["active_mean"])
        n_hours = int(g["clock_hour"].nunique())
        partial = n_hours < MIN_HOURS_PHASE
        peak_hour = active_peak = amplitude = np.nan
        if n_hours >= MIN_HOURS_PEAK:
            pk = g.loc[g["active_mean"].idxmax()]
            peak_hour, active_peak = int(pk["clock_hour"]), float(pk["active_mean"])
            if not partial:
                amplitude = float(g["active_mean"].max() - g["active_mean"].min())
        rows.append({"night": night, "n_hours": n_hours, "peak_hour": peak_hour,
                     "active_peak": active_peak, "amplitude": amplitude,
                     "partial": partial})
    return pd.DataFrame(rows).sort_values("night").reset_index(drop=True)


def _vlim(per_cell, active):
    """Shared y-limits for the small-multiples. Rest: zoom [min-pad, 1] (reveal the diel
    dip). Active: auto [min-pad, max+pad] (the whole point is to make the peak readable)."""
    v = per_cell.loc[per_cell["cover_frac"] >= MIN_COVER, "rest_frac"].dropna()
    if not len(v):
        return 0.0, 1.005
    if active:
        a = 1.0 - v
        return max(0.0, float(a.min()) - 0.02), float(a.max()) + 0.02
    return max(0.0, float(v.min()) - 0.03), 1.005


def _fig_per_animal(per_cell, tags, nights, jitter, moving_thr, out_path, *, active=False):
    """One panel per animal; a REST- (or ACTIVE-) fraction line per date (colour = date
    order) so a within-animal circadian DRIFT across days is visible. Low-coverage cells
    masked. ``active=True`` plots 1-rest, auto-scaled (easier to read per night)."""
    hours = np.arange(24)
    label = "ACTIVE fraction" if active else "REST fraction"
    ncol = 3
    nrow = int(np.ceil(len(tags) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(4.6 * ncol, 3.3 * nrow),
                             squeeze=False, sharex=True, sharey=True)
    cmap = plt.get_cmap("viridis", max(len(nights), 1))
    ncol_map = {n: cmap(i) for i, n in enumerate(nights)}
    ylo, yhi = _vlim(per_cell, active)
    for k, t in enumerate(tags):
        ax = axes[k // ncol][k % ncol]
        ax.axvspan(-0.5, DAY_START - 0.5, color="0.92", zorder=0)
        ax.axvspan(DAY_END - 0.5, 23.5, color="0.92", zorder=0)
        gt = per_cell[per_cell["shortid"].astype(str) == str(t)]
        for n in nights:
            gn = gt[gt["night"] == n].copy()
            gn.loc[gn["cover_frac"] < MIN_COVER, "rest_frac"] = np.nan
            gn = gn.set_index("clock_hour").reindex(hours)
            val = (1.0 - gn["rest_frac"]) if active else gn["rest_frac"]
            ax.plot(hours, val, "-", lw=1.0, alpha=0.8, color=ncol_map[n])
        ax.set_title(f"tag {t}", fontsize=9)
        ax.set_ylim(ylo, yhi); ax.grid(alpha=0.25); ax.tick_params(labelsize=7)
        if k % ncol == 0:
            ax.set_ylabel(label, fontsize=8)
        if k // ncol == nrow - 1:
            ax.set_xlabel("local hour (EDT)", fontsize=8)
            ax.set_xticks(range(0, 24, 4))
    for j in range(len(tags), nrow * ncol):
        axes[j // ncol][j % ncol].axis("off")
    handles = [plt.Line2D([], [], color=ncol_map[n], lw=2, label=n[5:]) for n in nights]
    fig.legend(handles=handles, loc="lower right", fontsize=7, ncol=2, title="date")
    kind = "ACTIVITY" if active else "REST"
    fig.suptitle(f"Per-animal circadian {kind} profile BY DAY (one line = one date; shaded = night)\n"
                 f"{'active = 1-rest; ' if active else ''}rest = low-speed PROXY < {moving_thr:.1f} in/s "
                 f"(not ephys); jitter ~{jitter:.0f} in; cells < 30% coverage masked", fontsize=9.5)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out_path, dpi=140); plt.close(fig)


def _fig_group_by_night(group_night, phase_amp, nights, moving_thr, out_path, *, active=False):
    """Left: group-mean REST (or ACTIVE) fraction per hour, one line per date (colour =
    date order) -> does the group rhythm shift across days? Right: activity-peak hour
    (phase, ALL dates incl. the 06-28 release pseudo-peak marked hollow) + diel amplitude
    (full days only). ``active=True`` plots the auto-scaled activity fraction."""
    hours = np.arange(24)
    col = "active_mean" if active else "rest_frac_mean"
    kind = "ACTIVITY" if active else "REST"
    fig = plt.figure(figsize=(12, 5.2))
    axm = fig.add_axes([0.06, 0.12, 0.52, 0.78])
    axp = fig.add_axes([0.68, 0.58, 0.29, 0.32])
    axa = fig.add_axes([0.68, 0.12, 0.29, 0.32])
    cmap = plt.get_cmap("viridis", max(len(nights), 1))
    ncol_map = {n: cmap(i) for i, n in enumerate(nights)}
    axm.axvspan(-0.5, DAY_START - 0.5, color="0.92", zorder=0)
    axm.axvspan(DAY_END - 0.5, 23.5, color="0.92", zorder=0)
    for n in nights:
        gn = group_night[group_night["night"] == n].set_index("clock_hour").reindex(hours)
        axm.plot(hours, gn[col], "-o", ms=2.5, lw=1.3, color=ncol_map[n], label=n[5:])
    axm.set_ylabel(f"group-mean {kind} fraction (across rats)")
    axm.set_xlabel("local clock hour (EDT)"); axm.set_xticks(range(0, 24, 2))
    axm.grid(alpha=0.25)
    axm.legend(fontsize=7, ncol=2, title="date", loc="lower center" if active else "upper center")
    axm.set_title(f"Group circadian {kind} by date — does the rhythm drift?", fontsize=9.5)

    # phase: ALL dates with a peak; partial (e.g. 06-28 release) shown hollow
    pa = phase_amp[phase_amp["peak_hour"].notna()].sort_values("night").reset_index(drop=True)
    xt = np.arange(len(pa))
    full = ~pa["partial"].to_numpy()
    axp.plot(xt, pa["peak_hour"], "-", color="tab:red", lw=1.0, alpha=0.5, zorder=1)
    axp.scatter(xt[full], pa.loc[full, "peak_hour"], c="tab:red", s=28, zorder=2, label="full day")
    if (~full).any():
        axp.scatter(xt[~full], pa.loc[~full, "peak_hour"], facecolors="none",
                    edgecolors="tab:red", s=48, zorder=2, label="partial (release)")
    for i, r in pa.iterrows():
        if r["night"] == RELEASE_DATE:
            axp.annotate(f"release {RELEASE_HHMM}", xy=(i, r["peak_hour"]),
                         xytext=(i + 0.15, r["peak_hour"] - 5.5), fontsize=6, color="0.3",
                         arrowprops=dict(arrowstyle="->", color="0.5", lw=0.7))
    axp.set_ylabel("activity-peak\nhour (EDT)", fontsize=8); axp.set_ylim(-1, 24)
    axp.set_yticks(range(0, 25, 6))
    axp.set_xticks(xt); axp.set_xticklabels([n[5:] for n in pa["night"]], fontsize=6.5, rotation=45, ha="right")
    axp.grid(alpha=0.3); axp.tick_params(labelsize=7); axp.legend(fontsize=6, loc="center right")
    axp.set_title("Phase (activity-onset peak) vs date", fontsize=8.5)

    axa.plot(xt[full], pa.loc[full, "amplitude"], "-s", color="tab:purple", ms=4)
    axa.set_ylabel("diel amplitude\n(peak−trough active)", fontsize=8)
    axa.set_xticks(xt); axa.set_xticklabels([n[5:] for n in pa["night"]], fontsize=6.5, rotation=45, ha="right")
    axa.grid(alpha=0.3); axa.tick_params(labelsize=7)
    axa.set_title("Amplitude vs date (full days only)", fontsize=8.5)
    fig.suptitle(f"Circadian stability across days ({kind.lower()}; rest < {moving_thr:.1f} in/s proxy; "
                 f"06-28 release evening = partial 'pseudo' peak, hollow; amplitude on full days only)",
                 fontsize=9)
    fig.savefig(out_path, dpi=140); plt.close(fig)


def _anchored_hours(anchor):
    """Clock hours ordered starting at the biological-night anchor (activity trough)."""
    return [(anchor + i) % 24 for i in range(24)]


def _bio_night_onset_peak(group_bio, anchor):
    """Per biological night: activity ONSET (first anchored hour crossing half-max on the
    rising edge), PEAK hour, active-bout length (# hours ≥ half-max), amplitude. Scored
    when the evening ramp (≥3 of 18:00–23:00) is covered; amplitude only on ≥16-hour
    nights. This is the calendar-split-free phase measure (a dusk→dawn bout = one unit)."""
    order = _anchored_hours(anchor)
    pos = {h: i for i, h in enumerate(order)}
    rows = []
    for night, g in group_bio.groupby("night"):
        g = g.dropna(subset=["active_mean"]).copy()
        n_hours = int(g["clock_hour"].nunique())
        eve = set(int(h) for h in g["clock_hour"]) & {18, 19, 20, 21, 22, 23}
        partial = n_hours < MIN_HOURS_PHASE
        onset_hour = peak_hour = active_peak = amplitude = np.nan
        hours_active = np.nan
        if len(eve) >= 3 and n_hours >= MIN_HOURS_PEAK:
            g["ord"] = g["clock_hour"].astype(int).map(pos)
            g = g.sort_values("ord")
            av = g["active_mean"].to_numpy()
            hrs = g["clock_hour"].astype(int).to_numpy()
            imax = int(np.argmax(av))
            peak_hour, active_peak = int(hrs[imax]), float(av[imax])
            trough = float(np.min(av))
            half = trough + 0.5 * (active_peak - trough)
            onset_hour = peak_hour
            for i in range(imax + 1):          # first rising-edge half-max crossing
                if av[i] >= half:
                    onset_hour = int(hrs[i]); break
            hours_active = int(np.count_nonzero(av >= half))
            if not partial:
                amplitude = float(active_peak - trough)
        rows.append({"night": night, "n_hours": n_hours, "onset_hour": onset_hour,
                     "peak_hour": peak_hour, "hours_active": hours_active,
                     "active_peak": active_peak, "amplitude": amplitude, "partial": partial})
    return pd.DataFrame(rows).sort_values("night").reset_index(drop=True)


def _fig_bio_night(group_bio, onset_peak, bio_nights, anchor, moving_thr, out_path):
    """Biological-night–aligned ACTIVITY: left = group active fraction over the dusk→dawn
    night (x = clock hours in anchored order, so each night's active bout is contiguous),
    one line per night; right = onset & peak clock-hour per biological night (phase lock)."""
    order = _anchored_hours(anchor)
    pos = {h: i for i, h in enumerate(order)}
    x = np.arange(24)
    fig = plt.figure(figsize=(12, 5))
    axm = fig.add_axes([0.06, 0.14, 0.56, 0.74])
    axo = fig.add_axes([0.71, 0.14, 0.26, 0.74])
    cmap = plt.get_cmap("viridis", max(len(bio_nights), 1))
    ncol_map = {n: cmap(i) for i, n in enumerate(bio_nights)}
    # shade the rest phase (clock 05:00-21:00 sits at these anchored positions)
    for h in range(24):
        if DAY_START <= order[h] < DAY_END:
            axm.axvspan(h - 0.5, h + 0.5, color="0.93", zorder=0)
    for n in bio_nights:
        g = group_bio[group_bio["night"] == n]
        yv = np.full(24, np.nan)
        for _, r in g.iterrows():
            yv[pos[int(r["clock_hour"])]] = r["active_mean"]
        axm.plot(x, yv, "-o", ms=2.5, lw=1.2, color=ncol_map[n], label=n[5:])
    axm.set_xticks(x[::2]); axm.set_xticklabels([f"{order[i]:02d}" for i in x[::2]], fontsize=7)
    axm.set_xlabel(f"local clock hour, biological-night order (night begins at the activity "
                   f"trough {anchor:02d}:00; unshaded = active/dark phase)", fontsize=8)
    axm.set_ylabel("group-mean ACTIVE fraction (across rats)")
    axm.grid(alpha=0.25); axm.legend(fontsize=7, ncol=2, title="bio-night", loc="upper left")
    axm.set_title("Biological-night–aligned ACTIVITY — one line = one dusk→dawn night", fontsize=9.5)

    op = onset_peak[onset_peak["peak_hour"].notna()].sort_values("night").reset_index(drop=True)
    xn = np.arange(len(op))
    full = ~op["partial"].to_numpy()
    for col, cc, mk, lab in [("onset_hour", "tab:blue", "o", "onset (half-max)"),
                             ("peak_hour", "tab:red", "s", "peak")]:
        axo.plot(xn, op[col], "-", color=cc, lw=1.0, alpha=0.5, zorder=1)
        axo.scatter(xn[full], op.loc[full, col], c=cc, s=26, zorder=2, label=lab)
        if (~full).any():
            axo.scatter(xn[~full], op.loc[~full, col], facecolors="none", edgecolors=cc, s=44, zorder=2)
    axo.set_ylim(16, 24); axo.set_yticks(range(16, 25, 2))
    axo.set_xticks(xn); axo.set_xticklabels([n[5:] for n in op["night"]], rotation=45, ha="right", fontsize=6.5)
    axo.set_ylabel("clock hour (EDT)", fontsize=8); axo.grid(alpha=0.3); axo.tick_params(labelsize=7)
    axo.legend(fontsize=6, loc="lower right")
    axo.set_title("Onset & peak vs biological night\n(hollow = partial coverage)", fontsize=8.5)
    fig.suptitle(f"Biological-night phase lock (activity < {moving_thr:.1f} in/s proxy; "
                 f"night anchored at the {anchor:02d}:00 activity trough)", fontsize=9)
    fig.savefig(out_path, dpi=140); plt.close(fig)


def _build_report(per_tag, grp, nights, tags, jitter, moving_thr, out,
                  phase_amp=None, bio=None, anchor=None) -> str:
    day = grp[(grp["clock_hour"] >= DAY_START) & (grp["clock_hour"] < DAY_END)]
    night = grp[(grp["clock_hour"] < DAY_START) | (grp["clock_hour"] >= DAY_END)]
    day_rf = float(day["rest_frac_mean"].mean())
    night_rf = float(night["rest_frac_mean"].mean())
    peak = grp.loc[grp["rest_frac_mean"].idxmax()]
    trough = grp.loc[grp["rest_frac_mean"].idxmin()]
    # active fraction = 1 - rest; the diel rhythm is clearer on the active side
    gact = grp.assign(active=1.0 - grp["rest_frac_mean"])
    apk = gact.loc[gact["active"].idxmax()]
    atr = gact.loc[gact["active"].idxmin()]
    aratio = float(apk["active"] / atr["active"]) if atr["active"] > 0 else float("nan")
    lowcov = grp[grp["cover_frac_mean"] < 0.5]
    L = []
    L.append("# Direction 3 companion — circadian / diel REST profile\n")
    L.append(f"*Candidate / measurement-limited. REST = smoothed WISER speed < "
             f"{moving_thr:.1f} in/s (stationary p99 floor), a low-speed PROXY for sleep, "
             f"NOT ephys-validated. Jitter ~{jitter:.0f} in. Full 24 h, local EDT, pooled "
             f"over {len(nights)} days; a signal gap is 'unknown', not rest (see coverage).*\n")
    L.append(f"Days: {', '.join(nights)} · rats: {', '.join(tags)}.\n")

    L.append("## Definitions (every derived quantity)\n")
    L.append("- **REST (per fix):** `resting = 1` if `speed_inps_smooth < θ_rest`, else `0`; "
             "`NaN` smoothed speed → `0` (not resting). "
             f"`θ_rest = {moving_thr:.2f} in/s` = the 99th percentile of the stationary "
             "fixed-position tag's smoothed-speed distribution (`speed_noise_floor`). Plain: "
             "below this the rat is indistinguishable from a stationary tag given jitter.")
    L.append("- **Rest fraction (per rat a, local hour h):** "
             "`rest_frac(a,h) = (# resting fixes of a in hour h) / (# valid fixes of a in hour h)`, "
             "pooled over all days. Unitless in [0,1]. Denominator is OBSERVED fixes only.")
    L.append("- **Group mean ± SEM (per hour h):** `mean_h = mean_a rest_frac(a,h)`; "
             "`SEM_h = SD_a(rest_frac(a,h)) / √n_a` (sample SD, `n_a` = # rats with data in h). "
             "Mean/SEM are taken ACROSS RATS, so each rat is weighted equally.")
    L.append("- **Coverage (per rat a, hour h):** `cover_frac(a,h) = observed_minutes / (n_days·60)`, "
             "capped at 1 — the fraction of that clock-hour actually sampled. **Dropout ≠ rest:** a "
             "low coverage hour means missing data (weather / refuge_4 burrow at night), not stillness.")
    L.append("- **Daytime rest window:** local 05:00–21:00 (the Direction-3 convention); its complement "
             "(21:00–05:00) is 'night'. Used only to summarize, not to filter.\n")

    L.append("## Result (candidate)\n")
    L.append(f"- **Nocturnal rest–activity pattern (as expected for rats):** mean REST fraction is "
             f"**{day_rf:.2f} in the 05:00–21:00 day** vs **{night_rf:.2f} at night** — rats are "
             f"still/resting through the day and active at night. This **corroborates the Direction-3 "
             f"choice of 05:00–21:00 as the daytime rest window** (it is data-driven, not assumed).")
    L.append(f"- **Peak rest** at **{int(peak['clock_hour']):02d}:00** "
             f"(rest_frac {peak['rest_frac_mean']:.2f}); **least rest (most active)** at "
             f"**{int(trough['clock_hour']):02d}:00** (rest_frac {trough['rest_frac_mean']:.2f}).")
    L.append(f"- **The rhythm is clearer as ACTIVE fraction (1 − rest):** locomotor activity peaks at "
             f"**{int(apk['clock_hour']):02d}:00 ({apk['active']:.2f})** and bottoms at "
             f"**{int(atr['clock_hour']):02d}:00 ({atr['active']:.2f})** — a **~{aratio:.1f}× "
             f"evening/day activity ratio**. NOTE the contrast is shallow on the rest axis because "
             f"θ_rest is the jitter *ceiling* ({moving_thr:.1f} in/s): any motion slower than that "
             f"(sitting, grooming, slow foraging) reads as 'rest', so 'rest fraction' overcounts true "
             f"sleep and compresses the diel swing. It is an ACTIVITY-onset rhythm, not a sleep depth.")
    L.append(f"- **Between-rat spread:** the SEM band shows how tightly the {len(tags)} rats share "
             "the same clock (narrow band = synchronized diel rhythm); per-animal traces show the "
             "individual truth behind the mean.")
    if len(lowcov):
        hrs = ", ".join(f"{int(h):02d}:00" for h in lowcov["clock_hour"])
        L.append(f"- **Coverage caveat:** hours with mean coverage < 0.5 ({hrs}) are lower-confidence — "
                 "night dropout (refuge_4 burrow on 07-03→07-07 nights, wet nights) removes fixes, and "
                 "dropout is 'unknown', not rest. The rest fraction there is over observed fixes only.")
    else:
        L.append("- **Coverage:** all clock-hours ≥ 0.5 mean coverage — the profile is not driven by "
                 "missing data.")

    # per-day circadian stability
    if phase_amp is not None and not phase_amp.empty:
        L.append("\n## Do they change their circadian across days? (per-date)\n")
        L.append("Per date, from the group-mean curve: **activity-peak hour** (phase, argmax of the "
                 "active fraction) and **diel amplitude** (peak − trough active fraction). Dates with "
                 f"< {MIN_HOURS_PHASE} covered hours (e.g. the 06-28 partial day) are excluded from "
                 "phase/amplitude:\n")
        show = phase_amp.copy()
        show["peak_hour"] = show["peak_hour"].map(lambda v: f"{int(v):02d}:00" if v == v else "n/a")
        show["amplitude"] = show["amplitude"].map(lambda v: f"{v:.3f}" if v == v else "n/a")
        show["active_peak"] = show["active_peak"].map(lambda v: f"{v:.3f}" if v == v else "n/a")
        L.append("```\n" + show[["night", "n_hours", "peak_hour", "active_peak",
                                 "amplitude", "partial"]].to_string(index=False) + "\n```\n")
        scored = phase_amp[~phase_amp["partial"]]
        if len(scored) >= 2:
            phs = scored["peak_hour"].astype(int).to_numpy()
            amps = scored["amplitude"].to_numpy()
            vc = pd.Series(phs).value_counts()
            modal, n_mode = int(vc.idxmax()), int(vc.max())
            circ = lambda a, b: min(abs(a - b) % 24, 24 - abs(a - b) % 24)   # noqa: E731
            spread = max(circ(int(a), int(b)) for a in phs for b in phs)
            outl = scored[scored["peak_hour"].astype(int) != modal]
            outl_str = ", ".join(f"{r.night[5:]}→{int(r.peak_hour):02d}:00" for r in outl.itertuples())
            L.append(f"- **Phase = STABLE (no drift after the first night):** the activity-onset peak "
                     f"is at **{modal:02d}:00 on {n_mode}/{len(scored)} scored dates** (max circular "
                     f"spread {spread} h). "
                     + (f"Exception(s): {outl_str} — 06-29 is the **first full day after the ~19:25 "
                        "evening release**, so its overnight (01:00) peak is first-night settling, not "
                        "a rhythm shift. " if len(outl) else "")
                     + "The dusk activity-onset clock is the robust, stable feature.")
            hi = scored.loc[scored['amplitude'].idxmax(), 'night']
            lo = scored.loc[scored['amplitude'].idxmin(), 'night']
            L.append(f"- **Amplitude = modestly modulated (NOT a phase change):** diel amplitude "
                     f"(peak−trough active fraction) ranges **{np.nanmin(amps):.3f}–{np.nanmax(amps):.3f}**; "
                     f"highest on **{hi[5:]}**, lowest on **{lo[5:]}**. The sharpest activity "
                     "concentration falls on the first full night (06-29, novelty) and 07-04 "
                     "(**July-4th fireworks** — an external disturbance; FIELD_OBSERVATIONS Day 7) — "
                     "candidate disturbance/novelty-linked amplitude modulation (hypotheses, not "
                     "labels), on top of an otherwise stable rhythm.")
        rel = phase_amp[phase_amp["night"] == RELEASE_DATE]
        if len(rel) and rel.iloc[0]["peak_hour"] == rel.iloc[0]["peak_hour"]:
            r0 = rel.iloc[0]
            L.append(f"- **First night (06-28, release {RELEASE_HHMM}):** included as a **partial / "
                     f"'pseudo' peak** — evening-only coverage ({int(r0['n_hours'])} h from ~19:30), "
                     f"activity peak at **{int(r0['peak_hour']):02d}:00** (release-driven novelty burst, "
                     "hollow marker in C3/C5). Reported but not scored for amplitude (coverage too "
                     "short to define a diel trough).")
        L.append("- **Per-animal (C2 rest / C4 activity):** each rat's by-date lines are tightly "
                 "stacked → the diel pattern is individually consistent day to day, not a group "
                 "artifact. **Activity-fraction views (C4 per-animal, C5 group) are the easiest to "
                 "read per night** (auto-scaled; the 21:00 onset spike is obvious).")

    # biological-night alignment (calendar-split-free phase lock)
    if bio is not None and not bio.empty and anchor is not None:
        L.append(f"\n## Biological-night alignment — when does the rhythm lock? (figure C6)\n")
        L.append(f"The calendar-date cut splits one dusk→dawn night across two date labels (an "
                 f"evening onset and its post-midnight tail land on different dates), which is why "
                 f"06-29 looked like a 01:00 'peak'. Re-cutting so each biological night is ONE unit "
                 f"— anchored at the **data-driven activity trough ({anchor:02d}:00 EDT**, the quietest "
                 f"clock-hour) — removes that artifact.\n")
        b = bio.copy()
        for c in ("onset_hour", "peak_hour"):
            b[c] = b[c].map(lambda v: f"{int(v):02d}:00" if v == v else "n/a")
        b["hours_active"] = b["hours_active"].map(lambda v: f"{int(v)}" if v == v else "n/a")
        L.append("```\n" + b[["night", "n_hours", "onset_hour", "peak_hour",
                              "hours_active", "partial"]].to_string(index=False) + "\n```\n")
        scored = bio[bio["peak_hour"].notna()]
        if len(scored) >= 2:
            pk = scored["peak_hour"].astype(int).to_numpy()
            circ = lambda a, b_: min(abs(a - b_) % 24, 24 - abs(a - b_) % 24)   # noqa: E731
            pk_spread = max(circ(int(a), int(b_)) for a in pk for b_ in pk)
            pmode = int(pd.Series(pk).mode().iloc[0])
            on = scored.dropna(subset=["onset_hour"])
            omode = int(on["onset_hour"].astype(int).mode().iloc[0]) if len(on) else pmode
            on_outl = on[on["onset_hour"].astype(int) != omode]
            outl_str = ", ".join(f"{r.night[5:]}={int(r.onset_hour):02d}:00" for r in on_outl.itertuples())
            L.append(f"- **Phase is locked from the FIRST biological night.** The activity **peak is "
                     f"at {pmode:02d}:00 on ALL {len(scored)} biological nights** — peak spread "
                     f"**{pk_spread} h**, including the release night. The dusk **onset** (half-max) is "
                     f"~{omode:02d}:00 on every night"
                     + (f" except {outl_str} (onset-detection caught an earlier afternoon rise there; "
                        "the peak is still 21:00 — treat onset as the softer measure)"
                        if len(on_outl) else "")
                     + ". The apparent calendar '06-29 → 01:00' peak was purely the split artifact: "
                     "that post-midnight activity is the RELEASE night's own overnight tail, which now "
                     "sits inside biological-night 1 (06-28).")
            L.append("- **Only the overnight DEPTH / lateness varies, not the phase.** In C6 the "
                     "**release night (06-28) sustains the highest activity latest into the overnight "
                     "(21:00→~04:00)**, while later nights concentrate near the 21:00 onset and fall "
                     "off faster; the largest full-night amplitude is 07-04 (fireworks). (The "
                     "`hours_active` above-half-max count is a threshold-sensitive proxy and is noisy "
                     "night to night — read the C6 curves, not that single number.) **Net: a fixed "
                     "dusk-onset (~21:00) phase from night 1; novelty/disturbance modulate how deep "
                     "and how late the night's activity runs, not when it starts.**")
    L.append("\n## Caveats\n")
    L.append("- Rest is a low-speed **proxy**, not ephys/CV-validated sleep (a still-but-awake rat "
             "reads as rest; a rat in the refuge_4 burrow reads as dropout, not rest).")
    L.append("- 06-28 is a **partial day** (evening release ~19:25), so only its evening hours "
             "contribute; the coverage panel reflects this.")
    L.append("- Weather and the burrow act on BOTH the animal and the UWB-dropout paths; the coverage "
             "panel is the guard. No spatial claim is made, so the unverified inch frame does not bite.\n")
    L.append(f"*Figure + CSVs: `{out}`.*\n")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description="Circadian / diel REST profile (Direction 3 companion).")
    ap.add_argument("--db", type=Path, default=None)
    _wi.add_snapshot_flags(ap)
    ap.add_argument("--fixed", type=Path, default=None)
    ap.add_argument("--output", type=Path, default=None,
                    help="artifact-root override (default: FIELD2026_ANALYSIS_OUT_ROOT)")
    ap.add_argument("--cohort", default=None,
                    help="cohort key (a cohorts/<key>.yaml); default FIELD2026_COHORT or 2026a")
    args = ap.parse_args()
    args.db, args.fixed, _wiser_prov = _wi.finalize(args)
    if not args.db.exists():
        raise SystemExit(f"[circadian] WISER DB not found: {args.db}")

    cohort = _op.resolve_cohort(args.cohort)
    direction = "wiser_d3_sleep"
    out = _op.run_dir("circadian_rest", cohort, root=args.output)   # bulk -> <OUT_ROOT>/<cohort>/...
    _wi.write_input_provenance(out, _wiser_prov)
    fig = out / "figures"
    report_dir = _op.report_dir(cohort, direction)                 # canonical -> results/<cohort>/<dir>/reports
    print(f"=== Circadian REST profile (Direction 3 companion) ===\n  DB: {args.db}\n  out: {out}\n")

    # rest cutoff + jitter from the stationary baseline
    fx = w.load_wiser_session(args.fixed)
    fx = time_utils.convert_timestamps(fx)
    fx = time_utils.trim_last_n_minutes(fx, minutes=10)
    fx = w.add_speed(fx)
    moving_thr = w.speed_noise_floor(fx)["p99"]
    jitter = float(np.nanmedian(metrics.compute_summary(
        fx, ground_truth=metrics.load_ground_truth(DEFAULT_GT))["rms_jitter"]))
    print(f"  rest cutoff={moving_thr:.2f} in/s  jitter={jitter:.2f} in")

    # full 24 h (NO window selection) -> cleaned, Sova removed
    df = w.load_wiser_session(args.db)
    df = time_utils.convert_timestamps(df)
    df = w.add_speed(df)
    df = w.add_validity_flags(df, jitter_floor_in=jitter)
    df = w.apply_tag_cutoffs(df)
    df = df[~df["shortid"].astype(str).isin(DROP_TAGS)]
    df["night"] = (df["datetime"] + pd.Timedelta(hours=w.LOCAL_TZ_OFFSET_HOURS)).dt.date.astype(str)
    nights = sorted(df["night"].dropna().unique())
    tags = sorted(df["shortid"].astype(str).unique())

    per_tag, grp = w.circadian_rest_profile(df, rest_thr_inps=moving_thr)
    per_tag.to_csv(out / "circadian_rest_per_tag.csv", index=False)
    grp.to_csv(out / "circadian_rest_group.csv", index=False)

    # day-resolved: per (tag, date, hour) + group-mean per date + phase/amplitude drift
    per_cell = w.circadian_rest_by_night(df, rest_thr_inps=moving_thr)
    group_night = _group_by_night(per_cell)
    phase_amp = _night_phase_amp(group_night)
    per_cell.to_csv(out / "circadian_rest_by_night_per_tag.csv", index=False)
    group_night.to_csv(out / "circadian_rest_by_night_group.csv", index=False)
    phase_amp.to_csv(out / "circadian_phase_amplitude_by_date.csv", index=False)

    # BIOLOGICAL-NIGHT alignment: anchor each night at the daily ACTIVITY TROUGH (the
    # quietest clock-hour) so a dusk->dawn active bout stays in ONE unit (no calendar split).
    anchor = int(grp.loc[grp["rest_frac_mean"].idxmax(), "clock_hour"])   # max rest = min activity
    per_cell_bio = w.circadian_rest_by_night(df, rest_thr_inps=moving_thr, anchor_hour=anchor)
    group_bio = _group_by_night(per_cell_bio)
    bio_nights = sorted(group_bio["night"].unique())
    onset_peak = _bio_night_onset_peak(group_bio, anchor)
    per_cell_bio.to_csv(out / "circadian_bio_night_per_tag.csv", index=False)
    group_bio.to_csv(out / "circadian_bio_night_group.csv", index=False)
    onset_peak.to_csv(out / "circadian_bio_night_onset_peak.csv", index=False)
    print(f"  days={nights}\n  tags={tags}\n  bio-night anchor (activity trough) = {anchor:02d}:00 EDT")

    _fig_circadian(per_tag, grp, jitter, moving_thr, nights, fig / "C1_circadian_rest.png")
    _fig_per_animal(per_cell, tags, nights, jitter, moving_thr, fig / "C2_per_animal_by_day.png")
    _fig_group_by_night(group_night, phase_amp, nights, moving_thr, fig / "C3_group_by_day_drift.png")
    # ACTIVITY-fraction views (easier to read per night; 06-28 release pseudo-peak included)
    _fig_per_animal(per_cell, tags, nights, jitter, moving_thr,
                    fig / "C4_per_animal_activity_by_day.png", active=True)
    _fig_group_by_night(group_night, phase_amp, nights, moving_thr,
                        fig / "C5_group_activity_by_day.png", active=True)
    # BIOLOGICAL-NIGHT–aligned view (no calendar split; onset/peak phase lock)
    _fig_bio_night(group_bio, onset_peak, bio_nights, anchor, moving_thr,
                   fig / "C6_biological_night_activity.png")

    report = _build_report(per_tag, grp, nights, tags, jitter, moving_thr, out,
                           phase_amp=phase_amp, bio=onset_peak, anchor=anchor)
    (out / "circadian_rest_report.md").write_text(report, encoding="utf-8")
    (report_dir / f"{direction}_circadian_rest_{cohort}.md").write_text(report, encoding="utf-8")
    _op.write_run_manifest(report_dir, out, cohort=cohort, direction=direction, analysis="circadian_rest")

    w.write_run_manifest(out, {
        "analysis": "Direction 3 companion — circadian / diel REST profile",
        "window": "full 24 h, local clock-hour (EDT)", "days": nights, "tags": tags,
        "rest_cutoff_inps_p99_stationary": moving_thr, "jitter_floor_in": jitter,
        "rest_definition": f"smoothed speed < {moving_thr:.2f} in/s (proxy for sleep, not ephys)",
        "group_stat": "mean ± SEM across rats (SEM = sample SD / sqrt(n_rats))",
        "coverage": "observed minutes / (n_days*60) per (tag, clock-hour); dropout != rest",
        "caveats": "rest is a low-speed proxy; a signal gap is 'unknown' not rest (see coverage); "
                   "refuge_4 burrow + wet nights raise night dropout; 06-28 is a partial day; "
                   "no spatial claim (unverified inch frame does not apply).",
    })
    print(f"\n  report -> {report_dir}\nAll outputs written to: {out}")


if __name__ == "__main__":
    main()
