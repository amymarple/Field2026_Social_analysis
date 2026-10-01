# -*- coding: utf-8 -*-
r"""Head-IMU video review (cohort 2026c): one clip per IMU event with the IMU's guess burnt in, plus a local review page.

Request (user, 2026-10-01): "make video clips and on the top of the frame show what you think the animal is doing from
shake or still. also tell me what animal is doing what. i need gui for this". Plan:
implementation_plan/2026-10-01-imu-video-review.md. The PERSON judges every frame; this script never looks at an image
(the self-test checks synthetic frames numerically only).

EVENTS  the rows of the gate-v2 `human_checks.csv` (default: `<fitted.run_dir>/human_checks.csv` of
        wiser/configs/imu_attitude_gate_v2_<c>.json; 20 strict still windows, 20 gyro-clipped shake trains, 10 largest-error
        test bouts). Times = field-PC local (EDT, naive); the IMU clock is field-PC Unix ms via the pc_time chain (tau*
        not applied; WISER lags the IMU by ~0.15 s, below the 1-s WISER bins used here).
CLIP    event start - 5 s -> event end + 5 s from the local video copy `F:\3rd_rat\<date>\<CH>\` (read-only), located by
        the FILE-NAME time (field-PC; `cv/cv_field/grab_frames.py segments()`, incl. never-renamed segments and the
        previous date folder). Never the burnt-in OSD (NVR clock, ~59.5 min behind). File-name time is good to ~+-1 s
        (1-s name resolution + recorder start latency); the review page lets the user shift the IMU traces and records the
        offset seen. Hour-file boundaries: one part per segment, placed at its own file-name time; frames missing in
        a camera show the dark canvas + "NO VIDEO".
CAMERAS WISER position at the event = median of the animal's valid 1-s fix medians (A2 cache
        `wiser_fix_cache/<period>/<SFxx>.csv.gz`; valid & not handling / silence / tag-validity / ADC-lane, as gate v2)
        over event +- 2 s (widened to +- 30 s if empty) -> zone by the house rectangles of wiser/configs/wiser_rois.json
        grown by 14 in (wiser_analysis_utils._rect_membership; the IMU<->WISER calibration pilot's house rule; WISER
        frame = inches, unverified origin): house_1 -> CH08 in-box + CH05 top-down; house_2 -> CH07 in-box + CH06
        top-down; outside / no WISER -> CH01 + CH02 panoramas (stored rotated; shown upright = 90 deg counter-clockwise).
        Majority zone over the 1-s medians in the window decides; mixtures are reported.
LAYOUT  houses: two 2560x1920 views side by side at equal height (2 x 1920x1440 -> 3840 wide); panoramas: two 7680x2160
        upright views stacked (2 x 3712x1044 -> 3712 wide); a 216-px dark banner on top (total height <= 2304, the usual
        H.264 hardware-decoder limit); 20 fps constant; H.264 yuv420p, faststart, GOP 1 s; h264_nvenc (VBR cq 26: SSIM
        0.981-0.986 vs a cq-14 reference on an in-box and a panorama sample, ~2/3 of the cq-23 size) with libx264 (preset
        veryfast, crf 24) as fallback.
OVERLAY ASS subtitles (ffmpeg `subtitles`, DejaVu Sans): rows 1-2 static = "<SFxx> . tag <hex> . IR mark: <pattern>
        (coban <colour>) . IMU event: <type + numbers>" / "<start> field-PC (file-name time, +-1 s) . <cams> . WISER: <zone>";
        row 3 dynamic every 0.25 s = "IMU now: <state> . |w| <deg/s> . |a|-g <m/s^2> . <field-PC hh:mm:ss.ss>" plus
        "EVENT" (with a triangle) while inside the event span; a small label per view; "NO VIDEO" in a view without frames.

IMU STATE per 0.25-s bin (the IMU's GUESS for the user to check; first rule that holds wins). Inputs: A3 100-Hz
calibrated head-frame IMU `imu100_cache/<SFxx>/<period>.npz` (acc m/s^2, gyr = 1.03 (w - b) deg/s, flags), the gate-v2
clipped-run table `sat_runs.csv.gz`, the A2 WISER fixes. Symbols: |w| = norm of gyr (deg/s); |a| = norm of acc (m/s^2);
g = 9.81 m/s^2; P_b = gyro band power in band b (below).
  1 SHAKE       the bin overlaps a gyro-clipped shake train (sat_runs class `shake_train`, span first run - 25 ms ->
                last run end + 25 ms) OR [max P_12-20 in the bin > its 99th percentile over the animal-period's valid
                samples AND max |a| in the bin > 2 g].
  2 STILL       >= 50 % of the bin's samples inside a gate-v2 strict still window: `detect_strict` (imported unchanged)
                on the whole period with the gate's candidate mask (in the period window, not frozen, not handling,
                IMU valid, no acc/gyro saturation): 0.1-s blocks; every block's acc direction within 0.3 deg of the
                window-mean direction, | |mean acc| - g | < 0.03 g, every |w| < 3 deg/s, >= 1.0 s.
  3 QUIET       (state ADDED to the requested list) >= 50 % of the bin's samples A3-quiet (make_imu 1-s rule: median |w|
                < 10 deg/s and | k_a median |a| - g | < 0.05 g) but not STILL: resting with small movements (breathing,
                slight head adjustments) that the strict rule rejects; without it those bins would read ACTIVE.
  4 LOCOMOTION  WISER 1-s speed >= 10 in/s (median library `speed_inps_smooth` of the second's valid fixes; the
                second containing the bin centre).
  5 RHYTHMIC 4-12 Hz   P_4-12 >= 0.6 x P_2-20 AND P_4-12 >= 400 (deg/s)^2 (bin means; 400 = RMS 20 deg/s, i.e. a
                ~0.75-deg head oscillation at 6 Hz; one absolute floor because the per-period median of the non-quiet
                samples differed ~10^4-fold between day sleep and night, 2026-10-01 trial). Could be grooming, scratching,
                sniffing or chewing - the label never names one.
  6 ACTIVE      anything else.
  0 NO IMU      < 50 % of the bin's samples present and not frozen.
Band power P_b (b = 2-4, 4-8, 8-12, 12-20 Hz; P_2-20 = their sum, P_4-12 = P_4-8 + P_8-12): Butterworth-4 zero-phase
band-pass of EACH gyro axis, squared, summed over the three axes, 0.5-s centred moving mean, (deg/s)^2. Deviation from
the A4 16-Hz cache: its bp_* are band powers of the norm |w|, which moves an oscillation's fundamental to 2f (a 15-Hz
shake -> 30 Hz, outside 12-20 Hz), and A4 exists for nights only. Display numbers per bin: |w| = bin mean (deg/s);
|a|-g = RMS of (|a| - g) over the bin (m/s^2).

Outputs (off-repo): `$FIELD2026_ANALYSIS_OUT_ROOT/<c>/imu_video_review_<ts>/` = `clips/*.mp4`, `index.html` (the review
page; data embedded, works from file://), `events.json`, `event_summary.csv`, `overlay_ass/*.ass` (the exact overlays),
`_fonts/`, `README.md`, `log.txt`. Human judgements exported from the page belong in
`wiser/configs/imu_video_review_<c>/` (commit them).

Usage (base Python + ffmpeg; node only for the self-test):
  python wiser/scripts/make_imu_video_review.py --cohort 2026c [--checks <human_checks.csv>] [--root F:\3rd_rat]
         [--encoder auto|nvenc|x264] [--workers 3] [--only 1 5 22]
  python wiser/scripts/make_imu_video_review.py --html-only <run_dir>      # rebuild index.html from events.json
  python wiser/scripts/make_imu_video_review.py --selftest                 # synthetic clips/signals, no field data
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import signal
from scipy.ndimage import uniform_filter1d

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "wiser" / "src"))
sys.path.insert(0, str(REPO / "wiser" / "scripts"))
sys.path.append(str(REPO / "ephys"))
import output_paths  # noqa: E402  (wiser shim -> common/output_paths.py)
import wiser_analysis_utils as WU  # noqa: E402  (_rect_membership)
import analyze_imu_attitude_gate_v2 as G2  # noqa: E402  (load_cfg, context, detect_strict, load_fixes, to_ms; unmodified)

_saved_path = list(sys.path)
sys.path.append(str(REPO / "cv" / "cv_field"))
import grab_frames as GF  # noqa: E402  (segments, probe_duration, find_ffmpeg; unmodified - it prepends cv/ paths)
sys.path[:] = _saved_path

NAME = "imu_video_review"
TZ = "America/New_York"
G = G2.G
FS100 = 100.0
CLIP_PAD_S = 5.0
FPS = 20
BIN_S = 0.25
BANNER_H = 216
HOUSE_BUFFER_IN = 14.0
WISER_PAD_S = (2.0, 30.0)
SHAKE_TRAIN_PAD_MS = 25.0
SHAKE_PCTL = 99.0
SHAKE_ACC_G = 2.0
RHYTHM_FRAC = 0.6
RHYTHM_FLOOR = 400.0                   # (deg/s)^2: RMS 20 deg/s in 4-12 Hz
LOCO_SPEED_INPS = 10.0
BANDS = ((2.0, 4.0), (4.0, 8.0), (8.0, 12.0), (12.0, 20.0))
BP_WIN_S = 0.5
MIN_FRAC = 0.5
BASE_RGB = (0x18, 0x18, 0x18)

# code -> (name, colour); the same colours are used in the overlay and the review page
STATES = [("NO IMU", "#5a5f66"), ("STILL", "#4da3ff"), ("QUIET", "#9cc3e6"), ("ACTIVE", "#c9d1d9"),
          ("RHYTHMIC 4–12 Hz", "#e3b341"), ("LOCOMOTION", "#3fb950"), ("SHAKE", "#ff5c57")]
S_NOIMU, S_STILL, S_QUIET, S_ACTIVE, S_RHYTHM, S_LOCO, S_SHAKE = range(7)

CAMS = {"house_1": [("CH08", "in-box · house_1"), ("CH05", "top-down · house_1")],
        "house_2": [("CH07", "in-box · house_2"), ("CH06", "top-down · house_2")],
        "outside": [("CH01", "panorama (upright)"), ("CH02", "panorama (upright)")]}
TYPE_SHORT = {"strict still window": "still", "shake train (gyro clipped)": "shake", "largest-error test bout": "bout"}
TYPE_LABEL = {"still": "STILL win", "shake": "SHAKE train", "bout": "ERR bout"}

THRESHOLDS = [
    ["Clip", "event start − 5 s → event end + 5 s; file-name (field-PC) time, ±1 s; 20 fps; never the burnt-in OSD clock (≈ 59½ min behind)"],
    ["Camera choice", "WISER valid 1-s medians over the event ± 2 s (± 30 s if empty) → house ROI (wiser_rois.json) grown by 14 in: house_1 → CH08 in-box + CH05 top-down; house_2 → CH07 in-box + CH06 top-down; outside / no WISER → CH01 + CH02 panoramas"],
    ["SHAKE", "bin overlaps a gyro-clipped shake train (gate-v2 sat_runs, ± 25 ms) OR (gyro 12–20 Hz band power > its 99th percentile in the animal-period AND max |a| > 2 g)"],
    ["STILL", "≥ 50 % of the bin in a gate-v2 strict still window: acc direction within 0.3° of the window mean, ||ā| − g| < 0.03 g, |ω| < 3 °/s, ≥ 1 s"],
    ["QUIET (added)", "≥ 50 % of the bin A3-quiet (1-s rule: median |ω| < 10 °/s, |median |a| − g| < 0.05 g) but not STILL — resting with small movements"],
    ["LOCOMOTION", "WISER 1-s speed (median speed_inps_smooth) ≥ 10 in/s"],
    ["RHYTHMIC 4–12 Hz", "gyro 4–12 Hz power ≥ 60 % of the 2–20 Hz power AND ≥ 400 (°/s)² (RMS 20 °/s ≈ a 0.75° head oscillation at 6 Hz); could be grooming, scratching, sniffing, chewing — not named"],
    ["ACTIVE", "none of the above"],
    ["NO IMU", "< 50 % of the bin's IMU samples present and not frozen"],
    ["Band power", "Butterworth-4 zero-phase band-pass of each gyro axis, squared, summed over axes, 0.5-s centred mean, (°/s)²; bands 2–4, 4–8, 8–12, 12–20 Hz"],
    ["Display", "|ω| = bin mean of the gyro norm (°/s); |a|−g = RMS of (|a| − g) over the bin (m/s²); bins of 0.25 s"],
]


def log(msg: str, fh=None) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if fh is not None:
        fh.write(line + "\n")
        fh.flush()


def git_commit() -> str:
    try:
        h = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        d = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
        return h + ("+dirty" if d else "")
    except Exception:  # noqa: BLE001
        return "unknown"


def ms_to_dt(ms: float) -> datetime:
    """Unix ms -> naive field-PC local datetime (EDT)."""
    return pd.Timestamp(int(round(ms)), unit="ms", tz="UTC").tz_convert(TZ).tz_localize(None).to_pydatetime()


def hms(sod: float) -> str:
    sod = sod % 86400.0
    h = int(sod // 3600)
    m = int((sod - 3600 * h) // 60)
    s = sod - 3600 * h - 60 * m
    return f"{h:02d}:{m:02d}:{s:05.2f}"


# ====================================================================================================== IMU features
def band_powers(gyr: np.ndarray, fs: float = FS100, bands=BANDS, win_s: float = BP_WIN_S) -> np.ndarray:
    """(n, len(bands)) vector band power: band-pass each axis, square, sum over axes, centred moving mean."""
    x = np.asarray(gyr, np.float64)
    out = np.empty((len(x), len(bands)), np.float32)
    w = max(1, int(round(win_s * fs)))
    for i, (lo, hi) in enumerate(bands):
        sos = signal.butter(4, [lo, hi], btype="bandpass", fs=fs, output="sos")
        y = signal.sosfiltfilt(sos, x, axis=0)
        out[:, i] = uniform_filter1d((y * y).sum(axis=1), w, mode="nearest")
    return out


def quiet_rule_1s(acc: np.ndarray, gyr: np.ndarray, fs: float = FS100) -> np.ndarray:
    """make_imu-style 1-s quiet rule on a 1-s grid from the array start (self-test only; production reads A3 `quiet`)."""
    n = len(acc)
    k = int(fs)
    q = np.zeros(n, bool)
    om, am = np.linalg.norm(gyr, axis=1), np.linalg.norm(acc, axis=1)
    for s in range(0, n - k + 1, k):
        q[s:s + k] = (np.median(om[s:s + k]) < 10.0) and (abs(np.median(am[s:s + k]) - G) < 0.05 * G)
    return q


def strict_mask(acc: np.ndarray, om: np.ndarray, cand: np.ndarray, cfg: dict) -> tuple[np.ndarray, np.ndarray]:
    win = G2.detect_strict(acc, om, cand, cfg, float(cfg["strict"]["gate_min_len_s"]))
    m = np.zeros(len(acc), bool)
    for s, e in win:
        m[s:e] = True
    return m, win


def classify_bins(t_ms: np.ndarray, om: np.ndarray, am: np.ndarray, bp: np.ndarray, strict: np.ndarray, quiet: np.ndarray,
                  present: np.ndarray, shake_spans: np.ndarray, speed_at, edges_ms: np.ndarray, thr: dict) -> dict:
    """State per bin [edges[k], edges[k+1]). speed_at(sec) -> WISER 1-s speed (in/s) or nan. thr: p99_hi, rhythm_floor."""
    nb = len(edges_ms) - 1
    state = np.zeros(nb, np.int8)
    om_m = np.full(nb, np.nan)
    a_rms = np.full(nb, np.nan)
    i_ed = np.searchsorted(t_ms, edges_ms)
    for k in range(nb):
        a, b = edges_ms[k], edges_ms[k + 1]
        i0, i1 = int(i_ed[k]), int(i_ed[k + 1])
        n_exp = max(1, int(round((b - a) / 1000.0 * FS100)))
        if i1 <= i0 or present[i0:i1].sum() < MIN_FRAC * n_exp:
            state[k] = S_NOIMU
            continue
        sl = slice(i0, i1)
        om_m[k] = float(np.mean(om[sl]))
        a_rms[k] = float(np.sqrt(np.mean((am[sl] - G) ** 2)))
        in_train = bool(len(shake_spans)) and bool(np.any((shake_spans[:, 0] < b) & (shake_spans[:, 1] > a)))
        if in_train or (float(np.max(bp[sl, 3])) > thr["p99_hi"] and float(np.max(am[sl])) > SHAKE_ACC_G * G):
            state[k] = S_SHAKE
        elif strict[sl].mean() >= MIN_FRAC:
            state[k] = S_STILL
        elif quiet[sl].mean() >= MIN_FRAC:
            state[k] = S_QUIET
        elif speed_at(math.floor(0.5 * (a + b) / 1000.0)) >= LOCO_SPEED_INPS:
            state[k] = S_LOCO
        else:
            pr = float(np.mean(bp[sl, 1] + bp[sl, 2]))
            pt = float(np.mean(bp[sl].sum(axis=1)))
            state[k] = S_RHYTHM if (pt > 0 and pr >= RHYTHM_FRAC * pt and pr >= thr["rhythm_floor"]) else S_ACTIVE
    return {"state": state, "om": om_m, "a_rms": a_rms}


def shake_spans_for(sat_runs: pd.DataFrame, animal: str, pkey: str) -> np.ndarray:
    R = sat_runs[(sat_runs["animal"] == animal) & (sat_runs["period"] == pkey) & (sat_runs["cls"] == "shake_train")]
    if not len(R):
        return np.zeros((0, 2))
    R = R.assign(t_end=R["t_unix_ms"] + R["dur_ms"])
    g = R.groupby("train_id").agg(t0=("t_unix_ms", "min"), t1=("t_end", "max"))
    return np.column_stack([g["t0"].to_numpy() - SHAKE_TRAIN_PAD_MS, g["t1"].to_numpy() + SHAKE_TRAIN_PAD_MS])


def load_period_imu(animal: str, pkey: str, cfg: dict, ctx: dict, sat_runs: pd.DataFrame, fh=None) -> dict:
    t0 = time.time()
    p = Path(cfg["cache_roots"]["imu100"]) / animal / f"{pkey}.npz"
    with np.load(p, allow_pickle=False) as z:
        t = z["t_unix_ms"].astype(np.float64)
        acc = z["acc"].astype(np.float64)
        gyr = z["gyr"].astype(np.float64)
        sat_acc, sat_gyr = z["sat_acc"].astype(bool), z["sat_gyr"].astype(bool)
        frozen, quiet = z["frozen"].astype(bool), z["quiet"].astype(bool)
    per = cfg["periods"][pkey]
    lo, hi = G2.to_ms(per["start"], TZ), G2.to_ms(per["end"], TZ)
    inwin = (t >= lo) & (t < hi)
    hand = G2.C.in_any(t, ctx["handling"])
    ivu = ctx["imu_valid_until"].get(animal)
    imu_ok = (t < ivu) if ivu is not None else np.ones(len(t), bool)
    valid = inwin & ~frozen & ~hand & imu_ok
    om = np.linalg.norm(gyr, axis=1)
    am = np.linalg.norm(acc, axis=1)
    strict, win = strict_mask(acc, om, valid & ~sat_acc & ~sat_gyr, cfg)
    bp = band_powers(gyr)
    p99_hi = float(np.percentile(bp[valid, 3], SHAKE_PCTL))
    act = valid & ~quiet
    med_act = float(np.median(bp[act, 1] + bp[act, 2])) if act.any() else float("nan")
    rfloor = RHYTHM_FLOOR
    spans = shake_spans_for(sat_runs, animal, pkey)
    log(f"IMU {animal} {pkey}: n {len(t):,}, strict windows {len(win)} ({strict[valid].mean() * 100:.1f} % of valid), "
        f"quiet {quiet[valid].mean() * 100:.1f} %, P12-20 p99 {p99_hi:.1f} (deg/s)^2, median P4-12 of non-quiet {med_act:.1f} (deg/s)^2, "
        f"shake trains {len(spans)}, {time.time() - t0:.1f} s", fh)
    return {"t": t, "om": om.astype(np.float32), "am": am.astype(np.float32), "bp": bp, "strict": strict, "quiet": quiet,
            "present": ~frozen, "sat_gyr": sat_gyr, "spans": spans, "thr": {"p99_hi": p99_hi, "rhythm_floor": rfloor},
            "n_strict": int(len(win)), "path": str(p)}


# ====================================================================================================== WISER
def wiser_seconds(fx: pd.DataFrame | None) -> pd.DataFrame:
    if fx is None or not len(fx):
        return pd.DataFrame(columns=["sec", "x", "y", "speed", "n"])
    ok = (fx["valid"].astype(bool) & ~fx["m_handling"].astype(bool) & ~fx["m_silence"].astype(bool)
          & ~fx["m_tag_validity"].astype(bool) & ~fx["m_adc_lane"].astype(bool))
    f = fx[ok]
    g = f.assign(sec=f["t_ms"].to_numpy(np.int64) // 1000).groupby("sec").agg(
        x=("x", "median"), y=("y", "median"), speed=("speed_inps_smooth", "median"), n=("x", "size"))
    return g.reset_index()


def house_label(x: float, y: float, houses: list) -> tuple[str, bool]:
    """(zone, in_core): zone = house name if inside its rectangle grown by HOUSE_BUFFER_IN, else 'outside'."""
    for roi in houses:
        core, buf = WU._rect_membership(np.array([x]), np.array([y]), roi, HOUSE_BUFFER_IN)
        if bool(buf[0]):
            return roi["name"], bool(core[0])
    return "outside", False


def choose_zone(ws: pd.DataFrame, ev_lo: float, ev_hi: float, houses: list) -> dict:
    sel, pad = ws.iloc[0:0], None
    for p in WISER_PAD_S:
        k0, k1 = math.floor((ev_lo - p * 1000) / 1000), math.ceil((ev_hi + p * 1000) / 1000)
        sel = ws[(ws["sec"] >= k0) & (ws["sec"] <= k1)]
        if len(sel):
            pad = p
            break
    if not len(sel):
        cams = CAMS["outside"]
        return {"zone": "outside", "zone_text": "no valid fix ± 30 s", "x": None, "y": None, "n": 0, "pad_s": None,
                "fractions": {}, "in_core": False, "cams": cams,
                "reason": "No valid WISER fix within ± 30 s of the event → zone unknown → CH01 + CH02 panoramas (whole field)."}
    labs = [house_label(float(r.x), float(r.y), houses) for r in sel.itertuples()]
    zs = pd.Series([z for z, _ in labs])
    fr = (zs.value_counts() / len(zs)).round(3).to_dict()
    mx, my = float(sel["x"].median()), float(sel["y"].median())
    zmed, core_med = house_label(mx, my, houses)
    top = zs.value_counts()
    zone = top.index[0] if (len(top) == 1 or top.iloc[0] > top.iloc[1]) else zmed
    cams = CAMS[zone]
    mix = ", ".join(f"{k} {v * 100:.0f} %" for k, v in fr.items())
    camtxt = " + ".join(f"{c} ({r})" for c, r in cams)
    if zone == "outside":
        where = "outside both house rectangles (+ 14 in)"
    else:
        where = (f"inside the {zone} rectangle" if core_med and zmed == zone else
                 f"within 14 in of {zone} but outside its footprint — the rat may be just outside the box, where the in-box view cannot see it")
    reason = (f"WISER: {len(sel)} valid 1-s medians in event ± {pad:.0f} s; median position ({mx:.0f}, {my:.0f}) in (WISER frame, "
              f"unverified origin) is {where}; per-second zones: {mix} → {zone} → {camtxt}.")
    return {"zone": zone, "zone_text": f"{zone} ({mx:.0f}, {my:.0f}) in", "x": mx, "y": my, "n": int(len(sel)), "pad_s": pad,
            "fractions": fr, "in_core": bool(core_med and zmed == zone), "cams": cams, "reason": reason}


# ====================================================================================================== video parts / layout
def view_parts(root: Path, cam: str, clip_lo: datetime, clip_hi: datetime, ffprobe: str) -> tuple[list, list]:
    """Parts (file, offset in file, duration, start in clip) covering [clip_lo, clip_hi) and the uncovered gaps (clip s)."""
    D = (clip_hi - clip_lo).total_seconds()
    parts = []
    for s, e, f in GF.segments(Path(root), cam, clip_hi.date(), ffprobe):
        if e <= clip_lo or s >= clip_hi:
            continue
        # a named segment's real content can end up to ~1 s before its name says; probing a fragmented MP4 on the HDD costs
        # seconds, so only when the clip reaches within 3 s of the named end (never-renamed ones were probed by segments())
        dur = GF.probe_duration(f, ffprobe) if clip_hi > e - timedelta(seconds=3) else (e - s).total_seconds()
        real_e = min(e, s + timedelta(seconds=dur)) if dur > 0 else e
        a, b = max(clip_lo, s), min(clip_hi, real_e)
        if (b - a).total_seconds() <= 0.01:
            continue
        parts.append({"file": f.name, "path": str(f), "offset_s": round((a - s).total_seconds(), 3),
                      "dur_s": round((b - a).total_seconds(), 3), "clip_t0_s": round((a - clip_lo).total_seconds(), 3),
                      "seg_start": f"{s:%Y-%m-%d %H:%M:%S}", "seg_end_by_name": f"{e:%Y-%m-%d %H:%M:%S}",
                      "file_duration_s": round(dur, 3)})
    parts.sort(key=lambda p: p["clip_t0_s"])
    gaps, t = [], 0.0
    for p in parts:
        if p["clip_t0_s"] - t > 0.1:
            gaps.append([round(t, 3), round(p["clip_t0_s"], 3)])
        t = max(t, p["clip_t0_s"] + p["dur_s"])
    if D - t > 0.1:
        gaps.append([round(t, 3), round(D, 3)])
    return parts, gaps


def layout(zone: str, scale: float = 1.0) -> dict:
    def ev(v):
        return int(round(v * scale / 2.0)) * 2
    bh = ev(BANNER_H)
    if zone == "outside":
        w, h = ev(3712), ev(1044)
        views = [{"x": 0, "y": bh, "w": w, "h": h, "pano": True}, {"x": 0, "y": bh + h, "w": w, "h": h, "pano": True}]
        W, H = w, bh + 2 * h
    else:
        w, h = ev(1920), ev(1440)
        views = [{"x": 0, "y": bh, "w": w, "h": h, "pano": False}, {"x": w, "y": bh, "w": w, "h": h, "pano": False}]
        W, H = 2 * w, bh + h
    return {"W": W, "H": H, "banner": bh, "views": views, "scale": scale}


# ====================================================================================================== overlay (ASS)
FONT_FILES = {"regular": "DejaVuSans.ttf", "bold": "DejaVuSans-Bold.ttf"}
FONT_NAME = "DejaVu Sans"
FONT_EM_PER_ASS = 1.0 / 1.164          # DejaVu Sans: (ascender + descender) / em = 1.164 -> ASS size S ~ em S / 1.164


def find_fonts() -> dict:
    d = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    out = {}
    for k, f in FONT_FILES.items():
        for cand in (d / f, Path.home() / "AppData/Local/Microsoft/Windows/Fonts" / f, Path("/usr/share/fonts/truetype/dejavu") / f):
            if cand.exists():
                out[k] = cand
                break
    return out


_PIL_FONTS: dict = {}


def text_width_px(text: str, ass_size: float, bold: bool, fonts: dict) -> float:
    """Rendered width estimate (PIL with the same font file); falls back to 0.62 em per character."""
    em = ass_size * FONT_EM_PER_ASS
    key = ("bold" if bold else "regular", int(round(em)))
    try:
        from PIL import ImageFont
        if key not in _PIL_FONTS:
            _PIL_FONTS[key] = ImageFont.truetype(str(fonts[key[0]]), key[1])
        return float(_PIL_FONTS[key].getlength(text))
    except Exception:  # noqa: BLE001
        return 0.62 * em * len(text)


def ass_color(hex_rgb: str, alpha: int = 0) -> str:
    h = hex_rgb.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"


def ass_c(hex_rgb: str) -> str:
    """Inline colour override value &HBBGGRR&."""
    h = hex_rgb.lstrip("#")
    return f"&H{h[4:6]}{h[2:4]}{h[0:2]}&".upper()


def ass_time(t: float) -> str:
    cs = max(0, int(round(t * 100)))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def ass_escape(s: str) -> str:
    return s.replace("\\", "\u2216").replace("{", "(").replace("}", ")").replace("\n", " ")


def fit_size(text: str, size: float, bold: bool, max_w: float, fonts: dict) -> float:
    w = text_width_px(text, size, bold, fonts)
    return size if w <= max_w else max(10.0, math.floor(size * max_w / w))


def dyn_text(code: int, om: float, arms: float, sod: float) -> tuple[str, str]:
    name, col = STATES[code]
    if code == S_NOIMU or not np.isfinite(om):
        return f"IMU now: {name}", col
    oms = f"{om:.1f}" if om < 10 else f"{om:.0f}"
    return f"IMU now: {name} · |ω| {oms} °/s · |a|−g {arms:.2f} m/s² · {hms(sod)}", col


def write_ass(path: Path, lay: dict, static_rows: list, bins: dict, bin_s: float, D: float, ev_span: tuple, view_labels: list,
              view_gaps: list, clip_lo_sod: float, fonts: dict) -> dict:
    """Write the overlay; returns the dialogue timing table (for the self-test)."""
    W, H, sc = lay["W"], lay["H"], lay["scale"]
    m = max(8, int(round(24 * sc)))
    fs_static, fs_dyn, fs_lab, fs_nov = 52 * sc, 60 * sc, 40 * sc, 72 * sc
    y1, y2, y3 = int(round(12 * sc)), int(round(78 * sc)), int(round(142 * sc))
    lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2",
             "ScaledBorderAndShadow: yes", "YCbCr Matrix: None", "", "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
             "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, "
             "MarginV, Encoding",
             f"Style: Static,{FONT_NAME},{fs_static:.0f},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,{max(1, 2 * sc):.0f},0,7,0,0,0,1",
             f"Style: Dyn,{FONT_NAME},{fs_dyn:.0f},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,{max(1, 2 * sc):.0f},0,7,0,0,0,1",
             f"Style: Event,{FONT_NAME},{fs_dyn:.0f},&H00FFFFFF,&H00FFFFFF,&H000000C8,&H000000C8,1,0,0,0,100,100,0,0,3,{max(2, 10 * sc):.0f},0,9,0,0,0,1",
             f"Style: Label,{FONT_NAME},{fs_lab:.0f},&H00FFFFFF,&H00FFFFFF,&H60000000,&H60000000,0,0,0,0,100,100,0,0,3,{max(2, 8 * sc):.0f},0,7,0,0,0,1",
             f"Style: NoVideo,{FONT_NAME},{fs_nov:.0f},&H0000D7FF,&H0000D7FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,{max(1, 3 * sc):.0f},0,5,0,0,0,1",
             "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    T = {"static": [], "dyn": [], "event": [], "nov": []}
    ev_tag = "▶ EVENT"
    ev_w = text_width_px(ev_tag, fs_dyn, True, fonts) + 2 * 10 * sc
    for r, y in zip(static_rows, (y1, y2)):
        s = fit_size(r, fs_static, False, W - 2 * m, fonts)
        lines.append(f"Dialogue: 0,{ass_time(0)},{ass_time(D)},Static,,0,0,0,,{{\\pos({m},{y})\\fs{s:.0f}}}{ass_escape(r)}")
        T["static"].append((0.0, D, r))
    nb = len(bins["state"])
    for k in range(nb):
        a, b = k * bin_s, min(D, (k + 1) * bin_s)
        if b <= a:
            continue
        txt, col = dyn_text(int(bins["state"][k]), float(bins["om"][k]), float(bins["a_rms"][k]), clip_lo_sod + a)
        name = STATES[int(bins["state"][k])][0]
        rest = txt[len("IMU now: ") + len(name):]
        s = fit_size(txt, fs_dyn, True, W - 2 * m - ev_w - m, fonts)
        lines.append(f"Dialogue: 1,{ass_time(a)},{ass_time(b)},Dyn,,0,0,0,,{{\\pos({m},{y3})\\fs{s:.0f}}}IMU now: "
                     f"{{\\c{ass_c(col)}}}{ass_escape(name)}{{\\c&HFFFFFF&}}{ass_escape(rest)}")
        T["dyn"].append((a, b, txt))
    e0, e1 = max(0.0, ev_span[0]), min(D, ev_span[1])
    if e1 > e0:
        lines.append(f"Dialogue: 2,{ass_time(e0)},{ass_time(e1)},Event,,0,0,0,,{{\\pos({W - m},{y3})}}{ev_tag}")
        T["event"].append((e0, e1, ev_tag))
    for v, lab, gaps in zip(lay["views"], view_labels, view_gaps):
        lines.append(f"Dialogue: 1,{ass_time(0)},{ass_time(D)},Label,,0,0,0,,{{\\pos({v['x'] + m},{v['y'] + m})}}{ass_escape(lab)}")
        for ga, gb in gaps:
            lines.append(f"Dialogue: 1,{ass_time(ga)},{ass_time(gb)},NoVideo,,0,0,0,,{{\\pos({v['x'] + v['w'] // 2},{v['y'] + v['h'] // 2})}}"
                         f"NO VIDEO ({ass_escape(lab.split(' ')[0])} has no frames here)")
            T["nov"].append((ga, gb, lab))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return T


# ====================================================================================================== ffmpeg
ENC = {"nvenc": ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "26", "-b:v", "0", "-maxrate", "40M",
                 "-bufsize", "80M", "-spatial-aq", "1", "-g", str(FPS), "-bf", "0", "-profile:v", "high"],
       "x264": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-g", str(FPS), "-bf", "0", "-profile:v", "high"]}


def nvenc_works(ffmpeg: str) -> bool:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "t.mp4"
        p = subprocess.run([ffmpeg, "-hide_banner", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x480:rate=20:duration=1",
                            *ENC["nvenc"], "-pix_fmt", "yuv420p", str(out)], capture_output=True)
        return p.returncode == 0 and out.exists() and out.stat().st_size > 0


def ffmpeg_cmd(ffmpeg: str, lay: dict, view_parts_list: list, D: float, ass_rel: str, fonts_rel: str, out: Path, enc: str) -> list:
    W, H = lay["W"], lay["H"]
    base = "0x{:02X}{:02X}{:02X}".format(*BASE_RGB)
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-v", "info"]
    filt = [f"color=c={base}:s={W}x{H}:r={FPS}:d={D:.3f},format=yuv420p[base]"]
    last, k = "base", 0
    for v, parts in zip(lay["views"], view_parts_list):
        for p in parts:
            cmd += ["-ss", f"{p['offset_s']:.3f}", "-t", f"{p['dur_s']:.3f}", "-i", p["path"]]
            chain = (f"scale={v['h']}:{v['w']}:flags=bicubic,transpose=2" if v["pano"] else f"scale={v['w']}:{v['h']}:flags=bicubic")
            filt.append(f"[{k}:v]setpts=PTS+{p['clip_t0_s']:.3f}/TB,{chain},format=yuv420p[p{k}]")
            filt.append(f"[{last}][p{k}]overlay=x={v['x']}:y={v['y']}:eof_action=pass:repeatlast=0[o{k}]")
            last, k = f"o{k}", k + 1
    filt.append(f"[{last}]subtitles=f={ass_rel}:fontsdir={fonts_rel},format=yuv420p[v]")
    cmd += ["-filter_complex", ";".join(filt), "-map", "[v]", "-t", f"{D:.3f}", "-r", str(FPS), "-an", *ENC[enc],
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
    return cmd


GLYPH_WARN = re.compile(r"(Glyph 0x[0-9A-Fa-f]+ not found|failed to find any fallback|fontselect: \(.*\) -> .*not found)", re.I)


def render(ffmpeg: str, ffprobe: str, job: dict, workdir: Path, enc: str) -> dict:
    t0 = time.time()
    out = Path(job["out"])
    tmp = out.with_name(out.stem + ".partial.mp4")
    cmd = ffmpeg_cmd(ffmpeg, job["layout"], job["view_parts"], job["D"], job["ass_rel"], job["fonts_rel"], tmp, enc)
    p = subprocess.run(cmd, cwd=str(workdir), capture_output=True)
    err = p.stderr.decode(errors="replace")
    used = enc
    if p.returncode != 0 and enc == "nvenc":
        used = "x264"
        cmd = ffmpeg_cmd(ffmpeg, job["layout"], job["view_parts"], job["D"], job["ass_rel"], job["fonts_rel"], tmp, "x264")
        p = subprocess.run(cmd, cwd=str(workdir), capture_output=True)
        err = p.stderr.decode(errors="replace")
    res = {"id": job["id"], "ok": p.returncode == 0 and tmp.exists(), "encoder": used, "seconds": round(time.time() - t0, 1),
           "glyph_warnings": sorted(set(m.group(0) for m in GLYPH_WARN.finditer(err)))[:5], "cmd": cmd}
    if not res["ok"]:
        res["error"] = err[-1500:]
        if tmp.exists():
            tmp.unlink()
        return res
    os.replace(tmp, out)
    pr = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                         "stream=codec_name,width,height,pix_fmt,avg_frame_rate,nb_frames:format=duration,size",
                         "-of", "json", str(out)], capture_output=True, text=True)
    try:
        info = json.loads(pr.stdout)
        st = info["streams"][0]
        res.update(width=int(st["width"]), height=int(st["height"]), codec=st["codec_name"], pix_fmt=st["pix_fmt"],
                   duration_s=float(info["format"]["duration"]), size_bytes=int(info["format"]["size"]),
                   nb_frames=int(st.get("nb_frames") or 0))
    except Exception as e:  # noqa: BLE001
        res["probe_error"] = str(e)
    return res


# ====================================================================================================== events
def load_identity(cohort: str) -> pd.DataFrame:
    return pd.read_csv(REPO / "wiser" / "configs" / f"rat_identities_{cohort}.csv", dtype=str)


def identity_at(ids: pd.DataFrame, animal: str, t_ms: float) -> dict:
    rows = ids[ids["animal"] == animal]
    best = None
    for r in rows.itertuples():
        a = pd.Timestamp(r.valid_from).value // 10**6
        b = pd.Timestamp(r.valid_until).value // 10**6
        if a <= t_ms < b:
            best = r
    if best is None:
        return {"tag": "?", "shortid": "", "pattern": "?", "coban": "?", "sticker": "?", "nickname": ""}
    coban = str(best.coband_color)
    m = re.match(r"^\s*([\w/ ]+?)\s*\(\s*([\w/ ]+?)\s+coban from (\d\d)-(\d\d)\s*\)\s*$", coban)
    if m:
        ch = pd.Timestamp(f"2026-{m.group(3)}-{m.group(4)}").tz_localize(TZ).value // 10**6
        coban = m.group(2) if t_ms >= ch else m.group(1)
    return {"tag": str(best.physical_tag_id), "shortid": str(best.shortid), "pattern": str(best.pattern), "coban": coban,
            "sticker": str(best.sticker_color), "nickname": "" if pd.isna(best.nickname) else str(best.nickname)}


def event_text(ev: dict) -> str:
    d, s = ev["detail"], ev["type_short"]
    if s == "still":
        m = re.match(r"([\d.]+) s, WISER (\w+)", d)
        return f"STRICT STILL {m.group(1)} s (WISER {m.group(2)})" if m else f"STRICT STILL ({d})"
    if s == "shake":
        m = re.match(r"(\d+) clipped readings, \|a\|max ([\d.]+) g, net (-?[\d.]+) deg", d)
        return (f"SHAKE TRAIN {m.group(1)} clipped gyro readings |a|max {m.group(2)} g, net {m.group(3)}°" if m else f"SHAKE TRAIN ({d})")
    m = re.match(r"e ([\d.]+) deg, T_in ([\d.]+) s, rotation (\d+) deg", d)
    return (f"LARGEST-ERROR BOUT tilt error {m.group(1)}° after T_in {m.group(2)} s, rotation {m.group(3)}°" if m else f"LARGEST-ERROR BOUT ({d})")


def read_events(path: Path) -> list:
    df = pd.read_csv(path)
    evs = []
    for i, r in enumerate(df.itertuples(), start=1):
        short = TYPE_SHORT.get(r.type, "other")
        lo, hi = G2.to_ms(r.start_local, TZ), G2.to_ms(r.end_local, TZ)
        st = pd.Timestamp(r.start_local)
        evs.append({"idx": i, "id": f"E{i:02d}_{short}_{r.animal}_{st:%m%d_%H%M%S}", "type": r.type, "type_short": short,
                    "type_label": TYPE_LABEL.get(short, short), "animal": r.animal, "period": r.period,
                    "start_local": r.start_local, "end_local": r.end_local, "detail": r.detail,
                    "t_ms": float(r.t_ms), "ev_lo_ms": float(lo), "ev_hi_ms": float(hi)})
    return evs


def r3(a, nd=2):
    """List with NaN -> None, rounded."""
    out = []
    for v in np.asarray(a, float).tolist():
        out.append(None if not np.isfinite(v) else round(v, nd))
    return out


def sig3(a):
    out = []
    for v in np.asarray(a, float).tolist():
        out.append(None if not np.isfinite(v) else float(f"{v:.3g}"))
    return out


def build_event(ev: dict, P: dict, ws: pd.DataFrame, houses: list, ids: pd.DataFrame, root: Path, ffprobe: str,
                out_dir: Path, fonts: dict, scale: float = 1.0) -> tuple[dict, dict]:
    """Payload for the page + render job for one event."""
    clip_lo_ms = ev["ev_lo_ms"] - CLIP_PAD_S * 1000
    clip_hi_ms = ev["ev_hi_ms"] + CLIP_PAD_S * 1000
    D = round((clip_hi_ms - clip_lo_ms) / 1000.0, 3)
    clip_lo, clip_hi = ms_to_dt(clip_lo_ms), ms_to_dt(clip_hi_ms)
    clip_lo_sod = clip_lo.hour * 3600 + clip_lo.minute * 60 + clip_lo.second + clip_lo.microsecond / 1e6
    ident = identity_at(ids, ev["animal"], ev["ev_lo_ms"])
    zc = choose_zone(ws, ev["ev_lo_ms"], ev["ev_hi_ms"], houses)
    lay = layout(zc["zone"], scale)
    vparts, vgaps, labels = [], [], []
    for cam, role in zc["cams"]:
        parts, gaps = view_parts(root, cam, clip_lo, clip_hi, ffprobe)
        vparts.append(parts)
        vgaps.append(gaps)
        labels.append(f"{cam} · {role}")
    # IMU state bins on the clip grid
    nb = int(math.ceil(D / BIN_S - 1e-9))
    edges = clip_lo_ms + 1000.0 * BIN_S * np.arange(nb + 1)
    edges[-1] = min(edges[-1], clip_hi_ms)
    spd = dict(zip(ws["sec"].astype(np.int64).tolist(), ws["speed"].astype(float).tolist()))
    bins = classify_bins(P["t"], P["om"], P["am"], P["bp"], P["strict"], P["quiet"], P["present"], P["spans"],
                         lambda s: spd.get(int(s), float("nan")), edges, P["thr"])
    ev_t0, ev_t1 = (ev["ev_lo_ms"] - clip_lo_ms) / 1000.0, (ev["ev_hi_ms"] - clip_lo_ms) / 1000.0
    mids = (edges[:-1] + edges[1:]) / 2
    inev = (mids >= ev["ev_lo_ms"]) & (mids < ev["ev_hi_ms"])
    if not inev.any():                                   # very short events: the bin(s) overlapping the span
        inev = (edges[1:] > ev["ev_lo_ms"]) & (edges[:-1] < ev["ev_hi_ms"])
    sc = pd.Series(bins["state"][inev]).value_counts(normalize=True)
    frac = {STATES[int(k)][0]: round(float(v), 3) for k, v in sc.items()}
    dom = int(sc.index[0]) if len(sc) else S_NOIMU
    # traces for the canvas
    i0, i1 = np.searchsorted(P["t"], [clip_lo_ms, clip_hi_ms])
    tt = P["t"][i0:i1]
    t0_s = float((tt[0] - clip_lo_ms) / 1000.0) if len(tt) else 0.0
    fs = float(1000.0 / np.median(np.diff(tt))) if len(tt) > 2 else FS100
    pres = P["present"][i0:i1]
    om = np.where(pres, P["om"][i0:i1], np.nan)
    adev = np.where(pres, P["am"][i0:i1] - G, np.nan)
    step = 5                                              # band powers at 20 Hz
    bp = P["bp"][i0:i1:step]
    sat_idx = np.flatnonzero(P["sat_gyr"][i0:i1]).tolist()
    spans = [[round((a - clip_lo_ms) / 1000.0, 3), round((b - clip_lo_ms) / 1000.0, 3)] for a, b in P["spans"]
             if b > clip_lo_ms and a < clip_hi_ms]
    wsel = ws[(ws["sec"] >= math.floor(clip_lo_ms / 1000)) & (ws["sec"] <= math.ceil(clip_hi_ms / 1000))]
    wiser_1s = [[round(float(r.sec) - clip_lo_ms / 1000.0 + 0.5, 2), round(float(r.x), 1), round(float(r.y), 1),
                 None if not np.isfinite(r.speed) else round(float(r.speed), 1), house_label(float(r.x), float(r.y), houses)[0]]
                for r in wsel.itertuples()]
    cams_text = (f"{zc['cams'][0][0]} + {zc['cams'][1][0]} panoramas" if zc["zone"] == "outside"
                 else f"{zc['cams'][0][0]} in-box + {zc['cams'][1][0]} top-down")
    st_lo = ms_to_dt(ev["ev_lo_ms"])
    row1 = (f"{ev['animal']} · tag {ident['tag']} · IR mark: {ident['pattern']} (coban {ident['coban']}) · "
            f"IMU event: {event_text(ev)}")
    row2 = f"{st_lo:%Y-%m-%d %H:%M:%S} field-PC (file-name time, ±1 s) · {cams_text} · WISER: {zc['zone_text']}"
    fname = f"{ev['idx']:02d}_{ev['type_short']}_{ev['animal']}_{st_lo:%Y%m%d_%H%M%S}.mp4"
    ass_name = fname.replace(".mp4", ".ass")
    T = write_ass(out_dir / "overlay_ass" / ass_name, lay, [row1, row2], bins, BIN_S, D, (ev_t0, ev_t1), labels, vgaps,
                  clip_lo_sod, fonts)
    payload = {**{k: ev[k] for k in ("idx", "id", "type", "type_short", "type_label", "animal", "period", "start_local",
                                       "end_local", "detail")},
               "identity": ident, "event_text": event_text(ev), "overlay_static": [row1, row2],
               "zone": zc["zone"], "zone_text": zc["zone_text"], "zone_reason": zc["reason"], "zone_fractions": zc["fractions"],
               "wiser_xy": [zc["x"], zc["y"]], "wiser_n": zc["n"], "cams_text": cams_text,
               "cams": [{"cam": c, "role": r, "parts": [{k: p[k] for k in ("file", "offset_s", "dur_s", "clip_t0_s", "seg_start",
                                                                            "seg_end_by_name", "file_duration_s")} for p in pp],
                         "gaps": gg} for (c, r), pp, gg in zip(zc["cams"], vparts, vgaps)],
               "clip": {"file": fname, "lo_local": f"{clip_lo:%Y-%m-%d %H:%M:%S.%f}"[:-3], "hi_local": f"{clip_hi:%Y-%m-%d %H:%M:%S.%f}"[:-3],
                        "lo_ms": clip_lo_ms, "lo_sod": round(clip_lo_sod, 3), "dur_s": D, "ev_t0_s": round(ev_t0, 3),
                        "ev_t1_s": round(ev_t1, 3), "fps": FPS, "width": lay["W"], "height": lay["H"]},
               "imu": {"t0_s": round(t0_s, 4), "fs": round(fs, 4), "om": r3(om, 1), "adev": r3(adev, 2), "bp_fs": round(fs / step, 4),
                       "bp": [sig3(bp[:, j]) for j in range(bp.shape[1])], "bands": [f"{lo:g}–{hi:g} Hz" for lo, hi in BANDS],
                       "sat_idx": sat_idx, "shake_spans": spans, "p99_hi": round(P["thr"]["p99_hi"], 2),
                       "rhythm_floor": round(P["thr"]["rhythm_floor"], 2), "source": P["path"]},
               "bins": {"bin_s": BIN_S, "state": bins["state"].astype(int).tolist(), "om": r3(bins["om"], 1), "a_rms": r3(bins["a_rms"], 2)},
               "wiser_1s": wiser_1s,
               "summary": {"dominant": dom, "dominant_name": STATES[dom][0], "dominant_frac": float(sc.iloc[0]) if len(sc) else 0.0,
                           "frac": frac, "frac_text": ", ".join(f"{k} {v * 100:.0f} %" for k, v in frac.items())}}
    job = {"id": ev["id"], "out": str(out_dir / "clips" / fname), "layout": lay, "view_parts": vparts, "D": D,
           "ass_rel": f"overlay_ass/{ass_name}", "fonts_rel": "_fonts", "timing": T}
    return payload, job


# ====================================================================================================== HTML
HTML_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>IMU Video Review</title>
<style>
:root{--bg:#0f1216;--panel:#181d23;--panel2:#20262e;--line:#2c343d;--fg:#e6e9ee;--mut:#97a1ac;--acc:#4da3ff;--ok:#3fb950;--warn:#d29922;--bad:#f85149}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.4 system-ui,"Segoe UI",sans-serif;height:100vh;display:flex;flex-direction:column}
header{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:6px 10px;background:var(--panel);border-bottom:1px solid var(--line)}
header b{font-size:14px}
button,.btn{background:var(--panel2);color:var(--fg);border:1px solid var(--line);border-radius:4px;padding:3px 9px;cursor:pointer;font:inherit}
button:hover,.btn:hover{border-color:var(--acc)}
input,select,textarea{background:#0b0e12;color:var(--fg);border:1px solid var(--line);border-radius:4px;font:inherit;padding:2px 5px}
main{flex:1;display:grid;grid-template-columns:290px minmax(0,1fr) 370px;min-height:0}
#list{overflow:auto;border-right:1px solid var(--line);background:var(--panel)}
#filters{display:flex;gap:4px;padding:6px;position:sticky;top:0;background:var(--panel);border-bottom:1px solid var(--line)}
#filters select{flex:1;min-width:0}
.item{padding:5px 8px;border-bottom:1px solid var(--line);cursor:pointer}
.item:hover{background:var(--panel2)}
.item.sel{background:#1f3550}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;background:#555}
.dot.partial{background:var(--warn)}.dot.done{background:var(--ok)}
.tag{display:inline-block;padding:0 5px;border-radius:3px;font-size:11px;background:#333}
.t-still{background:#1d4e89}.t-shake{background:#8b2b2b}.t-bout{background:#6b5310}
.mut{color:var(--mut)}
#centre{display:flex;flex-direction:column;min-width:0;overflow:auto;padding:6px 8px;gap:6px}
#evhead{background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:6px 8px}
#evhead .row1{font-weight:600}
video{width:100%;max-height:56vh;background:#000;border-radius:4px}
#controls{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
#tread{font-variant-numeric:tabular-nums;color:var(--mut)}
#cv{width:100%;height:330px;background:#0a0c0f;border:1px solid var(--line);border-radius:4px;cursor:crosshair;display:block}
#readout{font-variant-numeric:tabular-nums;color:var(--mut);min-height:1.4em}
#legend span{display:inline-block;margin-right:10px}
#legend i{display:inline-block;width:12px;height:10px;margin-right:4px;vertical-align:middle;border-radius:2px}
.box{background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:6px 8px}
#right{overflow:auto;border-left:1px solid var(--line);padding:8px;background:var(--panel)}
fieldset{border:1px solid var(--line);border-radius:4px;margin:0 0 8px;padding:5px 8px}
legend{color:var(--acc);padding:0 4px}
.opt{display:block;padding:2px 0;cursor:pointer}
.opt kbd,.kbd{display:inline-block;min-width:16px;text-align:center;border:1px solid var(--line);border-radius:3px;background:#0b0e12;color:var(--mut);font-size:11px;margin-right:5px;padding:0 3px}
textarea{width:100%;min-height:60px}
table{border-collapse:collapse;width:100%}
td,th{border-bottom:1px solid var(--line);padding:2px 4px;text-align:left;vertical-align:top;font-size:12px}
th{color:var(--mut);font-weight:500}
#help{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;align-items:center;justify-content:center;z-index:10}
#help.show{display:flex}
#help .card{background:var(--panel);border:1px solid var(--line);border-radius:6px;max-width:980px;max-height:88vh;overflow:auto;padding:14px 18px}
#saved{color:var(--mut);font-size:12px}
.warnline{color:var(--warn)}
</style></head>
<body>
<header>
 <b>Head-IMU video review · cohort __COHORT__</b>
 <span id="progress"></span>
 <label>Reviewer <input id="reviewer" size="8" placeholder="initials"></label>
 <button id="btnJson" title="download all judgements as JSON">Export JSON</button>
 <button id="btnCsv" title="download all judgements as CSV">Export CSV</button>
 <label class="btn" title="load a previously exported JSON">Import<input type="file" id="importFile" accept=".json,application/json" hidden></label>
 <button id="btnHelp">Help · rules (?)</button>
 <span id="saved"></span>
</header>
<main>
 <aside id="list">
  <div id="filters">
   <select id="fType"><option value="">all types</option><option value="still">still</option><option value="shake">shake</option><option value="bout">error bout</option></select>
   <select id="fAnimal"><option value="">all rats</option></select>
   <select id="fStatus"><option value="">any status</option><option value="todo">to do</option><option value="partial">partial</option><option value="done">done</option></select>
  </div>
  <div id="events"></div>
 </aside>
 <section id="centre">
  <div id="evhead"></div>
  <video id="vid" preload="auto" muted playsinline></video>
  <div id="controls">
   <button id="bPlay" title="Space">▶ / ❚❚</button>
   <button id="bBack1" title="Shift+←">−1 s</button>
   <button id="bBackF" title="←">−1 frame</button>
   <button id="bFwdF" title="→">+1 frame</button>
   <button id="bFwd1" title="Shift+→">+1 s</button>
   <button id="bEvent" title="j">⇥ event start</button>
   <label>speed <select id="speed"></select></label>
   <label title="Shift the IMU traces: IMU time = video time − shift. Positive = the video shows the behaviour later than the IMU says. Saved as the offset seen.">IMU shift (s) <input id="shift" type="number" step="0.05" style="width:70px" value="0"></label>
   <span id="tread"></span>
  </div>
  <canvas id="cv"></canvas>
  <div id="readout"></div>
  <div id="legend"></div>
  <div class="box" id="camreason"></div>
 </section>
 <aside id="right">
  <div id="form"></div>
  <button id="bDone" style="width:100%;margin:4px 0 10px">Save &amp; next (Enter)</button>
  <div class="box"><b>Identity cues</b> <span class="mut">(IR frames are monochrome: use the pattern; coban colour only in colour frames)</span>
   <table id="idtab"></table></div>
 </aside>
</main>
<div id="help"><div class="card" id="helpcard"></div></div>
<script>
"use strict";
const DATA = __DATA_JSON__;
const EV = DATA.events;
const ST = DATA.states;
const BEH = [["still","still / sleeping","s"],["wetdog","wet-dog shake","w"],["headshake","head shake","h"],["grooming","grooming","g"],["scratching","scratching","c"],["locomotion","walking / running","l"],["rearing","rearing","r"],["digging","digging","d"],["eating","eating","e"],["interacting","interacting with another rat","i"],["other","other (say in notes)","o"]];
const IMUOK = [["yes","yes","1"],["no","no","2"],["cant_tell","can't tell","3"]];
const IDENT = [["yes","yes — it is the labelled rat","4"],["another_rat","another rat (not sure it is this one)","5"],["not_visible","not visible","6"]];
const SPEEDS = [0.25, 0.5, 0.75, 1, 1.5, 2];
const BANDCOL = ["#8e9aaf", "#e3b341", "#f0883e", "#ff5c57"];
const KEY = "imu_video_review_" + DATA.run_id;
const $ = id => document.getElementById(id);
const vid = $("vid"), cv = $("cv");
let J = {}, reviewer = "", cur = 0, bg = null, hoverT = null, rate = 1;
const filt = {type: "", animal: "", status: ""};

function esc(s){ return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c])); }
function loadState(){
  try {
    const s = JSON.parse(localStorage.getItem(KEY) || "null");
    if (s && typeof s === "object") {
      J = s.judgements || {}; reviewer = s.reviewer || "";
      if (Number.isInteger(s.cur) && s.cur >= 0 && s.cur < EV.length) cur = s.cur;
      if (typeof s.rate === "number") rate = s.rate;
    }
  } catch (e) { console.warn("localStorage unavailable", e); }
}
function saveState(){
  try {
    localStorage.setItem(KEY, JSON.stringify({judgements: J, reviewer: reviewer, cur: cur, rate: rate, saved: new Date().toISOString()}));
    $("saved").textContent = "autosaved " + new Date().toLocaleTimeString();
  } catch (e) { $("saved").innerHTML = "<span class='warnline'>autosave unavailable — Export often</span>"; }
}
function jget(id){
  if (!J[id]) J[id] = {imu_correct: "", behaviours: [], identifiable: "", offset_s: "", notes: "", updated: ""};
  return J[id];
}
function touch(id){ jget(id).updated = new Date().toISOString(); jget(id).reviewer = reviewer; saveState(); renderList(); }
function status(id){
  const j = J[id]; if (!j) return "todo";
  const beh = Array.isArray(j.behaviours) ? j.behaviours : [];
  if (j.imu_correct && beh.length && j.identifiable) return "done";
  return (j.imu_correct || beh.length || j.identifiable || j.notes || (j.offset_s !== "" && j.offset_s != null)) ? "partial" : "todo";
}
function shift(){ const v = parseFloat($("shift").value); return isFinite(v) ? v : 0; }
function clock(sod){
  sod = ((sod % 86400) + 86400) % 86400;
  const h = Math.floor(sod / 3600), m = Math.floor((sod - 3600 * h) / 60), s = sod - 3600 * h - 60 * m;
  return String(h).padStart(2, "0") + ":" + String(m).padStart(2, "0") + ":" + s.toFixed(2).padStart(5, "0");
}

// ---------------------------------------------------------------- list
function renderList(){
  const box = $("events"); box.innerHTML = "";
  let nd = 0;
  EV.forEach((ev, i) => {
    const s = status(ev.id); if (s === "done") nd++;
    if (filt.type && ev.type_short !== filt.type) return;
    if (filt.animal && ev.animal !== filt.animal) return;
    if (filt.status && s !== filt.status) return;
    const d = document.createElement("div");
    d.className = "item" + (i === cur ? " sel" : "");
    d.innerHTML = "<span class='dot " + s + "'></span><b>" + ev.idx + "</b> <span class='tag t-" + esc(ev.type_short) + "'>" + esc(ev.type_label) +
      "</span> <b>" + esc(ev.animal) + "</b> <span class='mut'>" + esc(ev.start_local.slice(5, 19)) + "</span><br><span class='mut'>" +
      esc(ev.zone) + " · IMU " + esc(ev.summary.dominant_name) + " " + Math.round(100 * ev.summary.dominant_frac) + " %</span>";
    d.onclick = () => select(i);
    box.appendChild(d);
  });
  $("progress").textContent = nd + " / " + EV.length + " done";
}

// ---------------------------------------------------------------- event
function select(i){
  cur = Math.max(0, Math.min(EV.length - 1, i));
  const ev = EV[cur];
  vid.defaultPlaybackRate = rate;
  vid.src = "clips/" + ev.clip.file;
  vid.load();
  vid.playbackRate = rate;
  const j = J[ev.id];
  $("shift").value = (j && j.offset_s !== "" && j.offset_s != null) ? j.offset_s : 0;
  renderHead(); renderForm(); renderList(); buildBg(); draw(); saveState();
  const it = document.querySelector(".item.sel"); if (it) it.scrollIntoView({block: "nearest"});
}
function renderHead(){
  const ev = EV[cur];
  const fr = Object.entries(ev.summary.frac).map(([k, v]) => esc(k) + " " + Math.round(100 * v) + " %").join(", ");
  $("evhead").innerHTML = "<div class='row1'>#" + ev.idx + " · " + esc(ev.overlay_static[0]) + "</div><div>" + esc(ev.overlay_static[1]) +
    "</div><div class='mut'>IMU state during the event span: " + fr + " · clip " + ev.clip.dur_s.toFixed(1) + " s (" + esc(ev.clip.lo_local.slice(11)) +
    " → " + esc(ev.clip.hi_local.slice(11)) + "), event at " + ev.clip.ev_t0_s.toFixed(2) + "–" + ev.clip.ev_t1_s.toFixed(2) + " s · file " + esc(ev.clip.file) + "</div>";
  let cams = ev.cams.map(c => "<b>" + esc(c.cam) + "</b> " + esc(c.role) + ": " + (c.parts.length ? c.parts.map(p => esc(p.file) + " @ " + p.offset_s.toFixed(2) + " s (" + p.dur_s.toFixed(1) + " s)").join(" + ") : "<span class='warnline'>no file</span>") +
    (c.gaps.length ? " <span class='warnline'>· no frames " + c.gaps.map(g => g[0].toFixed(1) + "–" + g[1].toFixed(1) + " s").join(", ") + "</span>" : "")).join("<br>");
  $("camreason").innerHTML = "<b>Camera choice.</b> " + esc(ev.zone_reason) + "<br>" + cams +
    "<br><span class='mut'>Times are field-PC file-name times (±1 s); the burnt-in camera clock (OSD) runs ≈ 59½ min behind — ignore it. Event detail (gate v2): " + esc(ev.detail) + ".</span>";
}
function renderForm(){
  const ev = EV[cur], j = jget(ev.id);
  const radio = (name, opts, val) => opts.map(o => "<label class='opt'><input type='radio' name='" + name + "' value='" + o[0] + "'" + (val === o[0] ? " checked" : "") + "> <kbd>" + o[2] + "</kbd>" + esc(o[1]) + "</label>").join("");
  const beh = Array.isArray(j.behaviours) ? j.behaviours : [];
  $("form").innerHTML =
    "<fieldset><legend>IMU label correct?</legend><div class='mut' style='margin-bottom:3px'>IMU says: <b>" + esc(ev.event_text) + "</b>; during the event: " + esc(ev.summary.frac_text) + "</div>" + radio("imu_correct", IMUOK, j.imu_correct) + "</fieldset>" +
    "<fieldset><legend>What is THIS rat doing? (all that apply)</legend>" + BEH.map(o => "<label class='opt'><input type='checkbox' name='beh' value='" + o[0] + "'" + (beh.includes(o[0]) ? " checked" : "") + "> <kbd>" + o[2] + "</kbd>" + esc(o[1]) + "</label>").join("") + "</fieldset>" +
    "<fieldset><legend>Is the labelled rat (" + esc(ev.animal) + ", IR mark " + esc(ev.identity.pattern) + ") identifiable in view?</legend>" + radio("identifiable", IDENT, j.identifiable) + "</fieldset>" +
    "<fieldset><legend>Time offset seen (s, optional)</legend><input id='fOffset' type='number' step='0.05' style='width:90px' value='" + esc(j.offset_s) + "'> <span class='mut'>video time − IMU time; also shifts the traces</span></fieldset>" +
    "<fieldset><legend>Notes</legend><textarea id='fNotes'>" + esc(j.notes) + "</textarea></fieldset>";
  document.querySelectorAll("input[name=imu_correct]").forEach(el => el.onchange = () => { jget(ev.id).imu_correct = el.value; touch(ev.id); });
  document.querySelectorAll("input[name=identifiable]").forEach(el => el.onchange = () => { jget(ev.id).identifiable = el.value; touch(ev.id); });
  document.querySelectorAll("input[name=beh]").forEach(el => el.onchange = () => {
    const b = jget(ev.id); b.behaviours = Array.from(document.querySelectorAll("input[name=beh]:checked")).map(x => x.value); touch(ev.id);
  });
  $("fOffset").oninput = () => { const v = $("fOffset").value; jget(ev.id).offset_s = v === "" ? "" : parseFloat(v); $("shift").value = v === "" ? 0 : v; touch(ev.id); draw(); };
  $("fNotes").oninput = () => { jget(ev.id).notes = $("fNotes").value; touch(ev.id); };
}
function setRadio(name, val){ const el = document.querySelector("input[name=" + name + "][value='" + val + "']"); if (el) { el.checked = true; el.onchange(); } }
function toggleBeh(val){ const el = document.querySelector("input[name=beh][value='" + val + "']"); if (el) { el.checked = !el.checked; el.onchange(); } }

// ---------------------------------------------------------------- canvas
const PANELS = [{key: "state", h: 16, label: "IMU state"}, {key: "om", h: 76, label: "|ω| °/s"}, {key: "adev", h: 62, label: "|a|−g m/s²"},
                {key: "bp", h: 82, label: "gyro band power"}, {key: "speed", h: 44, label: "WISER in/s"}];
function geom(){
  const W = cv.clientWidth, H = cv.clientHeight, L = 82, R = 10, D = EV[cur].clip.dur_s;
  let y = 6; const P = {};
  PANELS.forEach(p => { P[p.key] = {y0: y, y1: y + p.h, label: p.label}; y += p.h + 7; });
  return {W, H, L, R, D, P, x: t => L + (t / D) * (W - L - R), t: px => (px - L) / (W - L - R) * D, axisY: y};
}
function buildBg(){
  const dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
  if (!W || !H) return;
  cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
  bg = document.createElement("canvas"); bg.width = cv.width; bg.height = cv.height;
  const c = bg.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0);
  const g = geom(), ev = EV[cur], im = ev.imu;
  c.fillStyle = "#0a0c0f"; c.fillRect(0, 0, W, H);
  c.font = "11px system-ui, sans-serif"; c.textBaseline = "middle";
  // event span
  c.fillStyle = "rgba(255,255,255,0.08)";
  c.fillRect(g.x(ev.clip.ev_t0_s), 2, Math.max(2, g.x(ev.clip.ev_t1_s) - g.x(ev.clip.ev_t0_s)), g.axisY - 4);
  c.strokeStyle = "rgba(255,255,255,0.35)"; c.setLineDash([3, 3]);
  [ev.clip.ev_t0_s, ev.clip.ev_t1_s].forEach(t => { c.beginPath(); c.moveTo(g.x(t), 2); c.lineTo(g.x(t), g.axisY - 2); c.stroke(); });
  c.setLineDash([]);
  // labels + frames
  Object.values(g.P).forEach(p => { c.strokeStyle = "#20262e"; c.strokeRect(g.L, p.y0, W - g.L - g.R, p.y1 - p.y0); });
  // state bar
  const sb = g.P.state, bs = ev.bins.bin_s;
  ev.bins.state.forEach((s, k) => { c.fillStyle = ST[s][1]; c.fillRect(g.x(k * bs), sb.y0, Math.max(1, g.x((k + 1) * bs) - g.x(k * bs)) + 0.5, sb.y1 - sb.y0); });
  // helpers
  const line = (arr, t0, fs, p, f, col, lw) => {
    c.strokeStyle = col; c.lineWidth = lw || 1; c.beginPath(); let pen = false;
    for (let i = 0; i < arr.length; i++) {
      const v = arr[i]; if (v === null) { pen = false; continue; }
      const xx = g.x(t0 + i / fs), yy = p.y1 - f(v) * (p.y1 - p.y0);
      if (!pen) { c.moveTo(xx, yy); pen = true; } else c.lineTo(xx, yy);
    }
    c.stroke(); c.lineWidth = 1;
  };
  const ytick = (p, f, vals, labs) => { c.fillStyle = "#6e7781"; c.strokeStyle = "#1b2027"; vals.forEach((v, i) => { const yy = p.y1 - f(v) * (p.y1 - p.y0); c.beginPath(); c.moveTo(g.L, yy); c.lineTo(W - g.R, yy); c.stroke(); c.fillText(labs[i], g.L - 30, yy); }); };
  // |w| log
  const fom = v => Math.max(0, Math.min(1, Math.log10(1 + Math.max(0, v)) / Math.log10(3001)));
  ytick(g.P.om, fom, [1, 10, 100, 1000], ["1", "10", "100", "1000"]);
  line(im.om, im.t0_s, im.fs, g.P.om, fom, "#c9d1d9");
  c.fillStyle = "#ff5c57"; im.sat_idx.forEach(i => c.fillRect(g.x(im.t0_s + i / im.fs), g.P.om.y0, 1.5, 4));
  c.strokeStyle = "#ff5c57"; c.lineWidth = 3; im.shake_spans.forEach(s => { c.beginPath(); c.moveTo(g.x(s[0]), g.P.om.y0 + 1); c.lineTo(g.x(s[1]), g.P.om.y0 + 1); c.stroke(); }); c.lineWidth = 1;
  // |a|-g symlog
  const sl = v => Math.sign(v) * Math.log10(1 + Math.abs(v)), lo = sl(-10), hi = sl(100);
  const fad = v => Math.max(0, Math.min(1, (sl(v) - lo) / (hi - lo)));
  ytick(g.P.adev, fad, [-1, 0, 1, 10, 100], ["−1", "0", "1", "10", "100"]);
  line(im.adev, im.t0_s, im.fs, g.P.adev, fad, "#9cc3e6");
  // band powers log10
  const fbp = v => Math.max(0, Math.min(1, (Math.log10(Math.max(v, 1e-3)) + 2) / 8));
  ytick(g.P.bp, fbp, [1e-2, 1, 1e2, 1e4, 1e6], ["0.01", "1", "100", "1e4", "1e6"]);
  c.setLineDash([4, 3]);
  [[im.p99_hi, "#ff5c57"], [im.rhythm_floor, "#e3b341"]].forEach(([v, col]) => { if (v && isFinite(v)) { const yy = g.P.bp.y1 - fbp(v) * (g.P.bp.y1 - g.P.bp.y0); c.strokeStyle = col; c.beginPath(); c.moveTo(g.L, yy); c.lineTo(W - g.R, yy); c.stroke(); } });
  c.setLineDash([]);
  im.bp.forEach((arr, j) => line(arr, im.t0_s, im.bp_fs, g.P.bp, fbp, BANDCOL[j], 1.2));
  // WISER speed
  const vmax = Math.max(30, ...ev.wiser_1s.map(r => r[3] || 0));
  const fsp = v => Math.max(0, Math.min(1, v / vmax));
  ytick(g.P.speed, fsp, [0, 10, Math.round(vmax)], ["0", "10", String(Math.round(vmax))]);
  c.fillStyle = "#3fb950";
  ev.wiser_1s.forEach(r => { if (r[3] !== null) { const yy = g.P.speed.y1 - fsp(r[3]) * (g.P.speed.y1 - g.P.speed.y0); c.fillRect(g.x(r[0] - 0.5) + 1, yy, Math.max(1, g.x(r[0] + 0.5) - g.x(r[0] - 0.5) - 2), g.P.speed.y1 - yy); } });
  // time axis
  const D = g.D, steps = [0.5, 1, 2, 5, 10, 15, 30, 60]; let st = steps.find(s => (W - g.L - g.R) / (D / s) >= 55) || 60;
  c.fillStyle = "#97a1ac"; c.textAlign = "center";
  for (let t = 0; t <= D + 1e-6; t += st) { const xx = g.x(t); c.fillRect(xx, g.axisY - 2, 1, 4); c.fillText(t.toFixed(st < 1 ? 1 : 0) + " s", xx, g.axisY + 8); }
  c.textAlign = "left"; c.fillText(clock(ev.clip.lo_sod), g.L, g.axisY + 20);
  c.textAlign = "right"; c.fillText(clock(ev.clip.lo_sod + D) + " field-PC", W - g.R, g.axisY + 20); c.textAlign = "left";
  // panel names on top of the traces (left edge inside the plot)
  Object.values(g.P).forEach(p => { if (p.y1 - p.y0 < 20) { c.fillStyle = "#97a1ac"; c.fillText(p.label, 4, (p.y0 + p.y1) / 2); return; }
    const w = c.measureText(p.label).width + 8; c.fillStyle = "rgba(10,12,15,0.75)"; c.fillRect(g.L + 2, p.y0 + 2, w, 14); c.fillStyle = "#c9d1d9"; c.fillText(p.label, g.L + 6, p.y0 + 9); });
}
function valAt(ev, t){
  const im = ev.imu, i = Math.round((t - im.t0_s) * im.fs), k = Math.floor(t / ev.bins.bin_s);
  const s = (k >= 0 && k < ev.bins.state.length) ? ev.bins.state[k] : null;
  const om = (i >= 0 && i < im.om.length) ? im.om[i] : null, ad = (i >= 0 && i < im.adev.length) ? im.adev[i] : null;
  const w = ev.wiser_1s.find(r => Math.abs(r[0] - t) <= 0.5);
  return "state " + (s === null ? "—" : ST[s][0]) + " · |ω| " + (om === null ? "—" : om.toFixed(1)) + " °/s · |a|−g " + (ad === null ? "—" : ad.toFixed(2)) +
    " m/s² · WISER " + (w ? "(" + w[1].toFixed(0) + ", " + w[2].toFixed(0) + ") " + w[4] + (w[3] !== null ? ", " + w[3].toFixed(1) + " in/s" : "") : "—");
}
function draw(){
  if (!bg) return;
  const c = cv.getContext("2d"), dpr = window.devicePixelRatio || 1;
  c.setTransform(1, 0, 0, 1, 0, 0); c.drawImage(bg, 0, 0); c.setTransform(dpr, 0, 0, dpr, 0, 0);
  const g = geom(), ev = EV[cur], tv = vid.currentTime || 0, ti = tv - shift();
  if (shift() !== 0) { c.strokeStyle = "rgba(255,214,0,0.35)"; c.setLineDash([2, 3]); c.beginPath(); c.moveTo(g.x(tv), 2); c.lineTo(g.x(tv), g.axisY - 2); c.stroke(); c.setLineDash([]); }
  c.strokeStyle = "#ffd600"; c.lineWidth = 1.5; c.beginPath(); c.moveTo(g.x(ti), 2); c.lineTo(g.x(ti), g.axisY - 2); c.stroke(); c.lineWidth = 1;
  if (hoverT !== null) { c.strokeStyle = "rgba(255,255,255,0.4)"; c.beginPath(); c.moveTo(g.x(hoverT), 2); c.lineTo(g.x(hoverT), g.axisY - 2); c.stroke(); }
  const inEv = ti >= ev.clip.ev_t0_s && ti <= ev.clip.ev_t1_s;
  $("tread").textContent = "video " + tv.toFixed(2) + " s · field-PC " + clock(ev.clip.lo_sod + tv) + (shift() ? " · IMU at " + ti.toFixed(2) + " s" : "") + (inEv ? " · ▶ EVENT" : "") + " · " + vid.playbackRate + "×";
  $("readout").textContent = (hoverT !== null ? "hover " + hoverT.toFixed(2) + " s: " + valAt(ev, hoverT) : "cursor: " + valAt(ev, ti));
}
function loop(){ draw(); if (!vid.paused && !vid.ended) requestAnimationFrame(loop); }
cv.addEventListener("mousemove", e => { const r = cv.getBoundingClientRect(), g = geom(); const t = g.t(e.clientX - r.left); hoverT = (t >= 0 && t <= g.D) ? t : null; draw(); });
cv.addEventListener("mouseleave", () => { hoverT = null; draw(); });
cv.addEventListener("click", e => { const r = cv.getBoundingClientRect(), g = geom(); const t = g.t(e.clientX - r.left); if (t >= 0 && t <= g.D) { vid.currentTime = Math.max(0, t + shift()); } });
["seeked", "timeupdate", "pause", "loadeddata", "ratechange"].forEach(n => vid.addEventListener(n, draw));
vid.addEventListener("play", () => requestAnimationFrame(loop));
vid.addEventListener("error", () => { $("tread").innerHTML = "<span class='warnline'>cannot load clips/" + esc(EV[cur].clip.file) + " — keep index.html next to the clips/ folder</span>"; });
window.addEventListener("resize", () => { buildBg(); draw(); });

// ---------------------------------------------------------------- controls
function stepBy(dt){ vid.pause(); vid.currentTime = Math.max(0, Math.min((vid.duration || EV[cur].clip.dur_s) - 0.001, (vid.currentTime || 0) + dt)); }
function setRate(r){ rate = r; vid.playbackRate = r; vid.defaultPlaybackRate = r; $("speed").value = String(r); saveState(); draw(); }
function speedStep(d){ let i = SPEEDS.indexOf(rate); if (i < 0) i = 3; setRate(SPEEDS[Math.max(0, Math.min(SPEEDS.length - 1, i + d))]); }
SPEEDS.forEach(s => { const o = document.createElement("option"); o.value = String(s); o.textContent = s + "×"; $("speed").appendChild(o); });
$("speed").onchange = () => setRate(parseFloat($("speed").value));
$("bPlay").onclick = () => { vid.paused ? vid.play() : vid.pause(); };
$("bBack1").onclick = () => stepBy(-1); $("bFwd1").onclick = () => stepBy(1);
$("bBackF").onclick = () => stepBy(-1 / EV[cur].clip.fps); $("bFwdF").onclick = () => stepBy(1 / EV[cur].clip.fps);
$("bEvent").onclick = () => { vid.pause(); vid.currentTime = Math.max(0, EV[cur].clip.ev_t0_s + shift()); };
$("shift").oninput = () => { const v = $("shift").value, j = jget(EV[cur].id); j.offset_s = (v === "" || !isFinite(parseFloat(v))) ? "" : parseFloat(v); const fo = $("fOffset"); if (fo) fo.value = j.offset_s; touch(EV[cur].id); draw(); };
$("bDone").onclick = () => { touch(EV[cur].id); select(cur + 1); };
$("reviewer").oninput = () => { reviewer = $("reviewer").value.trim(); saveState(); };
$("fType").onchange = () => { filt.type = $("fType").value; renderList(); };
$("fAnimal").onchange = () => { filt.animal = $("fAnimal").value; renderList(); };
$("fStatus").onchange = () => { filt.status = $("fStatus").value; renderList(); };
Array.from(new Set(EV.map(e => e.animal))).sort().forEach(a => { const o = document.createElement("option"); o.value = a; o.textContent = a; $("fAnimal").appendChild(o); });

document.addEventListener("keydown", e => {
  const t = e.target, tag = t && t.tagName ? t.tagName : "";
  if (tag === "TEXTAREA" || tag === "SELECT" || (tag === "INPUT" && t.type !== "radio" && t.type !== "checkbox")) { if (e.key === "Escape") t.blur(); return; }
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if ($("help").classList.contains("show")) { if (e.key === "Escape" || e.key === "?") { $("help").classList.remove("show"); e.preventDefault(); } return; }
  const fr = 1 / (EV[cur].clip.fps || 20), k = e.key;
  const beh = BEH.find(b => b[2] === k.toLowerCase());
  if (k === " ") { e.preventDefault(); vid.paused ? vid.play() : vid.pause(); }
  else if (k === "ArrowLeft") { e.preventDefault(); stepBy(e.shiftKey ? -1 : -fr); }
  else if (k === "ArrowRight") { e.preventDefault(); stepBy(e.shiftKey ? 1 : fr); }
  else if (k === "ArrowUp" || k === "p") { e.preventDefault(); select(cur - 1); }
  else if (k === "ArrowDown" || k === "n") { e.preventDefault(); select(cur + 1); }
  else if (k === "[") speedStep(-1);
  else if (k === "]") speedStep(1);
  else if (k === "\\") setRate(1);
  else if (k === "j") $("bEvent").onclick();
  else if (k === "Home") { vid.currentTime = 0; }
  else if (k === "Enter") { e.preventDefault(); $("bDone").onclick(); }
  else if (k === "?") { $("help").classList.add("show"); }
  else if (k >= "1" && k <= "3") setRadio("imu_correct", IMUOK[+k - 1][0]);
  else if (k >= "4" && k <= "6") setRadio("identifiable", IDENT[+k - 4][0]);
  else if (beh && !e.shiftKey) toggleBeh(beh[0]);
});

// ---------------------------------------------------------------- export / import
function stamp(){ const d = new Date(), p = n => String(n).padStart(2, "0"); return d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) + "_" + p(d.getHours()) + p(d.getMinutes()); }
function download(name, text, mime){
  const b = new Blob([text], {type: mime}), a = document.createElement("a");
  a.href = URL.createObjectURL(b); a.download = name; document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1500);
}
function rows(){
  return EV.map(ev => { const j = J[ev.id] || {};
    return {id: ev.id, idx: ev.idx, animal: ev.animal, type: ev.type, period: ev.period, start_local: ev.start_local, end_local: ev.end_local,
      clip: ev.clip.file, cameras: ev.cams_text, wiser_zone: ev.zone, imu_event: ev.event_text, imu_dominant_state: ev.summary.dominant_name,
      imu_state_fractions: ev.summary.frac_text, imu_correct: j.imu_correct || "", behaviours: (Array.isArray(j.behaviours) ? j.behaviours : []).join(";"),
      identifiable: j.identifiable || "", offset_s: (j.offset_s === undefined || j.offset_s === null) ? "" : j.offset_s, notes: j.notes || "",
      reviewer: j.reviewer || reviewer, updated: j.updated || "", status: status(ev.id)}; });
}
function fname(ext){ return "imu_video_review_" + DATA.cohort + "_" + (reviewer || "anon").replace(/[^A-Za-z0-9_-]/g, "") + "_" + stamp() + "." + ext; }
$("btnJson").onclick = () => {
  const o = {schema: "imu_video_review_labels/1", cohort: DATA.cohort, run_id: DATA.run_id, run_dir: DATA.run_dir, tool: DATA.tool,
    exported_local: new Date().toString(), reviewer: reviewer, n_events: EV.length, n_done: EV.filter(e => status(e.id) === "done").length,
    rows: rows(), judgements: J};
  download(fname("json"), JSON.stringify(o, null, 1), "application/json");
};
$("btnCsv").onclick = () => {
  const R = rows(), cols = Object.keys(R[0]);
  const q = v => { const s = String(v == null ? "" : v); return /[",\n\r]/.test(s) ? "\"" + s.replace(/"/g, "\"\"") + "\"" : s; };
  download(fname("csv"), [cols.join(",")].concat(R.map(r => cols.map(c => q(r[c])).join(","))).join("\r\n") + "\r\n", "text/csv");
};
$("importFile").onchange = e => {
  const f = e.target.files[0]; if (!f) return;
  const rd = new FileReader();
  rd.onload = () => {
    try {
      const o = JSON.parse(rd.result), src = o.judgements || {}; let n = 0;
      Object.keys(src).forEach(id => { if (src[id] && EV.some(x => x.id === id)) { J[id] = Object.assign(jget(id), src[id]); n++; } });
      if (o.reviewer && !reviewer) { reviewer = o.reviewer; $("reviewer").value = reviewer; }
      saveState(); select(cur); alert("Imported " + n + " judgements from " + f.name);
    } catch (err) { alert("Import failed: " + err); }
  };
  rd.readAsText(f); e.target.value = "";
};

// ---------------------------------------------------------------- static panels
function renderStatic(){
  $("legend").innerHTML = ST.map(s => "<span><i style='background:" + s[1] + "'></i>" + esc(s[0]) + "</span>").join("") +
    "<span class='mut'>· bands: " + EV[0].imu.bands.map((b, j) => "<b style='color:" + BANDCOL[j] + "'>" + esc(b) + "</b>").join(" ") +
    " · dashed: red = 12–20 Hz p99 (SHAKE), amber = 4–12 Hz floor (RHYTHMIC) · red ticks = gyro clipping, red bar = clipped shake train · shaded = event span</span>";
  $("idtab").innerHTML = "<tr><th>rat</th><th>tag</th><th>IR mark</th><th>coban</th><th>sticker</th><th>note</th></tr>" +
    DATA.identity.map(r => "<tr><td><b>" + esc(r.animal) + "</b></td><td>" + esc(r.tag) + "</td><td>" + esc(r.pattern) + "</td><td>" + esc(r.coban) + "</td><td>" + esc(r.sticker) + "</td><td class='mut'>" + esc(r.note) + "</td></tr>").join("");
  $("helpcard").innerHTML = "<h3 style='margin-top:0'>How to review</h3><p>" + DATA.help.map(esc).join("</p><p>") + "</p>" +
    "<h4>Keyboard</h4><table>" + [["Space", "play / pause"], ["← / →", "one frame (1/" + EV[0].clip.fps + " s); Shift = 1 s"], ["[ / ] / \\", "slower / faster / 1×"], ["j", "jump to the event start"],
      ["↑ / ↓ or p / n", "previous / next event"], ["1 2 3", "IMU label correct: yes / no / can't tell"], ["4 5 6", "identifiable: yes / another rat / not visible"],
      ["s w h g c l r d e i o", "toggle behaviour: still, wet-dog shake, head shake, grooming, scratching, walking/running, rearing, digging, eating, interacting, other"],
      ["Enter", "save & next"], ["? / Esc", "this help"]].map(r => "<tr><td><span class='kbd'>" + esc(r[0]) + "</span></td><td>" + esc(r[1]) + "</td></tr>").join("") + "</table>" +
    "<h4>IMU states and thresholds (the IMU's guesses)</h4><table>" + DATA.thresholds.map(r => "<tr><td><b>" + esc(r[0]) + "</b></td><td>" + esc(r[1]) + "</td></tr>").join("") + "</table>" +
    "<p class='mut'>Run " + esc(DATA.run_dir) + " · " + esc(DATA.tool) + " · generated " + esc(DATA.generated) + "</p><p><button onclick=\"document.getElementById('help').classList.remove('show')\">close (Esc)</button></p>";
}
$("btnHelp").onclick = () => $("help").classList.add("show");
$("help").onclick = e => { if (e.target === $("help")) $("help").classList.remove("show"); };

loadState();
$("reviewer").value = reviewer;
$("speed").value = String(rate);
renderStatic();
select(cur);
</script>
</body></html>
"""


