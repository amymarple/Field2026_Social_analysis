"""Analysis 1 (audit) + 2 (sensitivity surface) + 5 (does the scale move with the filter?).

Segments once per (smooth, moving_thr, pause_merge) with NO min-duration / min-disp filter,
then applies min_bout_s and min_disp_in as cheap post-filters. Tests whether the apparent
~4 s / ~100 in scale is fixed or tracks the segmentation parameters.
"""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

HERE = Path(__file__).resolve(); SRC = HERE.parent; ROOT = SRC.parent
sys.path.insert(0, str(SRC)); import bout_seg as bs
CACHE = Path(sys.argv[1]); TAB = ROOT / "tables"; PLT = ROOT / "plots"
TAB.mkdir(exist_ok=True); PLT.mkdir(exist_ok=True)
THR0 = 12.63; SMOOTH0 = 7

def mode_fixed(s, bw):
    s = np.asarray(s, float); s = s[np.isfinite(s)]
    if s.size == 0: return np.nan
    e = np.arange(s.min(), s.max() + bw, bw)
    if len(e) < 2: return float(np.median(s))
    h, e = np.histogram(s, bins=e)
    return float(0.5 * (e[h.argmax()] + e[h.argmax() + 1]))

def stats_row(b, cfg):
    d = b["dur_s"].to_numpy(); x = b["disp_in"].to_numpy()
    r = dict(cfg, n_bouts=len(b))
    if len(b):
        r.update(dur_median=round(float(np.median(d)), 2), dur_mode=round(mode_fixed(d, 0.5), 2),
                 dur_mean=round(float(d.mean()), 2), dur_cv=round(float(d.std()/d.mean()), 3),
                 dur_p90=round(float(np.percentile(d, 90)), 2), dur_p99=round(float(np.percentile(d, 99)), 2),
                 dur_max=round(float(d.max()), 2),
                 disp_median=round(float(np.median(x)), 1), disp_mode=round(mode_fixed(x, 10), 1),
                 disp_mean=round(float(x.mean()), 1), disp_cv=round(float(x.std()/x.mean()), 3),
                 disp_p90=round(float(np.percentile(x, 90)), 1), disp_p99=round(float(np.percentile(x, 99)), 1),
                 disp_max=round(float(x.max()), 1),
                 speed_median=round(float(b["speed_ips"].median()), 1),
                 straight_median=round(float(b["straight"].median()), 3),
                 dur_disp_corr=round(float(np.corrcoef(d, x)[0, 1]), 3) if len(b) > 2 else np.nan,
                 mean_n_pause=round(float(b["n_pause"].mean()), 2))
    return r

print("[load] positions + speed (smooth=7) ...")
pos = bs.load_positions(CACHE)
ps7 = bs.add_speed_param(pos, smooth_window=SMOOTH0)
# total moving-time denominator (for 'fraction retained')
def moving_time(ps, thr):
    tot = 0.0
    for _, g in ps.groupby(["night", "shortid"], sort=False):
        t = g["datetime"].values.astype("datetime64[ns]").astype("int64")/1e9
        sp = g["speed_inps_smooth"].to_numpy(); dt = np.diff(t)
        mv = (np.isfinite(sp) & (sp > thr))[1:] & (dt <= 2.0)
        tot += float(dt[mv].sum())
    return tot
MT = moving_time(ps7, THR0)

def raw_segments(ps, thr, pause):
    return bs.segment(ps, moving_thr=thr, min_bout_s=0.0, min_disp_in=0.0,
                      pause_merge_s=pause, max_gap_s=2.0)

# ---- sensitivity table: pause sweep (smooth7,thr1) x min_bout x min_disp ----
PAUSES = [0, 1, 2, 3, 5, 10, 20, 30]
MINB = [0, 1, 2, 3, 4, 5]
MIND = [0, 7, 15, 21, 30]
rows = []
seg_cache = {}
print("[sweep] pause x min_bout x min_disp (smooth7, thr1.0) ...")
for pause in PAUSES:
    raw = raw_segments(ps7, THR0, pause); seg_cache[pause] = raw
    for mb in MINB:
        for md in MIND:
            b = raw[(raw["dur_s"] >= mb) & (raw["disp_in"] >= md)]
            cfg = {"smooth": SMOOTH0, "thr_x": 1.0, "pause_s": pause, "min_bout_s": mb, "min_disp_in": md}
            r = stats_row(b, cfg)
            r["frac_move_time_retained"] = round(float(b["dur_s"].sum()/MT), 3) if MT else np.nan
            rows.append(r)
# ---- thr sweep (smooth7, pause0) ----
print("[sweep] moving-threshold ...")
for tx in [0.75, 1.25, 1.5]:
    raw = raw_segments(ps7, THR0*tx, 0)
    for mb in [0, 3]:
        b = raw[(raw["dur_s"] >= mb) & (raw["disp_in"] >= 15)]
        rows.append(stats_row(b, {"smooth": SMOOTH0, "thr_x": tx, "pause_s": 0, "min_bout_s": mb, "min_disp_in": 15}))
# ---- smooth sweep (thr1, pause0) ----
print("[sweep] smoothing window ...")
for sw in [1, 3, 15]:
    psx = bs.add_speed_param(pos, smooth_window=sw)
    raw = bs.segment(psx, moving_thr=THR0, min_bout_s=0.0, min_disp_in=0.0, pause_merge_s=0, max_gap_s=2.0)
    for mb in [0, 3]:
        b = raw[(raw["dur_s"] >= mb) & (raw["disp_in"] >= 15)]
        rows.append(stats_row(b, {"smooth": sw, "thr_x": 1.0, "pause_s": 0, "min_bout_s": mb, "min_disp_in": 15}))

