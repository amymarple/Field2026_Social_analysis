r"""IMU movement vs WISER tag speed for one night: identity matrix, lag, stillness agreement (validation, 2026-09-28).

Reads only local data: per-second IMU tables (ephys/make_imu.py, D:\3rd_rat_spikes\analysis\imu) and the WISER
incremental exports on the local backup (F:\wiser\Wiser_backup\incremental). Tags per animal = Notion cohort page
(hex): SF07 3079, SF08 3062, SF09 3077, SF10 306B, SF12 3059 (SF11 wore 305A until 09-02 00:03, then 3058 until
09-07 08:20; SF12 also wore 3058 until 08-31 19:24) - the default night (09-08 20:00 -> 09-09 06:00) avoids both
changes. Result 2026-09-28: every logger's best tag is its own (Spearman r 0.62-0.77 vs <= 0.25 off-diagonal); matched
pairs peak at +1..+2 s (about +1 s is from the backward 2-s WISER displacement); WISER shows ~1.1 in/s while the
IMU is still (UWB jitter).

Usage: python ephys/imu_wiser_crosscheck.py
"""
import glob
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

TZ = ZoneInfo("America/New_York")
T0 = datetime(2026, 9, 8, 20, 0, tzinfo=TZ)
T1 = datetime(2026, 9, 9, 6, 0, tzinfo=TZ)
t0_ms, t1_ms = int(T0.timestamp() * 1000), int(T1.timestamp() * 1000)
TAGS = {"SF07": 0x3079, "SF08": 0x3062, "SF09": 0x3077, "SF10": 0x306B, "SF12": 0x3059}
SMOOTH_S = 10          # rolling window for both series (s)
LAGS = range(-30, 31)

# ---- WISER: dedup, 1-s median position per tag, speed over 2 s
frames = [pd.read_csv(f, usecols=["shortid", "timestamp", "location_x", "location_y"])
          for f in sorted(glob.glob(r"F:/wiser/Wiser_backup/incremental/3rdcohort_Spike_2026_3_4_2026-09-0[89].csv.gz"))]
w = pd.concat(frames).drop_duplicates()
w = w[(w.timestamp >= t0_ms) & (w.timestamp < t1_ms)]
secs = np.arange(t0_ms // 1000, t1_ms // 1000)
wiser = {}
for an, tag in TAGS.items():
    d = w[w.shortid == tag].copy()
    d["sec"] = d.timestamp // 1000
    m = d.groupby("sec")[["location_x", "location_y"]].median().reindex(secs)
    xy = m.to_numpy()
    sp = np.full(len(secs), np.nan)
    sp[2:] = np.linalg.norm(xy[2:] - xy[:-2], axis=1) / 2.0            # in/s over 2 s
    wiser[an] = pd.Series(sp, index=secs)
    print(f"WISER {an} tag {tag}: {len(d):,} fixes, {np.isfinite(sp).mean():.0%} of seconds with speed, median {np.nanmedian(sp):.1f} in/s")

# ---- IMU: per-second tables of every session, indexed by field-PC unix second
imu = {}
for an in TAGS:
    parts = []
    for f in glob.glob(rf"D:/3rd_rat_spikes/analysis/imu/{an}/*.imu_1s.csv"):
        d = pd.read_csv(f, usecols=["t_pc_unix_ms", "vedba_mean", "omega_mean", "turn_abs_deg"])
        d = d[(d.t_pc_unix_ms >= t0_ms) & (d.t_pc_unix_ms < t1_ms)]
        if len(d):
            parts.append(d)
    d = pd.concat(parts)
    d["sec"] = (d.t_pc_unix_ms // 1000).astype(np.int64)
    imu[an] = d.groupby("sec")["vedba_mean"].mean().reindex(secs)
    print(f"IMU   {an}: {imu[an].notna().mean():.0%} of seconds covered, median VeDBA {imu[an].median():.2f} m/s^2")

def smooth_log(s):
    return np.log10(s.rolling(SMOOTH_S, center=True, min_periods=SMOOTH_S // 2).mean() + 0.02)

L_imu = {a: smooth_log(s) for a, s in imu.items()}
L_ws = {a: smooth_log(s) for a, s in wiser.items()}

# ---- identity matrix (Spearman on the smoothed log series)
names = list(TAGS)
M = pd.DataFrame(index=[f"IMU {a}" for a in names], columns=[f"tag {a}" for a in names], dtype=float)
for a in names:
    for b in names:
        ok = L_imu[a].notna() & L_ws[b].notna()
        M.loc[f"IMU {a}", f"tag {b}"] = L_imu[a][ok].rank().corr(L_ws[b][ok].rank())
print("\nSpearman r, IMU movement (rows) vs WISER speed (columns), 10-s smoothed, 20:00-06:00:")
print(M.round(2).to_string())
best = {a: M.loc[f"IMU {a}"].astype(float).idxmax() for a in names}
print("best tag per logger:", best)

# ---- lag of the matched pairs (positive lag = WISER later than IMU)
print("\nlag scan (matched pairs): peak lag s, r at peak, r at 0")
for a in names:
    rs = []
    for lag in LAGS:
        x, y = L_imu[a], L_ws[a].shift(-lag)
        ok = x.notna() & y.notna()
        rs.append(x[ok].corr(y[ok]))
    rs = np.array(rs)
    k = int(np.nanargmax(rs))
    print(f"  {a}: peak {list(LAGS)[k]:+d} s  r {rs[k]:.3f}  (r at 0: {rs[list(LAGS).index(0)]:.3f})")

# ---- stillness agreement: IMU still (VeDBA < 0.2 m/s^2, provisional) vs WISER speed
print("\nWISER speed (in/s, 1-s, 2-s displacement) when the IMU says still vs moving (provisional VeDBA 0.2 m/s^2):")
for a in names:
    still = imu[a] < 0.2
    mov = imu[a] >= 0.2
    ws = wiser[a]
    print(f"  {a}: still {np.nanmedian(ws[still]):5.1f} (p90 {np.nanpercentile(ws[still], 90):5.1f})   "
          f"moving {np.nanmedian(ws[mov]):5.1f} (p90 {np.nanpercentile(ws[mov], 90):5.1f})   still share {still.mean():.0%}")
