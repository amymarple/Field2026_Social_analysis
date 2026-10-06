r"""IMU-WISER consistency audit: where does WISER move or turn while the head IMU says it cannot? (cohort 2026c)

Plan: implementation_plan/2026-10-05-wiser-imu-consistency-audit.md (approved by the user 2026-10-05, "搞"; committed ff3c75c
before any result; operational details in its Amendment 1, written before any number). Report (full Definitions section):
results/<cohort>/wiser_baseline/reports/wiser_baseline_imu_consistency_<cohort>.md. MEASUREMENT ONLY - no correction is
applied; the production tracks are not modified.

  Scope     SF07-SF12, every production day, included seconds only (IMU-QC-ok per the IMU-seconds cache, no masked fix,
            before SF11's implant loss). Tracks: V3 (production default, primary), B2 (wiser_tracks_B2), raw fixes.
  I1        displacement without locomotion: run = maximal stretch of included seconds with no locomoting second, >= 5 s,
            trimmed 2 s at both ends; reference r = median of the 1-s medians p~ over the first 2 s of the trimmed run;
            event when |p~(s) - r| >= 12 in for >= 2 consecutive seconds; size = max, duration = seconds >= 12 in.
  I2        path turn without head turn: 0.5-s grid of centres c, Phase-0 1-s speed >= 10 in/s at c - 1 and c + 1, IMU-ok
            throughout; |dtheta| >= 90 deg (W = 2 s, Phase-0 heading from the track) while |dpsi| < 20 deg (Phase-0 gyro
            turn, make_imu 50 Hz); overlapping centres merge.
  I3        (reported only) head turn without path turn: |dpsi| >= 90 deg while |dtheta| < 20 deg.
  Metrics   rates per IMU-ok hour by track x type x stratum (day/night/twilight, house/field, rain/wet/dry, animal);
            enrichment of event windows vs matched controls (<= 6-anchor share, raw-fix dispersion about the 1-s median,
            fix rate) with a 10-min block bootstrap; size distributions; V3 vs B2 I1 overlap; the 30 largest I1 / I2 (V3)
            with the hourly video file + offset (file-name time; the agent never looks at a frame); per-fix QC flags.
  Decision  MATERIAL iff the pooled V3 I1 + I2 rate >= 1 per IMU-ok hour AND the pooled <= 6-anchor share ratio (event /
            control) >= 2 with its CI lower bound > 1; otherwise NOT MATERIAL (V3 stays; the QC flags are the deliverable).

Inputs (read-only): the production default tracks (wiser/src/default_tracks.py layout), the B2 tracks
(build_wiser_default_tracks.py --method B2), the IMU-seconds cache, the make_imu 50-Hz npz (gyro turn), the on-site AWN weather
CSV, Phase 0's pair table (reproduction), wiser_rois.json. Existing scripts are imported, never modified.

Usage:
  python wiser/scripts/analyze_wiser_imu_consistency.py --cohort 2026c [--workers 6] [--animals SF07 ...]
  python wiser/scripts/analyze_wiser_imu_consistency.py --report-only <run_dir> [--reuse]   # re-aggregate / re-render from tables
  python wiser/scripts/analyze_wiser_imu_consistency.py --install-flags <run_dir>   # copy the run's QC flags into the cache
  python wiser/scripts/analyze_wiser_imu_consistency.py --selftest                  # synthetic data, no field data
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "wiser" / "src"))
sys.path.insert(0, str(REPO / "wiser" / "scripts"))
sys.path.append(str(REPO / "ephys"))
import output_paths  # noqa: E402  (wiser shim -> common/output_paths.py)
import default_tracks as DT  # noqa: E402  (reader of the production tracks)
import wiser_analysis_utils as W  # noqa: E402  (_rect_membership)
import analyze_imu_wiser_calibration as C  # noqa: E402  (to_ms, true_runs, git_commit; unmodified)
import analyze_wiser_failure_audit as FA  # noqa: E402  (context, sessions_for, load_imu, sample_valid, roll_median, weather, boot_counts; unmodified)
import analyze_imu_turn_vs_heading as TV  # noqa: E402  (Phase-0 headings, Gyro, wrap; unmodified)
import analyze_imu_attitude_gate_v2 as GV2  # noqa: E402  (video_lookup by file-name time; unmodified)

DIRECTION = "wiser_baseline"
NAME = "wiser_imu_consistency"
STEM = f"{DIRECTION}_imu_consistency"
PLAN = "implementation_plan/2026-10-05-wiser-imu-consistency-audit.md"
DRIVER = "wiser/scripts/analyze_wiser_imu_consistency.py"
DN = ["night", "day", "twilight"]
WX = ["rain", "wet", "dry", "unknown"]
ZONES = ["house", "field"]
ZDET = ["house_1", "house_2", "field"]
TYPES = ["I1", "I2", "I3"]
# categorical slots of the dataviz reference palette (light); text stays neutral
COL = {"V3": "#2a78d6", "B2": "#eb6834", "raw": "#8a8986", "ink": "#0b0b0b", "ink2": "#52514e", "grid": "#d9d8d4"}


def log_to(fh, msg: str) -> None:
    print(msg, flush=True)
    if fh is not None:
        fh.write(msg + "\n")
        fh.flush()


# ====================================================================================================== config / context
def load_cfg(cohort: str, path: str | None = None) -> dict:
    cp = Path(path) if path else REPO / "wiser" / "configs" / f"wiser_imu_consistency_{cohort}.json"
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    cfg["_path"] = str(cp)
    cfg["_cohort"] = cohort
    return cfg


def load_acfg(cfg: dict) -> dict:
    return FA.load_cfg(cfg["_cohort"], str(REPO / cfg["audit_config"]))


_CTX: dict = {}


def _ctx(acfg: dict) -> dict:
    if acfg["_path"] not in _CTX:
        _CTX[acfg["_path"]] = FA.context(acfg)
    return _CTX[acfg["_path"]]


# ====================================================================================================== core estimators
def per_second_medians(tf: np.ndarray, P: np.ndarray, s0: int, n: int, minfix: int) -> tuple[np.ndarray, np.ndarray]:
    """p~(s): coordinate-wise median of P at the fixes with aligned time in [s, s + 1) (>= minfix fixes, else NaN), s = s0 .. s0 + n - 1."""
    c = float(s0) + 0.5 + np.arange(n, dtype=np.float64)
    return FA.roll_median(tf, P, c, 0.5, minfix)


def zones_from(ptil: np.ndarray, houses: list, buf: float) -> tuple[np.ndarray, np.ndarray]:
    """Per second: zone code (0 house / 1 field) and detail code (0 house_1 / 1 house_2 / 2 field) from the 1-s median
    position; seconds without a median take the last defined zone (else the next; all field when nothing is defined)."""
    n = len(ptil)
    x, y = ptil[:, 0], ptil[:, 1]
    fin = np.isfinite(x) & np.isfinite(y)
    det = np.full(n, -1, np.int8)
    det[fin] = 2
    for roi in houses[::-1]:                      # house_1 wins over house_2 where buffers overlap (they do not)
        k = ZDET.index(roi["name"]) if roi["name"] in ZDET else 0
        with np.errstate(invalid="ignore"):
            _, inb = W._rect_membership(np.where(fin, x, 0.0), np.where(fin, y, 0.0), roi, buf)
        det[fin & inb] = k
    s = pd.Series(np.where(det >= 0, det, np.nan)).ffill().bfill()
    det = s.fillna(2).to_numpy().astype(np.int8)
    zone = np.where(det == 2, 1, 0).astype(np.int8)
    return zone, det


def find_runs(incl: np.ndarray, state: np.ndarray, ic: dict) -> pd.DataFrame:
    """No-locomotion runs: maximal stretches of included seconds with state still (1) or active (2), >= min_run_s seconds
    (before trimming), trimmed by trim_s at both ends. Indices are second indices into the per-second grid."""
    ok = incl & ((state == 1) | (state == 2))
    rr = [(a, b) for a, b in C.true_runs(ok) if b - a >= int(ic["min_run_s"])]
    tr = int(ic["trim_s"])
    a = np.array([r[0] for r in rr], np.int64)
    b = np.array([r[1] for r in rr], np.int64)
    a2, b2 = a + tr, b - tr
    keep = b2 > a2
    a, b, a2, b2 = a[keep], b[keep], a2[keep], b2[keep]
    cs = np.r_[0, np.cumsum(state == 2)]
    act = (cs[b2] - cs[a2]) > 0 if len(a2) else np.zeros(0, bool)
    return pd.DataFrame({"run": np.arange(len(a)), "a": a, "b": b, "a2": a2, "b2": b2, "L": b2 - a2, "any_active": act})


def i1_track(runs: pd.DataFrame, ptil: np.ndarray, ic: dict) -> tuple[pd.DataFrame, dict]:
    """I1 per run for one track: evaluable, event, size (max displacement from the reference over the trimmed run, in),
    duration (seconds >= disp_in), onset / peak second index, and the event's segments (second indices, [a, b))."""
    ref_s, thr, mc = int(ic["ref_s"]), float(ic["disp_in"]), int(ic["min_consec_s"])
    n = len(runs)
    ev, evl = np.zeros(n, bool), np.zeros(n, bool)
    size, dur = np.full(n, np.nan), np.zeros(n, np.int64)
    onset, peak, maxc = np.full(n, -1, np.int64), np.full(n, -1, np.int64), np.zeros(n, np.int64)
    rx, ry = np.full(n, np.nan), np.full(n, np.nan)
    segs = {}
    A2, B2 = runs["a2"].to_numpy(), runs["b2"].to_numpy()
    for i in range(n):
        P = ptil[A2[i]:B2[i]]
        R = P[:ref_s]
        f = np.isfinite(R[:, 0]) & np.isfinite(R[:, 1])
        if not f.any():
            continue
        evl[i] = True
        r = np.median(R[f], axis=0)
        rx[i], ry[i] = r
        d = np.hypot(P[:, 0] - r[0], P[:, 1] - r[1])
        size[i] = float(np.nanmax(d))
        with np.errstate(invalid="ignore"):
            ab = d >= thr
        if not ab.any():
            continue
        rs = C.true_runs(ab)
        maxc[i] = max(bb - aa for aa, bb in rs)
        if maxc[i] >= mc:
            ev[i] = True
            dur[i] = int(ab.sum())
            onset[i] = A2[i] + int(np.flatnonzero(ab)[0])
            peak[i] = A2[i] + int(np.nanargmax(d))
            segs[i] = [(A2[i] + aa, A2[i] + bb) for aa, bb in rs]
    R = pd.DataFrame({"run": runs["run"].to_numpy(), "evaluable": evl, "event": ev, "size_in": size, "dur_s": dur,
                      "onset": onset, "peak": peak, "max_consec_s": maxc, "ref_x": rx, "ref_y": ry})
    return R, segs


def pair_track(tf: np.ndarray, P: np.ndarray, g: np.ndarray, pc: dict) -> dict:
    """Phase-0 pair quantities on the grid g: 1-s speeds at c - W/2 and c + W/2 and the heading change dtheta (deg, wrapped)."""
    hc = {"median_half_s": pc["median_half_s"], "median_offset_s": pc["median_offset_s"], "min_fix": pc["min_fix"]}
    H = TV.headings(tf, P, g, hc)
    step = float(pc["grid_s"])
    k = int(round(float(pc["W_s"]) / 2.0 / step))
    n = len(g)
    spd1, spd2 = np.full(n, np.nan), np.full(n, np.nan)
    th1, th2 = np.full(n, np.nan), np.full(n, np.nan)
    if n > 2 * k:
        spd1[k:] = H["spd"][:n - k]
        spd2[:n - k] = H["spd"][k:]
        th1[k:] = H["th"][:n - k]
        th2[:n - k] = H["th"][k:]
    return {"spd1": spd1, "spd2": spd2, "dth": TV.wrap(th2 - th1)}


def gyro_pairs(gyro, c: np.ndarray, pc: dict) -> tuple[np.ndarray, np.ndarray]:
    """Phase-0 gyro turn dpsi = psibar(c + W/2) - psibar(c - W/2) (1-s means of the integrated turn) and its span check
    (every 50-Hz sample of [c - W/2 - 0.5, c + W/2 + 0.5) valid, no gap)."""
    half = float(pc["gyro_window_s"]) / 2.0
    w2 = float(pc["W_s"]) / 2.0
    if len(gyro.u) < 2:
        return np.full(len(c), np.nan), np.zeros(len(c), bool)
    dpsi = gyro.mean(c + w2, half) - gyro.mean(c - w2, half)
    ok = gyro.span_ok(c - w2 - half, c + w2 + half)
    return dpsi, ok


def support_ok(g: np.ndarray, s0: int, incl: np.ndarray, half: float) -> np.ndarray:
    """True where every second [s, s + 1) overlapping [g - half, g + half) exists and is included."""
    n = len(incl)
    a = (np.floor(g - half) - s0).astype(np.int64)
    b = (np.ceil(g + half) - s0).astype(np.int64)
    inside = (a >= 0) & (b <= n) & (b > a)
    cs = np.r_[0, np.cumsum(~np.asarray(incl, bool))]
    ac, bc = np.clip(a, 0, n), np.clip(b, 0, n)
    return inside & ((cs[bc] - cs[ac]) == 0)


def merge_centres(idx: np.ndarray, g: np.ndarray, gap: float) -> list:
    """Groups of qualifying centre indices whose pair windows [c - W/2, c + W/2] overlap (spacing < gap = W)."""
    idx = np.asarray(idx, np.int64)
    if not len(idx):
        return []
    t = g[idx]
    br = np.flatnonzero(np.diff(t) >= gap - 1e-9) + 1
    return np.split(idx, br)


def flag_times(t: np.ndarray, starts, ends, ids) -> np.ndarray:
    """Event id (or -1) of the window [start, end) containing each time t; windows sorted by start with ends non-decreasing."""
    s, e, i = np.asarray(starts, float), np.asarray(ends, float), np.asarray(ids, np.int64)
    out = np.full(len(t), -1, np.int64)
    if not len(s):
        return out
    o = np.argsort(s, kind="stable")
    s, e, i = s[o], e[o], i[o]
    k = np.searchsorted(s, t, "right") - 1
    kc = np.clip(k, 0, len(s) - 1)
    inside = (k >= 0) & (t < e[kc])
    out[inside] = i[kc[inside]]
    return out


def win_metrics(tf: np.ndarray, anch: np.ndarray, disp: np.ndarray, segs: list, le: int) -> dict:
    """Raw-fix metrics over a window = list of [a, b) segments (aligned s): fixes n, <= le-anchor fixes, duration (s),
    dispersion values, anchors median."""
    n = nle = 0
    dur = 0.0
    dv, av = [], []
    for a, b in segs:
        i0, i1 = np.searchsorted(tf, [a, b])
        n += int(i1 - i0)
        nle += int((anch[i0:i1] <= le).sum())
        dur += float(b - a)
        dv.append(disp[i0:i1])
        av.append(anch[i0:i1])
    dv = np.concatenate(dv) if dv else np.zeros(0)
    av = np.concatenate(av) if av else np.zeros(0)
    fin = dv[np.isfinite(dv)]
    return {"n": n, "n_le6": nle, "dur": dur, "disp": dv.astype(np.float32),
            "disp_med": float(np.median(fin)) if len(fin) else np.nan,
            "anchors_med": float(np.median(av)) if len(av) else np.nan}


def psi_mean_seconds(s0: int, turn: np.ndarray, x: np.ndarray) -> np.ndarray:
    """(Information only.) Mean of psi over [x, x + 1) with psi piecewise linear between field-PC second boundaries,
    psi(s0 + i) = sum of the per-second turn_net_deg before i (NaN -> 0)."""
    T = np.nan_to_num(np.asarray(turn, float))
    P = np.r_[0.0, np.cumsum(T)]
    Fi = np.r_[0.0, np.cumsum(0.5 * (P[:-1] + P[1:]))]
    n = len(T)

    def F(xx):
        u = xx - s0
        i = np.clip(np.floor(u).astype(np.int64), 0, n - 1)
        f = u - i
        return Fi[i] + P[i] * f + 0.5 * T[i] * f * f
    return F(x + 1.0) - F(x)