sens = pd.DataFrame(rows)
sens.to_csv(TAB / "parameter_sensitivity.csv", index=False)
print(f"  wrote parameter_sensitivity.csv ({len(sens)} rows)")

# ---- Analysis 5: does the scale move with min_bout? (pause0, disp15) ----
sub = sens[(sens.pause_s == 0) & (sens.min_disp_in == 15) & (sens.thr_x == 1.0) & (sens.smooth == 7)]
sub = sub.sort_values("min_bout_s")
A5 = sub[["min_bout_s", "dur_mode", "dur_median", "disp_mode", "disp_median", "n_bouts"]].copy()
# linear fits observed-scale ~ a + b*min_bout
def lin(x, y):
    x = np.asarray(x, float); y = np.asarray(y, float); m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 2: return np.nan, np.nan, np.nan
    b1, b0 = np.polyfit(x[m], y[m], 1)
    yhat = b0 + b1 * x[m]; ss = 1 - ((y[m]-yhat)**2).sum()/max(((y[m]-y[m].mean())**2).sum(), 1e-9)
    return round(float(b0), 2), round(float(b1), 2), round(float(ss), 3)
vbar = float(sub["speed_median"].median())
fit = {"dur_median_vs_minbout": lin(A5.min_bout_s, A5.dur_median),
       "dur_mode_vs_minbout": lin(A5.min_bout_s, A5.dur_mode),
       "disp_median_vs_minbout": lin(A5.min_bout_s, A5.disp_median),
       "disp_mode_vs_minbout": lin(A5.min_bout_s, A5.disp_mode),
       "median_speed_ips": vbar,
       "predicted_disp_slope_if_scale_is_minbout_times_speed": round(vbar, 2)}
A5.to_csv(TAB / "scale_vs_minbout.csv", index=False)
(TAB / "scale_vs_minbout_fits.json").write_text(json.dumps(fit, indent=2))
print("[A5] fits (intercept, slope, R2):", json.dumps(fit, indent=2))

# ---- surface: min_bout x pause -> dur_median, disp_median ----
durM = np.full((len(MINB), len(PAUSES)), np.nan); dispM = durM.copy()
for j, pause in enumerate(PAUSES):
    raw = seg_cache[pause]
    for i, mb in enumerate(MINB):
        b = raw[(raw["dur_s"] >= mb) & (raw["disp_in"] >= 15)]
        if len(b):
            durM[i, j] = np.median(b["dur_s"]); dispM[i, j] = np.median(b["disp_in"])

def heat(M, title, fname, cbar):
    fig, ax = plt.subplots(figsize=(8, 4.6))
    im = ax.imshow(M, aspect="auto", cmap="viridis", origin="lower")
    ax.set_xticks(range(len(PAUSES))); ax.set_xticklabels(PAUSES)
    ax.set_yticks(range(len(MINB))); ax.set_yticklabels(MINB)
    ax.set_xlabel("pause-merge threshold (s)"); ax.set_ylabel("min bout duration (s)")
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            if np.isfinite(M[i, j]):
                ax.text(j, i, f"{M[i,j]:.0f}", ha="center", va="center", color="w", fontsize=8)
    ax.set_title(title); fig.colorbar(im, label=cbar); fig.tight_layout()
    fig.savefig(PLT / fname, dpi=120); plt.close(fig)
heat(durM, "Median bout DURATION (s) vs segmentation params\n(if fixed → moves only with min-bout row)",
     "duration_by_segmentation_parameters.png", "median dur (s)")
heat(dispM, "Median bout DISPLACEMENT (in) vs segmentation params",
     "displacement_by_segmentation_parameters.png", "median disp (in)")

# ---- A5 plots ----
fig, ax = plt.subplots(1, 2, figsize=(12, 4.4))
ax[0].plot(A5.min_bout_s, A5.dur_median, "-o", label="median")
ax[0].plot(A5.min_bout_s, A5.dur_mode, "-s", label="mode")
ax[0].plot(A5.min_bout_s, A5.min_bout_s, "k--", label="y = min_bout (1:1)")
ax[0].set_xlabel("imposed min bout duration (s)"); ax[0].set_ylabel("observed duration (s)")
ax[0].set_title("Duration scale vs imposed minimum"); ax[0].legend(fontsize=8)
ax[1].plot(A5.min_bout_s, A5.disp_median, "-o", label="median disp")
ax[1].plot(A5.min_bout_s, A5.disp_mode, "-s", label="mode disp")
ax[1].plot(A5.min_bout_s, A5.min_bout_s*vbar, "k--", label=f"y = min_bout x {vbar:.0f} in/s")
ax[1].set_xlabel("imposed min bout duration (s)"); ax[1].set_ylabel("observed displacement (in)")
ax[1].set_title("Displacement scale vs min_bout x speed prediction"); ax[1].legend(fontsize=8)
fig.tight_layout(); fig.savefig(PLT / "duration_mode_vs_minimum_duration.png", dpi=120); plt.close(fig)
fig.savefig(PLT / "displacement_mode_vs_filter_prediction.png", dpi=120)
print("[done] sensitivity + surface + A5")
