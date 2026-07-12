"""Analysis 1 — broad candidate-boundary extraction from the native ~4.4 Hz positions.
Vectorized (searchsorted windowed headings; merge_asof social join).

Classes (labelled, none discarded; confidence-flagged):
  pause        low-speed interval flanked by movement (a between-leg stop)
  heading_cp   a turn-in-motion: local-max windowed heading change > threshold, no full stop
  continuous   mid-run control points (uninterrupted movement) -> matched-control pool
Writes tables/candidate_boundaries.csv with a PINNED schema.
"""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve(); SRC = HERE.parent; ROOT = SRC.parent
sys.path.insert(0, str(SRC)); import dbv_common as dc
sys.path.insert(0, str(dc._BSV)); import bout_seg as bs
sys.path.insert(0, str(ROOT.parent / "src")); import wiser_analysis_utils as w
CACHE = Path(sys.argv[1]); TAB = ROOT / "tables"; TAB.mkdir(exist_ok=True)
THR = dc.MOVING_THR; JIT = dc.JITTER_IN; WINDOWS = [0.5, 1.0, 2.0]; TURN_CP_DEG = 40.0
N_CONT_PER_RUN = 3; rng = np.random.default_rng(0)

roi_cfg = w.load_rois(ROOT.parent / "configs" / "wiser_rois.json")
boundary = (roi_cfg or {}).get("boundary"); brect = boundary.get("rect") if boundary else None

def win_heading(t, xs, ys, wsz, side):
    n = len(t)
    if side == "pre":
        j = np.clip(np.searchsorted(t, t - wsz, "left"), 0, n-1); dx = xs - xs[j]; dy = ys - ys[j]
    else:
        j = np.clip(np.searchsorted(t, t + wsz, "right") - 1, 0, n-1); dx = xs[j] - xs; dy = ys[j] - ys
    disp = np.hypot(dx, dy)
    return np.where(disp > JIT, np.arctan2(dy, dx), np.nan), disp

def wrapdeg(a, b):
    return np.degrees(np.abs(np.angle(np.exp(1j*(b - a)))))

