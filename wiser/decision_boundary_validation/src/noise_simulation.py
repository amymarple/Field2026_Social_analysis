"""Analysis 7 — WISER jitter / sampling null for the boundary tests.

DECISIVE control: simulate STRAIGHT-LINE motion (no real turns) with a realistic speed profile
that includes sub-threshold pauses, add WISER stationary jitter, run through the EXACT pause
detection + robust-heading pipeline, and measure the apparent matched pause-vs-continuous turn
difference. If the null reproduces the real +18 deg, the effect is a jitter artifact (pauses have
low flanking displacement -> heading is jitter-dominated). Also: false-positive heading-changepoint
rate on straight/speed-change trajectories, and heading bias vs flank displacement.
"""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

HERE = Path(__file__).resolve(); SRC = HERE.parent; ROOT = SRC.parent
sys.path.insert(0, str(SRC)); import dbv_common as dc
sys.path.insert(0, str(dc._BSV)); import bout_seg as bs
CACHE = Path(sys.argv[1]); TAB = ROOT / "tables"; PLT = ROOT / "plots"
rng = np.random.default_rng(7)
THR = dc.MOVING_THR; JIT = dc.JITTER_IN; SIGMA = 5.0; DT = 0.228; TURN_CP_DEG = 40.0

# real speed profile to sample realistic pauses/slowdowns
pos = bs.load_positions(CACHE); ps = bs.add_speed_param(pos, smooth_window=7, speed_window_s=1.0)
real_speed = ps["speed_inps_smooth"].to_numpy(); real_speed = real_speed[np.isfinite(real_speed)]

def win_heading(t, xs, ys, wsz, side):
    n = len(t)
    if side == "pre":
        j = np.clip(np.searchsorted(t, t-wsz, "left"), 0, n-1); dx = xs-xs[j]; dy = ys-ys[j]
    else:
        j = np.clip(np.searchsorted(t, t+wsz, "right")-1, 0, n-1); dx = xs[j]-xs; dy = ys[j]-ys
    disp = np.hypot(dx, dy)
    return np.where(disp > JIT, np.arctan2(dy, dx), np.nan), disp

