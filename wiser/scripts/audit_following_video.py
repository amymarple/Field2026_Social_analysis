r"""
audit_following_video.py — Phase B2 video false-negative audit.

You mark strict-following events you SEE on video in configs/video_audit_manual.csv;
this pulls the WISER trajectories around each event and checks whether the current
detector caught it — and if not, WHY (lag / heading / radius / moving-mask / tag
dropout / clock-alignment / not-geometrically-strict). This measures detector RECALL
against human observation, the missing piece of Phase B.

Additive; reads only. Outputs to outputs/following_video_audit/.

Manual input schema (configs/video_audit_manual.csv), one row per observed event:
  date            2026-06-29        (local calendar date of the night start)
  start_local     22:05:00          (EDT wall-clock; date+time is the event start)
  end_local       22:05:40          (EDT; event end)
  leader          Sen  (or shortid) leader animal (name or WISER shortid)
  follower        Nox  (or shortid) follower animal
  confidence      high/med/low      your confidence it is strict trailing
  notes           free text
  camera_channel  CH01              (optional) channel you observed it on
  wiser_zone      open              (optional) rough WISER zone/ROI

    conda activate cv
    cd wiser
    python scripts/audit_following_video.py                 # uses configs/video_audit_manual.csv
    python scripts/audit_following_video.py --plots         # + per-event trajectory plots
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import wiser_analysis_utils as w              # noqa: E402
import time_utils                             # noqa: E402
import trajectory_stereotypy as ts            # noqa: E402
import following_incidents as fi              # noqa: E402
import camera_router as cr                    # noqa: E402
import analyze_trajectory_stereotypy as pa    # noqa: E402

DEFAULT_AUDIT = PROJECT_ROOT / "configs" / "video_audit_manual.csv"
DEFAULT_OUT = PROJECT_ROOT / "outputs" / "following_video_audit"
DEFAULT_VIS = PROJECT_ROOT / "configs" / "camera_visibility_map.yaml"
TZ = w.LOCAL_TZ_OFFSET_HOURS      # EDT = UTC-4


def _name_to_shortid():
    ids = pa._name_map()                       # shortid(str) -> name
    rev = {v.lower(): k for k, v in ids.items()}
    return ids, rev


def _resolve(token, rev):
    """Resolve a leader/follower token (name or shortid) to a shortid string."""
    t = str(token).strip()
    if t in rev:                                # exact shortid
        return t
    return rev.get(t.lower(), t)                # name -> shortid, else pass through


def _local_to_utc(date, hhmmss):
    ts = pd.Timestamp(f"{date} {hhmmss}")
    return ts - pd.Timedelta(hours=TZ)          # EDT -> UTC (subtract -4 => +4)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--audit-csv", type=Path, default=DEFAULT_AUDIT)
    ap.add_argument("--incremental-dir", type=Path, default=pa.DEFAULT_INCR)
    ap.add_argument("--baseline", type=Path, default=pa.DEFAULT_BASELINE)
    ap.add_argument("--gt", type=Path, default=pa.DEFAULT_GT)
    ap.add_argument("--vis-map", type=Path, default=DEFAULT_VIS)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--margin-s", type=float, default=60.0, help="WISER window ± this around the event")
    ap.add_argument("--lags-max", type=int, default=30)
    ap.add_argument("--cos-thresh", type=float, default=0.5)
    ap.add_argument("--min-bout-s", type=float, default=3.0)
    ap.add_argument("--bin-s", type=float, default=1.0)
    ap.add_argument("--smooth-s", type=float, default=5.0)
    ap.add_argument("--plots", action="store_true")
    args = ap.parse_args()

    out = args.out
    (out / "plots").mkdir(parents=True, exist_ok=True)
    ids, rev = _name_to_shortid()

    if not args.audit_csv.exists():
        print(f"no audit file at {args.audit_csv}; nothing to do."); return
    audit = pd.read_csv(args.audit_csv, dtype=str).fillna("")
    audit = audit[audit["date"].str.strip() != ""].reset_index(drop=True)
    if audit.empty:
        print("audit file has no rows; add observed events and re-run."); return
    dates = sorted(audit["date"].str.strip().unique())
    print(f"== Video-audit: {len(audit)} marked events over dates {dates} ==")

    print("[1/3] load WISER for the marked dates ...")
    # load the backup files for those dates (+ the previous day for pre-dawn events)
    want = set(dates)
    for d in list(dates):
        want.add((pd.Timestamp(d) - pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
        want.add((pd.Timestamp(d) + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
    df, load_log = ts.load_incremental_days(args.incremental_dir, dates=sorted(want))
    df = time_utils.convert_timestamps(df)
    floor = pa.establish_floor(args.baseline, args.gt)
    jitter_floor = floor["jitter_floor_in"]; R = w.follow_radius_in(jitter_floor)
    df = w.add_speed(df)
    df = w.add_validity_flags(df, jitter_floor_in=jitter_floor)
    df = w.apply_tag_cutoffs(df)
    grid_moving_thr = w.DEFAULT_ACTIVE_SPEED_INPS
    if floor.get("stationary") is not None:
        try:
            grid_moving_thr = round(w.grid_speed_noise_floor(
                floor["stationary"], bin_s=args.bin_s, smooth_s=args.smooth_s), 2)
        except Exception:
            pass
    vis_map = None
    try:
        vis_map = cr.load_visibility_map(args.vis_map)
    except Exception:
        pass

    print("[2/3] classify each marked event ...")
    rows = []
    for i, ev in audit.iterrows():
        lead = _resolve(ev["leader"], rev); fol = _resolve(ev["follower"], rev)
        start_utc = _local_to_utc(ev["date"].strip(), ev["start_local"].strip() or "00:00:00")
        end_txt = ev.get("end_local", "").strip() or ev["start_local"].strip()
        end_utc = _local_to_utc(ev["date"].strip(), end_txt)
        lo = start_utc - pd.Timedelta(seconds=args.margin_s)
        hi = end_utc + pd.Timedelta(seconds=args.margin_s)
        sub = df[(df["shortid"].astype(str).isin({lead, fol})) &
                 (df["datetime"] >= lo) & (df["datetime"] <= hi)].copy()
        rec = {"event_id": "aud%03d" % i, "date": ev["date"], "start_local": ev["start_local"],
               "end_local": end_txt, "leader": ids.get(lead, lead), "follower": ids.get(fol, fol),
               "leader_shortid": lead, "follower_shortid": fol,
               "confidence_obs": ev.get("confidence", ""), "notes": ev.get("notes", ""),
               "camera_channel_obs": ev.get("camera_channel", ""),
               "n_wiser_fixes": int(len(sub))}
        if len(sub) < 5 or sub["shortid"].astype(str).nunique() < 1:
            rec.update({"classification": "missed_alignment" if len(sub) == 0 else "missed_tag_dropout",
                        "detected": False, "recovered_by": None,
                        "leader_present_frac": np.nan, "follower_present_frac": np.nan,
                        "both_moving_bins": 0})
            rows.append(rec); continue
        grid = w.build_following_grid(sub, bin_s=args.bin_s, smooth_s=args.smooth_s,
                                      moving_thr_inps=grid_moving_thr)
        cls = fi.classify_audit_event(grid, lead, fol, R=R, cos_thresh=args.cos_thresh,
                                      lags=range(1, args.lags_max + 1), min_bout_s=args.min_bout_s)
        rec.update({k: cls[k] for k in ("detected", "classification", "recovered_by",
                                        "leader_present_frac", "follower_present_frac",
                                        "both_moving_bins", "n_episodes")})
        # route the event footprint for convenience
        if vis_map is not None and len(sub):
            fp = sub[["x", "y"]].to_numpy()
            r = cr.route_event(fp, vis_map, margin_in=6.0)
            rec["wiser_channel_rank_1"] = r["channel_rank_1"]
            rec["route_confidence"] = r["confidence"]
        rows.append(rec)
        if args.plots and len(sub):
            _plot_event(sub, ids, lead, fol, rec, out / "plots" / f"{rec['event_id']}.png")

    events = pd.DataFrame(rows)
    events.to_csv(out / "video_audit_events.csv", index=False)

    print("[3/3] summaries ...")
    n = len(events); n_det = int(events["detected"].sum())
    summary = pd.DataFrame([{
        "n_events": n, "n_detected": n_det, "n_missed": n - n_det,
        "recall": round(n_det / n, 3) if n else np.nan,
        "recall_high_conf": _recall_subset(events, "high"),
        "recall_med_conf": _recall_subset(events, "med"),
    }])
    summary.to_csv(out / "video_audit_detection_summary.csv", index=False)
    fm = (events["classification"].value_counts().rename_axis("failure_mode")
          .reset_index(name="count"))
    fm.to_csv(out / "video_audit_failure_modes.csv", index=False)

    manifest = {"analysis": "following_video_audit", "generated_utc": _dt.datetime.utcnow().isoformat(),
                "git_commit": pa._git_commit(), "n_events": n, "recall": round(n_det / n, 3) if n else None,
                "follow_radius_in": R, "margin_s": args.margin_s, "cos_thresh": args.cos_thresh,
                "lags_s": [1, args.lags_max], "audit_csv": str(args.audit_csv),
                "failure_modes": fm.set_index("failure_mode")["count"].to_dict(),
                "caveats": ["recall is vs the events YOU marked (not a random sample)",
                            "local EDT -> UTC assumes the -4 h offset; a systematic video/WISER clock "
                            "skew surfaces as 'missed_alignment'/'missed_lag_range'",
                            "inch frame UNVERIFIED; classification is geometric, not a behavior label"]}
    with open(out / "run_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2, default=str)

    print(f"\nrecall {n_det}/{n} = {(n_det/n if n else 0):.0%}; failure modes: "
          f"{fm.set_index('failure_mode')['count'].to_dict()}")
    print(f"DONE -> {out}")


def _recall_subset(events, conf_prefix):
    s = events[events["confidence_obs"].str.lower().str.startswith(conf_prefix)]
    if s.empty:
        return np.nan
    return round(float(s["detected"].mean()), 3)


def _plot_event(sub, ids, lead, fol, rec, path):
    fig, ax = plt.subplots(figsize=(5, 5))
    for tag, col in ((lead, "#C44E52"), (fol, "#4C72B0")):
        g = sub[sub["shortid"].astype(str) == tag].sort_values("datetime")
        ax.plot(g["x"], g["y"], "-o", ms=2, lw=0.8, color=col, label=ids.get(tag, tag))
    ax.set_aspect("equal"); ax.legend(fontsize=8)
    ax.set_title(f"{rec['event_id']} {rec['leader']}→{rec['follower']} "
                 f"[{rec['classification']}]", fontsize=9)
    fig.tight_layout(); fig.savefig(path, dpi=120); plt.close(fig)


if __name__ == "__main__":
    main()