pos = bs.load_positions(CACHE)
ps = bs.add_speed_param(pos, smooth_window=7, speed_window_s=1.0)
rows = []
for (night, tag), g in ps.groupby(["night", "shortid"], sort=False):
    t = g["datetime"].values.astype("datetime64[ns]").astype("int64")/1e9; t = t - t[0]
    tms = g["datetime"].values.astype("datetime64[ns]").astype("int64")//1_000_000
    xs = g["xs"].to_numpy(); ys = g["ys"].to_numpy(); sp = g["speed_inps_smooth"].to_numpy()
    hh = g["clock_hour"].to_numpy(); dts = g["dt_s"].to_numpy(); n = len(t)
    if n < 8:
        continue
    preH = {ww: win_heading(t, xs, ys, ww, "pre") for ww in WINDOWS}
    postH = {ww: win_heading(t, xs, ys, ww, "post") for ww in WINDOWS}
    preHcp, _ = win_heading(t, xs, ys, 0.75, "pre"); postHcp, _ = win_heading(t, xs, ys, 0.75, "post")
    turn_cp = wrapdeg(preHcp, postHcp)
    moving = np.isfinite(sp) & (sp > THR)
    starts, ends = bs._atomic_runs(moving, t, dc.MAX_GAP_S)

    def emit(kind, i, pause_dur):
        hp1, hq1 = preH[1.0][0][i], postH[1.0][0][i]
        rec = {"kind": kind, "night": night, "shortid": str(tag), "t_ms": int(tms[i]),
               "t_s": float(t[i]), "x": float(xs[i]), "y": float(ys[i]), "idx": int(i),
               "clock_hour": int(hh[i]), "pause_dur_s": float(pause_dur),
               "speed_pre": float(np.nanmean(sp[max(0, i-4):i+1])),
               "speed_post": float(np.nanmean(sp[i:i+5])),
               "head_pre_ok": bool(np.isfinite(hp1)), "head_post_ok": bool(np.isfinite(hq1)),
               "reversal": bool(np.isfinite(hp1) and np.isfinite(hq1) and wrapdeg(hp1, hq1) > 135),
               "roi": w.assign_roi(pd.DataFrame({"x": [xs[i]], "y": [ys[i]]}), roi_cfg)["roi"].iloc[0] if roi_cfg else "na",
               "dist_boundary_in": (float(min(xs[i]-brect[0], brect[1]-xs[i], ys[i]-brect[2], brect[3]-ys[i])) if brect else np.nan),
               "gap_near": bool(np.any(dts[max(0, i-2):i+3] > dc.MAX_GAP_S))}
        for ww in WINDOWS:
            rec[f"turn_deg_{ww}"] = float(wrapdeg(preH[ww][0][i], postH[ww][0][i]))
            rec[f"flankdisp_{ww}"] = float(min(preH[ww][1][i], postH[ww][1][i]))
        rows.append(rec)

    for r in range(1, len(starts)):                     # pauses
        a1, b0 = ends[r-1], starts[r]
        sd = np.diff(t[a1:b0+1])
        if sd.size and np.any(sd > dc.MAX_GAP_S):
            continue
        emit("pause", (a1+b0)//2, t[b0]-t[a1])
    cpm = (turn_cp > TURN_CP_DEG) & moving              # heading changepoints (local maxima)
    for (i0, i1) in zip(starts, ends):
        seg = np.arange(i0+2, i1-1)
        seg = seg[cpm[seg] & (turn_cp[seg] >= turn_cp[seg-1]) & (turn_cp[seg] >= turn_cp[seg+1])]
        for i in seg:
            emit("heading_cp", int(i), 0.0)
    for (i0, i1) in zip(starts, ends):                  # continuous controls
        cand = np.arange(i0+3, i1-3)
        if len(cand) == 0:
            continue
        for i in (cand if len(cand) <= N_CONT_PER_RUN else rng.choice(cand, N_CONT_PER_RUN, replace=False)):
            emit("continuous", int(i), 0.0)

cb = pd.DataFrame(rows)
# social: nearest-neighbour distance via merge_asof per (night, other animal)
ap = ps[["night", "shortid", "xs", "ys"]].copy()
ap["t_ms"] = ps["datetime"].values.astype("datetime64[ns]").astype("int64")//1_000_000
cb = cb.sort_values("t_ms").reset_index(drop=True); cb["nn_dist_in"] = np.inf; cb["n_within_2ft"] = 0
for night in cb["night"].unique():
    em = cb[cb.night == night]
    for other in ap[ap.night == night]["shortid"].unique():
        opos = ap[(ap.night == night) & (ap.shortid == other)].sort_values("t_ms")
        for foc in em["shortid"].unique():
            if foc == other:
                continue
            sub = em[em.shortid == foc]
            m = pd.merge_asof(sub[["t_ms", "x", "y"]].sort_values("t_ms"), opos[["t_ms", "xs", "ys"]],
                              on="t_ms", direction="nearest", tolerance=300)
            d = np.hypot(m["x"]-m["xs"], m["y"]-m["ys"]).to_numpy()
            idx = sub.index.to_numpy()
            better = np.isfinite(d) & (d < cb.loc[idx, "nn_dist_in"].to_numpy())
            cb.loc[idx[better], "nn_dist_in"] = d[better]
            cb.loc[idx[np.isfinite(d) & (d < 24)], "n_within_2ft"] += 1
cb["nn_dist_in"] = cb["nn_dist_in"].replace(np.inf, np.nan)
cb.to_csv(TAB / "candidate_boundaries.csv", index=False)
summ = cb.groupby("kind").size().to_dict()
(TAB / "candidate_boundaries_summary.json").write_text(json.dumps(
    {"counts": {k: int(v) for k, v in summ.items()}, "n_total": int(len(cb)),
     "turn_cp_deg": TURN_CP_DEG, "windows_s": WINDOWS,
     "head_pre_ok_frac": float(cb.head_pre_ok.mean()),
     "pause_dur_median_s": float(cb[cb.kind == "pause"].pause_dur_s.median())}, indent=2))
print(json.dumps({k: int(v) for k, v in summ.items()}, indent=2)); print(f"n_total={len(cb)}")
