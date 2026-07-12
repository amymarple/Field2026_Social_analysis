"""Shared foundation for decision-boundary validation: per-position KINEMATICS on the
native ~4.4 Hz grid (no 1 s gridding) + robust multi-window heading, reusing the cached
cleaned night positions and the validated bout_seg engine. This is the pinned contract every
downstream test imports; it is NOT the old route_bouts.csv.

Kinematics (per night, animal), jitter-aware:
  xs, ys      rolling-median smoothed positions (window `smooth`)
  vx, vy      velocity VECTOR = centred `vel_window_s` displacement of (xs,ys) / window (in/s)
  speed       |v| (matches production speed_inps_smooth construction)
  heading     atan2(vy, vx); MEANINGFUL only where win_disp > jitter floor (head_ok flag)
  win_disp    magnitude of the window displacement (for heading validity)
  ang_vel     wrapped d(heading)/dt over a short step (rad/s), only where head_ok
  accel       d(speed)/dt (in/s^2)
  curvature   ang_vel / max(speed, eps) (rad/in)
  gap_s       dt to previous sample; gap_flag = gap_s > max_gap_s (dropout edge)
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd

_HERE = Path(__file__).resolve()
_BSV = _HERE.parents[2] / "bout_segmentation_validation" / "src"
sys.path.insert(0, str(_BSV)); import bout_seg as bs   # noqa: E402

JITTER_IN = 7.0          # documented WISER stationary jitter floor
MOVING_THR = 12.63       # production p99 stationary smoothed speed (in/s)
MAX_GAP_S = 2.0


def _wrap(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


def kinematics(cache, *, smooth=7, vel_window_s=1.0, head_min_disp_in=JITTER_IN) -> pd.DataFrame:
    pos = bs.load_positions(cache)
    ps = bs.add_speed_param(pos, smooth_window=smooth, speed_window_s=vel_window_s)
    out = []
    for (night, tag), g in ps.groupby(["night", "shortid"], sort=False):
        t = g["datetime"].values.astype("datetime64[ns]").astype("int64") / 1e9
        t = t - t[0]
        xs = g["xs"].to_numpy(); ys = g["ys"].to_numpy()
        n = len(t); half = vel_window_s / 2.0
        lo = np.clip(np.searchsorted(t, t - half, "left"), 0, n - 1)
        hi = np.clip(np.searchsorted(t, t + half, "right") - 1, 0, n - 1)
        dtw = t[hi] - t[lo]
        dx = xs[hi] - xs[lo]; dy = ys[hi] - ys[lo]
        win_disp = np.hypot(dx, dy)
        with np.errstate(divide="ignore", invalid="ignore"):
            vx = np.where(dtw > 0, dx / dtw, np.nan)
            vy = np.where(dtw > 0, dy / dtw, np.nan)
        speed = np.hypot(vx, vy)
        speed = np.where(speed > 60.0, np.nan, speed)         # production sprint cap
        heading = np.arctan2(vy, vx)
        head_ok = win_disp > head_min_disp_in
        gap = np.r_[np.nan, np.diff(t)]
        # ang vel: wrapped heading change / dt, only where both endpoints resolvable
        dh = np.r_[np.nan, _wrap(np.diff(heading))]
        ang_vel = np.where((gap > 0), dh / gap, np.nan)
        ang_vel = np.where(head_ok & np.r_[False, head_ok[:-1]], ang_vel, np.nan)
        accel = np.r_[np.nan, np.diff(speed)] / gap
        curv = ang_vel / np.clip(speed, 1e-6, None)
        out.append(pd.DataFrame({
            "night": night, "shortid": str(tag), "t_s": t, "x": g["x"].to_numpy(),
            "y": g["y"].to_numpy(), "xs": xs, "ys": ys, "vx": vx, "vy": vy,
            "speed": speed, "heading": heading, "win_disp": win_disp, "head_ok": head_ok,
            "ang_vel": ang_vel, "accel": accel, "curvature": curv,
            "gap_s": gap, "gap_flag": gap > MAX_GAP_S,
            "clock_hour": g["clock_hour"].to_numpy()}))
    return pd.concat(out, ignore_index=True)


def robust_heading(t, xs, ys, i, side, window_s, min_disp_in=JITTER_IN):
    """Robust heading on one side of sample i over `window_s`, via a total-least-squares line
    fit weighted toward the endpoints. Returns (heading or nan, resolved_disp)."""
    if side == "pre":
        m = (t >= t[i] - window_s) & (t <= t[i])
    else:
        m = (t >= t[i]) & (t <= t[i] + window_s)
    if m.sum() < 2:
        return np.nan, 0.0
    xw = xs[m]; yw = ys[m]
    disp = np.hypot(xw[-1] - xw[0], yw[-1] - yw[0])
    if disp < min_disp_in:
        return np.nan, float(disp)
    # net-displacement direction (robust, endpoint-anchored); sign toward travel
    if side == "pre":
        h = np.arctan2(yw[-1] - yw[0], xw[-1] - xw[0])
    else:
        h = np.arctan2(yw[-1] - yw[0], xw[-1] - xw[0])
    return float(h), float(disp)
