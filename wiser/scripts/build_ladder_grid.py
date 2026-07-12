r"""
build_ladder_grid.py — build decision tables for the hysteretic sensitivity grid (run in `cv`).

Loads + cleans the 8 nights ONCE, then for each (buffer, exit) segmentation builds the visits
(jitter-tolerant hysteretic ROI state) once, the destination table once, and the leaving-hazard
table at each requested epoch — writing one config subdir per (buffer, exit, epoch) under
`outputs/.../grid/`. The identifiability ladder (analyze_policy_identifiability.py) is then run
per subdir and the verdicts aggregated (robustness, not a cherry-picked threshold).

Bounded grid (user-chosen): buffer{7,14,21}×exit{30,60}s at epoch 15 s (buffer/exit robustness)
+ buf14_exit30 at epochs {5,15,30}s (epoch robustness).

    conda activate cv
    cd wiser
    python scripts/build_ladder_grid.py --max-nights 2      # smoke
    python scripts/build_ladder_grid.py                      # all 8 nights
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import wiser_analysis_utils as w                     # noqa: E402
import time_utils                                    # noqa: E402
import trajectory_stereotypy as ts                   # noqa: E402
import semimarkov_decisions as smd                   # noqa: E402
import weather_context as wc                         # noqa: E402
from environment_map import EnvironmentMap           # noqa: E402

DEFAULT_INCR = Path(r"D:\Reolink_record\audio_in\Wiser_backup\incremental")
DEFAULT_WEATHER = Path(r"D:\Reolink_record\audio_in\weather_data")
NIGHTS = [f"2026-06-{d}" for d in (28, 29, 30)] + [f"2026-07-0{d}" for d in (1, 2, 3, 4, 5)]
JITTER = 7.0
# (buffer_in, exit_s) segmentations and the epochs to build each at
SEGMENTS = {
    (7.0, 30.0): [15.0], (14.0, 30.0): [5.0, 15.0, 30.0], (14.0, 60.0): [15.0],
    (21.0, 30.0): [15.0], (7.0, 60.0): [15.0], (21.0, 60.0): [15.0],
}
KEEP = ["shortid", "night", "datetime", "x", "y", "roi", "valid", "gap_flag", "moving"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--incremental-dir", type=Path, default=DEFAULT_INCR)
    ap.add_argument("--weather-dir", type=Path, default=DEFAULT_WEATHER)
    ap.add_argument("--env-map", type=Path, default=ROOT / "configs/environment_map/2026-06-28_to_2026-07-05.yaml")
    ap.add_argument("--rois", type=Path, default=ROOT / "configs/wiser_rois.json")
    ap.add_argument("--out", type=Path, default=ROOT / "outputs/policy_identifiability_2026-06-28_to_2026-07-06/grid")
    ap.add_argument("--nights", nargs="*", default=NIGHTS)
    ap.add_argument("--max-nights", type=int, default=None)
    args = ap.parse_args()
    nights = list(args.nights)[: args.max_nights] if args.max_nights else list(args.nights)
    args.out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    prog = open(args.out / "_grid_progress.log", "w", buffering=1)

    def plog(m):
        line = f"[{time.time()-t0:6.1f}s] {m}"
        print(line, flush=True); prog.write(line + "\n"); prog.flush()

    roi_cfg = w.load_rois(args.rois)
    em = EnvironmentMap.from_paths(args.env_map, args.rois)
    plog(f"load nights {nights[0]}..{nights[-1]}")
    load_dates = sorted(set(nights) | {str((pd.Timestamp(nights[-1]) + pd.Timedelta(days=1)).date())})
    df, _ = ts.load_incremental_days(args.incremental_dir, dates=load_dates)
    df = time_utils.convert_timestamps(df)
    df = ts.add_night_label(df)
    df = df[df["in_night"] & df["night"].isin([str(n) for n in nights])].copy()
    df = w.add_speed(df)
    df = w.add_validity_flags(df, boundary=roi_cfg.get("boundary"), jitter_floor_in=JITTER)
    df = w.apply_tag_cutoffs(df)
    win = df[df["valid"].astype(bool)].copy()
    win["shortid"] = win["shortid"].astype(str)
    win["moving"] = pd.to_numeric(win.get("speed_inps_smooth"), errors="coerce") > 12.0
    win = w.assign_roi(win, roi_cfg)                       # 'roi' present (build_leave_table needs KEEP cols)
    plog(f"cleaned valid {len(win):,}; building social grid + weather")
    social_grid = smd.build_social_grid(win, bin_s=1.0)
    wx = wc.load_weather_features(sorted(str(p) for p in Path(args.weather_dir).glob("AWN-*.csv")))

    manifest = []
    for (buf, ex), epochs in SEGMENTS.items():
        plog(f"segment hyst buf{int(buf)} exit{int(ex)}")
        vv = [smd.hysteretic_visits(g, roi_cfg, em, buffer_in=buf, bin_s=5.0, enter_s=10.0,
                                    exit_s=ex, flicker_merge_s=30.0)
              for _, g in win.groupby(["night", "shortid"])]
        visits = pd.concat([v for v in vv if not v.empty], ignore_index=True) if vv else pd.DataFrame()
        dest = smd.build_destination_table(visits, em)
        if not dest.empty:
            dest = smd.add_pre_decision_social(dest, social_grid, time_col="t_dep", window_s=10.0)
            dest = wc.attach_weather(dest, wx, time_col="t_dep", tol_minutes=15)
        for ep in epochs:
            tag = f"buf{int(buf)}_exit{int(ex)}_ep{int(ep)}"
            d = args.out / tag
            d.mkdir(parents=True, exist_ok=True)
            leave = smd.build_leave_table(visits, win[KEEP], em, epoch_s=ep)
            if not leave.empty:
                leave = smd.add_pre_decision_social(leave, social_grid, time_col="t_epoch", window_s=10.0)
                leave = wc.attach_weather(leave, wx, time_col="t_epoch", tol_minutes=15)
            leave.to_csv(d / "leave_decisions.csv", index=False)
            dest.to_csv(d / "destination_decisions.csv", index=False)
            visits.to_csv(d / "visits.csv", index=False)
            manifest.append({"config": tag, "buffer_in": buf, "exit_s": ex, "epoch_s": ep,
                             "n_leave": int(len(leave)), "n_dest": int(len(dest)),
                             "n_visits": int(len(visits))})
            plog(f"  {tag}: leave={len(leave)} dest={len(dest)}")

    (args.out / "grid_manifest.json").write_text(json.dumps(
        {"segmentation": "hysteretic_roi_state", "jitter_floor_in": JITTER, "nights": nights,
         "configs": manifest}, indent=2), encoding="utf-8")
    plog(f"done -> {args.out} ({len(manifest)} configs)")


if __name__ == "__main__":
    main()
