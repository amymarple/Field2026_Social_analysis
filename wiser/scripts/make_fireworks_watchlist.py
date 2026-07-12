r"""
make_fireworks_watchlist.py — focused video watch-list for the 07-04 following BURSTS (the acoustically
confirmed fireworks windows), so the following-vs-startle-co-flight construct can be checked on camera.
Filters the Phase-B2 `strict_following_video_queue.csv` to 07-04 and the two burst windows, tags each
episode by burst, and sorts by camera-routing confidence -> duration. NO new detection.

    C:\Users\Cornell\anaconda3\python.exe scripts\make_fireworks_watchlist.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
BURSTS = [("burst1_2125_2150", "2026-07-04 21:25", "2026-07-04 21:50"),
          ("burst2_2215_2230", "2026-07-04 22:15", "2026-07-04 22:30")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", type=Path,
                    default=ROOT / "outputs/following_incidents_2026-06-28_to_2026-07-08/strict_following_video_queue.csv")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "outputs/following_incidents_2026-06-28_to_2026-07-08/fireworks_0704_video_watchlist.csv")
    ap.add_argument("--top-per-burst", type=int, default=12)
    args = ap.parse_args()

    q = pd.read_csv(args.queue)
    q["t"] = pd.to_datetime(q["t_start_local"])
    rows = []
    for name, lo, hi in BURSTS:
        b = q[(q["t"] >= pd.Timestamp(lo)) & (q["t"] < pd.Timestamp(hi))].copy()
        b["burst"] = name
        rows.append(b)
    wl = pd.concat(rows, ignore_index=True)
    wl = wl.sort_values(["burst", "route_confidence", "duration_s"], ascending=[True, False, False])

    keep = ["burst", "t_start_local", "duration_s", "leader_name", "follower_name", "median_lag_s",
            "mean_sep_in", "mean_cos", "channel_rank_1", "channel_rank_2", "route_confidence", "near_boundary"]
    wl = wl[[c for c in keep if c in wl.columns]]
    wl.to_csv(args.out, index=False)

    # compact prioritized subset + per-channel summary
    print(f"07-04 burst-window episodes: {len(wl)} total")
    for name, lo, hi in BURSTS:
        bb = wl[wl["burst"] == name]
        chans = bb["channel_rank_1"].value_counts().to_dict()
        print(f"\n=== {name} ({lo[11:]}-{hi[11:]}): {len(bb)} episodes | channels {chans} ===")
        top = bb.head(args.top_per_burst)
        for _, r in top.iterrows():
            print(f"  {r['t_start_local'][11:19]}  {r['leader_name']:>7}->{r['follower_name']:<7} "
                  f"{r['duration_s']:>4.0f}s  sep {r['mean_sep_in']:>4.0f}in cos {r['mean_cos']:.2f} lag {r['median_lag_s']:.0f}s "
                  f"| {r['channel_rank_1']} conf {r['route_confidence']:.2f}{' (boundary)' if r.get('near_boundary') else ''}")
    print(f"\ndone -> {args.out}")


if __name__ == "__main__":
    main()
