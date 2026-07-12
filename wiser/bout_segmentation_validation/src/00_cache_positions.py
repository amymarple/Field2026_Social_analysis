"""Load + clean the WISER night-windowed valid positions ONCE and cache them, so the
segmentation-parameter sweeps run off a fixed position set (not the already-filtered
route_bouts.csv). Reuses the exact production load path. Also reports the sampling-rate
facts the segmentation audit needs. Read-only on the DB (incrementals only)."""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve()
WT = HERE.parents[2]                      # wiser/
sys.path.insert(0, str(WT / "src")); sys.path.insert(0, str(WT / "scripts"))
import wiser_analysis_utils as w
import time_utils
import trajectory_stereotypy as ts
import analyze_trajectory_stereotypy as pa

CACHE = Path(sys.argv[1]) if len(sys.argv) > 1 else (HERE.parent.parent / "_cache")
CACHE.mkdir(parents=True, exist_ok=True)
NIGHT_START, NIGHT_END = 21, 4            # match the production motif window

print("[load] incrementals ...")
df, load_log = ts.load_incremental_days(pa.DEFAULT_INCR, dates=None)
df = time_utils.convert_timestamps(df)
floor = pa.establish_floor(pa.DEFAULT_BASELINE, pa.DEFAULT_GT)
jitter_floor = float(floor["jitter_floor_in"]); moving_thr = float(floor["moving_thr_inps"])
df = w.add_speed(df)
roi_cfg = w.load_rois(pa.DEFAULT_ROIS)
boundary = (roi_cfg or {}).get("boundary")
df = w.add_validity_flags(df, boundary=boundary, jitter_floor_in=jitter_floor)
df = w.apply_tag_cutoffs(df)
win = ts.select_night_window(df, night_start=NIGHT_START, night_end=NIGHT_END, valid_only=True)
win = win[~win["shortid"].astype(str).isin(pa.DROP_TAGS)].reset_index(drop=True)

# keep only what the engine needs; datetime as int64 ms for a clean parquet roundtrip
keep = win[["shortid", "night", "clock_hour", "x", "y"]].copy()
keep["shortid"] = keep["shortid"].astype(str)
keep["t_ms"] = (win["datetime"].values.astype("datetime64[ns]").astype("int64") // 1_000_000)
keep = keep.sort_values(["night", "shortid", "t_ms"]).reset_index(drop=True)
keep.to_parquet(CACHE / "night_positions.parquet", index=False)

# sampling-rate facts for the audit (per night,animal dt of consecutive valid fixes)
dts = []
for _, g in keep.groupby(["night", "shortid"]):
    d = np.diff(np.sort(g["t_ms"].to_numpy())) / 1000.0
    dts.append(d[(d > 0) & (d < 60)])
dts = np.concatenate(dts) if dts else np.array([])
facts = {
    "n_positions": int(len(keep)),
    "n_nights": int(keep["night"].nunique()),
    "nights": sorted(keep["night"].unique().tolist()),
    "n_animals": int(keep["shortid"].nunique()),
    "animals": sorted(keep["shortid"].unique().tolist()),
    "jitter_floor_in": jitter_floor,
    "moving_thr_inps": moving_thr,
    "DEFAULT_SMOOTH_WINDOW": int(w.DEFAULT_SMOOTH_WINDOW),
    "DEFAULT_SPEED_WINDOW_S": float(w.DEFAULT_SPEED_WINDOW_S),
    "prod_min_bout_s": 3.0, "prod_max_gap_s": 2.0, "prod_min_disp_in": 15.0,
    "prod_max_per_night": 40,
    "dt_median_s": float(np.median(dts)), "dt_mean_s": float(dts.mean()),
    "dt_p10_s": float(np.percentile(dts, 10)), "dt_p90_s": float(np.percentile(dts, 90)),
    "sampling_hz_median": float(1.0 / np.median(dts)),
    "frac_dt_gt_2s": float((dts > 2.0).mean()),
    "frac_dt_gt_1s": float((dts > 1.0).mean()),
}
(CACHE / "cache_facts.json").write_text(json.dumps(facts, indent=2))
print(json.dumps(facts, indent=2))
print(f"[cache] -> {CACHE/'night_positions.parquet'}  ({len(keep):,} rows)")
