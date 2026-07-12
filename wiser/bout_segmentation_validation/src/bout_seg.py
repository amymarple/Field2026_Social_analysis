"""Re-extraction engine for the bout-segmentation validation.

Segments movement bouts from the CACHED cleaned night positions (not the filtered
route_bouts.csv), with every segmentation rule exposed as a parameter, so the sweeps
can test whether the apparent 4 s / 100 in scale moves with the pipeline.

Two distinct gap concepts (the production code conflates neither cleanly, so we split them):
  * ``max_gap_s``  — DROPOUT tolerance: a sampling gap dt > this splits a bout (data missing).
                     Production value 2.0. Rarely fires (0.4% of dt).
  * ``pause_merge_s`` — PAUSE tolerance: a NON-moving stretch shorter than this is BRIDGED,
                     merging run–pause–run into one unit ("trip"). Production = 0 (any
                     non-moving sample breaks the bout).

Speed + position smoothing reuse the production ``add_speed`` (rolling-median window
``smooth_window`` samples, fixed ``speed_window_s`` window), so a bout's moving mask is the
same construction the real pipeline uses; only the parameters vary.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

_WT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_WT / "src"))
import wiser_analysis_utils as w   # noqa: E402


def load_positions(cache) -> pd.DataFrame:
    pos = pd.read_parquet(Path(cache) / "night_positions.parquet")
    pos["datetime"] = pd.to_datetime(pos["t_ms"], unit="ms")   # naive UTC (matches pipeline)
    return pos


def add_speed_param(pos: pd.DataFrame, smooth_window: int,
                    speed_window_s: float = None) -> pd.DataFrame:
    """Production add_speed with a chosen smoothing window; adds speed_inps_smooth + the
    smoothed positions xs/ys used for the path. smooth_window<=1 → no smoothing."""
    if speed_window_s is None:
        speed_window_s = w.DEFAULT_SPEED_WINDOW_S
    sw = max(1, int(smooth_window))
    out = w.add_speed(pos, smooth_window=sw, speed_window_s=speed_window_s)
    # the smoothed positions (same rolling median add_speed used) per group, for path/disp
    xs = out.groupby("shortid")["x"].transform(
        lambda s: s.rolling(sw, center=True, min_periods=1).median())
    ys = out.groupby("shortid")["y"].transform(
        lambda s: s.rolling(sw, center=True, min_periods=1).median())
    out["xs"] = xs.to_numpy(); out["ys"] = ys.to_numpy()
    return out


def _atomic_runs(moving, t, max_gap_s):
    """Maximal spans of moving samples with internal dt <= max_gap_s (= production bouts
    at pause_merge=0). Returns (starts, ends) inclusive index arrays."""
    n = len(moving)
    if n == 0:
        return np.array([], int), np.array([], int)
    conn = np.zeros(n, bool)
    if n > 1:
        conn[1:] = moving[1:] & moving[:-1] & (np.diff(t) <= max_gap_s)
    starts = np.flatnonzero(moving & ~conn)
    ends_mask = moving & np.r_[~conn[1:], True]
    ends = np.flatnonzero(ends_mask)
    return starts, ends


def _segment_group(t, xs, ys, sp, *, moving_thr, max_gap_s, pause_merge_s):
    """Segments for one (night, animal). Returns list of (i0, i1, n_pause_merged)."""
    moving = np.isfinite(sp) & (sp > moving_thr)
    starts, ends = _atomic_runs(moving, t, max_gap_s)
    if len(starts) == 0:
        return []
    segs = []
    cs, ce, npause = starts[0], ends[0], 0
    for r in range(1, len(starts)):
        pause_dur = t[starts[r]] - t[ce]                       # non-moving stretch duration
        stretch_dt = np.diff(t[ce:starts[r] + 1])
        dropout = stretch_dt.size and np.any(stretch_dt > max_gap_s)
        if (pause_merge_s > 0) and (not dropout) and (pause_dur < pause_merge_s):
            ce = ends[r]; npause += 1                           # bridge the pause
        else:
            segs.append((cs, ce, npause)); cs, ce, npause = starts[r], ends[r], 0
    segs.append((cs, ce, npause))
    return segs


def segment(pos_speed: pd.DataFrame, *, moving_thr: float, min_bout_s: float,
            min_disp_in: float, pause_merge_s: float, max_gap_s: float = 2.0,
            keep_index: bool = False) -> pd.DataFrame:
    """Extract bouts from a pos frame that already has speed_inps_smooth + xs/ys
    (from add_speed_param). Post-filters by min_bout_s (duration), >=2 samples, min_disp_in."""
    recs = []
    for (night, tag), g in pos_speed.groupby(["night", "shortid"], sort=False):
        t = (g["datetime"].values.astype("datetime64[ns]").astype("int64") / 1e9)
        t = t - t[0]
        xs = g["xs"].to_numpy(); ys = g["ys"].to_numpy(); sp = g["speed_inps_smooth"].to_numpy()
        for (i0, i1, npause) in _segment_group(
                t, xs, ys, sp, moving_thr=moving_thr, max_gap_s=max_gap_s,
                pause_merge_s=pause_merge_s):
            nsamp = i1 - i0 + 1
            if nsamp < 2:
                continue
            dur = float(t[i1] - t[i0])
            if dur < min_bout_s:
                continue
            disp = float(np.hypot(xs[i1] - xs[i0], ys[i1] - ys[i0]))
            if disp < min_disp_in:
                continue
            path = float(np.nansum(np.hypot(np.diff(xs[i0:i1 + 1]), np.diff(ys[i0:i1 + 1]))))
            rec = {"night": night, "shortid": str(tag), "dur_s": round(dur, 3),
                   "disp_in": round(disp, 2), "path_in": round(path, 2),
                   "n_samp": int(nsamp), "n_pause": int(npause),
                   "speed_ips": round(disp / dur, 2) if dur > 0 else np.nan,
                   "straight": round(path / disp, 3) if disp > 0 else np.nan}
            if keep_index:
                rec["i0"] = int(g.index[i0]); rec["i1"] = int(g.index[i1])
            recs.append(rec)
    cols = ["night", "shortid", "dur_s", "disp_in", "path_in", "n_samp", "n_pause",
            "speed_ips", "straight"] + (["i0", "i1"] if keep_index else [])
    return pd.DataFrame(recs, columns=cols)


def dist_stats(s: np.ndarray, prefix: str) -> dict:
    """Median/mode/mean/CV/percentiles/max of a 1-D array. Mode = peak of a fixed-width
    histogram (robust, since durations are grid-quantized)."""
    s = np.asarray(s, float); s = s[np.isfinite(s)]
    if s.size == 0:
        return {f"{prefix}_{k}": np.nan for k in
                ["n", "median", "mode", "mean", "cv", "p90", "p95", "p99", "max"]}
    bins = np.histogram_bin_edges(s, bins="auto")
    h, e = np.histogram(s, bins=bins)
    mode = 0.5 * (e[h.argmax()] + e[h.argmax() + 1])
    return {f"{prefix}_n": int(s.size), f"{prefix}_median": round(float(np.median(s)), 2),
            f"{prefix}_mode": round(float(mode), 2), f"{prefix}_mean": round(float(s.mean()), 2),
            f"{prefix}_cv": round(float(s.std() / s.mean()), 3) if s.mean() else np.nan,
            f"{prefix}_p90": round(float(np.percentile(s, 90)), 2),
            f"{prefix}_p95": round(float(np.percentile(s, 95)), 2),
            f"{prefix}_p99": round(float(np.percentile(s, 99)), 2),
            f"{prefix}_max": round(float(s.max()), 2)}
