r"""
diagnose_decision_unit.py — decision-unit sensitivity grid + diagnostics (run in the `cv` env).

The raw point-in-ROI segmentation shredded rest into jitter-flicker micro-visits, which
INVALIDATED the M4/M5 identifiability verdicts. Before re-running the ladder we must establish
that the inferred visits/departures are real behavior, not measurement flicker. This driver
segments the SAME cleaned 8-night fixes under a preregistered grid and reports decision-unit
health metrics per representation — it does NOT fit any model. Pick the segmentation + epoch
from these diagnostics, THEN re-build the tables and re-run M1–M5.

Preregistered grid:
  * segmentation: buffer ∈ {1×,2×,3×} jitter floor (7/14/21 in) × sustained-exit ∈ {10,30,60}s
    (+ the RAW point-in-ROI baseline for contrast);
  * hazard epoch ∈ {5,15,30,60}s — reported as the 1-epoch-visit fraction per representation.

    conda activate cv
    cd wiser
    python scripts/diagnose_decision_unit.py --max-nights 2      # smoke
    python scripts/diagnose_decision_unit.py                      # all 8 nights
"""

from __future__ import annotations

import argparse
import json
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
from environment_map import EnvironmentMap           # noqa: E402

DEFAULT_INCR = Path(r"D:\Reolink_record\audio_in\Wiser_backup\incremental")
NIGHTS = [f"2026-06-{d}" for d in (28, 29, 30)] + [f"2026-07-0{d}" for d in (1, 2, 3, 4, 5)]
JITTER = 7.0
BUFFERS = [7.0, 14.0, 21.0]              # 1x, 2x, 3x jitter floor
EXITS = [10.0, 30.0, 60.0]               # sustained-exit s
EPOCHS = [5.0, 15.0, 30.0, 60.0]         # hazard epoch s (1-epoch fraction only)
SHELTER = {"house", "refuge"}
RESOURCE = {"water"}
TRANSIT = {"tunnel"}


def _load_clean(incr, nights, roi_cfg, plog):
    load_dates = sorted(set(nights) | {str((pd.Timestamp(nights[-1]) + pd.Timedelta(days=1)).date())})
    df, _ = ts.load_incremental_days(incr, dates=load_dates)
    df = time_utils.convert_timestamps(df)
    plog(f"  loaded {len(df):,}")
    df = ts.add_night_label(df)
    df = df[df["in_night"] & df["night"].isin([str(n) for n in nights])].copy()
    df = w.add_speed(df)
    df = w.add_validity_flags(df, boundary=roi_cfg.get("boundary"), jitter_floor_in=JITTER)
    df = w.apply_tag_cutoffs(df)
    win = df[df["valid"].astype(bool)].copy()
    win["shortid"] = win["shortid"].astype(str)
    win["moving"] = pd.to_numeric(win.get("speed_inps_smooth"), errors="coerce") > 12.0
    plog(f"  cleaned valid {len(win):,}")
    return win


