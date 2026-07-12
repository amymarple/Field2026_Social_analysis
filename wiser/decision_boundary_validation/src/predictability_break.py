"""Analysis 4 — predictability-break test (H3).

A control-update boundary should interrupt predictive continuity: pre-event velocity extrapolation
should predict the future WORSE after a boundary than at a matched continuous point. For each event
fit v_t over [t-1s, t] on smoothed positions, extrapolate p_hat(t+h)=p_t+v_t*h, measure error vs the
actual smoothed position at horizons {0.5,1,2,3,5}s. Compare pause vs continuous (and heading_cp).
Also: predict post-heading from pre-heading (+location) and report residual. Reloads the cache.
"""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve(); SRC = HERE.parent; ROOT = SRC.parent
sys.path.insert(0, str(SRC)); import dbv_common as dc
sys.path.insert(0, str(dc._BSV)); import bout_seg as bs
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
CACHE = Path(sys.argv[1]); TAB = ROOT / "tables"; PLT = ROOT / "plots"
rng = np.random.default_rng(0); HZ = [0.5, 1.0, 2.0, 3.0, 5.0]

cb = pd.read_csv(TAB / "candidate_boundaries.csv")
cb["shortid"] = cb["shortid"].astype(str); cb["night"] = cb["night"].astype(str)
cb = cb[cb.kind.isin(["pause", "continuous", "heading_cp"])]
# subsample for tractability, balanced-ish per kind
cap = 12000
cb = pd.concat([g.sample(min(cap, len(g)), random_state=1) for _, g in cb.groupby("kind")])
cb["t_ms"] = cb["t_ms"].astype(np.int64)

pos = bs.load_positions(CACHE); ps = bs.add_speed_param(pos, smooth_window=7, speed_window_s=1.0)
ps["t_ms"] = ps["datetime"].values.astype("datetime64[ns]").astype("int64")//1_000_000
recs = []
for (night, tag), g in ps.groupby(["night", "shortid"], sort=False):
    ev = cb[(cb.night == night) & (cb.shortid == tag)]
    if len(ev) == 0:
        continue
    t = g["t_ms"].to_numpy()/1000.0; t = t - t[0]
    tmsg = g["t_ms"].to_numpy(); xs = g["xs"].to_numpy(); ys = g["ys"].to_numpy()
    for _, e in ev.iterrows():
        i = int(np.searchsorted(tmsg, e.t_ms)); i = min(max(i, 0), len(t)-1)
        # pre velocity over [t_i-1, t_i]
        lo = np.searchsorted(t, t[i]-1.0, "left")
        if i - lo < 2 or (t[i]-t[lo]) <= 0:
            continue
        vx = (xs[i]-xs[lo])/(t[i]-t[lo]); vy = (ys[i]-ys[lo])/(t[i]-t[lo])
        rec = {"kind": e.kind}
        ok = False
        for h in HZ:
            k = np.searchsorted(t, t[i]+h, "left")
            if k >= len(t) or (t[k]-t[i]) < 0.5*h or (t[k]-t[i]) > 1.6*h:
                rec[f"err_{h}"] = np.nan; continue
            px = xs[i]+vx*(t[k]-t[i]); py = ys[i]+vy*(t[k]-t[i])
            rec[f"err_{h}"] = float(np.hypot(xs[k]-px, ys[k]-py)); ok = True
        if ok:
            recs.append(rec)
E = pd.DataFrame(recs)
summ = {}
for kind in ["pause", "continuous", "heading_cp"]:
    d = E[E.kind == kind]
    summ[kind] = {f"err_{h}_median": round(float(d[f"err_{h}"].median()), 1) for h in HZ}
    summ[kind]["n"] = int(len(d))
# ratio boundary/continuous at each horizon
ratio = {f"err_{h}_pause/cont": round(summ["pause"][f"err_{h}_median"]/max(summ["continuous"][f"err_{h}_median"], 1e-6), 2) for h in HZ}
ratio_cp = {f"err_{h}_hcp/cont": round(summ["heading_cp"][f"err_{h}_median"]/max(summ["continuous"][f"err_{h}_median"], 1e-6), 2) for h in HZ}

# post-heading prediction: from pre-heading only vs pre-heading+location (circular residual)
def circ_resid(df, feats):
    # predict post-heading; baseline = post ~ pre (persistence); model residual reduction with feats
    d = df.dropna(subset=["turn_deg_1.0"]).copy()
    base_res = np.radians(d["turn_deg_1.0"]).abs()   # |post-pre| = persistence residual
    # location-binned mean turn (does location predict the turn beyond persistence?)
    d["cell"] = (d["x"]//60).astype(int).astype(str)+"_"+(d["y"]//60).astype(int).astype(str)
    locmean = d.groupby("cell")["turn_deg_1.0"].transform("mean")
    loc_res = np.radians((d["turn_deg_1.0"]-locmean)).abs()
    return round(float(base_res.mean()), 3), round(float(loc_res.mean()), 3)
pb, pl = circ_resid(cb[cb.kind == "pause"], None)
out = {"future_error_median_by_kind": summ, "pause_over_continuous_ratio": ratio,
       "heading_cp_over_continuous_ratio": ratio_cp,
       "post_heading_residual_pause": {"persistence_only_rad": pb, "plus_location_rad": pl,
                                       "location_reduces_residual": pl < pb}}
(TAB / "predictability_break_results.json").write_text(json.dumps(out, indent=2))
E.to_csv(TAB / "predictability_break_events.csv", index=False)
print(json.dumps(out, indent=2))
fig, ax = plt.subplots(figsize=(8, 4.6))
for kind, c in [("continuous", "#3a7"), ("pause", "#c33"), ("heading_cp", "#37c")]:
    ax.plot(HZ, [summ[kind][f"err_{h}_median"] for h in HZ], "-o", color=c, label=kind)
ax.set_xlabel("prediction horizon (s)"); ax.set_ylabel("median extrapolation error (in)")
ax.set_title("Future-position error after boundary vs continuous\n(higher after boundary = predictive break)")
ax.legend(); fig.tight_layout(); fig.savefig(PLT / "prediction_error_after_boundary.png", dpi=120)
print("[done] predictability break")
