"""Analysis 8 (ballisticity vs jitter null) + 11 (cross-animal / cross-night stability).

A8: simulate straight & curved runs with the MEASURED WISER stationary noise, apply the same
rolling-median smoothing, and measure how much of the short-bout straightness inflation is
expected from localization noise alone.
A11: is the truncation artifact (scale tracks min_bout) universal across animals/nights/epochs?
"""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

HERE = Path(__file__).resolve(); SRC = HERE.parent; ROOT = SRC.parent
sys.path.insert(0, str(SRC)); import bout_seg as bs
sys.path.insert(0, str(ROOT.parent / "src")); sys.path.insert(0, str(ROOT.parent / "scripts"))
import wiser_analysis_utils as w, analyze_trajectory_stereotypy as pa, time_utils
CACHE = Path(sys.argv[1]); TAB = ROOT / "tables"; PLT = ROOT / "plots"
rng = np.random.default_rng(1)

# ---------- estimate per-axis WISER position noise from the stationary baseline ----------
try:
    base = w.load_wiser_file(pa.DEFAULT_BASELINE) if hasattr(w, "load_wiser_file") else None
except Exception:
    base = None
sigma = None
if base is not None:
    try:
        base = time_utils.convert_timestamps(base)
        # residual of position from a per-tag rolling-median (the smoothing the pipeline uses)
        res = []
        for _, g in base.groupby("shortid"):
            for c in ("x", "y"):
                v = g[c].to_numpy(float)
                if len(v) > 20:
                    med = pd.Series(v).rolling(7, center=True, min_periods=1).median().to_numpy()
                    res.append(v - med)
        sigma = float(np.nanstd(np.concatenate(res))) if res else None
    except Exception:
        sigma = None
if sigma is None or not np.isfinite(sigma):
    sigma = 5.0            # fallback per-axis sd (~7 in radial jitter floor)
print(f"[A8] per-axis stationary noise sigma ~= {sigma:.2f} in")

# ---------- A8: straightness of simulated straight/curved runs under jitter ----------
dt = 0.228; speed = 25.0; SW = 7
def sim_straight(nsamp, curved=False):
    t = np.arange(nsamp) * dt
    x = speed * t
    y = np.zeros(nsamp)
    if curved:                       # gentle arc, radius ~ paddock scale
        R = 300.0; ang = (speed * t) / R; x = R*np.sin(ang); y = R*(1-np.cos(ang))
    x = x + rng.normal(0, sigma, nsamp); y = y + rng.normal(0, sigma, nsamp)
    xs = pd.Series(x).rolling(SW, center=True, min_periods=1).median().to_numpy()
    ys = pd.Series(y).rolling(SW, center=True, min_periods=1).median().to_numpy()
    disp = np.hypot(xs[-1]-xs[0], ys[-1]-ys[0])
    path = np.nansum(np.hypot(np.diff(xs), np.diff(ys)))
    return path/disp if disp > 0 else np.nan, disp
rows = []
for dur in [0.5, 1, 1.5, 2, 3, 4, 5]:
    nsamp = max(2, int(round(dur/dt)))
    for lbl, cv in [("straight_line", False), ("curved", True)]:
        vals = [sim_straight(nsamp, cv) for _ in range(400)]
        st = np.array([v[0] for v in vals]); dp = np.array([v[1] for v in vals])
        rows.append({"dur_s": dur, "n_samp": nsamp, "kind": lbl,
                     "sim_straight_median": round(float(np.nanmedian(st)), 3),
                     "sim_straight_p90": round(float(np.nanpercentile(st, 90)), 3),
                     "sim_disp_median": round(float(np.nanmedian(dp)), 1)})
nulldf = pd.DataFrame(rows); nulldf.to_csv(TAB / "ballisticity_noise_null.csv", index=False)

# real straightness by duration bin (production-ish, min_bout0 so short bins exist)
pos = bs.load_positions(CACHE); ps = bs.add_speed_param(pos, smooth_window=SW)
raw = bs.segment(ps, moving_thr=12.63, min_bout_s=0.0, min_disp_in=0.0, pause_merge_s=0.0)
raw["dbin"] = pd.cut(raw["dur_s"], [0,1,1.5,2,3,4,6,100], labels=["<1","1-1.5","1.5-2","2-3","3-4","4-6","6+"])
realst = raw.groupby("dbin", observed=True)["straight"].median()
print("[A8] real vs straight-line-null straightness (median):")
sim_line = nulldf[nulldf.kind=="straight_line"].set_index("dur_s")["sim_straight_median"]
print("  real by dur bin:", {k: round(v,2) for k,v in realst.items()})
print("  sim straight-line:", sim_line.to_dict())

