"""Analysis 6 (trip reconstruction) table + bout-vs-trip distributions, and a light
Analysis 7 (turn angle at bridged pauses vs within-run). Uses the engine's pause-merge."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

HERE = Path(__file__).resolve(); SRC = HERE.parent; ROOT = SRC.parent
sys.path.insert(0, str(SRC)); import bout_seg as bs
CACHE = Path(sys.argv[1]); TAB = ROOT / "tables"; PLT = ROOT / "plots"

pos = bs.load_positions(CACHE); ps = bs.add_speed_param(pos, smooth_window=7)
MERGES = [0, 5, 10, 20, 30, 60]
rows = []; keep = {}
for g in MERGES:
    b = bs.segment(ps, moving_thr=12.63, min_bout_s=3.0, min_disp_in=15.0, pause_merge_s=g)
    keep[g] = b
    multi = (b["n_pause"] >= 1).mean()
    rows.append({"merge_s": g, "n_units": len(b),
                 "dur_median": round(float(b.dur_s.median()), 2), "dur_max": round(float(b.dur_s.max()), 1),
                 "disp_median": round(float(b.disp_in.median()), 1), "disp_p99": round(float(b.disp_in.quantile(.99)), 1),
                 "disp_max": round(float(b.disp_in.max()), 1), "path_median": round(float(b.path_in.median()), 1),
                 "straight_median": round(float(b.straight.median()), 2),
                 "mean_constituent_bouts": round(float(b.n_pause.mean() + 1), 2),
                 "frac_multi_bout_trips": round(float(multi), 3)})
trips = pd.DataFrame(rows); trips.to_csv(TAB / "trip_merging_results.csv", index=False)
print(trips.to_string(index=False))

# bout-vs-trip distributions
fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))
for g, c in [(0, "#333"), (10, "#3377cc"), (30, "#cc3333")]:
    ax[0].hist(keep[g].disp_in, bins=40, histtype="step", color=c, label=f"merge {g}s", density=True)
    ax[1].hist(keep[g].dur_s, bins=40, histtype="step", color=c, label=f"merge {g}s", density=True)
ax[0].axvline(537, ls=":", c="grey"); ax[0].text(537, 0, " paddock diag", fontsize=7, rotation=90, va="bottom")
ax[0].set_xlabel("displacement (in)"); ax[0].set_ylabel("density"); ax[0].legend(fontsize=8)
ax[0].set_title("Displacement: bouts (0s) vs merged trips")
ax[1].set_xlabel("duration (s)"); ax[1].set_ylabel("density"); ax[1].legend(fontsize=8)
ax[1].set_title("Duration: merging reveals long multi-stop trips")
fig.tight_layout(); fig.savefig(PLT / "bout_vs_trip_distributions.png", dpi=120); plt.close(fig)

# ---- Light A7: heading change across a bridged pause vs within continuous motion ----
# For merge=10s trips, recompute per-group headings at bridged pauses.
def group_headings(pause_merge_s=10.0):
    turn_at_pause, turn_within = [], []
    for (night, tag), gdf in ps.groupby(["night", "shortid"], sort=False):
        t = gdf["datetime"].values.astype("datetime64[ns]").astype("int64")/1e9; t = t-t[0]
        xs = gdf["xs"].to_numpy(); ys = gdf["ys"].to_numpy(); sp = gdf["speed_inps_smooth"].to_numpy()
        segs = bs._segment_group(t, xs, ys, sp, moving_thr=12.63, max_gap_s=2.0, pause_merge_s=0.0)
        # atomic runs; heading of a run = end-start vector
        def head(i0, i1):
            return np.arctan2(ys[i1]-ys[i0], xs[i1]-xs[i0])
        for r in range(1, len(segs)):
            (a0, a1, _), (b0, b1, _) = segs[r-1], segs[r]
            pause = t[b0]-t[a1]
            if 0 < pause < pause_merge_s:
                dth = np.abs(np.angle(np.exp(1j*(head(b0, b1)-head(a0, a1)))))
                turn_at_pause.append(np.degrees(dth))
        # within-run mid turn (first half vs second half heading)
        for (i0, i1, _) in segs:
            if i1-i0 >= 4:
                mid = (i0+i1)//2
                dth = np.abs(np.angle(np.exp(1j*(head(mid, i1)-head(i0, mid)))))
                turn_within.append(np.degrees(dth))
    return np.array(turn_at_pause), np.array(turn_within)
tp, tw = group_headings(10.0)
a7 = pd.DataFrame({"metric": ["median_turn_deg", "mean_turn_deg", "frac_turn_gt_60deg", "n"],
                   "across_pause": [round(np.median(tp), 1), round(tp.mean(), 1),
                                    round((tp > 60).mean(), 3), len(tp)],
                   "within_run": [round(np.median(tw), 1), round(tw.mean(), 1),
                                  round((tw > 60).mean(), 3), len(tw)]})
a7.to_csv(TAB / "pause_transition_results.csv", index=False)
print("\n[A7-light] heading change across bridged pause vs within a run:")
print(a7.to_string(index=False))
fig, ax = plt.subplots(figsize=(7, 4.4))
ax.hist(tw, bins=30, density=True, alpha=.5, label="within continuous run")
ax.hist(tp, bins=30, density=True, alpha=.5, label="across a <10s pause")
ax.set_xlabel("heading change (deg)"); ax.set_ylabel("density"); ax.legend()
ax.set_title("Do pauses reorient? turn angle across pause vs within run")
fig.tight_layout(); fig.savefig(PLT / "pause_turn_angle.png", dpi=120); plt.close(fig)
print("[done] trips + A7-light")