# ====================================================================================================== analysis of one animal (arrays)
def analyze_arrays(A: dict, cfg: dict, houses: list) -> dict:
    """Everything that depends only on arrays (shared by the field run and the selftest).
    A: animal, tau_ms, s0, n (per-second grid), incl, state (per second), tf (aligned s, unmasked fixes, sorted), anch,
       pos {track: (N, 2)}, dpsi / gok (per grid centre g = s0 + 0.5 k), dn / wx / bio / hour_ms (per second)."""
    ic, pc, cc, ec = cfg["i1"], cfg["pairs"], cfg["controls"], cfg["enrichment"]
    animal, s0, n = A["animal"], int(A["s0"]), int(A["n"])
    incl, state = A["incl"].astype(bool), A["state"].astype(np.int8)
    tf, anch, pos = A["tf"], A["anch"], A["pos"]
    tracks = list(pos)
    g = float(s0) + float(pc["grid_s"]) * np.arange(int(round(n / float(pc["grid_s"]))), dtype=np.float64)
    rng = np.random.default_rng([int(cc["seed"]), int("".join(ch for ch in animal if ch.isdigit()) or 0)])
    le = int(ec["anchor_le"])
    # ---- per-second medians, zones, raw dispersion
    ptil, nfs = {}, None
    for tr in tracks:
        m, nf = per_second_medians(tf, pos[tr], s0, n, int(ic["median_min_fix"]))
        ptil[tr] = m
        if tr == "raw":
            nfs = nf
    zone_src = "V3" if "V3" in ptil else tracks[0]
    zone, zdet = zones_from(ptil[zone_src], houses, float(cfg["house_buffer_in"]))
    si = np.floor(tf).astype(np.int64) - s0
    okk = (si >= 0) & (si < n)
    mr = np.full((len(tf), 2), np.nan)
    mr[okk] = ptil["raw"][si[okk]]
    disp = np.hypot(pos["raw"][:, 0] - mr[:, 0], pos["raw"][:, 1] - mr[:, 1])
    dn, wx, bio, hour_ms = A["dn"], A["wx"], A["bio"], A["hour_ms"]
    blk_s = int(cfg["bootstrap"]["block_s"])

    def strata(o: int) -> dict:
        o = int(np.clip(o, 0, n - 1))
        return {"zone": ZONES[zone[o]], "zone_detail": ZDET[zdet[o]], "dn": DN[dn[o]], "wx": WX[wx[o]], "hour_ms": int(hour_ms[o]),
                "bio": int(bio[o]), "block": int((s0 + o) // blk_s)}
    # ---- runs (IMU-defined, the same for every track) and pair support
    runs = find_runs(incl, state, ic)
    runs["bio"] = bio[np.clip(runs["a2"].to_numpy(), 0, n - 1)] if len(runs) else np.zeros(0, np.int64)
    sup = support_ok(g, s0, incl, float(pc["W_s"]) / 2.0 + float(pc["median_half_s"]) + float(pc["median_offset_s"]))
    gok, dpsi = A["gok"].astype(bool), A["dpsi"]
    gsec = np.clip(np.floor(g).astype(np.int64) - s0, 0, n - 1)
    gbio = bio[gsec]
    half_sup = float(pc["W_s"]) / 2.0 + float(pc["median_half_s"]) + float(pc["median_offset_s"])   # = 2 s
    events, controls, run_rows, cand_n = [], [], [], {}
    dparts, dwins = [], []
    flags = {"I1": [], "I2": []}
    grid_keep = {"dpsi": dpsi, "g0": float(g[0]) if len(g) else np.nan}
    wid = [0]

    def restrict_f2(segs: list) -> list:
        """(Post hoc, Amendment 2) the parts of integer-second segments whose seconds hold >= 2 unmasked raw fixes."""
        out_ = []
        for a_, b_ in segs:
            i0_, i1_ = int(round(a_)) - s0, int(round(b_)) - s0
            ok_ = nfs[max(i0_, 0):min(i1_, n)] >= 2
            out_ += [(float(s0 + max(i0_, 0) + x), float(s0 + max(i0_, 0) + y)) for x, y in C.true_runs(ok_)]
        return out_

    def add_window(segs: list, f2: bool = False) -> tuple[int, dict]:
        m = win_metrics(tf, anch, disp, segs, le)
        if f2:
            m2 = win_metrics(tf, anch, disp, restrict_f2(segs), le)
            m["n_f2"], m["n_le6_f2"], m["dur_f2"] = m2["n"], m2["n_le6"], m2["dur"]
        else:
            m["n_f2"], m["n_le6_f2"], m["dur_f2"] = m["n"], m["n_le6"], m["dur"]
        k = wid[0]
        wid[0] += 1
        if len(m["disp"]):
            dparts.append(m["disp"])
            dwins.append(np.full(len(m["disp"]), k, np.int32))
        return k, m

    for tr in tracks:
        # ================= I1
        R, segs = i1_track(runs, ptil[tr], ic)
        R.insert(0, "track", tr)
        R.insert(0, "animal", animal)
        R["L"] = runs["L"].to_numpy()
        R["any_active"] = runs["any_active"].to_numpy()
        R["bio"] = runs["bio"].to_numpy()
        R["a2"] = runs["a2"].to_numpy()
        run_rows.append(R)
        evr = np.flatnonzero(R["event"].to_numpy())
        L = R["L"].to_numpy()
        pool_ok = R["evaluable"].to_numpy() & ~R["event"].to_numpy()
        lo_r, hi_r = cc["i1_len_ratio"]
        for eid, i in enumerate(evr):
            r = R.iloc[i]
            sg = [(float(s0 + a), float(s0 + b)) for a, b in segs[i]]
            k, m = add_window(sg, f2=True)
            st = strata(int(r.onset))
            # matched controls: same animal, bio-day, track; event-free evaluable runs of similar trimmed length
            cand = np.flatnonzero(pool_ok & (R["bio"].to_numpy() == r.bio) & (L >= lo_r * r.L) & (L <= hi_r * r.L))
            pick = rng.choice(cand, size=min(int(cc["n_per_event"]), len(cand)), replace=False) if len(cand) else np.zeros(0, np.int64)
            D = int(r.dur_s)
            off = int(r.onset) - int(r.a2)
            for j, ci in enumerate(pick):
                Lc = int(L[ci])
                ln = min(D, Lc)
                st0 = int(R["a2"].iloc[ci]) + min(off, Lc - ln)
                kc, mc_ = add_window([(float(s0 + st0), float(s0 + st0 + ln))], f2=True)
                stc = strata(st0)
                controls.append({"animal": animal, "track": tr, "type": "I1", "event_id": eid, "ctrl": j, "win": kc,
                                 "run": int(ci), "t0": float(s0 + st0), "t1": float(s0 + st0 + ln), "n": mc_["n"], "n_le6": mc_["n_le6"],
                                 "dur": mc_["dur"], "n_f2": mc_["n_f2"], "n_le6_f2": mc_["n_le6_f2"], "dur_f2": mc_["dur_f2"],
                                 "disp_med": mc_["disp_med"], "anchors_med": mc_["anchors_med"],
                                 "zone": stc["zone"], "block": stc["block"], "bio": stc["bio"]})
            events.append({"animal": animal, "track": tr, "type": "I1", "event_id": eid, "win": k, "run": int(r.run),
                           "subtype": "any_active" if bool(r.any_active) else "all_still", "run_t0": float(s0 + runs["a2"].iloc[i]),
                           "run_t1": float(s0 + runs["b2"].iloc[i]), "run_len_s": int(r.L), "t0": float(s0 + r.onset), "t1": float(sg[-1][1]),
                           "peak_t": float(s0 + r.peak), "size": float(r.size_in), "dur_s": int(r.dur_s), "n_segments": len(sg),
                           "max_consec_s": int(r.max_consec_s), "ref_x": float(r.ref_x), "ref_y": float(r.ref_y),
                           "n": m["n"], "n_le6": m["n_le6"], "dur": m["dur"], "n_f2": m["n_f2"], "n_le6_f2": m["n_le6_f2"], "dur_f2": m["dur_f2"],
                           "disp_med": m["disp_med"], "anchors_med": m["anchors_med"], "n_controls": int(len(pick)), **st})
            if tr == "V3":
                for a_, b_ in sg:
                    flags["I1"].append((a_, b_, eid))
        # ================= I2 / I3
        Pq = pair_track(tf, pos[tr], g, pc)
        with np.errstate(invalid="ignore"):
            cand = sup & gok & (Pq["spd1"] >= float(pc["min_speed_inps"])) & (Pq["spd2"] >= float(pc["min_speed_inps"]))
            adth, adpsi = np.abs(Pq["dth"]), np.abs(dpsi)
            q2 = cand & (adth >= float(cfg["i2"]["min_abs_dtheta_deg"])) & (adpsi < float(cfg["i2"]["max_abs_dpsi_deg"]))
            q3 = cand & (adpsi >= float(cfg["i3"]["min_abs_dpsi_deg"])) & (adth < float(cfg["i3"]["max_abs_dtheta_deg"]))
        cand_n[tr] = int(cand.sum())
        grid_keep[f"dth_{tr}"] = Pq["dth"]
        grid_keep[f"cand_{tr}"] = cand
        for typ, q, sz in (("I2", q2, adth), ("I3", q3, adpsi)):
            groups = merge_centres(np.flatnonzero(q), g, float(cfg["merge_gap_s"]))
            ev_rows = []
            for eid, grp in enumerate(groups):
                jm = grp[int(np.argmax(sz[grp]))]
                w0, w1 = float(g[grp[0]] - half_sup), float(g[grp[-1]] + half_sup)
                k, m = add_window([(w0, w1)])
                st = strata(int(math.floor(w0)) - s0)
                ev_rows.append({"animal": animal, "track": tr, "type": typ, "event_id": eid, "win": k, "t0": w0, "t1": w1,
                                "c_first": float(g[grp[0]]), "c_last": float(g[grp[-1]]), "c_max": float(g[jm]), "n_centres": int(len(grp)),
                                "size": float(sz[jm]), "dtheta": float(Pq["dth"][jm]), "dpsi": float(dpsi[jm]),
                                "spd1": float(Pq["spd1"][jm]), "spd2": float(Pq["spd2"][jm]), "dur_s": w1 - w0,
                                "n": m["n"], "n_le6": m["n_le6"], "dur": m["dur"], "disp_med": m["disp_med"], "anchors_med": m["anchors_med"],
                                "n_controls": 0, **st})
                if tr == "V3" and typ == "I2":
                    flags["I2"].append((w0, w1, eid))
            if typ == "I2" and ev_rows:
                # matched controls: candidate pairs, not I2 centres, support not overlapping an I2 event window
                excl = np.zeros(len(g), bool)
                for e in ev_rows:
                    j0 = np.searchsorted(g, e["t0"] - half_sup, "right")
                    j1 = np.searchsorted(g, e["t1"] + half_sup, "left")
                    excl[j0:j1] = True
                pool = np.flatnonzero(cand & ~q & ~excl)
                pbio = gbio[pool]
                for e in ev_rows:
                    P_ = pool[pbio == e["bio"]]
                    if not len(P_):
                        continue
                    draw = P_[rng.choice(len(P_), size=min(len(P_), 25 * int(cc["n_per_event"])), replace=False)]
                    chosen = []
                    for jc in draw:
                        if all(abs(g[jc] - g[x]) >= float(cc["i2_min_sep_s"]) for x in chosen):
                            chosen.append(int(jc))
                        if len(chosen) >= int(cc["n_per_event"]):
                            break
                    for j, jc in enumerate(chosen):
                        w0, w1 = float(g[jc] - half_sup), float(g[jc] + half_sup)
                        kc, mc_ = add_window([(w0, w1)])
                        stc = strata(int(math.floor(w0)) - s0)
                        controls.append({"animal": animal, "track": tr, "type": "I2", "event_id": e["event_id"], "ctrl": j, "win": kc,
                                         "run": -1, "t0": w0, "t1": w1, "n": mc_["n"], "n_le6": mc_["n_le6"], "dur": mc_["dur"],
                                         "disp_med": mc_["disp_med"], "anchors_med": mc_["anchors_med"], "zone": stc["zone"],
                                         "block": stc["block"], "bio": stc["bio"]})
                    e["n_controls"] = len(chosen)
            events.extend(ev_rows)
    # ---- exposure (included seconds) by stratum and by 10-min block
    ii = np.flatnonzero(incl)
    X = pd.DataFrame({"hour_ms": hour_ms[ii], "dn": dn[ii], "zone": zone[ii], "wx": wx[ii]})
    X = X.value_counts().rename("n_s").reset_index()
    X["dn"] = [DN[v] for v in X["dn"]]
    X["zone"] = [ZONES[v] for v in X["zone"]]
    X["wx"] = [WX[v] for v in X["wx"]]
    X.insert(0, "animal", animal)
    bk = (s0 + ii) // blk_s
    ub, cn = np.unique(bk, return_counts=True)
    XB = pd.DataFrame({"animal": animal, "block": ub, "n_s": cn})
    info = {"animal": animal, "s0": s0, "n_sec": n, "incl_s": int(incl.sum()), "ok_s": int(A.get("ok", incl).sum()),
            "runs": int(len(runs)), "run_s": int(runs["L"].sum()) if len(runs) else 0,
            **{f"cand_pairs_{tr}": cand_n[tr] for tr in tracks},
            "fixes_unmasked": int(len(tf)), "seconds_with_fix": int((nfs > 0).sum()) if nfs is not None else 0}
    return {"events": pd.DataFrame(events), "controls": pd.DataFrame(controls), "runs": pd.concat(run_rows, ignore_index=True),
            "exposure": X, "exposure_blocks": XB, "info": info, "flags": flags, "grid": grid_keep, "g": g,
            "disp": np.concatenate(dparts) if dparts else np.zeros(0, np.float32),
            "disp_win": np.concatenate(dwins) if dwins else np.zeros(0, np.int32), "zone": zone, "zdet": zdet}


# ====================================================================================================== field inputs of one animal
def second_strata(s0: int, n: int, tz: str, hour_cls: dict, bio_off_h: float) -> dict:
    sec = np.int64(s0) + np.arange(n, dtype=np.int64)
    ts = pd.DatetimeIndex(pd.to_datetime(sec, unit="s", utc=True)).tz_convert(tz)
    loc = ts.tz_localize(None)
    mins = (loc.hour * 60 + loc.minute).to_numpy()
    night = (mins >= 21 * 60) | (mins < 4 * 60 + 20)
    day = (mins >= 8 * 60) & (mins < 18 * 60)
    dn = np.where(night, 0, np.where(day, 1, 2)).astype(np.int8)
    hour_ms = (ts.floor("h").asi8 // 10**6).astype(np.int64)
    codes = {int(h): WX.index(c) for h, c in hour_cls.items()}
    wx = pd.Series(hour_ms).map(codes).fillna(WX.index("unknown")).to_numpy().astype(np.int8)
    lsec = loc.asi8 // 10**9
    bio = ((lsec - int(bio_off_h * 3600)) // 86400).astype(np.int64)
    return {"dn": dn, "hour_ms": hour_ms, "wx": wx, "bio": bio}


def weather_hours(acfg: dict, cfg: dict, lo_ms: float, hi_ms: float) -> tuple[dict, pd.DataFrame]:
    """Class of every field-PC clock hour in [lo, hi): rain (any 5-min row with rain rate > 0), wet (<= wet_after_h after the
    last rain row), dry, unknown (no row in the hour)."""
    wx = FA.load_weather(acfg)
    t = wx["t_ms"].to_numpy(float)
    rr = wx["rain_rate"].fillna(0).to_numpy(float)
    rain_t = np.sort(t[rr > 0])
    tz = cfg["tz"]
    h0 = pd.Timestamp(int(lo_ms), unit="ms", tz="UTC").tz_convert(tz).floor("h")
    h1 = pd.Timestamp(int(hi_ms), unit="ms", tz="UTC").tz_convert(tz).ceil("h")
    hrs = pd.date_range(h0, h1, freq="h", inclusive="left")
    out, rows = {}, []
    wet_ms = float(cfg["weather"]["wet_after_h"]) * 3.6e6
    for h in hrs:
        H = float(h.value // 10**6)
        i0, i1 = np.searchsorted(t, [H, H + 3.6e6])
        nrow = int(i1 - i0)
        j0, j1 = np.searchsorted(rain_t, [H, H + 3.6e6])
        nrain = int(j1 - j0)
        k = j0 - 1
        last = float(rain_t[k]) if k >= 0 else np.nan
        if nrow == 0:
            cl = "unknown"
        elif nrain > 0:
            cl = "rain"
        elif np.isfinite(last) and H - last <= wet_ms:
            cl = "wet"
        else:
            cl = "dry"
        out[int(H)] = cl
        rows.append({"hour_ms": int(H), "hour_local": h.strftime("%Y-%m-%d %H:%M"), "rows": nrow, "rain_rows": nrain,
                     "rain_mm": float((rr[i0:i1] * 5.0 / 60.0).sum()), "h_since_rain": (H - last) / 3.6e6 if np.isfinite(last) else np.nan,
                     "class": cl})
    return out, pd.DataFrame(rows)


def track_days(root: str, label: str) -> list:
    d = Path(root) / label
    return sorted(f"{f.name[:4]}-{f.name[4:6]}-{f.name[6:8]}" for f in d.glob("*.csv.gz") if not f.name.endswith(".partial.csv.gz"))


def process_animal(job: dict) -> dict:
    t_job = time.time()
    cfg, acfg, animal, hour_cls = job["cfg"], job["acfg"], job["animal"], job["hour_cls"]
    ctx = _ctx(acfg)
    tz = cfg["tz"]
    pc, imc = cfg["pairs"], cfg["imu"]
    # ---- tracks (V3 production + B2) for every production day
    days = track_days(cfg["tracks_root"], animal)
    cols = ["t_ms", "t_al_ms", "x_raw", "y_raw", "anchors_used"] + cfg["masks"] + ["x", "y"]
    frames, day_rows = [], []
    for d in days:
        V = DT.load_default_track(animal, d, root=cfg["tracks_root"], columns=cols)
        Bq = DT.load_default_track(animal, d, root=cfg["b2_tracks_root"], columns=["t_ms", "x", "y"])
        if not np.array_equal(V["t_ms"].to_numpy(np.int64), Bq["t_ms"].to_numpy(np.int64)):
            raise ValueError(f"{animal} {d}: B2 fixes differ from the V3 fixes")
        V["xb"], V["yb"] = Bq["x"].to_numpy(), Bq["y"].to_numpy()
        day_rows.append((d, len(V)))
        frames.append(V)
    F = pd.concat(frames, ignore_index=True)
    starts = np.cumsum([0] + [len(f) for f in frames])[:-1]
    t_ms = F["t_ms"].to_numpy(np.int64)
    t_al = F["t_al_ms"].astype("float64").to_numpy()
    if not np.isfinite(t_al).all():
        raise ValueError(f"{animal}: t_al_ms missing")
    tau_ms = float(np.median(t_ms - t_al))
    mask = np.zeros(len(F), bool)
    for m in cfg["masks"]:
        mask |= F[m].to_numpy(bool)
    # ---- per-second grid over the production days (field-PC seconds = the IMU / aligned clock)
    d_first = C.to_ms(days[0] + " 00:00:00", tz) // 1000
    d_last = C.to_ms((pd.Timestamp(days[-1]) + pd.Timedelta(days=1)).strftime("%Y-%m-%d") + " 00:00:00", tz) // 1000
    s0 = int(d_first) - 1
    n = int(d_last) + 1 - s0
    ok = np.zeros(n, bool)
    state = np.zeros(n, np.int8)
    turn = np.full(n, np.nan)
    imu_days = []
    for d in days:
        p = Path(cfg["imu_seconds_root"]) / animal / f"{d.replace('-', '')}.csv.gz"
        if not p.exists():
            continue
        I = pd.read_csv(p, usecols=["sec", "ok", "state", "turn_net_deg"])
        j = I["sec"].to_numpy(np.int64) - s0
        mj = (j >= 0) & (j < n)
        okv = I["ok"].astype(bool).to_numpy()
        ok[j[mj]] = okv[mj]
        state[j[mj]] = np.where(okv, I["state"].to_numpy(np.int8), 0)[mj]
        turn[j[mj]] = I["turn_net_deg"].to_numpy(float)[mj]
        imu_days.append(d)
    excl = np.zeros(n, bool)
    sm = np.floor(t_al[mask] / 1000.0).astype(np.int64) - s0
    sm = sm[(sm >= 0) & (sm < n)]
    excl[sm] = True
    lost = ((ctx["coh"].get("ephys") or {}).get("loggers") or {}).get(animal, {}).get("implant_lost")
    lost_ms = C.to_ms(str(lost)[:19], tz) if lost else None
    if lost_ms is not None:
        excl[max(0, int(lost_ms // 1000) - s0):] = True
    incl = ok & ~excl
    um = ~mask
    tf = t_al[um] / 1000.0
    pos = {"V3": F.loc[um, ["x", "y"]].to_numpy(np.float64), "B2": F.loc[um, ["xb", "yb"]].to_numpy(np.float64),
           "raw": F.loc[um, ["x_raw", "y_raw"]].to_numpy(np.float64)}
    anch = F.loc[um, "anchors_used"].to_numpy(np.int64)
    # ---- gyro turn on the 0.5-s grid (Phase-0 Gyro on the make_imu 50-Hz npz), day by day with margins
    g = float(s0) + float(pc["grid_s"]) * np.arange(int(round(n / float(pc["grid_s"]))), dtype=np.float64)
    dpsi = np.full(len(g), np.nan)
    gok = np.zeros(len(g), bool)
    sess_used, imu_h = [], 0.0
    mg = float(imc["margin_s"]) * 1000.0
    for d in imu_days:
        d0 = C.to_ms(d + " 00:00:00", tz)
        d1 = C.to_ms((pd.Timestamp(d) + pd.Timedelta(days=1)).strftime("%Y-%m-%d") + " 00:00:00", tz)
        lo, hi = d0 - mg, d1 + mg
        sess = FA.sessions_for(acfg, ctx, animal, lo, hi)
        if not sess:
            continue
        imu = FA.load_imu(sess, lo, hi, tz)
        if not len(imu["unix_ms"]):
            continue
        valid = FA.sample_valid(imu, ctx, animal, lo, hi, -np.inf, np.inf)
        gyro = TV.Gyro(imu["unix_ms"] / 1000.0, imu["turn_dps"], valid, float(imc["fs"]), float(imc["max_gap_samples"]))
        j0, j1 = np.searchsorted(g, [d0 / 1000.0, d1 / 1000.0])
        dp, go = gyro_pairs(gyro, g[j0:j1], pc)
        dpsi[j0:j1], gok[j0:j1] = dp, go
        sess_used.append({"date": d, "sessions": ";".join(s["session"] for s in sess), "valid_h": float(gyro.n_good / float(imc["fs"]) / 3600.0)})
        imu_h += float(gyro.n_good / float(imc["fs"]) / 3600.0)
        del imu, valid, gyro
    strat = second_strata(s0, n, tz, hour_cls, float(cfg["controls"]["bio_day_offset_h"]))
    A = {"animal": animal, "tau_ms": tau_ms, "s0": s0, "n": n, "incl": incl, "ok": ok, "state": state, "tf": tf, "anch": anch,
         "pos": pos, "dpsi": dpsi, "gok": gok, **strat}
    res = analyze_arrays(A, cfg, ctx["houses"])
    # ---- Phase-0 reproduction (all W = 2 s pairs of this animal)
    P0 = job["phase0"]
    rep = pd.DataFrame()
    if len(P0):
        c = P0["c_ms"].to_numpy(np.float64) / 1000.0
        j = np.round((c - g[0]) / float(pc["grid_s"])).astype(np.int64)
        okj = (j >= 0) & (j < len(g))
        jj = np.clip(j, 0, len(g) - 1)
        Gk = res["grid"]
        rep = P0[["animal", "period", "set", "c_ms", "ok_raw", "ok_v3", "dtheta", "dtheta_v3", "dpsi"]].copy()
        rep["grid_match"] = okj & (np.abs(g[jj] - c) < 1e-6)
        rep["dtheta_prod"] = np.where(okj, Gk["dth_raw"][jj], np.nan)
        rep["dtheta_v3_prod"] = np.where(okj, Gk["dth_V3"][jj], np.nan)
        rep["dpsi_prod"] = np.where(okj, dpsi[jj], np.nan)
        rep["gok_prod"] = np.where(okj, gok[jj], False)
        rep["dpsi_sec"] = psi_mean_seconds(s0, turn, c + 0.5) - psi_mean_seconds(s0, turn, c - 1.5)
    # ---- QC flags per production V3 day (staged in the run dir; installed into the cache by --install-flags)
    fl = res["flags"]
    i1s = sorted(fl["I1"])
    i2s = sorted(fl["I2"])
    qdir = Path(job["out"]) / "qc_flags" / animal
    qdir.mkdir(parents=True, exist_ok=True)
    qrows = []
    for (d, nrow), st in zip(day_rows, starts):
        ta = t_al[st:st + nrow] / 1000.0
        e1 = flag_times(ta, [x[0] for x in i1s], [x[1] for x in i1s], [x[2] for x in i1s])
        e2 = flag_times(ta, [x[0] for x in i2s], [x[1] for x in i2s], [x[2] for x in i2s])
        Q = pd.DataFrame({"t_ms": t_ms[st:st + nrow], "qc_i1": (e1 >= 0).astype(np.int8), "qc_i2": (e2 >= 0).astype(np.int8),
                          "i1_event_id": e1, "i2_event_id": e2})
        p = qdir / f"{d.replace('-', '')}.csv.gz"
        Q.to_csv(p, index=False)
        qrows.append({"label": animal, "date": d, "n_fix": int(nrow), "n_qc_i1": int(Q.qc_i1.sum()), "n_qc_i2": int(Q.qc_i2.sum()),
                      "staged": str(p)})
    info = res["info"]
    info.update({"tau_ms": tau_ms, "days": len(days), "imu_days": len(imu_days), "imu_valid_50hz_h": imu_h,
                 "masked_fixes": int(mask.sum()), "lost_ms": lost_ms, "runtime_s": round(time.time() - t_job, 1)})
    res.pop("grid")
    res.pop("g")
    res.pop("flags")
    res.update({"repro": rep, "qc": pd.DataFrame(qrows), "sessions": sess_used, "info": info})
    return res


def _process_safe(job: dict) -> dict:
    try:
        return process_animal(job)
    except Exception as e:  # noqa: BLE001
        import traceback
        return {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc(), "animal": job["animal"]}


# ====================================================================================================== run
EXACT_TABLES = ("events", "controls")     # hold absolute times (s since epoch): written at full precision (Amendment 2)


def write_table(D: pd.DataFrame, path: Path, exact: bool) -> None:
    """%.6g keeps tables small but rounds an absolute time (~1.79e9 s) to ~1000 s; tables with times are written exactly."""
    D.to_csv(path, index=False, float_format=None if exact else "%.6g")


def run_compute(cfg: dict, workers: int, animals: list | None, fh_holder: dict) -> Path:
    t0 = time.time()
    acfg = load_acfg(cfg)
    ctx = _ctx(acfg)
    out = output_paths.run_dir(NAME, cfg["_cohort"])
    for sub in ("tables", "work", "qc_flags"):
        (out / sub).mkdir(exist_ok=True)
    fh = open(out / "log.txt", "w", encoding="utf-8")
    fh_holder["fh"] = fh
    log_to(fh, f"run dir {out}; git {C.git_commit()}; config {cfg['_path']}; plan {PLAN}")
    animals = animals or cfg["animals"]
    # weather classes over the cohort span
    lo = min(C.to_ms(track_days(cfg["tracks_root"], a)[0] + " 00:00:00", cfg["tz"]) for a in animals)
    hi = max(C.to_ms((pd.Timestamp(track_days(cfg["tracks_root"], a)[-1]) + pd.Timedelta(days=1)).strftime("%Y-%m-%d") + " 00:00:00", cfg["tz"])
             for a in animals)
    hour_cls, WH = weather_hours(acfg, cfg, lo, hi)
    WH.to_csv(out / "tables" / "weather_hours.csv", index=False)
    log_to(fh, f"weather hours: {WH['class'].value_counts().to_dict()}")
    P0 = pd.read_csv(Path(cfg["phase0_run"]) / "tables" / "pairs.csv.gz")
    P0 = P0[P0["W"] == float(cfg["pairs"]["W_s"])]
    jobs = [{"cfg": cfg, "acfg": acfg, "animal": a, "hour_cls": hour_cls, "phase0": P0[P0["animal"] == a].reset_index(drop=True),
             "out": str(out)} for a in animals]
    keys = ["events", "controls", "runs", "exposure", "exposure_blocks", "repro", "qc"]
    acc = {k: [] for k in keys}
    infos, sess, dparts, dwins = [], [], [], []
    woff = 0
    with ProcessPoolExecutor(max_workers=max(1, min(int(workers), 16, len(jobs)))) as ex:
        for r in ex.map(_process_safe, jobs):
            if "error" in r:
                log_to(fh, f"ERROR {r['animal']}: {r['error']}\n{r['trace']}")
                continue
            i = r["info"]
            ev = r["events"]
            cnt = ev.groupby(["track", "type"]).size().to_dict() if len(ev) else {}
            log_to(fh, f"{i['animal']}: {i['days']} days, included {i['incl_s'] / 3600:.1f} h, runs {i['runs']:,}, "
                       f"events {cnt}, IMU 50 Hz {i['imu_valid_50hz_h']:.1f} h, {i['runtime_s']} s")
            nw = int(max(ev["win"].max() if len(ev) else -1, r["controls"]["win"].max() if len(r["controls"]) else -1)) + 1
            for k in ("events", "controls"):
                if len(r[k]):
                    d = r[k].copy()
                    d["win"] = d["win"] + woff
                    acc[k].append(d)
            for k in ("runs", "exposure", "exposure_blocks", "repro", "qc"):
                if len(r[k]):
                    acc[k].append(r[k])
            if len(r["disp"]):
                dparts.append(r["disp"])
                dwins.append(r["disp_win"].astype(np.int64) + woff)
            woff += nw
            infos.append(i)
            sess.extend([{"animal": i["animal"], **s} for s in r["sessions"]])
    tb = out / "tables"
    for k in keys:
        D = pd.concat(acc[k], ignore_index=True) if acc[k] else pd.DataFrame()
        write_table(D, tb / f"{k}.csv.gz", exact=k in EXACT_TABLES)
    np.savez_compressed(out / "work" / "disp.npz", disp=np.concatenate(dparts) if dparts else np.zeros(0, np.float32),
                        win=np.concatenate(dwins) if dwins else np.zeros(0, np.int64))
    pd.DataFrame(infos).to_csv(tb / "animals_info.csv", index=False)
    pd.DataFrame(sess).to_csv(tb / "imu_sessions.csv", index=False)
    idx_v3 = DT.list_default_tracks(root=cfg["tracks_root"])
    idx_b2 = DT.list_default_tracks(root=cfg["b2_tracks_root"])
    prov = {"config": Path(cfg["_path"]).relative_to(REPO).as_posix(), "plan": PLAN, "driver": DRIVER, "git_commit": C.git_commit(),
            "audit_config": cfg["audit_config"], "tracks_root": cfg["tracks_root"], "b2_tracks_root": cfg["b2_tracks_root"],
            "b2_build_run": cfg["b2_build_run"], "imu_seconds_root": cfg["imu_seconds_root"], "imu_root": acfg["imu_root"],
            "weather_csv": acfg["weather"]["cloud_csv"], "phase0_run": cfg["phase0_run"], "rois": acfg["rois_json"],
            "track_files_v3": int(len(idx_v3[idx_v3.label.isin(animals)])), "track_files_b2": int(len(idx_b2[idx_b2.label.isin(animals)])),
            "track_bytes_v3": int(idx_v3[idx_v3.label.isin(animals)]["bytes"].sum()) if "bytes" in idx_v3 else None,
            "tau_ms": {i["animal"]: i["tau_ms"] for i in infos}, "animals": animals,
            "runtime_compute_s": round(time.time() - t0, 1)}
    (out / "input_provenance.json").write_text(json.dumps(prov, indent=2, default=str), encoding="utf-8")
    log_to(fh, f"compute done ({time.time() - t0:.0f} s)")
    return out


# ====================================================================================================== aggregation
def boot_ratio_shares(En, Ele, Ed, Cn, Cle, Cd, cnt):
    """Rows: point estimate (row 0) + replicates. Shares, fix rates and their event/control ratios."""
    en, ele, ed = cnt @ En, cnt @ Ele, cnt @ Ed
    cn, cle, cd = cnt @ Cn, cnt @ Cle, cnt @ Cd
    with np.errstate(invalid="ignore", divide="ignore"):
        se, sc = ele / en, cle / cn
        fe, fc = en / ed, cn / cd
        return {"share_e": se, "share_c": sc, "share_ratio": se / sc, "rate_e": fe, "rate_c": fc, "rate_ratio": fe / fc}


def enrichment(E: pd.DataFrame, Ct: pd.DataFrame, dv: np.ndarray, dw: np.ndarray, cfg: dict, seed: int,
               cols: tuple = ("n", "n_le6", "dur"), with_disp: bool = True) -> dict:
    """Pooled event / matched-control comparison with a block bootstrap (blocks = animal x 10-min bin of the window onset).
    E: event rows (one per event window), Ct: their controls (weights 1/k_e recomputed within the subset)."""
    ec, bc = cfg["enrichment"], cfg["bootstrap"]
    key = ["animal", "track", "type", "event_id"]
    if not len(E) or not len(Ct):
        return {"n_events": int(len(E)), "n_controls": int(len(Ct))}
    Ct = Ct.merge(E[key], on=key, how="inner")
    kk = Ct.groupby(key).size().rename("k").reset_index()
    E = E.merge(kk, on=key, how="inner")
    if not len(E):
        return {"n_events": 0, "n_controls": 0}
    Ct = Ct.merge(kk, on=key, how="inner")
    Ct["w"] = 1.0 / Ct["k"]
    bl = pd.concat([E["animal"] + ":" + E["block"].astype(str), Ct["animal"] + ":" + Ct["block"].astype(str)], ignore_index=True)
    codes, uniq = pd.factorize(bl)
    be, bcn = codes[:len(E)], codes[len(E):]
    K = len(uniq)
    cnt = FA.boot_counts(K, int(bc["n_boot"]), np.random.default_rng(seed))

    def bs(b, v, w=None):
        return np.bincount(b, weights=v if w is None else v * w, minlength=K)
    cn_, cl_, cd_ = cols
    R = boot_ratio_shares(bs(be, E[cn_].to_numpy(float)), bs(be, E[cl_].to_numpy(float)), bs(be, E[cd_].to_numpy(float)),
                          bs(bcn, Ct[cn_].to_numpy(float), Ct["w"].to_numpy()), bs(bcn, Ct[cl_].to_numpy(float), Ct["w"].to_numpy()),
                          bs(bcn, Ct[cd_].to_numpy(float), Ct["w"].to_numpy()), cnt)
    if not with_disp:
        res = {"n_events": int(len(E)), "n_controls": int(len(Ct)), "n_blocks": K}
        for k, v in R.items():
            res[k], res[k + "_lo"], res[k + "_hi"] = FA.ci(v)
        return res
    # dispersion: weighted histograms per block -> replicate medians
    edges = np.arange(0.0, float(ec["disp_max_in"]) + 1e-9, float(ec["disp_bin_in"]))
    nb = len(edges) - 1
    out = {}
    for tag, D, b, w in (("e", E, be, np.ones(len(E))), ("c", Ct, bcn, Ct["w"].to_numpy())):
        wmap = np.zeros(int(max(dw.max() if len(dw) else 0, D["win"].max())) + 1)
        bmap = np.zeros(len(wmap), np.int64)
        np.add.at(wmap, D["win"].to_numpy(np.int64), w)
        bmap[D["win"].to_numpy(np.int64)] = b
        sel = np.isfinite(dv) & (dw < len(wmap))
        wf = np.zeros(len(dv))
        wf[sel] = wmap[dw[sel]]
        sel &= wf > 0
        bins = np.clip(np.floor(dv[sel] / float(ec["disp_bin_in"])).astype(np.int64), 0, nb - 1)
        H = np.bincount(bmap[dw[sel]] * nb + bins, weights=wf[sel], minlength=K * nb).reshape(K, nb)
        out[tag] = FA.hist_q(cnt @ H, edges, 0.5)
    R["disp_e"], R["disp_c"] = out["e"], out["c"]
    with np.errstate(invalid="ignore", divide="ignore"):
        R["disp_ratio"] = out["e"] / out["c"]
    res = {"n_events": int(len(E)), "n_controls": int(len(Ct)), "n_blocks": K}
    for k, v in R.items():
        res[k], res[k + "_lo"], res[k + "_hi"] = FA.ci(v)
    return res


def rate_tables(E: pd.DataFrame, X: pd.DataFrame, tracks: list) -> pd.DataFrame:
    rows = []
    tsets = [("I1", ["I1"]), ("I2", ["I2"]), ("I3", ["I3"]), ("I1+I2", ["I1", "I2"])]
    strata = [("pooled", None), ("daynight", "dn"), ("zone", "zone"), ("weather", "wx"), ("animal", "animal")]
    for tr in tracks:
        for tn, ts in tsets:
            e = E[(E.track == tr) & E.type.isin(ts)]
            for sn, col in strata:
                if col is None:
                    rows.append({"track": tr, "type": tn, "stratum": "pooled", "level": "all", "events": int(len(e)),
                                 "hours": X.n_s.sum() / 3600.0, "rate_per_h": len(e) / (X.n_s.sum() / 3600.0)})
                    continue
                hx = X.groupby(col)["n_s"].sum() / 3600.0
                ce = e.groupby(col).size()
                for lv, h in hx.items():
                    k = int(ce.get(lv, 0))
                    rows.append({"track": tr, "type": tn, "stratum": sn, "level": lv, "events": k, "hours": h,
                                 "rate_per_h": k / h if h > 0 else np.nan})
            if tn == "I1":
                for st in ("all_still", "any_active"):
                    es = e[e.subtype == st]
                    rows.append({"track": tr, "type": f"I1 {st}", "stratum": "pooled", "level": "all", "events": int(len(es)),
                                 "hours": X.n_s.sum() / 3600.0, "rate_per_h": len(es) / (X.n_s.sum() / 3600.0)})
                    for z in ZONES:
                        h = X[X.zone == z].n_s.sum() / 3600.0
                        k = int((es.zone == z).sum())
                        rows.append({"track": tr, "type": f"I1 {st}", "stratum": "zone", "level": z, "events": k, "hours": h,
                                     "rate_per_h": k / h if h > 0 else np.nan})
    return pd.DataFrame(rows)


def rate_ci(E: pd.DataFrame, XB: pd.DataFrame, tracks: list, cfg: dict) -> pd.DataFrame:
    key = XB["animal"] + ":" + XB["block"].astype(str)
    codes, uniq = pd.factorize(key)
    K = len(uniq)
    cnt = FA.boot_counts(K, int(cfg["bootstrap"]["n_boot"]), np.random.default_rng(int(cfg["bootstrap"]["seed"]) + 7))
    secs = cnt @ np.bincount(codes, weights=XB["n_s"].to_numpy(float), minlength=K)
    look = pd.Series(np.arange(K), index=uniq)
    rows = []
    for tr in tracks:
        for tn, ts in (("I1", ["I1"]), ("I2", ["I2"]), ("I3", ["I3"]), ("I1+I2", ["I1", "I2"])):
            e = E[(E.track == tr) & E.type.isin(ts)]
            ek = (e["animal"] + ":" + e["block"].astype(str)).map(look)
            miss = int(ek.isna().sum())
            ev = cnt @ np.bincount(ek.dropna().astype(np.int64), minlength=K).astype(float)
            r = ev / secs * 3600.0
            p, lo, hi = FA.ci(r)
            rows.append({"track": tr, "type": tn, "rate_per_h": p, "lo": lo, "hi": hi, "events_outside_exposure": miss})
    return pd.DataFrame(rows)


def size_table(E: pd.DataFrame, tracks: list) -> pd.DataFrame:
    rows = []
    for tr in tracks:
        for typ, col in (("I1", "size"), ("I1", "dur_s"), ("I2", "size"), ("I3", "size")):
            v = E[(E.track == tr) & (E.type == typ)][col].to_numpy(float)
            v = v[np.isfinite(v)]
            q = np.percentile(v, [10, 50, 90, 99]) if len(v) else [np.nan] * 4
            rows.append({"track": tr, "type": typ, "quantity": {"size": "size (in)" if typ == "I1" else ("|Δθ| (°)" if typ == "I2" else "|Δψ| (°)"),
                                                               "dur_s": "duration (s)"}[col],
                         "n": int(len(v)), "p10": q[0], "p50": q[1], "p90": q[2], "p99": q[3], "max": float(v.max()) if len(v) else np.nan})
    return pd.DataFrame(rows)


def i1_overlap(E: pd.DataFrame) -> pd.DataFrame:
    rows = []
    e1 = E[E.type == "I1"]
    for st in ("all", "all_still", "any_active"):
        s = e1 if st == "all" else e1[e1.subtype == st]
        sets = {tr: set(zip(s[s.track == tr].animal, s[s.track == tr].run)) for tr in ("V3", "B2", "raw")}
        rows.append({"subtype": st, "V3": len(sets["V3"]), "B2": len(sets["B2"]), "raw": len(sets["raw"]),
                     "V3_and_B2": len(sets["V3"] & sets["B2"]), "B2_not_V3": len(sets["B2"] - sets["V3"]),
                     "V3_not_B2": len(sets["V3"] - sets["B2"]), "raw_and_V3": len(sets["raw"] & sets["V3"]),
                     "raw_not_V3": len(sets["raw"] - sets["V3"])})
    return pd.DataFrame(rows)


def ms_local(ms: float, tz: str) -> str:
    return FA.ms_local(ms, tz, frac=True)[:-2] if np.isfinite(ms) else ""


def event_list(E: pd.DataFrame, typ: str, cfg: dict, taus: dict, n: int) -> pd.DataFrame:
    vc = cfg["video"]
    chans = sorted({c for v in vc["channels_by_zone"].values() for c in v})
    cfgv = {"human_checks": {"channels": chans, "video_root": vc["root"]}, "tz": cfg["tz"]}
    e = E[(E.track == cfg["primary_track"]) & (E.type == typ)].sort_values("size", ascending=False).head(n).copy()
    rows = []
    for rank, r in enumerate(e.itertuples(), 1):
        tau = float(taus.get(r.animal, 0.0))
        t_on = float(r.t0) * 1000.0 + tau
        v = GV2.video_lookup(t_on, cfgv)
        zc = vc["channels_by_zone"].get(r.zone_detail, vc["channels_by_zone"]["field"])
        row = {"rank": rank, "animal": r.animal, "event_id": int(r.event_id), "onset_pc": ms_local(t_on, cfg["tz"]),
               "end_pc": ms_local(float(r.t1) * 1000.0 + tau, cfg["tz"]), "zone": r.zone_detail, "dn": r.dn, "wx": r.wx,
               "size": float(r.size), "dur_s": float(r.dur_s), "anchors_med": float(r.anchors_med),
               "le6_share": r.n_le6 / r.n if r.n else np.nan, "fixes": int(r.n), "disp_med": float(r.disp_med),
               "video": "; ".join(f"{c}: {v.get(c, 'n/a')}" for c in zc)}
        if typ == "I1":
            row.update({"subtype": r.subtype, "peak_pc": ms_local(float(r.peak_t) * 1000.0 + tau, cfg["tz"]),
                        "run_pc": f"{ms_local(float(r.run_t0) * 1000.0 + tau, cfg['tz'])} → {ms_local(float(r.run_t1) * 1000.0 + tau, cfg['tz'])}",
                        "run_len_s": int(r.run_len_s)})
        else:
            row.update({"c_max_pc": ms_local(float(r.c_max) * 1000.0 + tau, cfg["tz"]), "dtheta": float(r.dtheta), "dpsi": float(r.dpsi),
                        "spd1": float(r.spd1), "spd2": float(r.spd2), "n_centres": int(r.n_centres)})
        rows.append(row)
    return pd.DataFrame(rows)


def aggregate(out: Path, cfg: dict, fh=None, reuse: bool = False) -> dict:
    """reuse=True (--report-only --reuse): read the bootstrap tables (rates_ci, enrichment, enrichment_posthoc_f2) of the run
    instead of recomputing them (~20 min); every other table is recomputed from the event / control / exposure tables."""
    t0 = time.time()
    tb = out / "tables"
    rd = lambda k: pd.read_csv(tb / f"{k}.csv.gz") if (tb / f"{k}.csv.gz").exists() and (tb / f"{k}.csv.gz").stat().st_size > 30 else pd.DataFrame()  # noqa: E731
    E, Ct, X, XB, RP, Q = rd("events"), rd("controls"), rd("exposure"), rd("exposure_blocks"), rd("repro"), rd("qc")
    RU = rd("runs")
    INFO = pd.read_csv(tb / "animals_info.csv")
    z = np.load(out / "work" / "disp.npz")
    dv, dw = z["disp"].astype(np.float64), z["win"].astype(np.int64)
    tracks = cfg["tracks"]
    taus = dict(zip(INFO.animal, INFO.tau_ms))
    seed = int(cfg["bootstrap"]["seed"])
    # ---- rates
    RT = rate_tables(E, X, tracks)
    RT.to_csv(tb / "rates.csv", index=False)
    have = all((tb / f).exists() for f in ("rates_ci.csv", "enrichment.csv", "enrichment_posthoc_f2.csv"))
    if reuse and have:
        RC = pd.read_csv(tb / "rates_ci.csv")
        log_to(fh, "reusing the run's bootstrap tables (rates_ci, enrichment, enrichment_posthoc_f2)")
    else:
        RC = rate_ci(E, XB, tracks, cfg)
        RC.to_csv(tb / "rates_ci.csv", index=False)
    # ---- enrichment
    rows = []
    k = 0
    for tr in (tracks if not (reuse and have) else []):
        for tn, ts in (("I1", ["I1"]), ("I2", ["I2"]), ("I1+I2", ["I1", "I2"])):
            for zn in ("all", "house", "field"):
                e = E[(E.track == tr) & E.type.isin(ts)]
                c = Ct[(Ct.track == tr) & Ct.type.isin(ts)] if len(Ct) else Ct
                if zn != "all":
                    e = e[e.zone == zn]
                    c = c[c.zone == zn]
                r = enrichment(e, c, dv, dw, cfg, seed + k)
                k += 1
                rows.append({"track": tr, "type": tn, "zone": zn, "events_total": int(len(E[(E.track == tr) & E.type.isin(ts)]
                                                                                       [lambda d: (d.zone == zn) if zn != "all" else np.ones(len(d), bool)])),
                             **r})
    if reuse and have:
        EN = pd.read_csv(tb / "enrichment.csv")
    else:
        EN = pd.DataFrame(rows)
        EN.to_csv(tb / "enrichment.csv", index=False)
    # post hoc (Amendment 2, declared; no rule uses it): I1 windows restricted to seconds with >= 2 raw fixes on both sides
    rows = []
    if len(E) and "n_f2" in E and len(Ct) and "n_f2" in Ct and not (reuse and have):
        for tr in tracks:
            for zn in ("all", "house", "field"):
                e = E[(E.track == tr) & (E.type == "I1")]
                c = Ct[(Ct.track == tr) & (Ct.type == "I1")]
                if zn != "all":
                    e, c = e[e.zone == zn], c[c.zone == zn]
                r = enrichment(e, c, dv, dw, cfg, seed + 500 + len(rows), cols=("n_f2", "n_le6_f2", "dur_f2"), with_disp=False)
                rows.append({"track": tr, "type": "I1", "zone": zn, **r})
    if reuse and have:
        ENp = pd.read_csv(tb / "enrichment_posthoc_f2.csv")
    else:
        ENp = pd.DataFrame(rows)
        ENp.to_csv(tb / "enrichment_posthoc_f2.csv", index=False)
    # ---- decision (pre-registered)
    dr = cfg["decision_rule"]
    rate = RT[(RT.track == dr["track"]) & (RT.type == "I1+I2") & (RT.stratum == "pooled")]["rate_per_h"].iloc[0]
    en = EN[(EN.track == dr["track"]) & (EN.type == "I1+I2") & (EN.zone == "all")].iloc[0]
    c_rate = bool(rate >= float(dr["min_rate_i1_plus_i2_per_imu_ok_h"]))
    c_ratio = bool(np.isfinite(en.get("share_ratio", np.nan)) and en["share_ratio"] >= float(dr["min_le6_share_ratio"]))
    c_ci = bool(np.isfinite(en.get("share_ratio_lo", np.nan)) and en["share_ratio_lo"] > float(dr["ci_lower_gt"]))
    material = c_rate and c_ratio and c_ci
    rci = RC[(RC.track == dr["track"]) & (RC.type == "I1+I2")].iloc[0]
    dec = {"verdict": "MATERIAL" if material else "NOT MATERIAL", "rate_i1_plus_i2_per_h": float(rate),
           "rate_ci": [float(rci.lo), float(rci.hi)], "rate_rule_met": c_rate,
           "le6_share_ratio": float(en.get("share_ratio", np.nan)), "le6_share_ratio_ci": [float(en.get("share_ratio_lo", np.nan)), float(en.get("share_ratio_hi", np.nan))],
           "ratio_rule_met": c_ratio, "ci_rule_met": c_ci, "le6_share_event": float(en.get("share_e", np.nan)),
           "le6_share_control": float(en.get("share_c", np.nan)), "n_events_enrichment": int(en.get("n_events", 0)),
           "imu_ok_hours": float(X.n_s.sum() / 3600.0), "run_dir": str(out)}
    # ---- sizes, overlap, event lists, reproduction
    SZ = size_table(E, tracks)
    SZ.to_csv(tb / "sizes.csv", index=False)
    OV = i1_overlap(E)
    OV.to_csv(tb / "i1_overlap_v3_b2_raw.csv", index=False)
    RL = pd.DataFrame()
    if len(RU):
        RU["len_bin"] = pd.cut(RU["L"], [0, 10, 30, 60, 300, 1800, np.inf], labels=["1–10 s", "11–30 s", "31–60 s", "1–5 min", "5–30 min", "> 30 min"])
        RL = RU.groupby(["track", "len_bin"], observed=True).agg(runs=("event", "size"), evaluable=("evaluable", "mean"), events=("event", "sum"),
                                                                   event_share=("event", "mean"), run_hours=("L", lambda x: x.sum() / 3600.0)).reset_index()
        RL["events_per_run_hour"] = RL["events"] / RL["run_hours"]
        RL.to_csv(tb / "i1_by_run_length.csv", index=False)
    L1 = event_list(E, "I1", cfg, taus, int(cfg["n_event_list"]))
    L2 = event_list(E, "I2", cfg, taus, int(cfg["n_event_list"]))
    L1.to_csv(tb / "event_list_I1_V3.csv", index=False)
    L2.to_csv(tb / "event_list_I2_V3.csv", index=False)
    repro = {}
    if len(RP):
        tol = float(cfg["repro_tol_deg"])
        a = RP[RP.ok_raw.astype(bool) & RP.grid_match.astype(bool)]
        b = RP[RP.ok_v3.astype(bool) & RP.grid_match.astype(bool)]
        dr_ = np.abs(TV.wrap((a.dtheta_prod - a.dtheta).to_numpy(float)))
        dv_ = np.abs(TV.wrap((b.dtheta_v3_prod - b.dtheta_v3).to_numpy(float)))
        dp_ = np.abs(RP.dpsi_prod - RP.dpsi).to_numpy()
        ds_ = np.abs(RP.dpsi_sec - RP.dpsi).to_numpy()
        f = lambda x: float(np.nanmax(x)) if np.isfinite(x).any() else np.nan  # noqa: E731
        repro = {"pairs": int(len(RP)), "grid_match": int(RP.grid_match.sum()), "n_raw": int(len(a)), "n_v3": int(len(b)),
                 "dtheta_raw_max": f(dr_), "dtheta_raw_nan": int(np.isnan(dr_).sum()), "dtheta_v3_max": f(dv_), "dtheta_v3_nan": int(np.isnan(dv_).sum()),
                 "dpsi_max": f(dp_), "dpsi_nan": int(np.isnan(dp_).sum()), "dpsi_p99": float(np.nanpercentile(dp_, 99)) if np.isfinite(dp_).any() else np.nan,
                 "gok_share": float(RP.gok_prod.astype(bool).mean()), "dpsi_sec_med": float(np.nanmedian(ds_)), "dpsi_sec_p95": float(np.nanpercentile(ds_, 95)),
                 "dpsi_sec_max": f(ds_), "tol_deg": tol}
        repro["pass"] = bool(repro["dtheta_raw_max"] <= tol and repro["dtheta_v3_max"] <= tol and repro["dpsi_max"] <= tol
                             and repro["dtheta_raw_nan"] == 0 and repro["dtheta_v3_nan"] == 0 and repro["dpsi_nan"] == 0)
    # ---- coverage / info
    cov = INFO.copy()
    res = {"decision": dec, "repro": repro, "runtime_aggregate_s": round(time.time() - t0, 1),
           "imu_ok_hours": float(X.n_s.sum() / 3600.0), "n_events": E.groupby(["track", "type"]).size().to_dict() if len(E) else {},
           "qc_flags": {"files": int(len(Q)), "fixes": int(Q.n_fix.sum()) if len(Q) else 0, "qc_i1": int(Q.n_qc_i1.sum()) if len(Q) else 0,
                        "qc_i2": int(Q.n_qc_i2.sum()) if len(Q) else 0}}
    (out / "summary.json").write_text(json.dumps({**res, "n_events": {f"{a}|{b}": v for (a, b), v in res["n_events"].items()}},
                                                 indent=2, default=str), encoding="utf-8")
    log_to(fh, f"aggregate done ({res['runtime_aggregate_s']} s): verdict {dec['verdict']} (rate {rate:.3f}/h, "
               f"<=6 share ratio {dec['le6_share_ratio']:.2f} [{dec['le6_share_ratio_ci'][0]:.2f}, {dec['le6_share_ratio_ci'][1]:.2f}])")
    return {"res": res, "E": E, "Ct": Ct, "X": X, "RT": RT, "RC": RC, "EN": EN, "ENp": ENp, "RL": RL, "SZ": SZ, "OV": OV, "L1": L1, "L2": L2, "RP": RP,
            "Q": Q, "INFO": cov, "RU": RU, "dec": dec, "repro": repro}


# ====================================================================================================== figures
def make_figures(A: dict, cfg: dict, fdir: Path, cohort: str) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 8, "axes.edgecolor": COL["ink2"], "axes.labelcolor": COL["ink"], "xtick.color": COL["ink2"],
                         "ytick.color": COL["ink2"], "axes.spines.top": False, "axes.spines.right": False})
    figs = {}
    tracks = cfg["tracks"]
    RT, EN, E = A["RT"], A["EN"], A["E"]
    # 1) rates by stratum
    levels = [("pooled", "all"), ("daynight", "night"), ("daynight", "day"), ("daynight", "twilight"), ("zone", "house"), ("zone", "field"),
              ("weather", "rain"), ("weather", "wet"), ("weather", "dry")]
    fig, axs = plt.subplots(1, 3, figsize=(11, 3.2), sharey=False)
    for ax, typ in zip(axs, ("I1", "I2", "I3")):
        xx = np.arange(len(levels))
        wd = 0.26
        for j, tr in enumerate(tracks):
            vals = []
            for sn, lv in levels:
                r = RT[(RT.track == tr) & (RT.type == typ) & (RT.stratum == sn) & (RT.level == lv)]
                vals.append(float(r.rate_per_h.iloc[0]) if len(r) else np.nan)
            ax.bar(xx + (j - 1) * wd, vals, wd, color=COL[tr], label=tr)
        ax.set_xticks(xx)
        ax.set_xticklabels([lv for _, lv in levels], rotation=45, ha="right")
        ax.set_title(f"{typ} per IMU-ok hour" + (" (log scale)" if typ != "I1" else ""), color=COL["ink"])
        if typ != "I1":
            ax.set_yscale("log")
        ax.grid(axis="y", color=COL["grid"], lw=0.5)
        ax.set_axisbelow(True)
    axs[0].legend(frameon=False)
    fig.tight_layout()
    p = fdir / f"{STEM}_rates_{cohort}.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    figs["rates"] = p.name
    # 2) enrichment forest
    fig, axs = plt.subplots(1, 3, figsize=(11, 3.6), sharey=True)
    rows = [(tr, tn, zn) for tn in ("I1", "I2", "I1+I2") for zn in ("all", "house", "field") for tr in tracks]
    ylab = []
    for ax, (q, lab) in zip(axs, (("share_ratio", "≤ 6-anchor share ratio"), ("disp_ratio", "dispersion ratio"), ("rate_ratio", "fix-rate ratio"))):
        for i, (tr, tn, zn) in enumerate(rows):
            r = EN[(EN.track == tr) & (EN.type == tn) & (EN.zone == zn)]
            if not len(r) or q not in r or not np.isfinite(r[q].iloc[0]):
                continue
            v, lo, hi = r[q].iloc[0], r[q + "_lo"].iloc[0], r[q + "_hi"].iloc[0]
            ax.plot([lo, hi], [i, i], color=COL[tr], lw=1.2)
            ax.plot([v], [i], "o", color=COL[tr], ms=3.5)
        ax.axvline(1.0, color=COL["ink2"], lw=0.7)
        if q == "share_ratio":
            ax.axvline(2.0, color=COL["ink2"], lw=0.7, ls="--")
            ax.set_xscale("log")
            ax.set_xlim(0.3, 8.0)
            ax.set_xticks([0.5, 1, 2, 4])
            ax.set_xticklabels(["0.5", "1", "2", "4"])
        ax.set_title(lab, color=COL["ink"])
        ax.grid(axis="x", color=COL["grid"], lw=0.5)
    ylab = [f"{tn} {zn} {tr}" for tr, tn, zn in rows]
    axs[0].set_yticks(np.arange(len(rows)))
    axs[0].set_yticklabels(ylab, fontsize=6)
    axs[0].invert_yaxis()
    from matplotlib.lines import Line2D
    axs[2].legend([Line2D([0], [0], color=COL[tr], marker="o", ms=3.5) for tr in tracks], tracks, frameon=False, loc="upper left")
    fig.tight_layout()
    p = fdir / f"{STEM}_enrichment_{cohort}.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    figs["enrichment"] = p.name
    # 3) sizes
    fig, axs = plt.subplots(1, 2, figsize=(9, 3.2))
    for tr in tracks:
        v = E[(E.track == tr) & (E.type == "I1")]["size"].to_numpy(float)
        if len(v):
            axs[0].hist(np.clip(v, 12, 120), bins=np.arange(12, 121, 2), histtype="step", color=COL[tr], label=f"{tr} (n {len(v):,})")
        v = E[(E.track == tr) & (E.type == "I2")]["size"].to_numpy(float)
        if len(v):
            axs[1].hist(v, bins=np.arange(90, 181, 5), histtype="step", color=COL[tr], label=f"{tr} (n {len(v):,})")
    axs[0].set_yscale("log")
    axs[1].set_yscale("log")
    axs[0].set_xlabel("I1 size: max displacement from the run reference (in; > 120 shown at 120)")
    axs[1].set_xlabel("I2 size: max |Δθ| (°)")
    for ax in axs:
        ax.set_ylabel("events")
        ax.legend(frameon=False)
        ax.grid(color=COL["grid"], lw=0.5)
        ax.set_axisbelow(True)
    fig.tight_layout()
    p = fdir / f"{STEM}_sizes_{cohort}.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    figs["sizes"] = p.name
    return figs


# ====================================================================================================== report
def _f(x, nd: int = 2) -> str:
    try:
        if x is None or not np.isfinite(float(x)):
            return "–"
    except (TypeError, ValueError):
        return str(x)
    return f"{float(x):,.{nd}f}"


def _ci(r, q: str, nd: int = 2) -> str:
    return f"{_f(r[q], nd)} [{_f(r[q + '_lo'], nd)}, {_f(r[q + '_hi'], nd)}]" if q in r and np.isfinite(r.get(q, np.nan)) else "–"


def _rate(RT, tr, tn, sn="pooled", lv="all", nd=2):
    r = RT[(RT.track == tr) & (RT.type == tn) & (RT.stratum == sn) & (RT.level == lv)]
    return (_f(r.rate_per_h.iloc[0], nd), int(r.events.iloc[0]), float(r.hours.iloc[0])) if len(r) else ("–", 0, 0.0)


DEFINITIONS = r"""
## Definitions

All positions in the WISER native **inch** frame (UNVERIFIED offset origin; only distances and turn differences are used).
Times: aligned time $t^{\rm al} = t_{\rm WISER} - \tau^*_a$ (the IMU / field-PC clock; $\tau^*$ per animal from the production
tracks); event lists give field-PC time ($t^{\rm al} + \tau^*$). Symbols: $a$ animal, $s$ a field-PC second $[s, s+1)$, $k$ a
fix with aligned time $t_k$ and position $\mathbf z_k$ (raw fix, or the V3 / B2 track value at the fix), $A_k$ its anchors.

### Included second ($\mathrm{inc}(s)$) and IMU-ok hours
$$ \mathrm{inc}(s) = \mathrm{ok}(s) \wedge \neg\exists k: \lfloor t_k \rfloor = s \wedge \mathrm{mask}_k \wedge s < t^{\rm lost}_a $$
$\mathrm{ok}$ = the IMU-seconds cache's QC (≥ 40 of 50 samples, no saturated / frozen / invalid sample, Fusion recovery in < half,
not in handling ± 5 min, all-tag silences ± 120 s, the ADC-lane window, or outside tag validity); $\mathrm{mask}_k$ = any of
`m_handling`, `m_silence`, `m_tag_validity`, `m_adc_lane`, `m_off_animal`; $t^{\rm lost}$ = SF11's implant loss (cohort YAML).
**Text:** the seconds this audit covers; masked fixes are dropped from every estimate. IMU-ok hours $H = \sum_s \mathrm{inc}(s) / 3600$
(the denominator of every rate).

### 1-s median position ($\tilde{\mathbf p}(s)$)
$$ \tilde{\mathbf p}(s) = \operatorname{med}_{\rm coord}\{\mathbf z_k : t_k \in [s, s+1)\}, \quad \text{defined when } \ge 2 \text{ fixes} $$
**Text:** the track's position in second $s$ (coordinate-wise median). Units in. Computed separately for raw, V3 and B2.

### No-locomotion run, trimming, reference (I1)
A run $[a, b)$ = maximal stretch of consecutive included seconds with IMU state still (1) or active (2), $b - a \ge 5$ s; trimmed
run $[a + 2, b - 2)$; reference $\mathbf r = \operatorname{med}_{\rm coord}\{\tilde{\mathbf p}(s) : s \in [a+2, a+4),\ \tilde{\mathbf p}(s)\text{ defined}\}$
(a run with none is *not evaluable*). **Text:** a stretch the head IMU never calls locomotion; the 2-s trims absorb
loco-detector misses at the run edges (pre-registered, not tuned).

### I1 — displacement without locomotion
$$ d(s) = \lVert \tilde{\mathbf p}(s) - \mathbf r \rVert, \qquad \text{event} \iff \exists s: d(s) \ge 12 \wedge d(s+1) \ge 12 \ (s, s+1 \in \text{trimmed run}) $$
Size $= \max_s d(s)$ (in) over the trimmed run; duration $= \#\{s : d(s) \ge 12\}$ (s); window = the union of those seconds; onset =
the first. Subtype: *all_still* (every trimmed second still) or *any_active*. **Text:** the track moves ≥ 12 in away from where the
run started for ≥ 2 s while the IMU never reports locomotion. At most one event per run. Threshold 12 in pre-registered
(≈ 1.7 × the 7-in WISER jitter; the failure audit's crazy-drift bound).

### Pair quantities on the 0.5-s grid (Phase-0 estimators)
$m(t) = \operatorname{med}_{\rm coord}\{\mathbf z_k : t_k \in [t - 0.5, t + 0.5)\}$ (≥ 3 fixes), $\mathbf d(h) = m(h + 0.5) - m(h - 0.5)$,
1-s speed $v(h) = \lVert \mathbf d(h) \rVert / 1\,\mathrm s$, heading $\theta(h) = \operatorname{atan2}(d_y, d_x)$; for a centre $c$:
$$ \Delta\theta(c) = \mathrm{wrap}\big(\theta(c+1) - \theta(c-1)\big), \qquad \Delta\psi(c) = \bar\psi(c+1) - \bar\psi(c-1), \quad \bar\psi(h) = \operatorname{mean}\{\psi(u) : u \in [h - 0.5, h + 0.5)\} $$
$\psi(u) = \int \omega_z$ = the integrated make_imu head turn rate (+ = counter-clockwise seen from above), 50 Hz,
$\mathrm{wrap}(x) = ((x + 180) \bmod 360) - 180$. **Text:** the path's heading change and the head's turn over the same 2 s
(W = 2 s, Phase 0). Candidate pair: $v(c-1) \ge 10$ and $v(c+1) \ge 10$ in/s, every second overlapping $[c - 2, c + 2)$ included and
every 50-Hz sample of $[c - 1.5, c + 1.5)$ valid (`sample_valid`).

### I2 — path turn without head turn; I3 — head turn without path turn
$$ \mathrm{I2}(c) \iff |\Delta\theta(c)| \ge 90^\circ \wedge |\Delta\psi(c)| < 20^\circ, \qquad \mathrm{I3}(c) \iff |\Delta\psi(c)| \ge 90^\circ \wedge |\Delta\theta(c)| < 20^\circ $$
on candidate pairs; qualifying centres closer than 2 s (overlapping pair windows) merge into one event; window
$[c_{\rm first} - 2, c_{\rm last} + 2)$ (the fixes entering the headings); size = $\max|\Delta\theta|$ (I2) / $\max|\Delta\psi|$ (I3).
**Text:** I2 = the WISER path turns ≥ 90° within 2 s while the head turns < 20° (a body turn of ≥ 90° essentially always turns
the head); I3 = the head turns ≥ 90° while the path stays within 20° (expected scanning / turning in place; reported only).
Thresholds 90° / 20° pre-registered.

### Rates
$$ \mathrm{rate}_{\mathcal S} = \frac{\#\{\text{events with onset second in } \mathcal S\}}{\sum_{s \in \mathcal S} \mathrm{inc}(s) / 3600} \quad [\text{per IMU-ok hour}] $$
Strata $\mathcal S$: night 21:00–04:20 | day 08:00–18:00 | twilight (rest); zone house | field (below); weather of the clock hour
rain | wet | dry | unknown (below); animal. CI: 10-min block bootstrap (blocks = animal × 10-min field-PC bin; events
and seconds resampled together), 1000 replicates, 2.5–97.5 percentiles.

### Zone of a second
house if $\tilde{\mathbf p}_{\rm V3}(s)$ lies inside a house ROI (`wiser_rois.json` house_1 / house_2) grown by 14 in on every side,
else field; seconds without $\tilde{\mathbf p}$ take the last defined zone (else the next). A window's zone = that of its first
second. **Text:** the same rule for events and exposure.

### Weather class of an hour $[H, H + 1\,\mathrm h)$ (on-site AWN station, 5-min rows)
rain: ≥ 1 row with rain rate > 0 in the hour; wet: not rain and the last rain row before $H$ is ≤ 12 h earlier; dry: otherwise;
unknown: no row in the hour (before 08-31).

### Matched controls
Same animal, same noon-to-noon bio-day, same track, up to 5 per event drawn at random (seed fixed). I1: evaluable event-free
runs with trimmed length $L_c \in [0.5, 2] L_e$; control window = $\min(D, L_c)$ consecutive seconds starting at
$a_c + 2 + \min(o, L_c - \min(D, L_c))$ ($D$ = event duration, $o$ = onset offset in the event's trimmed run). I2: candidate pairs that
are not I2 centres and whose window $[c - 2, c + 2)$ does not overlap an I2 event window, ≥ 4 s apart. **Text:** the same kind of
window at a time the track did not produce an event.

### Enrichment ratios (event / control)
With window fix counts $n_w$, ≤ 6-anchor counts $n^{\le 6}_w$, durations $T_w$ and control weights $\omega_w = 1/k_e$ ($k_e$ = number of
controls of the event $e$ the control belongs to; events weight 1; events without a control left out):
$$ S = \frac{\sum_w \omega_w n^{\le 6}_w}{\sum_w \omega_w n_w}, \quad \rho_S = \frac{S_{\rm event}}{S_{\rm control}}; \qquad
   \rho_F = \frac{\sum_{\rm ev} n_w / \sum_{\rm ev} T_w}{\sum_{\rm ct} \omega_w n_w / \sum_{\rm ct} \omega_w T_w}; \qquad
   \rho_D = \frac{\operatorname{wmed}\{\delta_k\}_{\rm event}}{\operatorname{wmed}\{\delta_k\}_{\rm control}} $$
$\delta_k = \lVert \mathbf z^{\rm raw}_k - \tilde{\mathbf p}_{\rm raw}(\lfloor t_k \rfloor) \rVert$ = raw-fix dispersion about its 1-s raw median (in; weighted median on
0.1-in bins). **Text:** $\rho_S > 1$ = event windows hold more bad-geometry fixes than matched windows (circumstantial evidence that
the event is WISER's fault); $\rho_D > 1$ = wider raw scatter; $\rho_F < 1$ = fewer fixes (dropout). CI: 10-min block bootstrap
(block = animal × 10-min bin of the window onset; events and controls resampled together), 1000 replicates.

### Pre-registered decision
$$ \text{MATERIAL} \iff \mathrm{rate}^{\rm V3}_{\rm I1+I2} \ge 1\ \mathrm{h}^{-1} \wedge \rho_S^{\rm V3, I1+I2} \ge 2 \wedge \mathrm{CI}_{\rm lo}(\rho_S) > 1 $$
(pooled over all included hours and both zones). Otherwise NOT MATERIAL: V3 stays as is; the QC flags are the deliverable.

### QC flags
Per fix of the production V3 track: `qc_i1` = 1 when $t^{\rm al}_k$ lies in a V3 I1 event window (the union of its ≥ 12-in seconds),
`qc_i2` = 1 when it lies in a V3 I2 event window $[c_{\rm first} - 2, c_{\rm last} + 2)$; `i1_event_id` / `i2_event_id` = the event
(per animal, −1 = none). Masked fixes are flagged too if they fall inside a window (they never do: windows lie in included seconds).

### Reproduction (Phase 0)
$\max |\mathrm{wrap}(\Delta\theta_{\rm here} - \Delta\theta_{\rm Phase\,0})|$ (raw and V3) and $\max|\Delta\psi_{\rm here} - \Delta\psi_{\rm Phase\,0}|$ over all of
Phase 0's W = 2 s pairs; pass ≤ 0.1°.
"""


def render_report(A: dict, cfg: dict, out: Path, figs: dict, meta: dict) -> str:
    RT, RC, EN, SZ, OV, L1, L2, INFO, dec, rp = A["RT"], A["RC"], A["EN"], A["SZ"], A["OV"], A["L1"], A["L2"], A["INFO"], A["dec"], A["repro"]
    rl = A.get("RL", pd.DataFrame())
    E, Q = A["E"], A["Q"]
    c = cfg["_cohort"]
    tracks = cfg["tracks"]
    L = []
    w = L.append
    H = dec["imu_ok_hours"]
    w(f"# WISER baseline {c} — IMU–WISER consistency audit: where does WISER move or turn while the head IMU says it cannot?\n")
    w(f"- **Status:** measurement report, {pd.Timestamp.now(tz=cfg['tz']).strftime('%Y-%m-%d')}. Plan `{PLAN}` (approved by the user "
      f"2026-10-05, \"搞\"; committed ff3c75c before any result; operational details in its Amendment 1, written before any number; "
      f"Amendment 2, written after the first run's pooled numbers, fixes a CSV time-precision bug that changed only the event-list times "
      f"and adds a declared post-hoc sensitivity — no definition, threshold or rule changed; run `wiser_imu_consistency_20261005_1721` superseded). "
      f"Driver `{DRIVER}`, config `wiser/configs/wiser_imu_consistency_{c}.json` (verdict in `decision`), run `{out}`, git `{meta['git_commit']}`.")
    w("- **What this is:** a measurement of the residual inconsistencies between the production default WISER tracks and the "
      "head IMU — I1 (the track moves ≥ 12 in during a stretch the IMU never calls locomotion), I2 (the path turns ≥ 90° in 2 s while "
      "the head turns < 20°), I3 (head turn ≥ 90°, path < 20°; reported only). **No correction is applied and no behavioural claim is "
      "made.** Frame: WISER native inches, unverified offset origin (distances and turn differences only).")
    w("- **Regime context (regime-aware-wiser-tracking):** an event is a WISER error, a loco-detector miss (TPR 0.75 / FPR 0.15) or a "
      "real movement the IMU state does not capture (e.g. being pushed in a huddle). The evidence that events are WISER's fault is "
      "their enrichment in bad-geometry fixes (≤ 6 anchors, wide dispersion) relative to matched windows — circumstantial; the video "
      "check decides. House interiors have worse geometry by default → enrichment is also reported within zone.\n")
    w("## Verdict\n")
    w("| Pre-registered quantity (V3, pooled, all included hours) | value [95 % CI] | rule | met |\n|---|---|---|---|")
    w(f"| I1 + I2 rate per IMU-ok hour | {_f(dec['rate_i1_plus_i2_per_h'], 3)} [{_f(dec['rate_ci'][0], 3)}, {_f(dec['rate_ci'][1], 3)}] | ≥ 1 | {'yes' if dec['rate_rule_met'] else 'no'} |")
    w(f"| ≤ 6-anchor share ratio, event / matched control | {_f(dec['le6_share_ratio'])} [{_f(dec['le6_share_ratio_ci'][0])}, {_f(dec['le6_share_ratio_ci'][1])}] "
      f"(event {_f(100 * dec['le6_share_event'], 1)} % vs control {_f(100 * dec['le6_share_control'], 1)} %) | ≥ 2 | {'yes' if dec['ratio_rule_met'] else 'no'} |")
    w(f"| CI lower bound of that ratio | {_f(dec['le6_share_ratio_ci'][0])} | > 1 | {'yes' if dec['ci_rule_met'] else 'no'} |")
    w(f"| IMU-ok hours / events in the enrichment | {H:,.1f} h / {dec['n_events_enrichment']:,} | | |\n")
    if dec["verdict"] == "MATERIAL":
        w("**MATERIAL.** Per the plan, a correction (e.g. a soft speed cap during non-locomoting runs, down-weighting fixes of "
          "turn-inconsistent windows) is to be proposed as a new pre-registered test, scored against these events, certified "
          "stillness and the clean-WISER speed. Nothing is changed in this step.\n")
    else:
        w("**NOT MATERIAL.** Per the plan, V3 stays as is; the per-fix QC flags are the deliverable. Per-type results follow.\n")
    # ---- reading
    w("## Reading\n")
    r1, n1, _ = _rate(RT, "V3", "I1")
    r2, n2, _ = _rate(RT, "V3", "I2")
    r3, n3, _ = _rate(RT, "V3", "I3")
    w(f"- V3 per IMU-ok hour ({H:,.0f} h): I1 {r1} ({n1:,} events), I2 {r2} ({n2:,}), I3 {r3} ({n3:,}); B2: I1 "
      f"{_rate(RT, 'B2', 'I1')[0]}, I2 {_rate(RT, 'B2', 'I2')[0]}, I3 {_rate(RT, 'B2', 'I3')[0]}; raw medians: I1 {_rate(RT, 'raw', 'I1')[0]}, "
      f"I2 {_rate(RT, 'raw', 'I2')[0]}, I3 {_rate(RT, 'raw', 'I3')[0]}.")
    w(f"- **V3 I1 by stratum:** night {_rate(RT, 'V3', 'I1', 'daynight', 'night')[0]}, day {_rate(RT, 'V3', 'I1', 'daynight', 'day')[0]}, "
      f"twilight {_rate(RT, 'V3', 'I1', 'daynight', 'twilight')[0]}; house {_rate(RT, 'V3', 'I1', 'zone', 'house')[0]}, field "
      f"{_rate(RT, 'V3', 'I1', 'zone', 'field')[0]}; rain {_rate(RT, 'V3', 'I1', 'weather', 'rain')[0]}, wet {_rate(RT, 'V3', 'I1', 'weather', 'wet')[0]}, "
      f"dry {_rate(RT, 'V3', 'I1', 'weather', 'dry')[0]}. **V3 I2:** night {_rate(RT, 'V3', 'I2', 'daynight', 'night')[0]}, day "
      f"{_rate(RT, 'V3', 'I2', 'daynight', 'day')[0]}; house {_rate(RT, 'V3', 'I2', 'zone', 'house')[0]}, field {_rate(RT, 'V3', 'I2', 'zone', 'field')[0]}.")
    ov = OV[OV.subtype == "all"]
    if len(ov):
        o = ov.iloc[0]
        w(f"- **The filters already remove most of the raw inconsistencies:** I2 falls from {_rate(RT, 'raw', 'I2')[0]} (raw medians) to "
          f"{_rate(RT, 'B2', 'I2')[0]} (B2) and {_rate(RT, 'V3', 'I2')[0]} (V3) per hour; I1 from {_rate(RT, 'raw', 'I1')[0]} to "
          f"{_rate(RT, 'B2', 'I1')[0]} and {_rate(RT, 'V3', 'I1')[0]}. Matched by run, {o.B2_not_V3:,} B2 I1 events are absent in V3 and "
          f"{o.V3_not_B2:,} appear only in V3; {_rate(RT, 'V3', 'I1 all_still')[1]:,} V3 I1 events fall in all-still runs (V3's ZUPT pins "
          f"them), so the residual I1 sits in runs with at least one IMU-active second.")
    rv = rl[rl.track == "V3"] if len(rl) else rl
    if len(rv):
        w("- **I1 grows with run length:** the share of V3 runs with an event rises from "
          + ", ".join(f"{100 * r.event_share:.1f} % ({r.len_bin})" for r in rv.itertuples())
          + " (§4) — as compatible with slow repositioning, huddle shifts or a slow WISER bias inside long rests as with "
          "transient WISER errors (the reference is the start of the run).")
    for tn in ("I1", "I2", "I1+I2"):
        ee = EN[(EN.track == "V3") & (EN.type == tn)]
        cells = []
        for zn in ("all", "house", "field"):
            r_ = ee[ee.zone == zn]
            if len(r_) and r_.iloc[0].get("n_events", 0):
                cells.append(f"{zn} {_ci(r_.iloc[0], 'share_ratio')}")
        if cells:
            w(f"- **Enrichment V3 {tn}** (≤ 6-anchor share ratio): " + "; ".join(cells) + ".")
    e1 = EN[(EN.track == "V3") & (EN.type == "I1") & (EN.zone == "all")]
    if len(e1):
        w(f"  V3 I1 dispersion ratio {_ci(e1.iloc[0], 'disp_ratio')}, fix-rate ratio {_ci(e1.iloc[0], 'rate_ratio')}. B2 / raw I1 share ratios: "
          + ", ".join(f"{tr} {_ci(EN[(EN.track == tr) & (EN.type == 'I1') & (EN.zone == 'all')].iloc[0], 'share_ratio')}" for tr in ("B2", "raw")) + ".")
    ENp = A.get("ENp", pd.DataFrame())
    ep = ENp[(ENp.track == "V3") & (ENp.zone == "all")] if len(ENp) else ENp
    if len(ep) and ep.iloc[0].get("n_events", 0):
        w(f"  Post hoc (Amendment 2): with both windows restricted to seconds holding ≥ 2 raw fixes, the V3 I1 share ratio is "
          f"{_ci(ep.iloc[0], 'share_ratio')} and the fix-rate ratio {_ci(ep.iloc[0], 'rate_ratio')} — the fix-rate excess above is the "
          f"window-construction asymmetry, the ≤ 6-anchor excess is not.")
    w("- **Reading of the enrichment:** V3 event windows hold more ≤ 6-anchor fixes than matched windows (CI above 1, in both "
      "zones), so part of the residual events is bad WISER geometry; but the excess is well below the pre-registered 2×, smaller "
      "than in B2 and in the raw medians (V3 already discounts low-anchor fixes), and V3's I2 windows are not enriched at all. "
      "Most residual events are therefore not explained by geometry: they are as compatible with loco-detector misses (the "
      "largest I1 events are 70–120-in displacements in tens of seconds at 8–9 anchors) and real slow movement as with WISER "
      "errors. The video check of §5 decides individual cases.")
    w("- **I2 in V3** is rare (0.10 per IMU-ok hour, none by day); the largest are path reversals (|Δθ| ≈ 170–180°) at speeds just "
      "above the 10-in/s floor with good geometry — candidates for back-and-forth movement or WISER noise at low speed, to be "
      "checked on video. **I3** (head turn without a path turn, reported only) is 0.06 per hour in V3 and 0.27 in B2 / raw.")
    w("- Within zone and per track: §3. Sizes and V3 vs B2: §4. Event lists for the video check: §5. Flags: §6. Reproduction: §7.\n")
    w("Classification (regime-aware-wiser-tracking): a **measurement** result about WISER and the head IMU (no behavioural content). "
      "Rates count candidate inconsistencies, not errors.\n")
    # ---- 1 coverage
    w("## 1. Coverage\n")
    w("| animal | days | IMU-ok s (cache) | included h | runs (≥ 5 s) | run hours (trimmed) | candidate pairs V3 / B2 / raw | masked fixes | τ* (ms) |\n|---|---|---|---|---|---|---|---|---|")
    for r in INFO.itertuples():
        w(f"| {r.animal} | {r.days} | {r.ok_s:,} | {r.incl_s / 3600:,.1f} | {r.runs:,} | {r.run_s / 3600:,.1f} | "
          f"{r.cand_pairs_V3:,} / {r.cand_pairs_B2:,} / {r.cand_pairs_raw:,} | {r.masked_fixes:,} | {r.tau_ms:.0f} |")
    w(f"| **all** | | {INFO.ok_s.sum():,} | **{INFO.incl_s.sum() / 3600:,.1f}** | {INFO.runs.sum():,} | {INFO.run_s.sum() / 3600:,.1f} | "
      f"{INFO.cand_pairs_V3.sum():,} / {INFO.cand_pairs_B2.sum():,} / {INFO.cand_pairs_raw.sum():,} | {INFO.masked_fixes.sum():,} | |\n")
    w("Candidate pairs = 0.5-s centres meeting the speed rule (≥ 10 in/s at c ± 1) with IMU-ok support (the I2 / I3 exposure).\n")
    # ---- 2 rates
    w("## 2. Rates per IMU-ok hour\n")
    w(f"![rates](../figures/{figs['rates']})\n")
    w("| track | type | pooled [95 % CI] | night | day | twilight | house | field | rain | wet | dry |\n|---|---|---|---|---|---|---|---|---|---|---|")
    for tr in tracks:
        for tn in ("I1", "I2", "I3", "I1+I2"):
            rc = RC[(RC.track == tr) & (RC.type == tn)]
            pooled = f"{_f(rc.rate_per_h.iloc[0], 3)} [{_f(rc.lo.iloc[0], 3)}, {_f(rc.hi.iloc[0], 3)}]" if len(rc) else "–"
            cells = [_rate(RT, tr, tn, sn, lv, 3)[0] for sn, lv in (("daynight", "night"), ("daynight", "day"), ("daynight", "twilight"),
                                                                 ("zone", "house"), ("zone", "field"), ("weather", "rain"), ("weather", "wet"), ("weather", "dry"))]
            w(f"| {tr} | {tn} | {pooled} | " + " | ".join(cells) + " |")
    hrs = {lv: _rate(RT, "V3", "I1", sn, lv)[2] for sn, lv in (("daynight", "night"), ("daynight", "day"), ("daynight", "twilight"), ("zone", "house"),
                                                               ("zone", "field"), ("weather", "rain"), ("weather", "wet"), ("weather", "dry"), ("weather", "unknown"))}
    w("\nIMU-ok hours per stratum: " + ", ".join(f"{k} {v:,.0f}" for k, v in hrs.items()) + ". Weather *unknown* = no on-site AWN "
      "row in the hour: the station record has a gap 09-02 21:15 → 09-03 15:05 (the 09-03 rain night of the earlier audits), "
      "09-10 22:00–24:00, and nothing after 09-12 11:05.\n")
    w("**I1 by subtype** (V3 / B2 / raw, per IMU-ok hour; all_still = every trimmed second still, any_active = at least one active second):\n")
    w("| subtype | V3 pooled | V3 house | V3 field | B2 pooled | B2 house | B2 field | raw pooled | raw house | raw field |\n|---|---|---|---|---|---|---|---|---|---|")
    for st in ("all_still", "any_active"):
        cells = []
        for tr in tracks:
            for sn, lv in (("pooled", "all"), ("zone", "house"), ("zone", "field")):
                v, k_, _ = _rate(RT, tr, f"I1 {st}", sn, lv, 3)
                cells.append(f"{v} ({k_:,})")
        w(f"| {st} | " + " | ".join(cells) + " |")
    w("\n**Per animal** (V3, per IMU-ok hour):\n")
    w("| animal | IMU-ok h | I1 | I2 | I3 | I1 + I2 |\n|---|---|---|---|---|---|")
    for a in sorted(RT[RT.stratum == "animal"].level.unique()):
        cells = [_rate(RT, "V3", tn, "animal", a, 3) for tn in ("I1", "I2", "I3", "I1+I2")]
        w(f"| {a} | {cells[0][2]:,.1f} | " + " | ".join(f"{v} ({k_:,})" for v, k_, _ in cells) + " |")
    # ---- 3 enrichment
    w("\n## 3. Enrichment of event windows vs matched controls\n")
    w(f"![enrichment](../figures/{figs['enrichment']})\n")
    w("Dots = ratio event / control, bars = 95 % block-bootstrap CI (≤ 6-anchor panel on a log scale with the rule's 2× dashed; dispersion and fix-rate panels linear).\n")
    w("| track | type | zone | events (with controls / all) | controls | ≤ 6 share event | ≤ 6 share control | ≤ 6 share ratio [CI] | dispersion event / control (in) | dispersion ratio [CI] | fix rate event / control (Hz) | fix-rate ratio [CI] |\n|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in EN.itertuples():
        d = r._asdict()
        if not d.get("n_events"):
            w(f"| {r.track} | {r.type} | {r.zone} | 0 / {r.events_total:,} | – | – | – | – | – | – | – | – |")
            continue
        w(f"| {r.track} | {r.type} | {r.zone} | {int(d['n_events']):,} / {r.events_total:,} | {int(d['n_controls']):,} | {_f(100 * d['share_e'], 1)} % | "
          f"{_f(100 * d['share_c'], 1)} % | {_ci(d, 'share_ratio')} | {_f(d['disp_e'], 2)} / {_f(d['disp_c'], 2)} | {_ci(d, 'disp_ratio')} | "
          f"{_f(d['rate_e'], 2)} / {_f(d['rate_c'], 2)} | {_ci(d, 'rate_ratio')} |")
    ENp = A.get("ENp", pd.DataFrame())
    if len(ENp):
        w("\n**Post hoc sensitivity (Amendment 2, declared; no rule uses it):** an I1 event window consists only of seconds with a 1-s "
          "median (≥ 2 fixes), a control window is contiguous and may include seconds with 0–1 fixes. Restricting both to seconds with "
          "≥ 2 raw fixes:\n")
        w("| track | zone | events | ≤ 6 share event | ≤ 6 share control | ≤ 6 share ratio [CI] | fix-rate ratio [CI] |\n|---|---|---|---|---|---|---|")
        for r in ENp.itertuples():
            d = r._asdict()
            if not d.get("n_events"):
                continue
            w(f"| {r.track} | {r.zone} | {int(d['n_events']):,} | {_f(100 * d['share_e'], 1)} % | {_f(100 * d['share_c'], 1)} % | "
              f"{_ci(d, 'share_ratio')} | {_ci(d, 'rate_ratio')} |")
    # ---- 4 sizes
    w("\n## 4. Size distributions and V3 vs B2\n")
    w(f"![sizes](../figures/{figs['sizes']})\n")
    w("| track | type | quantity | n | p10 | p50 | p90 | p99 | max |\n|---|---|---|---|---|---|---|---|---|")
    for r in SZ.itertuples():
        w(f"| {r.track} | {r.type} | {str(r.quantity).replace('|', chr(92) + '|')} | {r.n:,} | {_f(r.p10, 1)} | {_f(r.p50, 1)} | {_f(r.p90, 1)} | {_f(r.p99, 1)} | {_f(r.max, 1)} |")
    w("\n**I1 events per track, matched by run** (the runs are IMU-defined and identical for every track):\n")
    w("| subtype | V3 | B2 | raw | V3 ∧ B2 | B2 only (removed by V3) | V3 only | raw ∧ V3 | raw only |\n|---|---|---|---|---|---|---|---|---|")
    for r in OV.itertuples():
        w(f"| {r.subtype} | {r.V3:,} | {r.B2:,} | {r.raw:,} | {r.V3_and_B2:,} | {r.B2_not_V3:,} | {r.V3_not_B2:,} | {r.raw_and_V3:,} | {r.raw_not_V3:,} |")
    if len(rl):
        w("\n**I1 by run length** (trimmed length; runs are IMU-defined, so the run counts are the same for every track):\n")
        w("| run length | runs | run hours | evaluable | V3 events (share of runs, per run-hour) | B2 events | raw events |\n|---|---|---|---|---|---|---|")
        for lb in rl.len_bin.unique():
            g_ = rl[rl.len_bin == lb].set_index("track")
            if "V3" not in g_.index:
                continue
            v3 = g_.loc["V3"]
            w(f"| {lb} | {int(v3.runs):,} | {v3.run_hours:,.1f} | {100 * v3.evaluable:.0f} % | {int(v3.events):,} ({100 * v3.event_share:.1f} %, "
              f"{v3.events_per_run_hour:.2f}) | {int(g_.loc['B2'].events) if 'B2' in g_.index else 0:,} | {int(g_.loc['raw'].events) if 'raw' in g_.index else 0:,} |")
    # ---- 5 event lists
    w("\n## 5. Event lists for the user's video check (V3)\n")
    w("Camera = hourly file under `F:\\3rd_rat\\<date>\\<CH>\\` with the offset into it at the event onset, by **file-name time** "
      "(field-PC; never the OSD). house_1 → CH08 in-box + CH05 top-down, house_2 → CH07 + CH06, open field → CH01 / CH02 "
      "panoramas; IR (monochrome) at night. **The agent has not looked at any frame.** Full tables: `tables/event_list_I1_V3.csv`, "
      "`tables/event_list_I2_V3.csv` in the run dir.\n")
    w(f"### 5a. The {len(L1)} largest I1 (by size)\n")
    w("| # | animal | onset (field-PC) | peak | size (in) | dur (s) | subtype | run (s) | zone | anchors med (≤ 6 share) | video at onset |\n|---|---|---|---|---|---|---|---|---|---|---|")
    for r in L1.itertuples():
        w(f"| {r.rank} | {r.animal} | {r.onset_pc} | {r.peak_pc[11:]} | {_f(r.size, 1)} | {_f(r.dur_s, 0)} | {r.subtype} | {r.run_len_s:,} | {r.zone} | "
          f"{_f(r.anchors_med, 0)} ({_f(100 * r.le6_share, 0)} %) | {r.video} |")
    w(f"\n### 5b. The {len(L2)} largest I2 (by |Δθ|)\n")
    w("| # | animal | window start (field-PC) | centre of max | Δθ (°) | Δψ (°) | speeds c∓1 (in/s) | zone | anchors med (≤ 6 share) | video at window start |\n|---|---|---|---|---|---|---|---|---|---|")
    for r in L2.itertuples():
        w(f"| {r.rank} | {r.animal} | {r.onset_pc} | {r.c_max_pc[11:]} | {_f(r.dtheta, 0)} | {_f(r.dpsi, 0)} | {_f(r.spd1, 0)} / {_f(r.spd2, 0)} | {r.zone} | "
          f"{_f(r.anchors_med, 0)} ({_f(100 * r.le6_share, 0)} %) | {r.video} |")
    # ---- 6 flags
    w("\n## 6. QC flags\n")
    nf = int(Q.n_fix.sum()) if len(Q) else 0
    w(f"Per fix of the production V3 track, every day of SF07–SF12 ({len(Q)} files, {nf:,} fixes): `qc_i1` set on "
      f"{int(Q.n_qc_i1.sum()):,} fixes ({_f(100 * Q.n_qc_i1.sum() / max(nf, 1), 3)} %), `qc_i2` on {int(Q.n_qc_i2.sum()):,} "
      f"({_f(100 * Q.n_qc_i2.sum() / max(nf, 1), 3)} %; I1 windows can be long — duration p90 65 s, p99 ≈ 570 s — hence the I1 share). "
      f"Cache: `{cfg['qc_root']}/<label>/<YYYYMMDD>.csv.gz` (columns `t_ms`, `qc_i1`, "
      f"`qc_i2`, `i1_event_id`, `i2_event_id`; same row order as the production file; README + index there). The production tracks "
      f"are not modified. Join: `pd.read_csv(qc).merge(track, on='t_ms')` or positional.\n")
    # ---- 7 reproduction
    w("## 7. Reproduction of Phase 0 from the production caches\n")
    if rp:
        w(f"All {rp['pairs']:,} W = 2 s pairs of Phase 0 (grid matched {rp['grid_match']:,}): max |Δθ difference| raw "
          f"{_f(rp['dtheta_raw_max'], 4)}° (n {rp['n_raw']:,}), V3 {_f(rp['dtheta_v3_max'], 4)}° (n {rp['n_v3']:,}); max |Δψ difference| "
          f"{_f(rp['dpsi_max'], 4)}° (p99 {_f(rp['dpsi_p99'], 4)}°); missing values: raw {rp['dtheta_raw_nan']}, V3 {rp['dtheta_v3_nan']}, "
          f"Δψ {rp['dpsi_nan']}; gyro span ok here on {_f(100 * rp['gok_share'], 1)} % of them. Tolerance {rp['tol_deg']}° → "
          f"**{'PASS' if rp['pass'] else 'FAIL'}**.")
        w(f"For information (Amendment 1.2): Δψ approximated from the per-second `turn_net_deg` (piecewise-linear ψ between second "
          f"boundaries) differs from the 50-Hz value by median {_f(rp['dpsi_sec_med'], 2)}°, p95 {_f(rp['dpsi_sec_p95'], 2)}°, max "
          f"{_f(rp['dpsi_sec_max'], 1)}° — the reason the 50-Hz npz is used.\n")
    else:
        w("No Phase-0 pairs available.\n")
    w("## 8. Caveats\n")
    w("- No ground truth: an event is a WISER error, a loco-detector miss or a real movement the IMU state does not capture; "
      "enrichment is circumstantial, the video check decides.\n- Head turn ≠ body turn (scanning), hence the strict asymmetric I2 rule; "
      "I3 is expected to be mostly scanning / turning in place.\n- I1's reference is the start of the run: a genuine slow repositioning "
      "(or a WISER bias shift) inside a long run keeps every later second ≥ 12 in away, so durations can be long; such events dilute "
      "the enrichment toward 1, which is the intended reading.\n- Weather: rain inside the 09-02 21:15 → 09-03 15:05 station gap is "
      "not seen, so the hours right after the gap may be classed dry instead of wet.\n- Positions are in the unverified WISER inch frame; zones use the "
      "house ROIs + 14 in.\n- The 12-in / 90° / 20° thresholds were set in advance and are not tuned.\n")
    w(DEFINITIONS)
    return "\n".join(L) + "\n"


def publish(A: dict, cfg: dict, out: Path, fh=None) -> None:
    c = cfg["_cohort"]
    fdir = output_paths.figure_dir(c, DIRECTION)
    figs = make_figures(A, cfg, fdir, c)
    for f in figs.values():
        shutil.copy2(fdir / f, out / "figures" / f) if (out / "figures").exists() else None
    meta = {"cohort": c, "direction": DIRECTION, "analysis": NAME, "report": f"{STEM}_{c}.md", "driver": DRIVER,
            "config": f"wiser/configs/wiser_imu_consistency_{c}.json", "plan": PLAN, "git_commit": C.git_commit(),
            "figures": sorted(figs.values()), "verdict": A["dec"]["verdict"], "rate_i1_plus_i2_per_h": A["dec"]["rate_i1_plus_i2_per_h"],
            "le6_share_ratio": A["dec"]["le6_share_ratio"], "le6_share_ratio_ci": A["dec"]["le6_share_ratio_ci"],
            "qc_root": cfg["qc_root"], "b2_tracks_root": cfg["b2_tracks_root"]}
    rdir = output_paths.report_dir(c, DIRECTION)
    rep = rdir / f"{STEM}_{c}.md"
    rep.write_text(render_report(A, cfg, out, figs, meta), encoding="utf-8")
    output_paths.write_run_manifest(out, out, **meta)
    mp = rdir / f"run_manifest_imu_consistency_{c}.json"
    mp.write_text(json.dumps({"run_dir": str(out.resolve()), **meta}, indent=2, default=str) + "\n", encoding="utf-8")
    # verdict into the config
    cp = Path(cfg["_path"])
    raw = json.loads(cp.read_text(encoding="utf-8"))
    raw["decision"] = {**A["dec"], "repro_pass": A["repro"].get("pass"), "written": pd.Timestamp.now(tz=cfg["tz"]).strftime("%Y-%m-%d %H:%M")}
    cp.write_text(json.dumps(raw, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    log_to(fh, f"report {rep}; pointer {mp}; figures {sorted(figs.values())}; config decision written")


# ====================================================================================================== QC-flag cache
def install_flags(run: Path, cfg: dict, fh=None) -> dict:
    """Copy the run's staged QC flags into <qc_root>/<label>/<date>.csv.gz, never overwriting; README + index."""
    root = Path(cfg["qc_root"])
    root.mkdir(parents=True, exist_ok=True)
    Q = pd.read_csv(run / "tables" / "qc.csv.gz")
    rows = []
    for r in Q.itertuples():
        src = Path(r.staged)
        dst = root / r.label / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        existing = dst.exists()
        if not existing:
            tmp = dst.with_name(dst.name.replace(".csv.gz", ".partial.csv.gz"))
            shutil.copy2(src, tmp)
            os.replace(tmp, dst)
        rows.append({"label": r.label, "date": r.date, "n_fix": r.n_fix, "n_qc_i1": r.n_qc_i1, "n_qc_i2": r.n_qc_i2, "path": str(dst),
                     "existing": existing, "run_dir": str(run), "bytes": dst.stat().st_size, "git_commit": C.git_commit(), "writer": DRIVER})
    I = pd.DataFrame(rows)
    ip = root / f"index_{cfg['_cohort']}.csv"
    if ip.exists():
        old = pd.read_csv(ip)
        I = pd.concat([old[~old.path.isin(I.path)], I], ignore_index=True)
    I.to_csv(ip, index=False)
    rm = root / "README.md"
    if not rm.exists():
        rm.write_text(f"""# QC flags for the default WISER tracks - cohort {cfg['_cohort']} (IMU-WISER consistency audit)

Written by `{DRIVER}` (`--install-flags`, plan `{PLAN}`), never overwriting. Report (definitions, rates, enrichment, event lists):
`results/{cfg['_cohort']}/wiser_baseline/reports/{STEM}_{cfg['_cohort']}.md`; run dir `{run}`.

Layout: `<label>/<YYYYMMDD>.csv.gz` = one row per fix of the production V3 default track
`wiser_default_tracks/<label>/<YYYYMMDD>.csv.gz`, **same row order**, keyed by `t_ms` (labels SF07-SF12; every production day,
days without IMU all 0). `index_{cfg['_cohort']}.csv` = one row per file (fixes, flagged fixes, run dir). The production tracks are
not modified.

Columns:
- `t_ms` - the fix's WISER time (= the production track's `t_ms`).
- `qc_i1` (0/1) - the fix's aligned time (t_ms - tau*) lies in a V3 **I1** event window: during a no-locomotion run (IMU still /
  active, >= 5 s, trimmed 2 s at both ends) the V3 track's 1-s median is >= 12 in from the run's reference (median of the first
  2 s) for >= 2 consecutive seconds; the window = every second of that run with displacement >= 12 in.
- `qc_i2` (0/1) - the fix lies in a V3 **I2** event window [c_first - 2, c_last + 2): the V3 path heading turns >= 90 deg over
  W = 2 s (Phase-0 estimator, 1-s speed >= 10 in/s at c - 1 and c + 1) while the head gyro turns < 20 deg.
- `i1_event_id`, `i2_event_id` - the event (per animal, matches `event_id` of the run's `tables/events.csv.gz` rows with track
  V3; -1 = none).

Reading: a flag marks a **candidate** inconsistency (WISER error, loco-detector miss or a real movement the IMU state misses), not
a confirmed error; the report's enrichment and the user's video check say how often it is WISER's fault. Positions remain in the
unverified WISER inch frame.
""", encoding="utf-8")
    log_to(fh, f"QC flags installed under {root}: {int((~I.existing).sum()) if 'existing' in I else 0} new, "
               f"{int(I.existing.sum()) if 'existing' in I else 0} existing (kept)")
    return {"n": int(len(I)), "new": int((~I.existing).sum()), "existing": int(I.existing.sum())}


# ====================================================================================================== selftest
def _synth(seed: int = 7) -> dict:
    """A synthetic animal: walking bouts (real turns with a gyro turn, head scanning), in-place runs with planted 15-in WISER
    drifts built from <= 6-anchor fixes, planted sideways WISER kinks during straight running (no gyro turn), planted head
    turns without a path turn, and a loco-detector miss at a run edge."""
    rng = np.random.default_rng(seed)
    fsg = 50.0
    s0 = int(C.to_ms("2026-09-05 22:00:00") // 1000)
    plan = []                                    # (kind, dur, dict)
    plan.append(("still", 40, {}))
    plan.append(("walk", 30, {"turns": [(12.0, 90.0)], "scan": False}))
    plan.append(("miss", 2, {}))
    plan.append(("inplace", 200, {"edge_run": True}))
    for k in range(8):
        plan.append(("walk", 25, {"turns": [(10.0, 90.0 if k % 2 == 0 else -90.0)], "scan": True}))
        plan.append(("inplace", 200, {"drift": 100.0}))
    for k in range(12):
        kw = {"turns": [], "scan": False}
        if k < 6:
            kw["kink"] = 12.0
        elif k < 9:
            kw["headturn"] = 8.0
        plan.append(("walk", 25, kw))
        plan.append(("inplace", 200, {}))
    T = int(sum(p[1] for p in plan))
    t = np.arange(0.0, T, 1.0 / fsg)
    x, y = np.zeros(len(t)), np.zeros(len(t))
    hd = np.zeros(len(t))                        # path heading (deg)
    psi = np.zeros(len(t))                       # head yaw (deg)
    state = np.zeros(T, np.int8)
    drifts, kinks, headturns, real_turns, edge = [], [], [], [], None
    cx, cy, ch = 100.0, 100.0, 0.0
    t0 = 0
    v = 20.0
    for kind, dur, kw in plan:
        i0, i1 = int(t0 * fsg), int((t0 + dur) * fsg)
        tt = t[i0:i1] - t0
        if kind in ("still", "inplace"):
            x[i0:i1], y[i0:i1], hd[i0:i1], psi[i0:i1] = cx, cy, ch, ch
            if kind == "still":
                state[t0:t0 + dur] = 1
            else:
                state[t0:t0 + dur] = np.where((np.arange(dur) // 10) % 2 == 0, 2, 1)
            if kw.get("drift") is not None:
                drifts.append(t0 + kw["drift"])
            if kw.get("edge_run"):
                edge = (t0 - 2, t0 + dur)
        else:                                    # walk / miss: constant speed, heading changes linearly over 1 s at turns
            h = np.full(len(tt), ch)
            for tr_, dh in kw.get("turns", []):
                h += dh * np.clip(tt - tr_, 0.0, 1.0)
                real_turns.append(t0 + tr_ + 0.5)
            ang = np.radians(h)
            vx, vy = v * np.cos(ang), v * np.sin(ang)
            x[i0:i1] = cx + np.cumsum(vx) / fsg
            y[i0:i1] = cy + np.cumsum(vy) / fsg
            hd[i0:i1] = h
            ps = h.copy()
            if kw.get("scan"):
                ps += 40.0 * np.sin(2 * np.pi * 0.4 * tt)
            if kw.get("headturn") is not None:
                ht = kw["headturn"]
                ps += 100.0 * np.clip((tt - ht) / 0.5, 0, 1) - 100.0 * np.clip((tt - ht - 3.5) / 0.5, 0, 1)
                headturns.append(t0 + ht)
            if kw.get("kink") is not None:
                kinks.append(t0 + kw["kink"])
            psi[i0:i1] = ps
            state[t0:t0 + dur] = 3 if kind == "walk" else 2
            cx, cy, ch = x[i1 - 1], y[i1 - 1], h[-1]
        t0 += dur
    # WISER fixes at ~8 Hz
    tfx = np.sort(np.arange(0.0, T, 0.125) + rng.uniform(0, 0.02, int(T / 0.125)))
    tfx = tfx[tfx < T - 0.05]
    X = np.interp(tfx, t, x) + rng.normal(0, 1.5, len(tfx))
    Y = np.interp(tfx, t, y) + rng.normal(0, 1.5, len(tfx))
    anch = np.where(rng.uniform(size=len(tfx)) < 0.9, 9, rng.choice([5, 6], size=len(tfx))).astype(np.int64)
    planted = np.zeros(len(tfx), np.int8)       # 1 drift, 2 kink
    for d0 in drifts:                            # 15 in along +x: ramp 3 s, hold 6 s, ramp 3 s
        u = tfx - d0
        m = (u >= 0) & (u < 12)
        off = np.where(u < 3, 5.0 * u, np.where(u < 9, 15.0, 15.0 - 5.0 * (u - 9)))
        X[m] += off[m]
        anch[m] = 5
        planted[m] = 1
    for k0 in kinks:                             # sideways bump (perpendicular to the path: +y while walking along x)
        u = tfx - k0
        m = (u >= 0) & (u < 3)
        hh = np.interp(k0, t, hd)
        nx, ny = -np.sin(np.radians(hh)), np.cos(np.radians(hh))
        off = np.where(u < 1.5, 30.0 * u, 45.0 - 30.0 * (u - 1.5))
        X[m] += nx * off[m]
        Y[m] += ny * off[m]
        anch[m] = 5
        planted[m] = 2
    P = np.column_stack([X, Y])

    def smooth(a, wlen, fn):
        return pd.DataFrame(a).rolling(wlen, center=True, min_periods=1).agg(fn).to_numpy()
    pos = {"V3": smooth(P, 5, "median"), "B2": smooth(P, 9, "mean"), "raw": P}
    turn = np.gradient(psi) * fsg
    gyro = TV.Gyro(s0 + t, turn, np.ones(len(t), bool), fsg, 1.5)
    return {"s0": s0, "T": T, "tf": s0 + tfx, "pos": pos, "anch": anch, "state": state, "gyro": gyro, "drifts": drifts, "kinks": kinks,
            "headturns": headturns, "real_turns": real_turns, "edge": edge, "planted": planted, "t": t, "psi": psi}


def _synth_arrays(S: dict, cfg: dict) -> dict:
    s0, T = S["s0"], S["T"]
    n = T + 2
    s0g = s0 - 1
    incl = np.zeros(n, bool)
    incl[1:T + 1] = True
    state = np.zeros(n, np.int8)
    state[1:T + 1] = S["state"]
    g = float(s0g) + 0.5 * np.arange(2 * n)
    dpsi, gok = gyro_pairs(S["gyro"], g, cfg["pairs"])
    return {"animal": "SF00", "tau_ms": 0.0, "s0": s0g, "n": n, "incl": incl, "ok": incl, "state": state, "tf": S["tf"], "anch": S["anch"],
            "pos": S["pos"], "dpsi": dpsi, "gok": gok, "dn": np.zeros(n, np.int8), "wx": np.full(n, 3, np.int8),
            "bio": np.zeros(n, np.int64), "hour_ms": np.full(n, s0g * 1000, np.int64)}


def selftest() -> int:
    t_start = time.time()
    cfg = load_cfg("2026c")
    ok_all = True

    def check(name, cond, detail=""):
        nonlocal ok_all
        ok_all &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}", flush=True)
    S = _synth()
    A = _synth_arrays(S, cfg)
    R = analyze_arrays(A, cfg, [])
    E, Ct = R["events"], R["controls"]
    s0 = S["s0"]
    # 1) I1 finds every planted drift (raw and V3), nothing else
    for tr in ("raw", "V3"):
        e = E[(E.track == tr) & (E.type == "I1")]
        hit = [any((r.t0 - s0 >= d - 1) and (r.t0 - s0 <= d + 12) for r in e.itertuples()) for d in S["drifts"]]
        false = [r for r in e.itertuples() if not any(d - 1 <= r.t0 - s0 <= d + 12 for d in S["drifts"])]
        check(f"I1 ({tr}) finds all {len(S['drifts'])} planted 15-in drifts and nothing else", all(hit) and not false,
              f"(events {len(e)}, hits {sum(hit)}, false {len(false)}; sizes {np.round(e['size'].to_numpy(), 1).tolist()})")
    # 2) the 2-s trimming removes the loco-detector edge miss
    cfg0 = json.loads(json.dumps(cfg))
    cfg0["i1"]["trim_s"] = 0
    R0 = analyze_arrays(A, cfg0, [])
    e0 = R0["events"]
    e0 = e0[(e0.track == "raw") & (e0.type == "I1")]
    ea, eb = S["edge"]
    in_edge0 = [r for r in e0.itertuples() if ea <= r.t0 - s0 < eb]
    e2 = E[(E.track == "raw") & (E.type == "I1")]
    in_edge2 = [r for r in e2.itertuples() if ea <= r.t0 - s0 < eb]
    check("loco-detector edge miss: an I1 event without trimming, none with the 2-s trim", len(in_edge0) == 1 and not in_edge2,
          f"(trim 0: {len(in_edge0)} (size {in_edge0[0].size if in_edge0 else float('nan'):.1f} in); trim 2: {len(in_edge2)})")
    # 3) I2 finds the planted kinks, not the real turns
    for tr in ("raw", "V3"):
        e = E[(E.track == tr) & (E.type == "I2")]
        hit = [any((r.t0 - s0 <= k + 1.5) and (r.t1 - s0 >= k + 1.5) for r in e.itertuples()) for k in S["kinks"]]
        near_real = [r for r in e.itertuples() if any((r.t0 - s0 - 1 <= rt <= r.t1 - s0 + 1) for rt in S["real_turns"])]
        check(f"I2 ({tr}) finds all {len(S['kinks'])} planted kinks, none at the {len(S['real_turns'])} real turns", all(hit) and not near_real and len(e) == len(S["kinks"]),
              f"(events {len(e)}, hits {sum(hit)}, at real turns {len(near_real)}; |dθ| {np.round(e['size'].to_numpy(), 0).tolist()}, "
              f"|dψ| {np.round(np.abs(e['dpsi'].to_numpy()), 1).tolist()})")
    # 4) I3 finds the planted head turns, not the real turns
    e = E[(E.track == "raw") & (E.type == "I3")]
    hit = [any((r.t0 - s0 <= h + 4.5) and (r.t1 - s0 >= h) for r in e.itertuples()) for h in S["headturns"]]
    near_real = [r for r in e.itertuples() if any((r.t0 - s0 + 1 <= rt <= r.t1 - s0 - 1) for rt in S["real_turns"])]
    check("I3 finds the planted head turns without a path turn, none at real turns", all(hit) and not near_real,
          f"(events {len(e)}, head turns hit {sum(hit)}/{len(S['headturns'])}, at real turns {len(near_real)})")
    # 5) real turns: dpsi ~ 90 and dtheta ~ 90 at the turn centre
    g = float(A["s0"]) + 0.5 * np.arange(2 * A["n"])
    pq = pair_track(A["tf"], S["pos"]["raw"], g, cfg["pairs"])
    j = [int(np.argmin(np.abs(g - (s0 + rt)))) for rt in S["real_turns"]]
    dps = A["dpsi"][j]
    tt_, ps_ = S["t"] + s0, S["psi"]
    expect_psi = np.array([ps_[(tt_ >= g[x] + 0.5) & (tt_ < g[x] + 1.5)].mean() - ps_[(tt_ >= g[x] - 1.5) & (tt_ < g[x] - 0.5)].mean() for x in j])
    dts = np.abs(pq["dth"][j])
    check("real 90° turns: Δψ = the true head-yaw change of the 1-s means (≤ 1°), |Δθ| ≈ 90° (Phase-0 estimators)",
          np.all(np.abs(dps - expect_psi) < 1.0) and np.all(np.abs(dts - 90) < 20),
          f"(Δψ {np.round(dps, 1).tolist()} vs true {np.round(expect_psi, 1).tolist()}, |Δθ| {np.round(dts, 0).tolist()})")
    # 6) enrichment ~ planted ratio (I1 raw: event windows are all <= 6 anchors, background 10 %)
    z = R["disp"]
    dw = R["disp_win"].astype(np.int64)
    er = E[(E.track == "raw") & (E.type == "I1")]
    cr = Ct[(Ct.track == "raw") & (Ct.type == "I1")]
    en = enrichment(er, cr, z.astype(float), dw, cfg, 1)
    bg = float((S["anch"][S["planted"] == 0] <= 6).mean())
    expect = 1.0 / bg
    check("I1 enrichment: <= 6-anchor share ratio ≈ planted ratio (1 / background share), CI > 1", abs(en["share_ratio"] / expect - 1) < 0.3 and en["share_ratio_lo"] > 1,
          f"(ratio {en['share_ratio']:.2f} [{en['share_ratio_lo']:.2f}, {en['share_ratio_hi']:.2f}] vs planted {expect:.2f}; "
          f"dispersion ratio {en['disp_ratio']:.2f}; controls {en['n_controls']} for {en['n_events']} events)")
    er2 = E[(E.track == "raw") & (E.type == "I2")]
    cr2 = Ct[(Ct.track == "raw") & (Ct.type == "I2")]
    en2 = enrichment(er2, cr2, z.astype(float), dw, cfg, 2)
    tfw = A["tf"]
    exp2 = []
    for r in er2.itertuples():
        i0, i1 = np.searchsorted(tfw, [r.t0, r.t1])
        exp2.append((S["anch"][i0:i1] <= 6).mean())
    exp2 = float(np.mean(exp2)) / bg if exp2 else np.nan
    check("I2 enrichment: ratio ≈ the planted share in the event windows / background", abs(en2["share_ratio"] / exp2 - 1) < 0.3,
          f"(ratio {en2['share_ratio']:.2f} [{en2['share_ratio_lo']:.2f}, {en2['share_ratio_hi']:.2f}] vs planted {exp2:.2f})")
    # 7) controls: <= 5 per event, never overlapping an event window of the same type and track
    okc = True
    for (tr, typ), cc in Ct.groupby(["track", "type"]):
        ee = E[(E.track == tr) & (E.type == typ)]
        if cc.groupby("event_id").size().max() > 5:
            okc = False
        for r in cc.itertuples():
            if ((ee.t0 < r.t1) & (ee.t1 > r.t0)).any() and typ == "I2":
                okc = False
    i1c = Ct[(Ct.type == "I1")]
    i1e = E[E.type == "I1"]
    for r in i1c.itertuples():
        runs_ev = set(i1e[i1e.track == r.track].run)
        if r.run in runs_ev:
            okc = False
    check("matched controls: <= 5 per event, I1 controls from event-free runs, I2 controls outside I2 windows", okc,
          f"(I1 controls {int((Ct.type == 'I1').sum())}, I2 controls {int((Ct.type == 'I2').sum())})")
    # 8) flags cover the event windows (V3)
    fl = R["flags"]
    i1s, i2s = sorted(fl["I1"]), sorted(fl["I2"])
    e1 = flag_times(A["tf"], [a for a, _, _ in i1s], [b for _, b, _ in i1s], [k for _, _, k in i1s])
    e2f = flag_times(A["tf"], [a for a, _, _ in i2s], [b for _, b, _ in i2s], [k for _, _, k in i2s])
    u = A["tf"] - s0
    core = np.zeros(len(u), bool)
    for d in S["drifts"]:
        core |= (u >= d + 3.5) & (u < d + 8.5)              # planted offset 15 in (>= 12 in after the ramp)
    kink_core = np.zeros(len(u), bool)
    for k in S["kinks"]:
        kink_core |= (u >= k) & (u < k + 3)
    walk = np.isin(np.floor(u).astype(np.int64), np.flatnonzero(S["state"] == 3)) & ~kink_core
    far = np.ones(len(u), bool)
    for r in E[(E.track == "V3") & (E.type == "I2")].itertuples():
        far &= ~((A["tf"] >= r.t0 - 1) & (A["tf"] < r.t1 + 1))
    check("QC flags: planted drift cores carry qc_i1, kinks carry qc_i2, walking outside I2 windows unflagged",
          (e1[core] >= 0).mean() > 0.97 and (e2f[kink_core] >= 0).all() and not (e1[walk & far] >= 0).any() and not (e2f[walk & far] >= 0).any(),
          f"(drift core flagged {100 * (e1[core] >= 0).mean():.1f} %, kink fixes flagged {100 * (e2f[kink_core] >= 0).mean():.1f} %, "
          f"walking flagged {int((e1[walk & far] >= 0).sum() + (e2f[walk & far] >= 0).sum())})")
    # 8b) the CSV writer keeps absolute event times exact (bug found in the first field run, Amendment 2)
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        pth = Path(td) / "events.csv.gz"
        write_table(E, pth, exact=True)
        E2 = pd.read_csv(pth)
        dt = float(np.max(np.abs(E2[["t0", "t1"]].to_numpy(float) - E[["t0", "t1"]].to_numpy(float))))
    check("event tables round-trip through CSV with exact times", dt < 1e-6, f"(max |Δt| {dt:.2e} s)")
    # 9) small helpers
    sup = support_ok(np.array([10.0, 10.5, 3.0]), 0, np.r_[np.ones(20, bool)], 2.0)
    inc2 = np.ones(20, bool)
    inc2[12] = False
    sup2 = support_ok(np.array([10.0, 10.5, 14.5, 15.0]), 0, inc2, 2.0)
    mg = merge_centres(np.array([1, 2, 3, 8, 9, 20]), np.arange(30) * 0.5, 2.0)
    pm = psi_mean_seconds(0, np.full(10, 10.0), np.array([2.0, 2.5]))
    check("helpers: support (seconds overlapping [c - 2, c + 2)), centre merging (< 2 s), per-second ψ mean", list(sup) == [True, True, True]
          and list(sup2) == [True, False, False, True] and [len(x) for x in mg] == [3, 2, 1] and np.allclose(pm, [25.0, 30.0]),
          f"({list(sup2)}, {[len(x) for x in mg]}, {pm.tolist()})")
    # 10) rate / enrichment / overlap tables run on the synthetic output
    X = R["exposure"]
    RT = rate_tables(E, X, ["V3", "B2", "raw"])
    OV = i1_overlap(E)
    check("aggregation helpers run (rates, I1 overlap)", len(RT) > 0 and len(OV) == 3, f"(V3 I1 rate {RT[(RT.track == 'V3') & (RT.type == 'I1') & (RT.stratum == 'pooled')].rate_per_h.iloc[0]:.2f}/h)")
    print(f"selftest {time.time() - t_start:.1f} s -> {'ALL PASS' if ok_all else 'FAILED'}", flush=True)
    return 0 if ok_all else 1


# ====================================================================================================== main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cohort", default="2026c")
    ap.add_argument("--config", default=None)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--animals", nargs="*", default=None)
    ap.add_argument("--report-only", default=None, help="re-aggregate and re-render from an existing run dir")
    ap.add_argument("--reuse", action="store_true", help="with --report-only: reuse the run's bootstrap tables")
    ap.add_argument("--install-flags", default=None, help="copy a run's staged QC flags into the QC-flag cache (never overwriting)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    if a.selftest:
        sys.exit(selftest())
    cfg = load_cfg(a.cohort, a.config)
    if a.install_flags:
        run = Path(a.install_flags)
        with open(run / "log.txt", "a", encoding="utf-8") as fh:
            install_flags(run, cfg, fh)
        return
    holder = {}
    if a.report_only:
        out = Path(a.report_only)
        fh = open(out / "log_report.txt", "a", encoding="utf-8")
    else:
        out = run_compute(cfg, a.workers or int(cfg["workers"]), a.animals, holder)
        fh = holder["fh"]
    A = aggregate(out, cfg, fh, reuse=bool(a.report_only and a.reuse))
    publish(A, cfg, out, fh)
    fh.close()


if __name__ == "__main__":
    main()
