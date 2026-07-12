r"""
build_locomotor_states.py — Phase 1 / Module 3 Stage-0 builder.

Loads the same cleaned WISER stream as the module-5 leaving-hazard builder (via the shared
``build_decision_tables.load_clean_stream``), runs the unified locomotor state machine, and writes:
  * ``locomotor_state_stream.csv``   — per-bin unified state (rest/local_active/transit/pause/unknown);
  * ``rest_episodes.csv``            — settled-residence episodes + how each ended (onset / censored);
  * ``bouts.csv``                    — locomotor bouts + in_place/relocating labels (module-4 substrate);
  * ``initiation_decisions.csv``     — the bout-INITIATION at-risk table (one row per at-risk rest epoch,
                                       ``initiated`` = 1 on an onset), with strictly pre-decision social
                                       + weather attached — the input to the hazard ladder;
  * ``state_occupancy.csv`` / ``distinction_diagnostics.json`` — support + measurement-gate evidence;
  * ``run_manifest.json``.

Frame-invariant, inch frame UNVERIFIED; onset is speed-onset ABOVE the ~7 in jitter floor (a LOWER
bound; in-nest sub-jitter stirring is invisible — never 'wake'); gaps stay 'unknown'; below-plane
dropout ROIs (refuge_4 burrow nights) excluded. Modeling runs in analyze_locomotor_initiation.py.

    conda activate cv   # or the anaconda3 interpreter (no GPU/torch needed)
    cd wiser
    python scripts/build_locomotor_states.py --max-nights 2      # smoke
    python scripts/build_locomotor_states.py                      # all 8 nights (matches module 5)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time as _time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))       # for build_decision_tables

import locomotor_states as ls                                  # noqa: E402
import weather_context as wc                                   # noqa: E402
from build_decision_tables import (load_clean_stream, DEFAULT_INCR, DEFAULT_WEATHER,  # noqa: E402
                                   NIGHTS, MOVING_THR_INPS, JITTER_FLOOR_IN)

# state-machine parameters (mirror the selftest; the module-5 substrate uses the same buffer/enter/exit)
STATE_KWARGS = dict(buffer_in=14.0, bin_s=5.0, roi_enter_s=10.0, roi_exit_s=30.0,
                    move_thr_inps=MOVING_THR_INPS, move_enter_s=10.0, move_exit_s=10.0,
                    move_near_frac=0.5, move_far_frac=0.2, near_frac=0.5, far_frac=0.2,
                    flicker_merge_s=30.0, long_gap_s=120.0)


def _git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT)).decode().strip()
    except Exception:
        return "unknown"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--incremental-dir", type=Path, default=DEFAULT_INCR)
    ap.add_argument("--weather-dir", type=Path, default=DEFAULT_WEATHER)
    ap.add_argument("--env-map", type=Path,
                    default=ROOT / "configs/environment_map/2026-06-28_to_2026-07-08.yaml")
    ap.add_argument("--rois", type=Path, default=ROOT / "configs/wiser_rois.json")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "outputs/locomotor_initiation_2026-06-28_to_2026-07-08")
    ap.add_argument("--nights", nargs="*", default=NIGHTS)
    ap.add_argument("--max-nights", type=int, default=None)
    ap.add_argument("--epoch-s", type=float, default=5.0)
    ap.add_argument("--bin-s", type=float, default=5.0)
    ap.add_argument("--social-window-s", type=float, default=10.0)
    args = ap.parse_args()

    nights = list(args.nights)[: args.max_nights] if args.max_nights else list(args.nights)
    args.out.mkdir(parents=True, exist_ok=True)
    _t0 = _time.time()
    _prog = open(args.out / "_progress.log", "w", buffering=1)

    def plog(msg):
        line = f"[{_time.time() - _t0:6.1f}s] {msg}"
        print(line, flush=True); _prog.write(line + "\n"); _prog.flush()

    plog(f"[1/4] load + clean + ROI + weather for nights {nights[0]}..{nights[-1]}")
    S = load_clean_stream(args.incremental_dir, args.weather_dir, args.env_map, args.rois,
                          nights, plog=plog)
    win, em, wx, roi_cfg = S["win"], S["em"], S["wx"], S["roi_cfg"]

    plog("[2/4] locomotor state machine + initiation at-risk table")
    keep = ["shortid", "night", "datetime", "x", "y", "gap_flag", "moving", "speed_inps_smooth"]
    keep = [c for c in keep if c in win.columns]
    stream, stat_eps, bouts, init, diag, occ = ls.build_locomotor_tables(
        win[keep], roi_cfg, em, bin_s=args.bin_s, epoch_s=args.epoch_s, add_social=True,
        social_window_s=args.social_window_s, state_kwargs=STATE_KWARGS)
    plog(f"      stream={len(stream)} bins, stationary_eps={len(stat_eps)}, bouts={len(bouts)}, "
         f"initiation={len(init)} epochs")

    plog("[3/4] attach weather to the initiation decisions + write")
    if not init.empty:
        init = wc.attach_weather(init, wx, time_col="t_epoch", tol_minutes=15)
    for name, tbl in [("locomotor_state_stream", stream), ("stationary_episodes", stat_eps),
                      ("bouts", bouts), ("initiation_decisions", init), ("state_occupancy", occ)]:
        tbl.to_csv(args.out / f"{name}.csv", index=False)
        plog(f"      {name}: {len(tbl):,} rows -> {name}.csv")
    (args.out / "distinction_diagnostics.json").write_text(json.dumps(diag, indent=2, default=str),
                                                           encoding="utf-8")

    plog("[4/4] manifest")
    n_onset = int((stat_eps["ended_by"] == "onset").sum()) if not stat_eps.empty else 0
    manifest = {
        "analysis": "behavioral_policy/module_3_locomotor_bout_initiation/build",
        "generated_by": "build_locomotor_states.py", "git_commit": _git_commit(),
        "generated_utc": __import__("datetime").datetime.utcnow().isoformat(),
        "module": 3, "module_name": "locomotor_bout_initiation",
        "units": "inches (WISER native, UNVERIFIED offset origin)",
        "night_window": {"start_hour": 21, "end_hour": 5, "tz_offset_hours": -4},
        "nights": nights, **S["counts"],
        "params": {"epoch_s": args.epoch_s, "moving_thr_inps": MOVING_THR_INPS,
                   "jitter_floor_in": JITTER_FLOOR_IN, "social_window_s": args.social_window_s,
                   "state_kwargs": STATE_KWARGS},
        "n_state_bins": int(len(stream)), "n_stationary_episodes": int(len(stat_eps)),
        "n_bout_onsets": n_onset, "n_bouts": int(len(bouts)),
        "n_initiation_epochs": int(len(init)),
        "n_initiated": int(init["initiated"].sum()) if not init.empty else 0,
        "distinction_diagnostics": diag,
        "registration": em.registration_note(),
        "caveats": [
            "Bout-INITIATION onset is a LOWER bound: speed-onset above the ~7 in jitter floor; "
            "in-nest sub-jitter stirring and the ~18:00 arousal are invisible. NOT 'wake'.",
            "Initiation != ROI departure; a bout can occur without an ROI transition.",
            "Rest is a low-speed proxy (not sleep); frame UNVERIFIED (topology only).",
            "Gaps are 'unknown', never an onset; refuge_4 burrow-night rest excluded (below-plane).",
            "Whole nights are the outer inference blocks (~8), not independent cells.",
        ],
    }
    (args.out / "run_manifest.json").write_text(json.dumps(manifest, indent=2, default=str),
                                                encoding="utf-8")
    plog(f"done -> {args.out}  (onsets={n_onset}, initiated epochs="
         f"{manifest['n_initiated']}/{manifest['n_initiation_epochs']})")


if __name__ == "__main__":
    main()
