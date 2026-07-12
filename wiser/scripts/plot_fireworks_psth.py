r"""
plot_fireworks_psth.py — illustrate the 07-04 fireworks -> following result: a stimulus-aligned
time-course (PSTH-style) of following-episode rate around the acoustically-defined fireworks window,
with the two camera mics (CH01+CH02) confirming the fireworks timing and the other-10-nights
matched-clock following as the control band. Saves a PNG for the scientific report.

    C:\Users\Cornell\anaconda3\python.exe scripts\plot_fireworks_psth.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import matplotlib.dates as mdates        # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
AUD = ROOT.parent / "audio/outputs"
FI = ROOT / "outputs/following_incidents_2026-06-28_to_2026-07-08"
FW_NIGHT = "2026-07-04"
GRID = 5           # min
X0, X1 = pd.Timestamp("2026-07-04 20:00"), pd.Timestamp("2026-07-04 23:30")
LEQ_THR = -50.0    # SUSTAINED level (leq) above this = fireworks-active bin (peaks are too transient)


def _audio(ch):
    """(peak per 5-min bin, leq per 5-min bin) for the transient volleys vs sustained-loud window."""
    f = AUD / f"audio_features_{ch}_2026-07-04.csv"
    if not f.exists():
        return None, None
    a = pd.read_csv(f)
    a["_t"] = pd.to_datetime(a["window_start_timestamp"])
    if "valid_audio" in a.columns:
        for c in ("peak_dbfs_relative", "leq_dbfs_relative"):
            a.loc[~a["valid_audio"].astype(bool), c] = np.nan
    a = a[(a["_t"] >= X0) & (a["_t"] <= X1)]
    g = a.groupby(a["_t"].dt.floor(f"{GRID}min"))
    return g["peak_dbfs_relative"].max(), g["leq_dbfs_relative"].mean()


def main():
    grid = pd.date_range(X0, X1, freq=f"{GRID}min")
    ep = pd.read_csv(FI / "strict_following_episodes.csv")
    ep["_t"] = pd.to_datetime(ep["t_start_local"])
    ep["night"] = ep["night"].astype(str)
    ep["clockbin"] = ep["_t"].dt.strftime("%H:%M")
    # minutes-since-21:00 clock key for matched between-night comparison
    ns = pd.to_datetime(ep["night"]) + pd.Timedelta(hours=21)
    ep["min_open"] = (ep["_t"] - ns).dt.total_seconds() / 60
    ep["gbin"] = (ep["min_open"] // GRID).astype("Int64")

    nights = sorted(ep["night"].unique())
    others = [n for n in nights if n != FW_NIGHT]
    # 07-04 count per clock bin (on the real 07-04 clock)
    e4 = ep[ep["night"] == FW_NIGHT]
    cnt4 = e4.groupby(e4["_t"].dt.floor(f"{GRID}min")).size().reindex(grid).fillna(0)
    # other nights: count per gbin (minutes-since-21:00) -> map to 07-04 clock
    gbin_of = {t: int((t - pd.Timestamp("2026-07-04 21:00")).total_seconds() // 60 // GRID) for t in grid}
    om = {}
    for n in others:
        en = ep[ep["night"] == n]
        om[n] = en.groupby("gbin").size()
    ctrl_mean, ctrl_sd = [], []
    for t in grid:
        gb = gbin_of[t]
        vals = np.array([om[n].get(gb, 0) for n in others], float)
        ctrl_mean.append(vals.mean()); ctrl_sd.append(vals.std(ddof=1))
    ctrl_mean = np.array(ctrl_mean); ctrl_sd = np.array(ctrl_sd)

    p1, l1 = _audio("CH01"); p2, l2 = _audio("CH02")
    a1 = p1.reindex(grid) if p1 is not None else None
    a2 = p2.reindex(grid) if p2 is not None else None
    l1 = l1.reindex(grid) if l1 is not None else None
    l2 = l2.reindex(grid) if l2 is not None else None
    # fireworks-active window = the LONGEST contiguous run where either mic SUSTAINED level (leq) >
    # LEQ_THR (single-bin dips between volleys filled), so isolated pre-fireworks blips are excluded.
    loud = np.zeros(len(grid), bool)
    for lq in (l1, l2):
        if lq is not None:
            loud |= (lq.to_numpy() > LEQ_THR)
    filled = loud.copy()
    for i in range(1, len(loud) - 1):
        if not loud[i] and loud[i - 1] and loud[i + 1]:
            filled[i] = True
    best_lo = best_hi = None; best_len = 0; i = 0
    while i < len(filled):
        if filled[i]:
            j = i
            while j < len(filled) and filled[j]:
                j += 1
            if j - i > best_len:
                best_len = j - i; best_lo, best_hi = i, j - 1
            i = j
        else:
            i += 1
    fw_lo, fw_hi = (grid[best_lo], grid[best_hi]) if best_lo is not None else (None, None)

    fig, (axA, axB) = plt.subplots(2, 1, figsize=(11, 7.2), sharex=True,
                                   gridspec_kw={"height_ratios": [1, 1.25], "hspace": 0.08})
    # shade fireworks window in both
    for ax in (axA, axB):
        if fw_lo is not None:
            ax.axvspan(fw_lo, fw_hi, color="#ffd27f", alpha=0.35, lw=0, zorder=0)

    # Panel A: audio
    if a1 is not None:
        axA.plot(grid, a1.to_numpy(), color="#1f77b4", lw=1.6, marker="o", ms=3, label="CH01 mic peak")
    if a2 is not None:
        axA.plot(grid, a2.to_numpy(), color="#17becf", lw=1.4, marker="s", ms=3, alpha=0.8, label="CH02 mic peak")
    axA.set_ylabel("audio peak\n(rel. dBFS)")
    axA.legend(loc="upper right", fontsize=8, framealpha=0.9)
    axA.set_title("July-4 fireworks → following: acoustically time-locked co-movement bursts (07-04, 11-night pilot)",
                  fontsize=11, fontweight="bold")
    axA.text(0.01, 0.95, "A  Fireworks (both camera mics)", transform=axA.transAxes,
             va="top", fontsize=9, fontweight="bold")

    # Panel B: following
    axB.fill_between(grid, ctrl_mean - ctrl_sd, ctrl_mean + ctrl_sd, color="#bbbbbb", alpha=0.45,
                     lw=0, label="other 10 nights, same clock (mean±SD)")
    axB.plot(grid, ctrl_mean, color="#666", lw=1.2, ls="--")
    axB.bar(grid, cnt4.to_numpy(), width=pd.Timedelta(minutes=GRID) * 0.85, color="#d62728",
            alpha=0.85, label="07-04 following episodes / 5 min", zorder=3)
    # annotate the two bursts
    for clock, txt in [("21:35", "burst 1\n(z=2.4)"), ("22:20", "burst 2\n(z=5.2)")]:
        tb = pd.Timestamp(f"2026-07-04 {clock}")
        y = cnt4.reindex([tb.floor(f"{GRID}min")]).fillna(0).iloc[0]
        axB.annotate(txt, xy=(tb, y), xytext=(tb, y + 6), fontsize=8, ha="center", color="#a01010",
                     arrowprops=dict(arrowstyle="->", color="#a01010", lw=1))
    axB.set_ylabel("following episodes\nper 5 min")
    axB.set_xlabel("clock time (EDT), 2026-07-04")
    axB.legend(loc="upper right", fontsize=8, framealpha=0.9)
    axB.text(0.01, 0.95, "B  Coordinated following (WISER)", transform=axB.transAxes,
             va="top", fontsize=9, fontweight="bold")
    axB.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    axB.xaxis.set_major_locator(mdates.MinuteLocator(interval=30))
    axB.set_xlim(X0, X1)

    fig.text(0.012, 0.012,
             "Shaded = fireworks-active window (either mic sustained level leq > −50 dBFS-rel). Following bursts coincide with the "
             "acoustic peak (lag≈0, r≈0.34–0.37) and exceed the matched-clock control. Audio = relative dBFS (not SPL); camera↔WISER "
             "clock unverified; timing coincidence does NOT distinguish social following from startle co-flight (video pending). n=1 night.",
             fontsize=6.5, color="#444", wrap=True)
    fig.subplots_adjust(left=0.09, right=0.985, top=0.925, bottom=0.11)
    (FI / "plots").mkdir(exist_ok=True)
    outpng = FI / "plots" / "fireworks_following_audio_psth.png"
    fig.savefig(outpng, dpi=150)
    print(f"fireworks-active window: {fw_lo} .. {fw_hi}")
    print(f"07-04 following in fireworks window: {int(cnt4[(grid>=fw_lo)&(grid<=fw_hi)].sum()) if fw_lo is not None else 'NA'}")
    print(f"saved -> {outpng}")


if __name__ == "__main__":
    main()