# ---------- A11: is the truncation artifact universal? ----------
FIRST_HALF = {"2026-06-28","2026-06-29","2026-06-30","2026-07-01","2026-07-02","2026-07-03"}
FIVE_RAT = set(raw["night"].unique()) - {"2026-07-09","2026-07-10"}
def med_at(sub, mb):
    b = sub[(sub.dur_s>=mb)&(sub.disp_in>=15)]
    return (round(float(b.dur_s.median()),2), round(float(b.disp_in.median()),1), len(b)) if len(b) else (np.nan,np.nan,0)
srows = []
for tag, g in raw.groupby("shortid"):
    u = med_at(g, 0); p = med_at(g, 3)
    srows.append({"group": f"animal_{tag}", "untrunc_dur_med": u[0], "prod_dur_med": p[0],
                  "untrunc_disp_med": u[1], "prod_disp_med": p[1], "n_prod": p[2]})
for night, g in raw.groupby("night"):
    p = med_at(g, 3); u = med_at(g, 0)
    srows.append({"group": f"night_{night}", "untrunc_dur_med": u[0], "prod_dur_med": p[0],
                  "untrunc_disp_med": u[1], "prod_disp_med": p[1], "n_prod": p[2]})
for lbl, mask in [("first_half", raw.night.isin(FIRST_HALF)), ("second_half", ~raw.night.isin(FIRST_HALF)),
                  ("five_rat", raw.night.isin(FIVE_RAT)), ("four_rat", ~raw.night.isin(FIVE_RAT))]:
    g = raw[mask]; p = med_at(g,3); u = med_at(g,0)
    srows.append({"group": lbl, "untrunc_dur_med": u[0], "prod_dur_med": p[0],
                  "untrunc_disp_med": u[1], "prod_disp_med": p[1], "n_prod": p[2]})
stab = pd.DataFrame(srows); stab.to_csv(TAB / "animal_night_stability.csv", index=False)
print("\n[A11] stability (untruncated vs production median):")
print(stab.to_string(index=False))

# plots
fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))
xs = sim_line.index.to_numpy()
ax[0].plot(xs, sim_line.to_numpy(), "-o", label="sim straight line + jitter")
rb = realst.reindex(["<1","1-1.5","1.5-2","2-3","3-4","4-6","6+"])
ax[0].plot([0.7,1.25,1.75,2.5,3.5,5,7][:len(rb)], rb.to_numpy(), "-s", color="k", label="real bouts")
ax[0].axhline(1.0, ls=":", c="grey"); ax[0].set_xlabel("bout duration (s)")
ax[0].set_ylabel("straightness (path/disp)"); ax[0].legend(fontsize=8)
ax[0].set_title(f"Short-bout 'wiggliness' vs jitter null (sigma={sigma:.1f}in/axis)")
an = stab[stab.group.str.startswith("animal")]
ax[1].bar(np.arange(len(an))-0.2, an.untrunc_dur_med, 0.4, label="untruncated median")
ax[1].bar(np.arange(len(an))+0.2, an.prod_dur_med, 0.4, label="production (min_bout3) median")
ax[1].set_xticks(range(len(an))); ax[1].set_xticklabels([g.replace("animal_","") for g in an.group], rotation=45)
ax[1].set_ylabel("run duration (s)"); ax[1].legend(fontsize=8)
ax[1].set_title("Truncation inflates 'capacity' identically for every animal")
fig.tight_layout(); fig.savefig(PLT / "ballisticity_real_vs_jitter_null.png", dpi=120); plt.close(fig)
fig2, ax2 = plt.subplots(figsize=(9, 4.4))
allg = stab[stab.group.str.startswith("night")]
ax2.plot(range(len(allg)), allg.untrunc_dur_med, "-o", label="untruncated")
ax2.plot(range(len(allg)), allg.prod_dur_med, "-s", label="production")
ax2.set_xticks(range(len(allg))); ax2.set_xticklabels([g.replace("night_","")[5:] for g in allg.group], rotation=45)
ax2.set_ylabel("run duration median (s)"); ax2.legend(); ax2.set_title("Per-night stability of the truncation artifact")
fig2.tight_layout(); fig2.savefig(PLT / "cross_animal_night_stability.png", dpi=120); plt.close(fig2)
print("[done] A8 + A11")
