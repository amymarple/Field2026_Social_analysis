r"""
analyze_fireworks_timecourse.py — TIME-RESOLVED test of the 07-04 fireworks → increased-following
observation. A whole-night average is n=1; the fireworks are a TIME-LOCALIZED event (~21:00 EDT), so
bin the night into 10-min windows and (a) trace 07-04's within-night following time-course, and (b)
compare 07-04's fireworks WINDOW against the SAME clock window on the other 10 nights (n=10 controls —
matching clock time partly controls circadian movement level). No detector rebuild; reads the Phase-B2
`strict_following_episodes.csv` (per-episode local start times).

Metric: following-episode COUNT per 10-min bin per night (movement-normalization not available at this
resolution — matched-clock between-night comparison is the control; see caveats). Fireworks window =
the first hour of the night (21:00-22:00 EDT), per the field note "~21:00" (exact timing NOT logged).

    set KMP_DUPLICATE_LIB_OK=TRUE
    C:\Users\Cornell\anaconda3\python.exe scripts\analyze_fireworks_timecourse.py
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
FW_NIGHT = "2026-07-04"
NIGHT_START_H = 21          # local night window opens 21:00 EDT
BIN_MIN = 10
FW_WINDOW_MIN = (0, 60)     # first hour = 21:00-22:00 (the "~21:00" fireworks window)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=Path,
                    default=ROOT / "outputs/following_incidents_2026-06-28_to_2026-07-08/strict_following_episodes.csv")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "outputs/following_incidents_2026-06-28_to_2026-07-08")
    ap.add_argument("--bin-min", type=int, default=BIN_MIN)
    ap.add_argument("--fw-window-min", type=int, nargs=2, default=list(FW_WINDOW_MIN))
    args = ap.parse_args()

    ep = pd.read_csv(args.episodes)
    ep["night"] = ep["night"].astype(str)
    ep["_t"] = pd.to_datetime(ep["t_start_local"])
    # minutes since that night's 21:00 (episodes after midnight land at >180 min, still their night)
    night_start = pd.to_datetime(ep["night"]) + pd.Timedelta(hours=NIGHT_START_H)
    ep["min_since_open"] = (ep["_t"] - night_start).dt.total_seconds() / 60.0
    ep = ep[(ep["min_since_open"] >= 0) & (ep["min_since_open"] < 480)].copy()
    ep["bin"] = (ep["min_since_open"] // args.bin_min).astype(int)

    nights = sorted(ep["night"].unique())
    n_bins = 480 // args.bin_min
    # count matrix: night x bin
    M = pd.DataFrame(0, index=nights, columns=range(n_bins))
    for (nn, b), g in ep.groupby(["night", "bin"]):
        if b < n_bins:
            M.loc[nn, b] = len(g)

    fw_lo, fw_hi = args.fw_window_min[0] // args.bin_min, args.fw_window_min[1] // args.bin_min
    others = [n for n in nights if n != FW_NIGHT]

    # (b) between-night matched-clock: fireworks WINDOW total, 07-04 vs the other 10 nights
    win_counts = M.iloc[:, fw_lo:fw_hi].sum(axis=1)
    fw_win = float(win_counts.loc[FW_NIGHT])
    ctrl = win_counts.loc[others].to_numpy(float)
    z_win = (fw_win - ctrl.mean()) / ctrl.std(ddof=1) if ctrl.std(ddof=1) > 0 else np.nan
    pct = float((ctrl < fw_win).mean())          # fraction of control nights below 07-04
    rank = int((win_counts.rank(ascending=False).loc[FW_NIGHT]))

    # per-bin z across the first 2 hours (the time-course of how much of an outlier 07-04 is)
    tc = []
    for b in range(0, min(12, n_bins)):
        c = M.loc[others, b].to_numpy(float)
        z = (M.loc[FW_NIGHT, b] - c.mean()) / c.std(ddof=1) if c.std(ddof=1) > 0 else np.nan
        tc.append({"bin": b, "clock": f"{(NIGHT_START_H + (b*args.bin_min)//60) % 24:02d}:{(b*args.bin_min) % 60:02d}",
                   "n0704": int(M.loc[FW_NIGHT, b]), "ctrl_mean": round(float(c.mean()), 2),
                   "ctrl_sd": round(float(c.std(ddof=1)), 2), "z": round(float(z), 2) if z == z else None})

    # (a) within-night 07-04: first-hour rate vs rest-of-night rate (per 10-min bin)
    fw_bins = M.loc[FW_NIGHT, fw_lo:fw_hi]
    rest_bins = M.loc[FW_NIGHT, fw_hi:]
    within = {"fw_window_per_bin": round(float(fw_bins.mean()), 2),
              "rest_of_night_per_bin": round(float(rest_bins.mean()), 2),
              "ratio": round(float(fw_bins.mean() / rest_bins.mean()), 2) if rest_bins.mean() else None}
    # same within-night ratio for the CONTROL nights (does every night have an early bump, or only 07-04?)
    ctrl_ratios = []
    for n in others:
        fwn = M.loc[n, fw_lo:fw_hi].mean(); rn = M.loc[n, fw_hi:].mean()
        if rn > 0:
            ctrl_ratios.append(fwn / rn)
    within["ctrl_within_night_ratio_mean"] = round(float(np.mean(ctrl_ratios)), 2)
    within["z_of_0704_ratio_vs_ctrl"] = (round((within["ratio"] - np.mean(ctrl_ratios)) / np.std(ctrl_ratios, ddof=1), 2)
                                         if np.std(ctrl_ratios, ddof=1) > 0 else None)

    R = {"generated_utc": datetime.datetime.utcnow().isoformat(),
         "bin_min": args.bin_min, "fw_window_min": args.fw_window_min,
         "fireworks_window_between_night": {
             "n0704_episodes_in_window": fw_win, "ctrl_nights": len(others),
             "ctrl_mean": round(float(ctrl.mean()), 2), "ctrl_sd": round(float(ctrl.std(ddof=1)), 2),
             "z": round(float(z_win), 2) if z_win == z_win else None,
             "percentile_over_ctrl": round(pct, 3), "rank_of_11_nights": rank},
         "within_0704": within, "time_course_first_2h": tc}
    R["verdict"] = _verdict(R)
    (args.out / "fireworks_timecourse_results.json").write_text(json.dumps(R, indent=2, default=str), encoding="utf-8")
    M.to_csv(args.out / "following_by_night_and_10min_bin.csv")

    print(f"[between-night] fireworks window (21:00-22:00), 07-04 = {fw_win:.0f} episodes vs "
          f"other {len(others)} nights {ctrl.mean():.1f}±{ctrl.std(ddof=1):.1f} -> z={z_win:+.2f}, "
          f"rank {rank}/11, above {pct:.0%} of control nights")
    print(f"[within 07-04] first-hour {within['fw_window_per_bin']}/bin vs rest {within['rest_of_night_per_bin']}/bin "
          f"= {within['ratio']}x (control nights' early bump {within['ctrl_within_night_ratio_mean']}x; "
          f"07-04 ratio z vs ctrl = {within['z_of_0704_ratio_vs_ctrl']})")
    print("[time-course first 2h] (bin z = 07-04 vs other nights at that clock):")
    for r in tc:
        bar = "#" * max(0, int((r["z"] or 0) * 3))
        print(f"    {r['clock']}  n0704={r['n0704']:>3}  ctrl={r['ctrl_mean']:>5}±{r['ctrl_sd']:>4}  z={r['z']:+.2f} {bar}")
    print(f"\n[verdict] {R['verdict']}")
    _write_report(args.out, R)
    print(f"done -> {args.out}")


def _verdict(R):
    bt = R["fireworks_window_between_night"]; w = R["within_0704"]
    strong = (bt["z"] or 0) >= 2 and (bt["percentile_over_ctrl"] or 0) >= 0.9
    peaked = (w["z_of_0704_ratio_vs_ctrl"] or 0) >= 1.5
    head = (f"Splitting the night into {R['bin_min']}-min bins DOES give real n for the between-night test: "
            f"in the 21:00-22:00 fireworks window 07-04 had {bt['n0704_episodes_in_window']:.0f} following "
            f"episodes vs {bt['ctrl_mean']}±{bt['ctrl_sd']} on the other {bt['ctrl_nights']} nights "
            f"(z={bt['z']}, rank {bt['rank_of_11_nights']}/11, above {bt['percentile_over_ctrl']:.0%} of them).")
    if strong:
        body = (" So the fireworks-window following is a genuine between-night OUTLIER, and the "
                f"{'within-night early peak is also unusual (ratio-z ' + str(w['z_of_0704_ratio_vs_ctrl']) + ') — a time-localized spike' if peaked else 'within-night early peak is NOT unusual (every night bumps early), so the effect is a raised LEVEL, not a fireworks-time spike'}.")
    elif (bt["z"] or 0) >= 1:
        body = (" So 07-04's fireworks-window following is ELEVATED but not a clean outlier (z~1-2) at "
                "n=10 controls — consistent with the observation, still not decisive.")
    else:
        body = (" So the fireworks window is NOT a between-night outlier — the whole-night elevation is "
                "not localized to the ~21:00 fireworks time.")
    tail = (" CAVEATS unchanged: episode count is not movement-normalized (matched clock only partly "
            "controls it); fireworks time is approximate (~21:00, not logged), so the window may be "
            "mis-set; startle co-flight to shelter would also raise this count and is not the same "
            "construct as social following (the observer noted it did NOT look like simple escape); "
            "07-04 is also a burrow night. Mechanism still needs the video (B2 queue).")
    return head + body + tail


def _write_report(out, R):
    bt = R["fireworks_window_between_night"]; w = R["within_0704"]
    tc = pd.DataFrame(R["time_course_first_2h"])
    md = (f"# Fireworks (07-04) following — time-resolved test\n\n"
          f"**Status:** ⚠️ candidate. Addresses the n=1 limit by binning the night into "
          f"{R['bin_min']}-min windows: the fireworks are time-localized (~21:00 EDT), so 07-04's "
          f"fireworks WINDOW is compared to the SAME clock window on the other 10 nights (n=10 controls). "
          f"Reads Phase-B2 `strict_following_episodes.csv`. Generated {R['generated_utc']}.\n\n"
          f"## Between-night matched-clock test (the real-n test)\n\n"
          f"21:00-22:00 window: 07-04 = **{bt['n0704_episodes_in_window']:.0f}** episodes vs other "
          f"{bt['ctrl_nights']} nights **{bt['ctrl_mean']}±{bt['ctrl_sd']}** → **z = {bt['z']}**, "
          f"rank **{bt['rank_of_11_nights']}/11**, above **{bt['percentile_over_ctrl']:.0%}** of control nights.\n\n"
          f"## Within-07-04 time-course (is it a spike or a raised level?)\n\n"
          f"First-hour {w['fw_window_per_bin']}/bin vs rest-of-night {w['rest_of_night_per_bin']}/bin = "
          f"**{w['ratio']}x**. Control nights' own early bump = {w['ctrl_within_night_ratio_mean']}x, so "
          f"07-04's early concentration is z={w['z_of_0704_ratio_vs_ctrl']} vs controls "
          f"(>~1.5 ⇒ a genuine fireworks-time spike; ~0 ⇒ just the normal early-night bump).\n\n"
          f"### Per-10-min-bin z, first 2 h (07-04 vs other nights at each clock)\n\n"
          + tc[["clock", "n0704", "ctrl_mean", "ctrl_sd", "z"]].to_markdown(index=False) + "\n\n"
          f"## Verdict\n\n{R['verdict']}\n\n"
          f"## Definitions\n\n"
          f"- **following-episode count per 10-min bin** — # of Phase-B2 strict lagged-following episodes "
          f"whose `t_start_local` falls in the bin. NOT movement-normalized at this resolution.\n"
          f"- **between-night z** — (07-04 window count − mean of other nights' same-clock window) / their SD "
          f"(n=10 controls).\n"
          f"- **within-night ratio** — first-hour mean per-bin count ÷ rest-of-night mean per-bin count; "
          f"z-scored against the other nights' own ratios to ask whether 07-04 concentrates MORE early than "
          f"a typical night.\n\n"
          f"## Scope\n\nFireworks time approximate (~21:00, exact NOT logged) — window may be mis-set. "
          f"Episode count not movement-normalized (matched clock partly controls it). Startle co-flight ≠ "
          f"social following (construct). 07-04 also a burrow night. Frame UNVERIFIED. Video (B2 queue) "
          f"remains the mechanism check.\n")
    (out / "fireworks_timecourse_report.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