def write_html(out_dir: Path, payload: dict) -> Path:
    js = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = HTML_TEMPLATE.replace("__DATA_JSON__", js).replace("__COHORT__", payload["cohort"])
    p = out_dir / "index.html"
    p.write_text(html, encoding="utf-8")
    return p


def page_payload(cohort: str, run_dir: Path, events: list, ids: pd.DataFrame) -> dict:
    t_ref = max((pd.Timestamp(e["start_local"]).tz_localize(TZ).value // 10**6 for e in events), default=0)
    rows = []
    for a in sorted(ids["animal"].unique()):
        info = identity_at(ids, a, t_ref)
        note = ""
        if info["tag"] == "?":
            r = ids[ids["animal"] == a].iloc[-1]
            info = {"tag": f"{r.physical_tag_id} (until {str(r.valid_until)[5:16]})", "pattern": r.pattern,
                    "coban": r.coband_color, "sticker": r.sticker_color}
            note = "implant + tag off 09-07 06:10; the rat stays in the paddock, untracked (no logger, no tag)" if a == "SF11" else "no valid tag at these dates"
        rows.append({"animal": a, "tag": info["tag"], "pattern": info["pattern"], "coban": info["coban"], "sticker": info["sticker"], "note": note})
    help_ = [
        "Each clip runs from 5 s before to 5 s after one head-IMU event. The banner shows the IMU's guess: rows 1–2 are fixed (animal, WISER tag, IR mark, the event and its numbers, time, cameras, WISER zone); row 3 updates every 0.25 s with the IMU state and the gyro / accelerometer magnitudes; ▶ EVENT marks the event span.",
        "Cameras were chosen automatically from the animal's WISER position (reason under the traces). house_1 → CH08 in-box + CH05 top-down; house_2 → CH07 in-box + CH06 top-down; elsewhere → CH01 + CH02 panoramas. WISER positions are noisy (~4–7 in) and in an unverified frame; if the rat is not where the cameras look, say so (identifiable = not visible).",
        "Find the labelled rat by its IR mark (night and in-box frames are monochrome) or its coban colour (colour frames only). Six rats are in the paddock: five with loggers (SF07–SF10, SF12) and SF11 without logger or tag since 09-07.",
        "Clip time = video file-name time (field-PC clock), good to about ±1 s. If the video shows the IMU event earlier/later, enter the shift (video − IMU, s): the traces move, and it is saved as the offset seen. Never read the clock burnt into the image (≈ 59½ min behind).",
        "Judgements autosave in this browser only. Export JSON (and CSV) when done and put the files in wiser/configs/imu_video_review_" + cohort + "/ in the analysis repo.",
    ]
    return {"cohort": cohort, "run_id": run_dir.name, "run_dir": str(run_dir), "tool": "wiser/scripts/make_imu_video_review.py",
            "generated": time.strftime("%Y-%m-%d %H:%M"), "states": [[n, c] for n, c in STATES], "thresholds": THRESHOLDS,
            "identity": rows, "help": help_, "events": events}


def check_js(html_path: Path) -> tuple[bool, str]:
    node = shutil.which("node") or r"C:\Program Files\nodejs\node.exe"
    txt = html_path.read_text(encoding="utf-8")
    m = re.search(r"<script>(.*)</script>", txt, re.S)
    if not m:
        return False, "no <script>"
    with tempfile.TemporaryDirectory() as td:
        jsf = Path(td) / "page.js"
        jsf.write_text(m.group(1), encoding="utf-8")
        p = subprocess.run([node, "--check", str(jsf)], capture_output=True, text=True)
        return p.returncode == 0, (p.stderr or p.stdout).strip()[-800:]


# ====================================================================================================== README
def write_readme(out_dir: Path, cohort: str, payloads: list, results: dict, enc: str, checks: Path, wall_s: float) -> None:
    ok = [p for p in payloads if results.get(p["id"], {}).get("ok")]
    tot_mb = sum(results[p["id"]].get("size_bytes", 0) for p in ok) / 1e6
    tot_s = sum(results[p["id"]].get("duration_s", 0) for p in ok)
    lines = [f"# Head-IMU video review — cohort {cohort}", "",
             f"Written by `wiser/scripts/make_imu_video_review.py` (git {git_commit()}) on {time.strftime('%Y-%m-%d %H:%M')}; "
             f"plan `implementation_plan/2026-10-01-imu-video-review.md`. Events: `{checks}`.", "",
             "## How to use", "",
             "1. Open `index.html` in Chrome / Edge / Firefox (double-click; it works from file:// — keep it next to `clips/`).",
             "2. Pick an event on the left, play the clip (Space; ←/→ one frame, Shift 1 s; [ ] speed), compare the rat with the IMU banner and the traces under the video (the yellow cursor follows the video).",
             "3. Answer on the right: IMU label correct? · what is THIS rat doing (all that apply) · is the labelled rat identifiable · optional time offset · notes. Enter = save & next. Press ? for all keys and the rules.",
             f"4. Judgements autosave in the browser only. **Export JSON + CSV** and put them in `wiser/configs/imu_video_review_{cohort}/` of the analysis repo (human labels, committed).",
             "", "## What the banner says", "",
             "Rows 1–2 (fixed): animal · WISER tag · IR mark (coban) · IMU event + numbers / event start (field-PC file-name time, ±1 s) · cameras · WISER zone. "
             "Row 3 (every 0.25 s): `IMU now: <state> · |ω| · |a|−g · field-PC time`, and `▶ EVENT` inside the event span. These are the IMU's guesses — the review decides.", "",
             "| state / rule | definition |", "|---|---|"] + [f"| {a} | {b} |" for a, b in THRESHOLDS] + [
             "", "Never read the clock burnt into the image (NVR OSD, ≈ 59½ min behind the field PC). Cameras: house_1 → CH08 in-box + CH05 top-down; "
             "house_2 → CH07 in-box + CH06 top-down; outside / no WISER → CH01 + CH02 panoramas (upright).", "",
             "## Files", "",
             f"- `clips/` — {len(ok)} H.264 clips ({enc}), {tot_mb:.0f} MB, {tot_s / 60:.1f} min in total; 20 fps; banner 216 px.",
             "- `index.html` — the review page (all data embedded); `events.json` — the same data; `event_summary.csv` — one row per event.",
             "- `overlay_ass/` — the exact ASS overlay of each clip; `_fonts/` — DejaVu Sans used by the overlay; `log.txt`.",
             "", "## Events", "", "| # | animal | IMU event | start (field-PC) | cameras / WISER zone | IMU state during the event | clip |", "|---|---|---|---|---|---|---|"]
    for p in payloads:
        r = results.get(p["id"], {})
        lines.append(f"| {p['idx']} | {p['animal']} | {p['event_text']} | {p['start_local'][:19]} | {p['cams_text']} / {p['zone_text']} | "
                     f"{p['summary']['frac_text']} | {p['clip']['file'] if r.get('ok') else 'FAILED'} |")
    lines += ["", f"Wall time {wall_s / 60:.1f} min."]
    (out_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ====================================================================================================== driver
def run(args) -> int:
    t_start = time.time()
    cohort = args.cohort
    cfg, _p0 = G2.load_cfg(cohort)
    ctx = G2.context(cfg)
    gate_run = Path(cfg["fitted"]["run_dir"])
    checks = Path(args.checks) if args.checks else gate_run / "human_checks.csv"
    sat_runs = pd.read_csv(gate_run / "sat_runs.csv.gz")
    out = Path(args.out) if args.out else output_paths.run_dir(NAME, cohort, make_figures=False)
    for sub in ("clips", "overlay_ass", "_fonts"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    fh = open(out / "log.txt", "a", encoding="utf-8")
    log(f"{NAME}: out {out}; events {checks}; root {args.root}; git {git_commit()}", fh)
    fonts = find_fonts()
    if "regular" not in fonts or "bold" not in fonts:
        raise SystemExit("DejaVu Sans (DejaVuSans.ttf / DejaVuSans-Bold.ttf) not found - needed for the overlay glyphs (ω ° − ▶)")
    for f in fonts.values():
        shutil.copy2(f, out / "_fonts" / f.name)
    ffmpeg, ffprobe = GF.find_ffmpeg()
    enc = args.encoder
    if enc == "auto":
        enc = "nvenc" if nvenc_works(ffmpeg) else "x264"
    log(f"encoder {enc}; fonts {[str(f) for f in fonts.values()]}", fh)
    rois = json.loads((REPO / "wiser" / "configs" / "wiser_rois.json").read_text(encoding="utf-8"))
    houses = [r for r in rois["rois"] if r["name"] in ("house_1", "house_2")]
    ids = load_identity(cohort)
    events = read_events(checks)
    if args.only:
        events = [e for e in events if e["idx"] in set(args.only)]
    payloads, jobs = {}, {}
    for (animal, pkey), grp in pd.DataFrame(events).groupby(["animal", "period"], sort=False):
        P = load_period_imu(animal, pkey, cfg, ctx, sat_runs, fh)
        ws = wiser_seconds(G2.load_fixes(cfg, pkey, animal))
        for ev in grp.to_dict("records"):
            pl, job = build_event(ev, P, ws, houses, ids, Path(args.root), ffprobe, out, fonts)
            payloads[ev["id"]], jobs[ev["id"]] = pl, job
            log(f"  #{ev['idx']:02d} {animal} {ev['type_short']} {ev['start_local'][:19]}: zone {pl['zone_text']} -> {pl['cams_text']}; "
                f"IMU in event: {pl['summary']['frac_text']}; parts {[len(c['parts']) for c in pl['cams']]}, gaps {[c['gaps'] for c in pl['cams']]}", fh)
        del P
    order = [e["id"] for e in events]
    log(f"rendering {len(order)} clips with {args.workers} workers ...", fh)
    results = {}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = {i: ex.submit(render, ffmpeg, ffprobe, jobs[i], out, enc) for i in order}
        for i in order:
            r = futs[i].result()
            results[i] = r
            if r["ok"]:
                log(f"  clip {Path(jobs[i]['out']).name}: {r.get('width')}x{r.get('height')} {r.get('duration_s', 0):.1f} s "
                    f"{r.get('size_bytes', 0) / 1e6:.1f} MB {r['encoder']} in {r['seconds']} s"
                    + (f"; GLYPH WARNINGS {r['glyph_warnings']}" if r["glyph_warnings"] else ""), fh)
            else:
                log(f"  clip {Path(jobs[i]['out']).name}: FAILED - {r.get('error', '')[-600:]}", fh)
    evs = []
    for i in order:
        pl = payloads[i]
        r = results[i]
        pl["clip"].update({"ok": bool(r["ok"]), "encoder": r.get("encoder"), "size_bytes": r.get("size_bytes"),
                           "duration_probe_s": r.get("duration_s")})
        evs.append(pl)
    page = page_payload(cohort, out, evs, ids)
    (out / "events.json").write_text(json.dumps(page, ensure_ascii=False, indent=1), encoding="utf-8")
    html = write_html(out, page)
    ok_js, msg = check_js(html)
    log(f"index.html {html.stat().st_size / 1e6:.1f} MB; node --check {'OK' if ok_js else 'FAILED ' + msg}", fh)
    with open(out / "event_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["idx", "id", "animal", "type", "start_local", "end_local", "imu_event", "zone", "wiser_x", "wiser_y", "cameras",
                    "imu_dominant_state", "imu_state_fractions", "clip", "clip_ok", "clip_s", "clip_mb", "zone_reason"])
        for p in evs:
            w.writerow([p["idx"], p["id"], p["animal"], p["type"], p["start_local"], p["end_local"], p["event_text"], p["zone"],
                        p["wiser_xy"][0], p["wiser_xy"][1], p["cams_text"], p["summary"]["dominant_name"], p["summary"]["frac_text"],
                        p["clip"]["file"], p["clip"]["ok"], p["clip"].get("duration_probe_s"),
                        round((p["clip"].get("size_bytes") or 0) / 1e6, 1), p["zone_reason"]])
    write_readme(out, cohort, evs, results, enc, checks, time.time() - t_start)
    n_ok = sum(1 for r in results.values() if r["ok"])
    log(f"done: {n_ok}/{len(results)} clips, {sum(r.get('size_bytes', 0) for r in results.values()) / 1e6:.0f} MB, "
        f"{sum(r.get('duration_s', 0) for r in results.values()) / 60:.1f} min; wall {(time.time() - t_start) / 60:.1f} min -> {out}", fh)
    fh.close()
    return 0 if n_ok == len(results) and ok_js else 1


def html_only(run_dir: Path) -> int:
    page = json.loads((run_dir / "events.json").read_text(encoding="utf-8"))
    page["generated"] = time.strftime("%Y-%m-%d %H:%M") + " (html rebuilt)"
    page["thresholds"] = THRESHOLDS
    html = write_html(run_dir, page)
    ok, msg = check_js(html)
    print(f"index.html rebuilt ({html.stat().st_size / 1e6:.1f} MB); node --check {'OK' if ok else 'FAILED ' + msg}")
    return 0 if ok else 1


# ====================================================================================================== self-test
def selftest() -> int:
    ok_all = True

    def check(name, cond, info=""):
        nonlocal ok_all
        ok_all &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {info}", flush=True)

    rng = np.random.default_rng(7)
    # ---------------------------------------------------------------- 1. classifier on synthetic 100-Hz signals
    fs, T = FS100, 80.0
    n = int(T * fs)
    t = np.arange(n) / fs
    acc = np.tile([0.0, 0.0, G], (n, 1)) + rng.normal(0, 0.002, (n, 3))
    gyr = rng.normal(0, 0.15, (n, 3))
    seg = lambda a, b: (t >= a) & (t < b)  # noqa: E731
    # 0-10 still; 10-20 quiet (slow 0.3-Hz nod, 4 deg/s, small tilt wobble); 20-30 rhythmic 6 Hz; 30-40 broadband active;
    # 40-41 shake (16 Hz, 900 deg/s, |a| ~ 4 g); 41-50 broadband; 50-60 locomotion (WISER 20 in/s); 60-80 broadband low
    m = seg(10, 20)
    gyr[m, 1] += 4.0 * np.sin(2 * np.pi * 0.3 * t[m])
    tilt = np.deg2rad(1.0) * np.sin(2 * np.pi * 0.3 * t[m])
    acc[m, 0] += G * np.sin(tilt)
    m = seg(20, 30)
    gyr[m, 0] += 120 * np.sin(2 * np.pi * 6.0 * t[m])
    acc[m] += rng.normal(0, 0.3, (m.sum(), 3))
    sos = signal.butter(2, 1.2, fs=fs, output="sos")
    for a_, b_ in ((30, 40), (41, 50), (50, 60), (60, 80)):
        m = seg(a_, b_)
        gyr[m] += signal.sosfiltfilt(sos, rng.normal(0, 400, (m.sum(), 3)), axis=0)
        acc[m] += signal.sosfiltfilt(sos, rng.normal(0, 8, (m.sum(), 3)), axis=0)
    m = seg(40, 41)
    gyr[m, 0] += 900 * np.sin(2 * np.pi * 16 * t[m])
    acc[m, 1] += 3.5 * G * np.sin(2 * np.pi * 16 * t[m] + 0.7)
    om, am = np.linalg.norm(gyr, axis=1), np.linalg.norm(acc, axis=1)
    cfg_st = {"strict": {"block_s": 0.1, "gate_min_len_s": 1.0, "dir_max_deg": 0.3, "mag_tol_g": 0.03, "omega_max_dps": 3.0}}
    strict, win = strict_mask(acc, om, np.ones(n, bool), cfg_st)
    quiet = quiet_rule_1s(acc, gyr, fs)
    bp = band_powers(gyr, fs)
    thr = {"p99_hi": float(np.percentile(bp[:, 3], SHAKE_PCTL)), "rhythm_floor": RHYTHM_FLOOR}
    t_ms = 1.789e12 + t * 1000.0
    edges = t_ms[0] + 1000.0 * BIN_S * np.arange(int(T / BIN_S) + 1)
    speed = {int(math.floor((t_ms[0] + 1000 * s) / 1000.0)): (20.0 if 50 <= s < 60 else 1.0) for s in range(-1, int(T) + 2)}
    res = classify_bins(t_ms, om, am, bp, strict, quiet, np.ones(n, bool), np.zeros((0, 2)), lambda s: speed.get(int(s), float("nan")), edges, thr)
    st = res["state"]
    mids = ((edges[:-1] + edges[1:]) / 2 - t_ms[0]) / 1000.0                  # bin centres, s from the start

    def frac_in(a, b, code):
        k = (mids >= a + 0.5) & (mids < b - 0.5)
        return float(np.mean(st[k] == code))

    check("still segment -> STILL", frac_in(0, 10, S_STILL) >= 0.9, f"{frac_in(0, 10, S_STILL):.2f}")
    check("slow-nod segment -> QUIET (not strict)", frac_in(10, 20, S_QUIET) >= 0.8, f"{frac_in(10, 20, S_QUIET):.2f}")
    check("6-Hz oscillation -> RHYTHMIC", frac_in(20, 30, S_RHYTHM) >= 0.8, f"{frac_in(20, 30, S_RHYTHM):.2f}")
    check("16-Hz burst with |a| > 2 g -> SHAKE (band-power rule)", float(np.mean(st[(mids >= 40.0) & (mids < 41.0)] == S_SHAKE)) >= 0.75,
          f"{np.mean(st[(mids >= 40.0) & (mids < 41.0)] == S_SHAKE):.2f}")
    check("broadband movement -> ACTIVE", frac_in(31, 39, S_ACTIVE) >= 0.7, f"{frac_in(31, 39, S_ACTIVE):.2f}")
    check("WISER >= 10 in/s with movement -> LOCOMOTION", frac_in(50, 60, S_LOCO) >= 0.9, f"{frac_in(50, 60, S_LOCO):.2f}")
    spans = np.array([[t_ms[0] + 65_000.0, t_ms[0] + 65_300.0]])
    res2 = classify_bins(t_ms, om, am, bp, strict, quiet, np.ones(n, bool), spans, lambda s: speed.get(int(s), float("nan")), edges, thr)
    k = (mids > 64.9) & (mids < 65.4)
    check("clipped shake-train span -> SHAKE", k.sum() >= 2 and bool(np.all(res2["state"][k] == S_SHAKE)), str(res2["state"][k].tolist()))
    pres = np.ones(n, bool)
    pres[int(70 * fs):int(72 * fs)] = False
    res3 = classify_bins(t_ms, om, am, bp, strict, quiet, pres, np.zeros((0, 2)), lambda s: speed.get(int(s), float("nan")), edges, thr)
    kf = (mids > 70.1) & (mids < 71.9)
    check("frozen samples -> NO IMU", kf.sum() >= 6 and bool(np.all(res3["state"][kf] == S_NOIMU)), f"{int(kf.sum())} bins")
    # vector vs norm band power: a 15-Hz single-axis oscillation is in 12-20 Hz for the vector power, not for the norm
    x15 = np.zeros((2000, 3))
    x15[:, 2] = 300 * np.sin(2 * np.pi * 15 * np.arange(2000) / fs)
    bv = band_powers(x15, fs)[500:1500].mean(axis=0)
    sosb = signal.butter(4, [12, 20], btype="bandpass", fs=fs, output="sos")
    bn = float(np.mean(signal.sosfiltfilt(sosb, np.abs(x15[:, 2]))[500:1500] ** 2))
    check("vector band power keeps a 15-Hz shake in 12-20 Hz (the norm moves it to 30 Hz)", bv[3] > 50 * bn and bv[3] == bv.max(),
          f"vector {bv[3]:.0f} vs norm {bn:.1f} (deg/s)^2")

    # ---------------------------------------------------------------- 2. zone + identity
    houses = [{"name": "house_1", "shape": "rect", "x": 411.46, "y": 718.61, "width_in": 36.39, "height_in": 26.59, "orientation_deg": 90.0},
              {"name": "house_2", "shape": "rect", "x": 613.58, "y": 717.34, "width_in": 36.39, "height_in": 26.59, "orientation_deg": 90.0}]
    check("zone: (620, 731) -> house_2 core", house_label(620, 731, houses) == ("house_2", True))
    check("zone: (640, 717) -> house_2 buffer only", house_label(640, 717, houses) == ("house_2", False), str(house_label(640, 717, houses)))
    check("zone: (674, 842) / (483, 711) -> outside", house_label(674, 842, houses)[0] == "outside" and house_label(483, 711, houses)[0] == "outside")
    ws = pd.DataFrame({"sec": np.arange(100, 110), "x": [408.0] * 10, "y": [715.0] * 10, "speed": [1.0] * 10, "n": [5] * 10})
    z = choose_zone(ws, 104_000.0, 105_000.0, houses)
    check("choose_zone: house_1 -> CH08 + CH05", z["zone"] == "house_1" and [c for c, _ in z["cams"]] == ["CH08", "CH05"])
    z = choose_zone(ws, 200_000.0, 201_000.0, houses)
    check("choose_zone: no fix within 30 s -> panoramas", z["zone"] == "outside" and z["n"] == 0 and [c for c, _ in z["cams"]] == ["CH01", "CH02"])
    ids = load_identity("2026c")
    i10 = identity_at(ids, "SF10", G2.to_ms("2026-09-10 22:00:00", TZ))
    check("identity: SF10 tag 306b, square with cross, yellow coban after 08-31",
          i10["tag"] == "306b" and i10["pattern"] == "square with cross" and i10["coban"] == "yellow", str(i10))

    # ---------------------------------------------------------------- 3. synthetic clip: parts, overlay timing, render
    ffmpeg, ffprobe = GF.find_ffmpeg()
    fonts = find_fonts()
    check("DejaVu Sans fonts found", "regular" in fonts and "bold" in fonts, str(fonts))
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "video"
        out = Path(td) / "run"
        for sub in ("clips", "overlay_ass", "_fonts"):
            (out / sub).mkdir(parents=True)
        for f in fonts.values():
            shutil.copy2(f, out / "_fonts" / f.name)

        def make(cam: str, day: str, name: str, secs: float):
            d = root / day / cam
            d.mkdir(parents=True, exist_ok=True)
            # luma encodes the source frame index: Y = 100 + (5 N mod 130)
            subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=gray:s=320x240:r=20:d={secs}",
                            "-vf", "geq=lum=100+mod(5*N\\,130):cb=128:cr=128", "-c:v", "libx264", "-g", "40",
                            "-pix_fmt", "yuv420p", str(d / name)], check=True)
        make("CH07", "2026-09-10", "CH07_2026-09-10_23-59-55_to_00-00-01.mp4", 6)      # crosses midnight
        make("CH07", "2026-09-11", "CH07_2026-09-11_00-00-01.mp4", 6)                  # never renamed
        make("CH06", "2026-09-10", "CH06_2026-09-10_23-59-55_to_23-59-58.mp4", 3)      # then a 2-s gap
        make("CH06", "2026-09-11", "CH06_2026-09-11_00-00-00_to_00-00-06.mp4", 6)
        clip_lo, clip_hi = datetime(2026, 9, 10, 23, 59, 56), datetime(2026, 9, 11, 0, 0, 5)
        D = (clip_hi - clip_lo).total_seconds()
        p7, g7 = view_parts(root, "CH07", clip_lo, clip_hi, ffprobe)
        p6, g6 = view_parts(root, "CH06", clip_lo, clip_hi, ffprobe)
        check("parts: CH07 = closed segment (midnight) + never-renamed segment, no gap",
              len(p7) == 2 and abs(p7[0]["offset_s"] - 1.0) < 1e-6 and abs(p7[1]["clip_t0_s"] - 5.0) < 1e-6 and not g7,
              f"{[(p['file'], p['offset_s'], p['dur_s'], p['clip_t0_s']) for p in p7]} gaps {g7}")
        check("parts: CH06 gap 2-4 s found", len(p6) == 2 and g6 == [[2.0, 4.0]], f"gaps {g6}")
        lay = layout("house_2", scale=0.25)
        nb = int(math.ceil(D / BIN_S))
        bins = {"state": np.array([S_ACTIVE] * nb, np.int8), "om": np.full(nb, 50.0), "a_rms": np.full(nb, 1.0)}
        bins["state"][20:24] = S_SHAKE                                   # 5.0-6.0 s
        ev_span = (5.0, 6.0)
        T_ = write_ass(out / "overlay_ass" / "t.ass", lay, ["SF10 · tag 306b · IR mark: square with cross · IMU event: SHAKE TRAIN test",
                                                             "2026-09-11 00:00:01 field-PC · CH07 in-box + CH06 top-down · WISER: house_2"],
                       bins, BIN_S, D, ev_span, ["CH07 · in-box · house_2", "CH06 · top-down · house_2"], [g7, g6], 86396.0, fonts)
        dyn = T_["dyn"]
        tiles = all(abs(dyn[i][1] - dyn[i + 1][0]) < 1e-9 for i in range(len(dyn) - 1)) and abs(dyn[0][0]) < 1e-9 and abs(dyn[-1][1] - D) < 1e-9
        check("overlay: dynamic row tiles the clip in 0.25-s steps", tiles and len(dyn) == nb, f"{len(dyn)} lines")
        check("overlay: SHAKE text exactly in 5.0-6.0 s", all(("SHAKE" in x[2]) == (5.0 <= x[0] < 6.0) for x in dyn))
        check("overlay: EVENT tag spans the event", T_["event"] == [(5.0, 6.0, "▶ EVENT")], str(T_["event"]))
        check("overlay: NO VIDEO only in the CH06 gap", T_["nov"] == [(2.0, 4.0, "CH06 · top-down · house_2")], str(T_["nov"]))
        txt = (out / "overlay_ass" / "t.ass").read_text(encoding="utf-8")
        check("overlay: dynamic line carries the field-PC clock", "23:59:56.00" in txt and "00:00:00.50" in txt)
        enc = "nvenc" if nvenc_works(ffmpeg) else "x264"
        job = {"id": "t", "out": str(out / "clips" / "t.mp4"), "layout": lay, "view_parts": [p7, p6], "D": D,
               "ass_rel": "overlay_ass/t.ass", "fonts_rel": "_fonts"}
        r = render(ffmpeg, ffprobe, job, out, enc)
        check(f"render ({r.get('encoder')}): H.264 yuv420p {lay['W']}x{lay['H']}", r["ok"] and r.get("codec") == "h264" and r.get("pix_fmt") == "yuv420p"
              and r.get("width") == lay["W"] and r.get("height") == lay["H"], r.get("error", "")[-300:])
        check("render: duration = clip (+-1 frame)", r["ok"] and abs(r.get("duration_s", 0) - D) <= 1.0 / FPS + 1e-3, f"{r.get('duration_s')} vs {D}")
        check("render: no missing-glyph warnings from libass", r["ok"] and not r["glyph_warnings"], str(r.get("glyph_warnings")))
        if r["ok"]:
            W, H = lay["W"], lay["H"]
            # raw yuv420p, Y plane only (no limited -> full range conversion)
            p = subprocess.run([ffmpeg, "-v", "error", "-i", job["out"], "-f", "rawvideo", "-pix_fmt", "yuv420p", "-"], capture_output=True)
            fsz = W * H * 3 // 2
            fr = np.frombuffer(p.stdout, np.uint8).reshape(-1, fsz)[:, :W * H].reshape(-1, H, W)
            nf = len(fr)

            def region(v, k):
                y0, y1 = v["y"] + int(0.6 * v["h"]), v["y"] + int(0.9 * v["h"])
                x0, x1 = v["x"] + int(0.1 * v["w"]), v["x"] + int(0.9 * v["w"])
                return float(fr[k, y0:y1, x0:x1].mean())

            def expected(parts, tc):
                for pp in parts:
                    if pp["clip_t0_s"] - 1e-6 <= tc < pp["clip_t0_s"] + pp["dur_s"] - 1e-6:
                        N = int(math.floor((tc - pp["clip_t0_s"] + pp["offset_s"]) * 20 + 1e-6))
                        return 100 + (5 * N) % 130
                return None
            good, tot, gapdark, bad = 0, 0, [], []
            for k in range(nf):
                tc = k / FPS
                for v, parts in zip(lay["views"], [p7, p6]):
                    e = expected(parts, tc)
                    val = region(v, k)
                    if e is None:
                        gapdark.append(val)
                        continue
                    tot += 1
                    good += abs(val - e) <= 4
                    if abs(val - e) > 4 and len(bad) < 6:
                        bad.append((k, round(val, 1), e))
            check("timing: each view shows the source frame of its file-name time (luma-coded frames)", tot and good / tot >= 0.95,
                  f"{good}/{tot} frames within 1 code step; first misses (frame, luma, expected) {bad}")
            check("timing: the CH06 gap shows the empty canvas", len(gapdark) >= 30 and max(gapdark) < 90, f"n {len(gapdark)}, max luma {max(gapdark) if gapdark else None}")
            ys, xs = int(round(142 * 0.25)), W - int(round(24 * 0.25)) - int(round(text_width_px('▶ EVENT', 15, True, fonts)))
            tag = lambda k: float(fr[k, ys:ys + 14, xs:W - 6].mean())  # noqa: E731
            inside, outside = tag(int(5.5 * FPS)), tag(int(2.5 * FPS))
            check("overlay: EVENT box drawn inside the event span only", inside - outside > 15, f"luma {inside:.0f} vs {outside:.0f}")

    # ---------------------------------------------------------------- 4. HTML page + node --check
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        ev = {"idx": 1, "id": "E01_shake_SF10_0910_220000", "type": "shake train (gyro clipped)", "type_short": "shake", "type_label": "SHAKE train",
              "animal": "SF10", "period": "night_20260910", "start_local": "2026-09-10 22:00:00.000", "end_local": "2026-09-10 22:00:00.300",
              "detail": "3 clipped readings, |a|max 8.0 g, net 5 deg", "identity": identity_at(ids, "SF10", G2.to_ms("2026-09-10 22:00:00", TZ)),
              "event_text": "SHAKE TRAIN 3 clipped gyro readings |a|max 8.0 g, net 5°", "overlay_static": ["row 1 </script> test", "row 2"],
              "zone": "house_2", "zone_text": "house_2 (620, 731) in", "zone_reason": "test", "zone_fractions": {"house_2": 1.0}, "wiser_xy": [620, 731],
              "wiser_n": 9, "cams_text": "CH07 in-box + CH06 top-down",
              "cams": [{"cam": "CH07", "role": "in-box", "parts": [{"file": "a.mp4", "offset_s": 1.0, "dur_s": 10.3, "clip_t0_s": 0.0}], "gaps": []},
                       {"cam": "CH06", "role": "top-down", "parts": [], "gaps": [[0.0, 10.3]]}],
              "clip": {"file": "a.mp4", "lo_local": "2026-09-10 21:59:55.000", "hi_local": "2026-09-10 22:00:05.300", "lo_ms": 0, "lo_sod": 79195.0,
                       "dur_s": 10.3, "ev_t0_s": 5.0, "ev_t1_s": 5.3, "fps": 20, "width": 3840, "height": 1656},
              "imu": {"t0_s": 0.0, "fs": 100.0, "om": [1.0, None, 3.0], "adev": [0.1, None, -0.2], "bp_fs": 20.0, "bp": [[1, 2], [1, 2], [1, 2], [1, 2]],
                      "bands": ["2–4 Hz", "4–8 Hz", "8–12 Hz", "12–20 Hz"], "sat_idx": [1], "shake_spans": [[5.0, 5.3]], "p99_hi": 100.0, "rhythm_floor": 10.0},
              "bins": {"bin_s": 0.25, "state": [3, 6, 1], "om": [1.0, 2.0, None], "a_rms": [0.1, 0.2, None]},
              "wiser_1s": [[0.5, 620.0, 731.0, 1.2, "house_2"]],
              "summary": {"dominant": 6, "dominant_name": "SHAKE", "dominant_frac": 1.0, "frac": {"SHAKE": 1.0}, "frac_text": "SHAKE 100 %"}}
        page = page_payload("2026c", out, [ev], ids)
        html = write_html(out, page)
        txt = html.read_text(encoding="utf-8")
        check("HTML: data embedded, '</script>' inside data escaped", txt.count("</script>") == 1 and "row 1 <\\/script> test" in txt)
        okj, msg = check_js(html)
        check("HTML: page JavaScript passes node --check", okj, msg)
        check("HTML: identity table has SF11 untracked note", any(r["animal"] == "SF11" and "untracked" in r["note"] for r in page["identity"]))
    print("PASS - make_imu_video_review self-test" if ok_all else "FAIL - make_imu_video_review self-test")
    return 0 if ok_all else 1


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], allow_abbrev=False)
    ap.add_argument("--cohort", default="2026c")
    ap.add_argument("--checks", default=None, help="events CSV (default: gate-v2 run human_checks.csv)")
    ap.add_argument("--root", default=r"F:\3rd_rat", help="cohort video root <root>/<date>/<CH>/")
    ap.add_argument("--out", default=None, help="output folder (default: a new run dir under $FIELD2026_ANALYSIS_OUT_ROOT/<c>/)")
    ap.add_argument("--encoder", choices=["auto", "nvenc", "x264"], default="auto")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--only", type=int, nargs="+", default=None, help="event numbers (1-based rows of the CSV)")
    ap.add_argument("--html-only", default=None, help="rebuild index.html of an existing run from its events.json")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.html_only:
        return html_only(Path(a.html_only))
    return run(a)


if __name__ == "__main__":
    raise SystemExit(main())
