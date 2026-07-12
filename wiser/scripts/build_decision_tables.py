r"""
build_decision_tables.py — Stage-0 builder (run in the `cv` env).

Loads the WISER incremental nights, cleans them (speed + validity + tag cutoffs), assigns ROIs,
resolves the versioned environment map, and writes the two hierarchical semi-Markov decision
tables plus the pre-modeling audit artifacts. Frame-invariant, inch frame (UNVERIFIED); gaps
stay 'unknown' (never a departure). The modeling (Stages A0-M5) runs separately under the
anaconda3 interpreter from these CSVs.

Guardrails: read-only on the transferred backups; night window 21:00->05:00 EDT; Sova (12409)
dropped via tag cutoff; refuge_4 burrow-night occupancy is a below-plane dropout (under-counts;
gaps unknown). See implementation_plan/2026-07-09-agent-policy-identifiability.md.

    conda activate cv
    cd wiser
    python scripts/build_decision_tables.py --max-nights 2        # smoke
    python scripts/build_decision_tables.py                        # all 8 nights
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
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
NIGHTS = [f"2026-06-{d}" for d in (28, 29, 30)] + [f"2026-07-0{d}" for d in (1, 2, 3, 4, 5, 6, 7, 8)]
JITTER_FLOOR_IN = 7.0
MOVING_THR_INPS = 12.0        # speed above the stationary noise floor => 'moving'
GAP_FACTOR = 5.0


def _git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT)).decode().strip()
    except Exception:
        return "unknown"


def _redetect_gaps(win: pd.DataFrame, gap_factor=GAP_FACTOR) -> pd.DataFrame:
    """After valid-only filtering the original gap_flag rows are removed; re-mark a gap on the
    row FOLLOWING a dt discontinuity (dt > gap_factor x per-(animal,night) median dt) so the
    segmenter still treats those as 'unknown'."""
    win = win.sort_values(["shortid", "night", "datetime"]).copy()
    dt = win.groupby(["shortid", "night"])["datetime"].diff().dt.total_seconds()
    med = win.groupby(["shortid", "night"])["datetime"].transform(
        lambda s: s.diff().dt.total_seconds().median())
    win["gap_flag"] = (dt > gap_factor * med).fillna(False).to_numpy()
    return win


def load_clean_stream(incremental_dir, weather_dir, env_map_path, rois_path, nights, plog=None):
    """Load → clean (speed + validity + tag cutoffs) → ROI → weather → the valid stream with
    re-detected gaps. The single shared WISER loader for the agent-policy decision-table builders
    (module 5 leaving hazard here; module 3 locomotor-bout initiation in build_locomotor_states.py),
    so both start from an IDENTICAL cleaned stream. Read-only on the transferred backups.

    Returns a dict: ``win_all`` (valid+invalid, ROI+weather, for the measurement audit), ``win``
    (valid-only stream with re-detected gaps + ``moving``), ``em``, ``wx``, ``roi_cfg``,
    ``load_log``, ``counts`` (n_fixes_deduped / n_in_night_fixes / n_valid_in_night)."""
    plog = plog or (lambda _m: None)
    nights = [str(n) for n in nights]
    plog(f"[load] incrementals {nights[0]}..{nights[-1]}")
    load_dates = sorted(set(nights) | {str((pd.Timestamp(nights[-1]) + pd.Timedelta(days=1)).date())})
    df, load_log = ts.load_incremental_days(incremental_dir, dates=load_dates)
    n_deduped = int(len(df))                              # true deduped total (BEFORE the night filter)
    plog(f"      loaded+deduped {n_deduped:,} fixes")
    df = time_utils.convert_timestamps(df)
    roi_cfg = w.load_rois(rois_path)
    df = ts.add_night_label(df)
    df = df[df["in_night"] & df["night"].isin(nights)].copy()
    plog(f"      {len(df):,} in-night raw fixes; cleaning")
    df = w.add_speed(df)
    df = w.add_validity_flags(df, boundary=roi_cfg.get("boundary"), jitter_floor_in=JITTER_FLOOR_IN)
    df = w.apply_tag_cutoffs(df)
    win_all = w.assign_roi(df, roi_cfg)
    win_all["shortid"] = win_all["shortid"].astype(str)
    win_all["moving"] = (pd.to_numeric(win_all.get("speed_inps_smooth"), errors="coerce") > MOVING_THR_INPS)
    plog("      ROI assigned")
    wx = wc.load_weather_features(sorted(str(p) for p in Path(weather_dir).glob("AWN-*.csv")))
    win_all = wc.attach_weather(win_all, wx, time_col="datetime", tol_minutes=15)
    plog("      weather attached to fixes")
    em = EnvironmentMap.from_paths(env_map_path, rois_path)
    win = win_all[win_all["valid"].astype(bool)].copy()
    win = _redetect_gaps(win)
    counts = {"n_fixes_deduped": n_deduped, "n_in_night_fixes": int(len(win_all)),
              "n_valid_in_night": int(len(win))}
    return {"win_all": win_all, "win": win, "em": em, "wx": wx, "roi_cfg": roi_cfg,
            "load_log": load_log, "counts": counts}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--incremental-dir", type=Path, default=DEFAULT_INCR)
    ap.add_argument("--weather-dir", type=Path, default=DEFAULT_WEATHER)
    ap.add_argument("--env-map", type=Path,
                    default=ROOT / "configs/environment_map/2026-06-28_to_2026-07-08.yaml")
    ap.add_argument("--rois", type=Path, default=ROOT / "configs/wiser_rois.json")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "outputs/policy_identifiability_2026-06-28_to_2026-07-08")
    ap.add_argument("--nights", nargs="*", default=NIGHTS)
    ap.add_argument("--max-nights", type=int, default=None)
    ap.add_argument("--epoch-s", type=float, default=5.0)
    ap.add_argument("--min-dwell-s", type=float, default=3.0)
    ap.add_argument("--social-window-s", type=float, default=10.0)
    args = ap.parse_args()

    nights = list(args.nights)[: args.max_nights] if args.max_nights else list(args.nights)
    args.out.mkdir(parents=True, exist_ok=True)
    import time as _time
    _t0 = _time.time()
    _prog = open(args.out / "_progress.log", "w", buffering=1)   # line-buffered; bypasses conda stdout buffering

    def plog(msg):
        line = f"[{_time.time() - _t0:6.1f}s] {msg}"
        print(line, flush=True)
        _prog.write(line + "\n"); _prog.flush()

    plog(f"[1-3/6] load + clean + ROI + weather for nights {nights[0]}..{nights[-1]}")
    S = load_clean_stream(args.incremental_dir, args.weather_dir, args.env_map, args.rois,
                          nights, plog=plog)
    win_all, win, em, wx, roi_cfg, load_log = (S["win_all"], S["win"], S["em"], S["wx"],
                                               S["roi_cfg"], S["load_log"])
    df_counts = S["counts"]

    plog("[4/6] measurement-process audit")
    audit = wc.measurement_process_audit(win_all, weather_col="w_rain_log1p", min_n=40)
    audit.to_csv(args.out / "measurement_process_audit.csv", index=False)
    plog(f"      audit done ({len(audit)} strata)")

    plog("[5/6] build decision tables (leaving hazard + destination choice)")
    keep = ["shortid", "night", "datetime", "x", "y", "roi", "valid", "gap_flag", "moving"]
    plog(f"      cleaned valid stream {len(win):,}; segmenting + building tables")
    leave, dest, visits = smd.build_decision_tables(
        win[keep], em, epoch_s=args.epoch_s, min_dwell_s=args.min_dwell_s,
        social_window_s=args.social_window_s)
    plog(f"      tables built (leave={len(leave)}, dest={len(dest)}, visits={len(visits)})")
    # attach the prespecified weather vector to each DECISION (strictly by decision time)
    if not leave.empty:
        leave = wc.attach_weather(leave, wx, time_col="t_epoch", tol_minutes=15)
    if not dest.empty:
        dest = wc.attach_weather(dest, wx, time_col="t_dep", tol_minutes=15)

    for name, tbl in [("leave_decisions", leave), ("destination_decisions", dest), ("visits", visits)]:
        tbl.to_csv(args.out / f"{name}.csv", index=False)
        print(f"      {name}: {len(tbl):,} rows -> {name}.csv")

    # environment map resolved per (night, roi)
    rows = []
    for n in nights:
        reg = em.night_regime(n)
        for r in em.active_rois(n):
            rows.append({"night": n, "roi": r, "resource_type": em.resource_type(r),
                         "is_dropout": int(em.is_dropout(r, n)), **reg})
    pd.DataFrame(rows).to_csv(args.out / "environment_map_resolved.csv", index=False)

    print("[6/6] manifest")
    manifest = {
        "analysis": "agent_policy_identifiability/build_decision_tables",
        "generated_by": "build_decision_tables.py", "git_commit": _git_commit(),
        "generated_utc": __import__("datetime").datetime.utcnow().isoformat(),
        "units": "inches (WISER native, UNVERIFIED offset origin)",
        "timestamp_method": "Unix ms UTC -> naive UTC (time_utils.convert_timestamps)",
        "night_window": {"start_hour": 21, "end_hour": 5, "tz_offset_hours": -4},
        "nights": nights, "n_fixes_deduped": df_counts["n_fixes_deduped"],
        "n_in_night_fixes": df_counts["n_in_night_fixes"], "n_valid_in_night": df_counts["n_valid_in_night"],
        "params": {"epoch_s": args.epoch_s, "min_dwell_s": args.min_dwell_s,
                   "social_window_s": args.social_window_s, "moving_thr_inps": MOVING_THR_INPS,
                   "gap_factor": GAP_FACTOR, "jitter_floor_in": JITTER_FLOOR_IN,
                   "social_radius_in": smd.RADIUS_1M_IN},
        "n_leave_decisions": int(len(leave)), "n_destination_decisions": int(len(dest)),
        "n_visits": int(len(visits)),
        "registration": em.registration_note(),
        "load_log": {k: (v if isinstance(v, (int, float, str, list)) else str(v))
                     for k, v in (load_log or {}).items()},
        "caveats": [
            "Inch frame UNVERIFIED; topology + coarse (>=14 in) distances only.",
            "Gaps are 'unknown', never a departure; refuge_4 burrow-night occupancy under-counts.",
            "Sova (12409) removed 2026-06-29 via tag cutoff; night 06-28 has 6 rats.",
            "Weather is dynamic context + measurement-quality determinant, NOT causal.",
            "Whole nights are the outer inference blocks (~8), not 40 independent cells.",
        ],
    }
    (args.out / "run_manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    print(f"done -> {args.out}")


if __name__ == "__main__":
    main()