def _diag(visits: pd.DataFrame, em, label: str) -> dict:
    """Decision-unit health metrics for one segmentation's visits (named only)."""
    v = visits[visits["roi"] != "open"].copy() if not visits.empty else visits
    if v.empty:
        return {"repr": label, "n_visits": 0}
    v["rtype"] = v["roi"].map(em.resource_type)
    leaves = v[v["ended_by"] == "leave"]
    self_ret = leaves[leaves["next_roi"] == leaves["roi"]]
    genuine = leaves[leaves["next_roi"] != leaves["roi"]]
    an = genuine.groupby(["night", "shortid"]).size()
    rec = {
        "repr": label,
        "n_visits": int(len(v)),
        "total_occupancy_h": round(float(v["dwell_s"].sum()) / 3600, 2),
        "dwell_median_s": round(float(v["dwell_s"].median()), 1),
        "dwell_shelter_median_s": round(float(v[v.rtype.isin(SHELTER)]["dwell_s"].median()), 1) if (v.rtype.isin(SHELTER)).any() else np.nan,
        "dwell_resource_median_s": round(float(v[v.rtype.isin(RESOURCE | TRANSIT)]["dwell_s"].median()), 1) if (v.rtype.isin(RESOURCE | TRANSIT)).any() else np.nan,
        "n_departures": int(len(leaves)),
        "self_return_frac": round(float(len(self_ret) / max(len(leaves), 1)), 3),
        "self_return_excursion_median_s": round(float(self_ret["excursion_s"].median()), 1) if "excursion_s" in self_ret and len(self_ret) else np.nan,
        "gap_ended_frac": round(float((v["ended_by"] == "gap").mean()), 3),
        "n_genuine_transitions": int(len(genuine)),
        "animal_nights_with_ge5_genuine": int((an >= 5).sum()),
    }
    for e in EPOCHS:
        rec[f"frac_visit_lt_{int(e)}s"] = round(float((v["dwell_s"] < e).mean()), 3)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--incremental-dir", type=Path, default=DEFAULT_INCR)
    ap.add_argument("--env-map", type=Path, default=ROOT / "configs/environment_map/2026-06-28_to_2026-07-05.yaml")
    ap.add_argument("--rois", type=Path, default=ROOT / "configs/wiser_rois.json")
    ap.add_argument("--out", type=Path, default=ROOT / "outputs/policy_identifiability_2026-06-28_to_2026-07-06")
    ap.add_argument("--nights", nargs="*", default=NIGHTS)
    ap.add_argument("--max-nights", type=int, default=None)
    args = ap.parse_args()
    nights = list(args.nights)[: args.max_nights] if args.max_nights else list(args.nights)
    args.out.mkdir(parents=True, exist_ok=True)
    prog = open(args.out / "_diag_progress.log", "w", buffering=1)

    def plog(m):
        print(m, flush=True); prog.write(m + "\n"); prog.flush()

    roi_cfg = w.load_rois(args.rois)
    em = EnvironmentMap.from_paths(args.env_map, args.rois)
    plog(f"[load] nights {nights[0]}..{nights[-1]}")
    win = _load_clean(args.incremental_dir, nights, roi_cfg, plog)

    rows = []
    # RAW baseline (needs a roi column)
    plog("[seg] RAW point-in-ROI baseline")
    win_r = w.assign_roi(win, roi_cfg)
    raw_all = []
    for (n, s), g in win_r.groupby(["night", "shortid"]):
        raw_all.append(smd.segment_visits(g, min_dwell_s=3.0))
    raw = pd.concat(raw_all, ignore_index=True) if raw_all else pd.DataFrame()
    rows.append(_diag(raw, em, "RAW_pointwise"))

    # hysteretic grid
    for buf in BUFFERS:
        for ex in EXITS:
            label = f"hyst_buf{int(buf)}_exit{int(ex)}"
            plog(f"[seg] {label}")
            vv = []
            for (n, s), g in win.groupby(["night", "shortid"]):
                vv.append(smd.hysteretic_visits(g, roi_cfg, em, buffer_in=buf, bin_s=5.0,
                                                enter_s=10.0, exit_s=ex, flicker_merge_s=30.0))
            visits = pd.concat(vv, ignore_index=True) if vv else pd.DataFrame()
            rows.append(_diag(visits, em, label))

    diag = pd.DataFrame(rows)
    diag.to_csv(args.out / "decision_unit_diagnostics.csv", index=False)
    plog("\n=== DECISION-UNIT DIAGNOSTICS (pick a representation, THEN re-run the ladder) ===")
    cols = ["repr", "n_visits", "total_occupancy_h", "dwell_shelter_median_s", "dwell_resource_median_s",
            "self_return_frac", "self_return_excursion_median_s", "gap_ended_frac",
            "n_genuine_transitions", "animal_nights_with_ge5_genuine", "frac_visit_lt_5s", "frac_visit_lt_30s"]
    plog(diag[cols].to_string(index=False))
    plog(f"\nwrote {args.out / 'decision_unit_diagnostics.csv'}")


if __name__ == "__main__":
    main()