def simulate(kind, n=3000):
    """One trajectory. kind: 'straight_pauses' (no turns), 'speed_change' (no turns),
    'real_turn' (a true 90 deg turn while moving), 'pause_turn' (stop then 90 deg turn)."""
    theta = rng.uniform(0, 2*np.pi)
    v = rng.choice(real_speed, n)                    # realistic speed incl. sub-threshold
    if kind == "speed_change":
        v = np.where(np.arange(n) % 40 < 20, np.percentile(real_speed, 80), np.percentile(real_speed, 20))
    heads = np.full(n, theta)
    if kind in ("real_turn", "pause_turn"):
        heads[n//2:] = theta + np.pi/2                # 90 deg turn at midpoint
        if kind == "pause_turn":
            v[n//2-3:n//2+3] = 0.0                    # stop at the turn
    # integrate true path
    x = np.cumsum(np.cos(heads)*v*DT); y = np.cumsum(np.sin(heads)*v*DT)
    x += rng.normal(0, SIGMA, n); y += rng.normal(0, SIGMA, n)
    t = np.arange(n)*DT
    xs = pd.Series(x).rolling(7, center=True, min_periods=1).median().to_numpy()
    ys = pd.Series(y).rolling(7, center=True, min_periods=1).median().to_numpy()
    # window speed
    half = 0.5; lo = np.clip(np.searchsorted(t, t-half, "left"), 0, n-1); hi = np.clip(np.searchsorted(t, t+half, "right")-1, 0, n-1)
    sp = np.hypot(xs[hi]-xs[lo], ys[hi]-ys[lo])/np.clip(t[hi]-t[lo], 1e-6, None)
    return t, xs, ys, sp

def matched_null_turn(ntraj=200):
    """apparent turn at simulated pauses vs continuous on STRAIGHT-with-pauses trajectories."""
    tp, tc = [], []
    for _ in range(ntraj):
        t, xs, ys, sp = simulate("straight_pauses")
        moving = np.isfinite(sp) & (sp > THR)
        starts, ends = bs._atomic_runs(moving, t, dc.MAX_GAP_S)
        preH = win_heading(t, xs, ys, 1.0, "pre")[0]; postH = win_heading(t, xs, ys, 1.0, "post")[0]
        turn = np.degrees(np.abs(np.angle(np.exp(1j*(postH-preH)))))
        for r in range(1, len(starts)):
            ci = (ends[r-1]+starts[r])//2
            if np.isfinite(turn[ci]): tp.append(turn[ci])
        for (i0, i1) in zip(starts, ends):
            for i in range(i0+3, i1-3, 5):
                if np.isfinite(turn[i]): tc.append(turn[i])
    tp, tc = np.array(tp), np.array(tc)
    return {"null_mean_turn_pause": round(float(np.nanmean(tp)), 1),
            "null_mean_turn_continuous": round(float(np.nanmean(tc)), 1),
            "null_turn_diff": round(float(np.nanmean(tp)-np.nanmean(tc)), 1),
            "null_P>90_pause": round(float((tp > 90).mean()), 3),
            "null_P>90_continuous": round(float((tc > 90).mean()), 3), "n_pause": len(tp)}

null_turn = matched_null_turn()

# false-positive heading_cp rate on straight & speed-change (should be ~0 real turns)
def fp_rate(kind, ntraj=100):
    fp = tot = 0
    for _ in range(ntraj):
        t, xs, ys, sp = simulate(kind)
        moving = np.isfinite(sp) & (sp > THR)
        preH = win_heading(t, xs, ys, 0.75, "pre")[0]; postH = win_heading(t, xs, ys, 0.75, "post")[0]
        turn = np.degrees(np.abs(np.angle(np.exp(1j*(postH-preH)))))
        starts, ends = bs._atomic_runs(moving, t, dc.MAX_GAP_S)
        for (i0, i1) in zip(starts, ends):
            seg = np.arange(i0+2, i1-1)
            cp = seg[(turn[seg] > TURN_CP_DEG) & moving[seg]]
            fp += len(cp); tot += len(seg)
    return round(fp/max(tot, 1), 4)

# detection sensitivity: real_turn / pause_turn SHOULD be detected
def detect_rate(kind, ntraj=100):
    det = 0
    for _ in range(ntraj):
        t, xs, ys, sp = simulate(kind)
        mid = len(t)//2
        preH = win_heading(t, xs, ys, 1.0, "pre")[0]; postH = win_heading(t, xs, ys, 1.0, "post")[0]
        turn = np.degrees(np.abs(np.angle(np.exp(1j*(postH-preH)))))
        if np.nanmax(turn[mid-5:mid+5]) > TURN_CP_DEG: det += 1
    return round(det/ntraj, 3)

# heading resolution bias vs flank displacement (few bins)
bias = []
for _ in range(300):
    t, xs, ys, sp = simulate("straight_pauses", n=200)
    preH = win_heading(t, xs, ys, 1.0, "pre"); postH = win_heading(t, xs, ys, 1.0, "post")
    turn = np.degrees(np.abs(np.angle(np.exp(1j*(postH[0]-preH[0])))))
    fd = np.minimum(preH[1], postH[1])
    for tt, ff in zip(turn, fd):
        if np.isfinite(tt): bias.append((ff, tt))
bias = pd.DataFrame(bias, columns=["flank_disp_in", "apparent_turn_deg"])
bias["db"] = pd.cut(bias.flank_disp_in, [0, 10, 15, 25, 40, 200])
biasg = bias.groupby("db", observed=True)["apparent_turn_deg"].median().round(1)

out = {"matched_null_turn (straight+pauses, NO real turns)": null_turn,
       "false_positive_heading_cp_rate": {"straight_pauses": fp_rate("straight_pauses"),
                                          "speed_change": fp_rate("speed_change")},
       "detection_sensitivity": {"real_turn_90deg": detect_rate("real_turn"),
                                 "pause_turn_90deg": detect_rate("pause_turn")},
       "apparent_turn_vs_flank_disp_median": {str(k): float(v) for k, v in biasg.items()},
       "sigma_per_axis_in": SIGMA, "real_matched_pause_turn_diff_for_comparison": 17.9}
(TAB / "noise_null_results.json").write_text(json.dumps(out, indent=2))
print(json.dumps(out, indent=2))
fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))
ax[0].bar(["pause\n(null)", "continuous\n(null)", "pause\n(REAL)", "continuous\n(REAL)"],
          [null_turn["null_mean_turn_pause"], null_turn["null_mean_turn_continuous"], 43.0, 25.0],
          color=["#c99", "#9c9", "#c33", "#3a3"])
ax[0].set_ylabel("mean turn (deg)"); ax[0].set_title("Matched pause turn: jitter null vs real\n(real diff must EXCEED null diff)")
ax[1].plot(biasg.index.astype(str), biasg.values, "-o")
ax[1].set_xlabel("flank displacement bin (in)"); ax[1].set_ylabel("apparent turn (deg, straight path)")
ax[1].set_title("Jitter-induced apparent turn vs flank displacement")
fig.tight_layout(); fig.savefig(PLT / "real_vs_noise_null.png", dpi=120)
print("[done] noise simulation")
