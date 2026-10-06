r"""wiser_assist_p0.py — WISER-assisted YOLO, phase 0, on the step-2 hour (cohort-3 CH01, field-PC 2026-09-06 21:00-22:00):
A. WISER -> paddock mapping checked against the CH01 YOLO detections (fit / test blocks, negative control, similarity
   sensitivity, pre-registered acceptance); B. WISER presence at the YOLO fixed spots (SEALED: written only to
   wiser_spots.csv, never printed or reported); C. missed-rat candidates (WISER animal in CH01's ground support, no box).

Specification: implementation_plan/2026-10-05-wiser-assisted-yolo-p0.md (pre-registered) + its dated amendments.
Every data location: cv/cv_field/DATA_MAP_c1yolo_wiser.md (sections C, D, E, G).

Inputs (read-only): the step-2 run ($OUT/2026c/cv_field_c1yolo_video_20261005_1848: detections.csv.gz, frames.csv.gz,
fixed_spots/fixed_spots.csv, fixed_spots/cells.csv.gz); the default WISER tracks SF07-SF12 of 2026-09-06
(wiser/src/default_tracks.py; rows with `valid` and no m_* mask only; t_ms = Unix ms UTC, field-PC local = UTC - 4 h);
wiser/configs/wiser_rois.json (house_1 / house_2 rectangles grown by 14 in); cv/configs/cohort3_handling_windows.json;
the CH01 frame correction + 09-24 calibration (frame_correction.Corrections("2026c").to_paddock, z = 60 mm, inches).

A (plan A1-A5 + amendment 1):
  one frame per second (PTS nearest each whole second after the file-name start, 3 600 frames); YOLO boxes conf >= 0.5
  whose centre is not in a fixed-spot cell (40-px cell with box-centre occupancy >= 5 %, cells.csv.gz); centres -> paddock
  inches; WISER animals outside both house zones at frame time + L (linear between the two bracketing clean fixes, if
  <= 5 s apart). Model paddock = WISER + d. Coarse grid over d (difference of the means +- 100 in, 2-in steps, at L = 0)
  maximising the share of detections with an animal within 20 in; then iterate: L re-chosen on [-90, 90] s (0.5-s grid)
  by the minimum mean truncated Huber cost of the per-frame Hungarian assignment; Hungarian (gate 30 in); Huber least
  squares (k = 6 in) -> d; until d moves < 0.1 in. Blocks of 5 min: odd = fit, even = test. Model selection (amendment 2,
  external review relayed by the user): translation and similarity p = s R(theta)(w - c) + c + d (each with its own L)
  fitted on fit blocks 1, 5, 9 and compared on fit blocks 3, 7, 11; the similarity is chosen only if its inner-validation
  median residual is >= 10 % lower; the chosen model is refitted on all six fit blocks. Negative control: WISER
  22:00-23:00 placed on the same frames, translation refitted identically on the fit blocks. The test blocks are used
  once: the chosen model's test median residual <= 14 in AND the control's test within-14-in share <= half the chosen
  model's -> accepted. If not accepted, B and C are not produced.
  WISER never creates a negative: an animal WISER does not locate is unknown, never "no rat"; nothing is marked empty.
B (only if accepted; blind): spot centre -> paddock (to_paddock at the spot's middle frame) -> WISER frame (inverse map);
  per minute: spot on (box in >= 50 % of the minute's frames, from fixed_spots.csv), median per-second distance to the
  nearest tagged animal (all animals, in or out of houses), that animal and its still share; per spot: minutes on / off
  with an animal within 14 / 30 in and a still animal within 14 in; Spearman rho(occupancy, within-14 indicator).
C (only if accepted): CH01 ground support = union of the 40-px pixel cells whose four corners map (raster 1 in); per
  second each tagged animal outside the houses, mapped and inside the support, with no YOLO box (conf >= 0.25) of the
  sampled frame mapped within 20 in = a miss second; >= 3 consecutive miss seconds of one animal = an episode; per-episode
  start, duration, animal, paddock x / y, nearest 40-px grid pixel, IMU state; a 40-in paddock grid of miss seconds.
  Episodes are SUSPECTED misses for the user's eyes (column kind = suspected_miss), never boxes or labels: an occluded
  animal must not get a box.
The agent never looks at images; WISER positions are proposals, never labels; the lag L is reported only.

Usage (base Python C:/Python313 or the cv env with PYTHONIOENCODING=utf-8):
  python cv/cv_field/wiser_assist_p0.py --selftest
  python cv/cv_field/wiser_assist_p0.py --run [--step2 <step-2 run dir>] [--out <run dir>]
      -> $OUT/2026c/cv_field_wiser_assist_p0_<ts>/ (mapping.json, pairs.csv.gz, residuals_test.csv, control.json,
         lag_profiles.csv, support_polygon.json, wiser_spots.csv [sealed], fn_episodes.csv, fn_grid.csv, run.json)
         + results/2026c/cv_field/reports/cv_field_wiser_assist_p0_2026c.md, figures/wiser_assist_p0/, pointer
         run_manifest_wiser_assist_p0_2026c.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import warnings
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _p in (str(HERE), str(HERE.parent), str(REPO / "wiser" / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

OUT_ROOT = Path(os.environ.get("FIELD2026_ANALYSIS_OUT_ROOT", "D:/Field2026_analysis_out"))
STEP2_RUN = OUT_ROOT / "2026c" / "cv_field_c1yolo_video_20261005_1848"
# the first run, whose model choice used the test blocks (superseded by plan amendment 2; kept as the record)
SUPERSEDED_RUN = OUT_ROOT / "2026c" / "cv_field_wiser_assist_p0_20261005_2158"
ROIS = REPO / "wiser" / "configs" / "wiser_rois.json"
HANDLING = REPO / "cv" / "configs" / "cohort3_handling_windows.json"
LAYOUT = REPO / "cv" / "configs" / "field_layout.json"
COHORT, DIRECTION, NAME = "2026c", "cv_field", "cv_field_wiser_assist_p0"
REPORT_NAME = "cv_field_wiser_assist_p0_2026c.md"
POINTER_NAME = "run_manifest_wiser_assist_p0_2026c.json"
FIG_SUB = "wiser_assist_p0"
PLAN = "implementation_plan/2026-10-05-wiser-assisted-yolo-p0.md"
CAM = "CH01"
HOUR_START = datetime(2026, 9, 6, 21, 0, 0)
DATE = "2026-09-06"
LABELS = ("SF07", "SF08", "SF09", "SF10", "SF11", "SF12")
EDT_H = 4                                   # field-PC local (EDT) = UTC - 4 h
MASK_COLS = ("m_handling", "m_silence", "m_tag_validity", "m_adc_lane", "m_off_animal")
STATE_NAME = {-1: "not located", 0: "unusable", 1: "still", 2: "active", 3: "locomoting"}
CLASSES = (("still", (1,)), ("moving (active + locomoting)", (2, 3)), ("active", (2,)), ("locomoting", (3,)),
           ("IMU unusable", (0,)))


@dataclass(frozen=True)
class Params:
    n_sec: int = 3600              # seconds of the hour (one sampled frame each)
    block_s: int = 300             # validation blocks (odd = fit, even = test)
    conf_a: float = 0.5            # A: box confidence
    spot_occ: float = 0.05         # A: fixed-spot cell occupancy (excluded box centres)
    cell_px: int = 40              # fixed-spot cell size (step-2 diagnostic)
    z_mm: float = 60.0             # assumed height of a box centre (a rat's back)
    lag_max: float = 90.0          # L grid half-width (s)
    lag_step: float = 0.5
    grid_half: float = 100.0       # coarse d grid half-width (in)
    grid_step: float = 2.0
    coarse_r: float = 20.0         # coarse score radius (in)
    gate: float = 30.0             # Hungarian gate (in)
    huber_k: float = 6.0           # Huber threshold (in)
    conv: float = 0.1              # convergence: d moves < conv (in)
    max_it: int = 50
    within: float = 14.0           # "animal within" radius (in) = acceptance threshold
    control_offset: float = 3600.0 # negative control: WISER one hour later
    sim_gain: float = 0.10         # similarity adopted if the test median improves by >= 10 %
    gap_max: float = 5.0           # WISER interpolation: bracketing fixes at most this far apart (s)
    house_buf: float = 14.0        # house zone = rectangle grown by this (in)
    on_frac: float = 0.5           # B: spot "on" in a minute if a box in >= 50 % of its frames
    near2: float = 30.0            # B: second radius (in)
    still_frac: float = 0.5        # B: "still animal" = nearest animal still in >= 50 % of the minute's seconds
    conf_c: float = 0.25           # C: box confidence
    grid_px: int = 40              # C: support grid (px)
    miss_r: float = 20.0           # C: no box within this (in) = miss
    min_ep: int = 3                # C: episode >= this many consecutive miss seconds
    fn_cell: float = 40.0          # C: paddock grid of miss seconds (in)
    support_res: float = 1.0       # C: support raster resolution (in)
    width: int = 7680              # upright pano
    height: int = 2160


# ----------------------------------------------------------------------------------------------- small helpers
def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def git_commit(repo: Path) -> str:
    try:
        c = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        d = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"], capture_output=True,
                           text=True).stdout.strip()
        return c + ("+dirty" if d else "")
    except Exception:  # noqa: BLE001
        return "unknown"


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        v = float(o)
        return v if np.isfinite(v) else None
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return jsonable(o.tolist())
    if isinstance(o, (Path, datetime)):
        return str(o)
    return o


def rho_huber(r: np.ndarray, k: float) -> np.ndarray:
    """Huber loss of a distance r (in): r^2 / 2 inside k, k (r - k / 2) beyond."""
    r = np.asarray(r, float)
    return np.where(r <= k, 0.5 * r * r, k * (r - 0.5 * k))


def trunc_cost(r: np.ndarray, gate: float, k: float) -> float:
    """Mean truncated Huber cost; an unassigned detection (r = inf) costs rho(gate)."""
    r = np.asarray(r, float)
    return float(np.mean(rho_huber(np.minimum(r, gate), k))) if r.size else float("nan")


def q(x, p):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return float(np.percentile(x, p)) if x.size else float("nan")


# ----------------------------------------------------------------------------------------------- WISER
class Tracks:
    """Clean WISER fixes per animal -> positions at query times (s since the hour start): linear between the two
    bracketing fixes when they are <= gap_max apart (else not located); IMU state of the nearer fix."""

    def __init__(self, data: dict, gap_max: float):
        self.labels = list(data)
        self.gap_max = gap_max
        self.t, self.x, self.y, self.st = [], [], [], []
        for lab in self.labels:
            df = data[lab].sort_values("s").drop_duplicates("s")
            self.t.append(df["s"].to_numpy(float))
            self.x.append(df["x"].to_numpy(float))
            self.y.append(df["y"].to_numpy(float))
            self.st.append(df["imu_state"].to_numpy(int))

    def at(self, tq) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        tq = np.asarray(tq, float)
        n, J = len(tq), len(self.labels)
        X = np.full((n, J, 2), np.nan)
        S = np.full((n, J), -1, np.int8)
        ok = np.zeros((n, J), bool)
        for j in range(J):
            t = self.t[j]
            if len(t) < 2:
                continue
            i = np.searchsorted(t, tq, side="right")
            il = np.clip(i - 1, 0, len(t) - 1)
            ir = np.clip(i, 0, len(t) - 1)
            gap = t[ir] - t[il]
            v = (i > 0) & (i < len(t)) & (gap <= self.gap_max) & (gap > 0)
            a = np.where(v, (tq - t[il]) / np.where(gap > 0, gap, 1.0), 0.0)
            X[v, j, 0] = (self.x[j][il] + a * (self.x[j][ir] - self.x[j][il]))[v]
            X[v, j, 1] = (self.y[j][il] + a * (self.y[j][ir] - self.y[j][il]))[v]
            near = np.where(tq - t[il] <= t[ir] - tq, il, ir)
            S[v, j] = self.st[j][near][v]
            ok[:, j] = v
        return X, S, ok


def load_houses(path: Path = ROIS) -> list[dict]:
    R = {r["name"]: r for r in json.loads(Path(path).read_text(encoding="utf-8"))["rois"]}
    return [R["house_1"], R["house_2"]]


def in_houses(X: np.ndarray, houses: list[dict], buf: float) -> np.ndarray:
    """(n, J) True where the position is inside either house rectangle grown by buf (wiser_analysis_utils rule)."""
    import wiser_analysis_utils as wau
    h = np.zeros(X.shape[:2], bool)
    x, y = X[..., 0].ravel(), X[..., 1].ravel()
    with np.errstate(invalid="ignore"):
        for roi in houses:
            _, inb = wau._rect_membership(x, y, roi, buf)
            h |= inb.reshape(X.shape[:2])
    return h


def load_tracks_real(prm: Params, labels=LABELS, date=DATE, hour_start=HOUR_START, handling=HANDLING) -> tuple[dict, dict]:
    """Clean fixes (valid, no m_* mask, outside handling windows) of each label around the hour and the control hour."""
    from default_tracks import load_default_track
    t0_ms = int((pd.Timestamp(hour_start) + pd.Timedelta(hours=EDT_H)).value // 10**6)
    win = [(pd.Timestamp(a), pd.Timestamp(b)) for a, b, _ in json.loads(Path(handling).read_text(encoding="utf-8"))["windows"]]
    lo, hi = -prm.lag_max - 30.0, prm.control_offset + prm.n_sec + prm.lag_max + 30.0
    data, meta = {}, {}
    for lab in labels:
        df = load_default_track(lab, date)
        s = (df["t_ms"].to_numpy(np.int64) - t0_ms) / 1000.0
        w = df[(s >= lo) & (s <= hi)].copy()
        w["s"] = (w["t_ms"].to_numpy(np.int64) - t0_ms) / 1000.0
        clean = w["valid"] & ~w[list(MASK_COLS)].any(axis=1)
        loc = pd.Timestamp(hour_start) + pd.to_timedelta(w["s"], unit="s")
        inh = np.zeros(len(w), bool)
        for a, b in win:
            inh |= ((loc >= a) & (loc < b)).to_numpy()
        keep = clean.to_numpy() & ~inh
        data[lab] = w.loc[keep, ["s", "x", "y", "imu_state"]].reset_index(drop=True)
        meta[lab] = {"path": df.attrs.get("path"), "rows_window": int(len(w)), "clean": int(clean.sum()),
                     "handling_dropped": int((clean.to_numpy() & inh).sum()), "used": int(keep.sum()),
                     "method": w["method"].value_counts().to_dict()}
    return data, meta


# ----------------------------------------------------------------------------------------------- map
@dataclass
class Map:
    """paddock = s R(theta) (w - c) + c + d (inches); theta = 0, s = 1 is the primary translation model."""
    dx: float
    dy: float
    theta: float = 0.0
    s: float = 1.0
    cx: float = 0.0
    cy: float = 0.0

    def M(self) -> np.ndarray:
        c, s_ = np.cos(self.theta), np.sin(self.theta)
        return self.s * np.array([[c, -s_], [s_, c]])

    def fwd(self, W) -> np.ndarray:
        W = np.asarray(W, float)
        c = np.array([self.cx, self.cy])
        return (W - c) @ self.M().T + c + np.array([self.dx, self.dy])

    def inv(self, P) -> np.ndarray:
        P = np.asarray(P, float)
        c = np.array([self.cx, self.cy])
        return (P - c - np.array([self.dx, self.dy])) @ np.linalg.inv(self.M()).T + c

    def as_dict(self) -> dict:
        return {"dx_in": self.dx, "dy_in": self.dy, "theta_deg": float(np.degrees(self.theta)), "scale": self.s,
                "centre_wiser_in": [self.cx, self.cy]}


def huber_translation(V: np.ndarray, k: float, d0, tol: float = 1e-6, it: int = 500) -> np.ndarray:
    """argmin_d sum_i rho_k(|v_i - d|) by IRLS (v_i = paddock - WISER of a matched pair)."""
    d = np.asarray(d0, float).copy()
    for _ in range(it):
        e = np.hypot(*(V - d).T)
        w = np.where(e <= k, 1.0, k / np.maximum(e, 1e-12))
        dn = (w[:, None] * V).sum(0) / w.sum()
        if np.hypot(*(dn - d)) < tol:
            return dn
        d = dn
    return d


def umeyama_w(W: np.ndarray, P: np.ndarray, w: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    """Weighted least-squares similarity P ~ s R W + t (Umeyama 1991 with weights)."""
    sw = w.sum()
    mw, mp = (w[:, None] * W).sum(0) / sw, (w[:, None] * P).sum(0) / sw
    Wc, Pc = W - mw, P - mp
    U, D, Vt = np.linalg.svd((Pc * w[:, None]).T @ Wc / sw)
    sg = np.sign(np.linalg.det(U @ Vt)) or 1.0
    Sg = np.diag([1.0, sg])
    R = U @ Sg @ Vt
    var = (w * (Wc ** 2).sum(1)).sum() / sw
    s = float(np.trace(np.diag(D) @ Sg) / var)
    return s, R, mp - s * R @ mw


def huber_similarity(W: np.ndarray, P: np.ndarray, k: float, m0: Map, tol: float = 1e-6, it: int = 500) -> Map:
    m = m0
    c = np.array([m0.cx, m0.cy])
    for _ in range(it):
        e = np.hypot(*(P - m.fwd(W)).T)
        w = np.where(e <= k, 1.0, k / np.maximum(e, 1e-12))
        s, R, t = umeyama_w(W, P, w)
        d = t + s * R @ c - c
        mn = Map(float(d[0]), float(d[1]), float(np.arctan2(R[1, 0], R[0, 0])), s, m0.cx, m0.cy)
        mv = float(np.max(np.hypot(*(mn.fwd(W) - m.fwd(W)).T)))
        m = mn
        if mv < tol:
            break
    return m


# ----------------------------------------------------------------------------------------------- matching
class Ctx:
    """Detections of part A (sorted by second) + WISER + the block split: odd blocks = fit, even blocks = test; the fit
    blocks split again for model selection (amendment 2): inner fit = 1st, 3rd, 5th fit block (1, 5, 9), inner validation
    = 2nd, 4th, 6th (3, 7, 11). `fit_*` attributes follow the blocks a fit may use (view())."""

    def __init__(self, xy: np.ndarray, sec: np.ndarray, tracks: Tracks, houses: list[dict], prm: Params):
        o = np.argsort(sec, kind="stable")
        self.order = o
        self.xy, self.sec = np.asarray(xy, float)[o], np.asarray(sec, int)[o]
        self.tracks, self.houses, self.prm = tracks, houses, prm
        self.secs = np.arange(prm.n_sec)
        self.block = self.secs // prm.block_s + 1
        self.start = np.searchsorted(self.sec, self.secs, "left")
        self.end = np.searchsorted(self.sec, self.secs, "right")
        bl = np.unique(self.block)
        self.fit_blocks = tuple(int(b) for b in bl if b % 2 == 1)
        self.test_blocks = tuple(int(b) for b in bl if b % 2 == 0)
        self.inner_fit_blocks, self.inner_val_blocks = self.fit_blocks[0::2], self.fit_blocks[1::2]
        self.test_secs_det = self.secs_det(self.test_blocks)
        self.test_mask = self.mask(self.test_blocks)
        self.all_secs_det = np.flatnonzero(self.end > self.start)
        self.lags = np.round(np.arange(-prm.lag_max, prm.lag_max + prm.lag_step / 2, prm.lag_step), 6)
        self.set_fit_blocks(self.fit_blocks)

    def secs_det(self, blocks) -> np.ndarray:
        return np.flatnonzero((self.end > self.start) & np.isin(self.block, blocks))

    def mask(self, blocks) -> np.ndarray:
        return np.isin(self.block[self.sec], blocks)

    def set_fit_blocks(self, blocks) -> None:
        self.used_fit_blocks = tuple(blocks)
        self.fit_sec = np.isin(self.block, blocks)
        self.fit_secs_det = self.secs_det(blocks)
        self.fit_mask = self.mask(blocks)

    def view(self, blocks) -> "Ctx":
        import copy
        c = copy.copy(self)
        c.set_fit_blocks(blocks)
        return c

    def positions(self, shift: float):
        X, S, ok = self.tracks.at(self.secs + shift)
        return X, S, ok, in_houses(X, self.houses, self.prm.house_buf)


def hungarian(xy, start, end, secs, P, avail, gate):
    """Per second: optimal one-to-one assignment detections <-> available animals, cost = distance capped at the gate;
    pairs beyond the gate dropped. -> (animal index or -1, distance or inf) per detection."""
    n = len(xy)
    aj = np.full(n, -1, int)
    r = np.full(n, np.inf)
    for s in secs:
        i0, i1 = start[s], end[s]
        js = np.flatnonzero(avail[s])
        if i1 <= i0 or js.size == 0:
            continue
        qq = P[s, js]
        D = np.hypot(xy[i0:i1, 0, None] - qq[None, :, 0], xy[i0:i1, 1, None] - qq[None, :, 1])
        if D.shape[0] == 1:
            c = int(np.argmin(D[0]))
            if D[0, c] <= gate:
                aj[i0], r[i0] = js[c], D[0, c]
            continue
        if D.shape[1] == 1:
            k = int(np.argmin(D[:, 0]))
            if D[k, 0] <= gate:
                aj[i0 + k], r[i0 + k] = js[0], D[k, 0]
            continue
        rr, cc = linear_sum_assignment(np.minimum(D, gate))
        dd = D[rr, cc]
        kk = dd <= gate
        aj[i0 + rr[kk]] = js[cc[kk]]
        r[i0 + rr[kk]] = dd[kk]
    return aj, r


def nearest(xy, sec, P, avail):
    """Nearest available animal per detection (no one-to-one constraint) -> (index or -1, distance or inf)."""
    Q = P[sec]
    with np.errstate(invalid="ignore"):
        D = np.hypot(xy[:, None, 0] - Q[..., 0], xy[:, None, 1] - Q[..., 1])
    D[~avail[sec]] = np.inf
    D[~np.isfinite(D)] = np.inf
    j = np.argmin(D, 1)
    d = D[np.arange(len(xy)), j]
    j[~np.isfinite(d)] = -1
    return j, d


def coarse_grid(xy, sec, X0, av0, centre, prm: Params):
    """Share of detections with an available animal within coarse_r for each d on the grid (WISER at L = 0)."""
    V = xy[:, None, :] - X0[sec]
    V[~av0[sec]] = np.nan
    g = np.arange(-prm.grid_half, prm.grid_half + prm.grid_step / 2, prm.grid_step)
    gx, gy = centre[0] + g, centre[1] + g
    hits = np.zeros((len(gy), len(gx)))
    R2 = prm.coarse_r ** 2
    with np.errstate(invalid="ignore"):
        for i0 in range(0, len(V), 64):
            v = V[i0:i0 + 64]
            dx2 = (v[..., 0, None] - gx) ** 2
            dy2 = (v[..., 1, None] - gy) ** 2
            hit = ((dy2[..., :, None] + dx2[..., None, :]) <= R2).any(1)
            hits += hit.sum(0)
    score = hits / max(len(V), 1)
    best = score.max()
    cand = np.argwhere(score >= best - 1e-12)
    dist = np.hypot(gx[cand[:, 1]] - centre[0], gy[cand[:, 0]] - centre[1])
    iy, ix = cand[int(np.argmin(dist))]
    return {"score": score, "gx": gx, "gy": gy, "best": [float(gx[ix]), float(gy[iy])], "best_score": float(best),
            "centre": [float(centre[0]), float(centre[1])]}


def choose_lag(ctx: Ctx, m: Map, offset: float, secs_det, mask):
    """L on the grid minimising the mean truncated Huber cost of the Hungarian assignment (ties -> smallest |L|)."""
    prm = ctx.prm
    costs = np.empty(len(ctx.lags))
    for i, L in enumerate(ctx.lags):
        X, S, ok, h = ctx.positions(offset + L)
        P = m.fwd(X.reshape(-1, 2)).reshape(X.shape)
        _, r = hungarian(ctx.xy, ctx.start, ctx.end, secs_det, P, ok & ~h, prm.gate)
        costs[i] = trunc_cost(r[mask], prm.gate, prm.huber_k)
    best = np.nanmin(costs)
    cand = np.flatnonzero(costs <= best + 1e-12)
    i = cand[int(np.argmin(np.abs(ctx.lags[cand])))]
    return float(ctx.lags[i]), costs


def matched_pairs(ctx: Ctx, m: Map, L: float, offset: float, secs_det, mask):
    X, S, ok, h = ctx.positions(offset + L)
    P = m.fwd(X.reshape(-1, 2)).reshape(X.shape)
    aj, r = hungarian(ctx.xy, ctx.start, ctx.end, secs_det, P, ok & ~h, ctx.prm.gate)
    k = mask & (aj >= 0)
    return ctx.xy[k], X[ctx.sec[k], aj[k]], k


def fit_translation(ctx: Ctx, offset: float, log=print) -> dict:
    prm = ctx.prm
    fm = ctx.fit_mask
    X0, _, ok0, h0 = ctx.positions(offset + 0.0)
    av0 = ok0 & ~h0
    fs = np.flatnonzero(ctx.fit_sec)
    cen = ctx.xy[fm].mean(0) - X0[fs][av0[fs]].mean(0)
    co = coarse_grid(ctx.xy[fm], ctx.sec[fm], X0, av0, cen, prm)
    m = Map(*co["best"])
    hist, conv = [], False
    for it in range(prm.max_it):
        L, costs = choose_lag(ctx, m, offset, ctx.fit_secs_det, fm)
        Pp, Ww, _ = matched_pairs(ctx, m, L, offset, ctx.fit_secs_det, fm)
        dn = huber_translation(Pp - Ww, prm.huber_k, [m.dx, m.dy])
        mv = float(np.hypot(dn[0] - m.dx, dn[1] - m.dy))
        hist.append({"it": it + 1, "L_s": L, "cost": float(np.nanmin(costs)), "n_pairs": int(len(Pp)), "dx_in": float(dn[0]),
                     "dy_in": float(dn[1]), "move_in": mv})
        log(f"  [translation, WISER {offset:+.0f} s, blocks {','.join(map(str, ctx.used_fit_blocks))}] it {it + 1}: "
            f"L {L:+.1f} s, cost {np.nanmin(costs):.2f}, pairs {len(Pp)}, "
            f"d ({dn[0]:.2f}, {dn[1]:.2f}), moved {mv:.3f} in")
        m = Map(float(dn[0]), float(dn[1]))
        if mv < prm.conv:
            conv = True
            break
    L, costs = choose_lag(ctx, m, offset, ctx.fit_secs_det, fm)
    Pp, Ww, _ = matched_pairs(ctx, m, L, offset, ctx.fit_secs_det, fm)
    return {"kind": "translation", "fit_blocks": list(ctx.used_fit_blocks), "offset_s": offset, "map": m, "L": L,
            "lag_costs": costs, "coarse": co,
            "history": hist, "converged": conv, "n_iter": len(hist), "n_fit_pairs": int(len(Pp)),
            "fit_pairs_wiser_mean": Ww.mean(0).tolist() if len(Ww) else [0.0, 0.0]}


def fit_similarity(ctx: Ctx, prim: dict, log=print) -> dict:
    prm = ctx.prm
    fm = ctx.fit_mask
    c = prim["fit_pairs_wiser_mean"]
    m = Map(prim["map"].dx, prim["map"].dy, 0.0, 1.0, float(c[0]), float(c[1]))
    hist, conv = [], False
    for it in range(prm.max_it):
        L, costs = choose_lag(ctx, m, 0.0, ctx.fit_secs_det, fm)
        Pp, Ww, _ = matched_pairs(ctx, m, L, 0.0, ctx.fit_secs_det, fm)
        mn = huber_similarity(Ww, Pp, prm.huber_k, m)
        mv = float(np.max(np.hypot(*(mn.fwd(Ww) - m.fwd(Ww)).T)))
        hist.append({"it": it + 1, "L_s": L, "cost": float(np.nanmin(costs)), "n_pairs": int(len(Pp)), **mn.as_dict(),
                     "move_in": mv})
        log(f"  [similarity, blocks {','.join(map(str, ctx.used_fit_blocks))}] it {it + 1}: L {L:+.1f} s, "
            f"theta {np.degrees(mn.theta):.3f} deg, s {mn.s:.4f}, "
            f"d ({mn.dx:.2f}, {mn.dy:.2f}), moved {mv:.3f} in")
        m = mn
        if mv < prm.conv:
            conv = True
            break
    L, costs = choose_lag(ctx, m, 0.0, ctx.fit_secs_det, fm)
    Pp, _, _ = matched_pairs(ctx, m, L, 0.0, ctx.fit_secs_det, fm)
    return {"kind": "similarity", "fit_blocks": list(ctx.used_fit_blocks), "offset_s": 0.0, "map": m, "L": L,
            "lag_costs": costs, "history": hist,
            "converged": conv, "n_iter": len(hist), "n_fit_pairs": int(len(Pp))}


def evaluate(ctx: Ctx, m: Map, L: float, offset: float, secs_det) -> dict:
    X, S, ok, h = ctx.positions(offset + L)
    P = m.fwd(X.reshape(-1, 2)).reshape(X.shape)
    av = ok & ~h
    aj, r = hungarian(ctx.xy, ctx.start, ctx.end, secs_det, P, av, ctx.prm.gate)
    nj, nd = nearest(ctx.xy, ctx.sec, P, av)
    _, nd_all = nearest(ctx.xy, ctx.sec, P, ok)
    sec = ctx.sec
    st_m = np.where(aj >= 0, S[sec, np.maximum(aj, 0)], -1)
    st_n = np.where(nj >= 0, S[sec, np.maximum(nj, 0)], -1)
    return {"X": X, "S": S, "ok": ok, "house": h, "P": P, "aj": aj, "r": r, "nj": nj, "nd": nd, "nd_all": nd_all,
            "st_m": st_m, "st_n": st_n}


def summarize(ev: dict, mask: np.ndarray, labels, prm: Params, tag: str) -> list[dict]:
    r, aj, nd, nj = ev["r"], ev["aj"], ev["nd"], ev["nj"]
    pm = mask & (aj >= 0)

    def row(name, pmask, dmask, dist=None):
        dd = (nd if dist is None else dist)[dmask]
        rr = r[pmask]
        return {"fit": tag, "subset": name, "n_pairs": int(pmask.sum()), "resid_median_in": q(rr, 50),
                "resid_p90_in": q(rr, 90), "n_detections": int(dmask.sum()),
                "within_share": float(np.mean(dd <= prm.within)) if dmask.sum() else float("nan"),
                "matched_share": float(pmask.sum() / dmask.sum()) if (dist is None and name == "all" and dmask.sum()) else float("nan")}

    rows = [row("all", pm, mask),
            row("all (animals in houses counted for within-14)", pm, mask, dist=ev["nd_all"])]
    for name, states in CLASSES:
        rows.append(row(name, pm & np.isin(ev["st_m"], states), mask & np.isin(ev["st_n"], states)))
    for j, lab in enumerate(labels):
        rows.append(row(lab, pm & (aj == j), mask & (nj == j)))
    return rows


# ----------------------------------------------------------------------------------------------- camera mapping
def sample_frames(pts: np.ndarray, n_sec: int) -> np.ndarray:
    """Index of the frame whose PTS is nearest each whole second 0 .. n_sec - 1."""
    s = np.arange(n_sec, dtype=float)
    k = np.clip(np.searchsorted(pts, s), 1, len(pts) - 1)
    return np.where(np.abs(pts[k - 1] - s) <= np.abs(pts[k] - s), k - 1, k)


def map_by_window(d: pd.DataFrame, mapper, hour_start: datetime) -> tuple[np.ndarray, np.ndarray, dict]:
    """Box centres -> paddock inches, one mapper call per whole-second window (time = hour start + window second).
    -> (n, 2) paddock xy (NaN when not mapped), status per box ('ok' / 'flag:<flag>' / 'outside support'), last info."""
    xy = np.full((len(d), 2), np.nan)
    status = np.array(["ok"] * len(d), dtype=object)
    uv = d[["cx", "cy"]].to_numpy(float)
    info_last = {}
    for w, idx in d.groupby("win").indices.items():
        p, info = mapper(hour_start + timedelta(seconds=int(w)), uv[idx])
        info_last = info
        if p is None or info.get("flag") != "ok":
            status[idx] = f"flag:{info.get('flag')}"
            continue
        p = np.asarray(p, float).reshape(-1, 2)
        bad = ~np.isfinite(p).all(1)
        status[idx[bad]] = "outside support"
        xy[idx] = p
    xy[status != "ok"] = np.nan
    return xy, status, info_last


class Support:
    """CH01 ground support: union of the grid_px pixel cells whose four corners map (z = z_mm), rasterised in paddock
    inches; the mapped cell centres give the nearest-grid pano pixel."""

    def __init__(self, mapper, t: datetime, prm: Params):
        import cv2
        from scipy.spatial import cKDTree
        g, W, H = prm.grid_px, prm.width, prm.height
        cu, cv_ = np.arange(g / 2, W, g), np.arange(g / 2, H, g)
        UU, VV = np.meshgrid(cu, cv_)
        cen_uv = np.stack([UU.ravel(), VV.ravel()], 1)
        cxy, info = mapper(t, cen_uv)
        if cxy is None or info.get("flag") != "ok":
            raise RuntimeError(f"support grid not mappable: {info}")
        cxy = np.asarray(cxy, float).reshape(-1, 2)
        fin = np.isfinite(cxy).all(1)
        self.cen_uv, self.cen_xy = cen_uv[fin], cxy[fin]
        self.tree = cKDTree(self.cen_xy)
        ku, kv = np.minimum(np.arange(0, W + 1, g), W - 1), np.minimum(np.arange(0, H + 1, g), H - 1)
        KU, KV = np.meshgrid(ku, kv)
        kxy, _ = mapper(t, np.stack([KU.ravel(), KV.ravel()], 1).astype(float))
        kxy = np.asarray(kxy, float).reshape(len(kv), len(ku), 2)
        allx = kxy[..., 0][np.isfinite(kxy[..., 0])]
        ally = kxy[..., 1][np.isfinite(kxy[..., 1])]
        self.res = prm.support_res
        self.x0, self.y0 = float(np.floor(allx.min()) - 5), float(np.floor(ally.min()) - 5)
        nx = int(np.ceil((allx.max() + 5 - self.x0) / self.res)) + 1
        ny = int(np.ceil((ally.max() + 5 - self.y0) / self.res)) + 1
        self.raster = np.zeros((ny, nx), np.uint8)
        polys = []
        for j in range(len(kv) - 1):
            for i in range(len(ku) - 1):
                quad = np.array([kxy[j, i], kxy[j, i + 1], kxy[j + 1, i + 1], kxy[j + 1, i]])
                if np.isfinite(quad).all():
                    polys.append(np.round(((quad - [self.x0, self.y0]) / self.res) * 4).astype(np.int32))
        cv2.fillPoly(self.raster, polys, 1, lineType=cv2.LINE_8, shift=2)
        self.n_cells = len(polys)
        cs, _ = cv2.findContours(self.raster.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        self.polygons = [((c.reshape(-1, 2) + 0.5) * self.res + [self.x0, self.y0]).round(2).tolist() for c in cs]
        yy, xx = np.nonzero(self.raster)
        px, py = self.x0 + (xx + 0.5) * self.res, self.y0 + (yy + 0.5) * self.res
        self.area_in2 = float(len(xx) * self.res ** 2)
        self.paddock_share = float(np.sum((px >= 0) & (px <= 480) & (py >= 0) & (py <= 240)) * self.res ** 2 / (480 * 240))
        self.time = t
        self.info = info
        self.grid_px = g

    def contains(self, P: np.ndarray) -> np.ndarray:
        P = np.asarray(P, float)
        sh = P.shape[:-1]
        P = P.reshape(-1, 2)
        out = np.zeros(len(P), bool)
        f = np.isfinite(P).all(1)
        ix = np.floor((P[f, 0] - self.x0) / self.res).astype(int)
        iy = np.floor((P[f, 1] - self.y0) / self.res).astype(int)
        inr = (ix >= 0) & (ix < self.raster.shape[1]) & (iy >= 0) & (iy < self.raster.shape[0])
        v = np.zeros(f.sum(), bool)
        v[inr] = self.raster[iy[inr], ix[inr]] > 0
        out[f] = v
        return out.reshape(sh)

    def nearest_px(self, xy) -> tuple[np.ndarray, np.ndarray]:
        d, i = self.tree.query(np.asarray(xy, float).reshape(-1, 2))
        return self.cen_uv[i], d

    def as_dict(self) -> dict:
        return {"camera": CAM, "time": str(self.time), "grid_px": self.grid_px,
                "n_cells_mapped": self.n_cells, "n_grid_centres_mapped": int(len(self.cen_uv)), "raster_res_in": self.res,
                "area_in2": self.area_in2, "paddock_share": self.paddock_share, "polygons_in": self.polygons,
                "correction_flag": self.info.get("flag"), "units": "paddock inches, origin pole A0, 480 x 240 in"}


# ----------------------------------------------------------------------------------------------- B (sealed)
def part_b(spots: pd.DataFrame, fr: pd.DataFrame, mapper, tracks: Tracks, m: Map, L: float, prm: Params,
           hour_start: datetime, out: Path) -> tuple[Path, int]:
    """WISER presence at each fixed spot -> wiser_spots.csv ONLY (blind to the user's verdicts). Returns (path, rows);
    no number of this part is returned, printed or reported."""
    from scipy.stats import spearmanr
    occ_cols = sorted(c for c in spots.columns if c.startswith("occ_min"))
    n_min = len(occ_cols)
    secs = np.arange(prm.n_sec)
    X, S, ok = tracks.at(secs + L)
    tpc = fr.set_index("frame")["t_pc"]
    rows = []
    for sp in spots.itertuples():
        t = datetime.fromisoformat(str(tpc.loc[int(sp.frame_middle)]))
        p, info = mapper(t, np.array([[sp.cx_median, sp.cy_median]], float))
        good = p is not None and info.get("flag") == "ok" and np.isfinite(np.asarray(p, float)).all()
        pxy = np.asarray(p, float).reshape(2) if good else np.array([np.nan, np.nan])
        w = m.inv(pxy[None])[0] if good else np.array([np.nan, np.nan])
        with np.errstate(invalid="ignore"):
            D = np.hypot(X[..., 0] - w[0], X[..., 1] - w[1])
        D[~ok] = np.inf
        D[~np.isfinite(D)] = np.inf
        jn = np.argmin(D, 1)
        dn = D[secs, jn]
        loc = np.isfinite(dn)
        mins = []
        for mm in range(n_min):
            ss = secs[(secs >= 60 * mm) & (secs < 60 * mm + 60)]
            occ = float(getattr(sp, occ_cols[mm]))
            on = occ >= prm.on_frac
            ll = ss[loc[ss]]
            if not good or ll.size == 0:
                dist, lab, still = np.nan, "", np.nan
            else:
                dist = float(np.median(dn[ll]))
                jm = int(np.bincount(jn[ll], minlength=len(tracks.labels)).argmax())
                lab = tracks.labels[jm]
                sj = ss[ok[ss, jm]]
                still = float(np.mean(S[sj, jm] == 1)) if sj.size else np.nan
            w14 = bool(dist <= prm.within) if np.isfinite(dist) else np.nan
            w30 = bool(dist <= prm.near2) if np.isfinite(dist) else np.nan
            s14 = bool(dist <= prm.within and still >= prm.still_frac) if np.isfinite(dist) and np.isfinite(still) else np.nan
            mins.append({"level": "minute", "spot_id": int(sp.spot_id), "minute": mm, "occupancy": occ, "on": on,
                         "n_seconds_located": int(ll.size), "dist_nearest_median_in": dist, "nearest_animal": lab,
                         "nearest_still_share": still, "animal_within_14": w14, "animal_within_30": w30,
                         "still_animal_within_14": s14})
        mdf = pd.DataFrame(mins)
        summ = {"level": "spot", "spot_id": int(sp.spot_id), "pano_cx": float(sp.cx_median), "pano_cy": float(sp.cy_median),
                "middle_frame_time": str(t), "paddock_x_in": pxy[0], "paddock_y_in": pxy[1], "wiser_x_in": w[0],
                "wiser_y_in": w[1], "in_support": bool(good), "correction_flag": info.get("flag")}
        for side, sel in (("on", mdf["on"]), ("off", ~mdf["on"])):
            sub = mdf[sel]
            summ[f"n_min_{side}"] = int(len(sub))
            for col, key in (("animal_within_14", "within14"), ("animal_within_30", "within30"),
                             ("still_animal_within_14", "still_within14")):
                v = sub[col]
                summ[f"n_{side}_{key}"] = int((v == True).sum()) if good else np.nan  # noqa: E712
        if good:
            ind = mdf["animal_within_14"].map(lambda v: float(v) if v in (True, False) else np.nan).to_numpy(float)
            okm = np.isfinite(ind)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                rr = spearmanr(mdf["occupancy"].to_numpy(float)[okm], ind[okm]) if okm.sum() > 2 else (np.nan, np.nan)
            summ["spearman_rho_occ_vs_within14"] = float(rr[0])
            summ["spearman_p"] = float(rr[1])
        else:
            summ["spearman_rho_occ_vs_within14"] = np.nan
            summ["spearman_p"] = np.nan
        rows.append(summ)
        rows.extend(mins)
    df = pd.DataFrame(rows)
    path = out / "wiser_spots.csv"
    df.to_csv(path, index=False)
    return path, int(len(df))


# ----------------------------------------------------------------------------------------------- C
def part_c(d_all: pd.DataFrame, frs: pd.DataFrame, fr: pd.DataFrame, tracks: Tracks, houses, m: Map, L: float,
           sup: Support, prm: Params, hour_start: datetime, seconds_out: list | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """seconds_out (a list): if given, the per-second table of every eligible animal-second is appended to it (sec,
    animal, WISER and paddock position, IMU state, nearest box, miss, episode_id) - nothing else changes."""
    secs = np.arange(prm.n_sec)
    X, S, ok = tracks.at(secs + L)
    h = in_houses(X, houses, prm.house_buf)
    P = m.fwd(X.reshape(-1, 2)).reshape(X.shape)
    insup = sup.contains(P)
    elig = ok & ~h & insup
    J = len(tracks.labels)
    bs = d_all[d_all["sampled"] & (d_all["conf"] >= prm.conf_c) & d_all["mapped"]].sort_values("sec")
    bsec = bs["sec"].to_numpy(int)
    bxy = bs[["px", "py"]].to_numpy(float)
    st, en = np.searchsorted(bsec, secs, "left"), np.searchsorted(bsec, secs, "right")
    nbd = np.full((prm.n_sec, J), np.inf)
    for s in np.flatnonzero(elig.any(1)):
        if en[s] > st[s]:
            b = bxy[st[s]:en[s]]
            js = np.flatnonzero(elig[s])
            D = np.hypot(P[s, js, 0][:, None] - b[None, :, 0], P[s, js, 1][:, None] - b[None, :, 1])
            nbd[s, js] = D.min(1)
    miss = elig & (nbd > prm.miss_r)
    # flicker indicator: share of the window's frames (PTS within +-0.5 s of the second) with a box within miss_r
    wb = d_all[(d_all["conf"] >= prm.conf_c) & d_all["mapped"]]
    wb_by = {w: g for w, g in wb.groupby("win")}
    fwin = np.floor(fr["pts_s"].to_numpy(float) + 0.5).astype(int)
    nfr = np.bincount(fwin[(fwin >= 0) & (fwin < prm.n_sec)], minlength=prm.n_sec)
    eps = []
    for j, lab in enumerate(tracks.labels):
        x = np.r_[False, miss[:, j], False].astype(int)
        dd = np.diff(x)
        for a, b in zip(np.flatnonzero(dd == 1), np.flatnonzero(dd == -1)):
            if b - a < prm.min_ep:
                continue
            ss = np.arange(a, b)
            med = np.median(P[ss, j], axis=0)
            uv, gd = sup.nearest_px(med[None])
            stv = S[ss, j]
            vals, cnt = np.unique(stv, return_counts=True)
            share = []
            for s in ss:
                g = wb_by.get(int(s))
                if g is None or nfr[s] == 0:
                    share.append(0.0)
                    continue
                dg = np.hypot(g["px"].to_numpy() - P[s, j, 0], g["py"].to_numpy() - P[s, j, 1]) <= prm.miss_r
                share.append(g.loc[dg, "frame"].nunique() / nfr[s])
            nb = nbd[ss, j]
            eps.append({"animal": lab, "start_sec": int(a), "end_sec": int(b - 1), "duration_s": int(b - a),
                        "start_t_pc": str(frs.loc[a, "t_pc"]), "end_t_pc": str(frs.loc[b - 1, "t_pc"]),
                        "start_frame": int(frs.loc[a, "frame"]), "end_frame": int(frs.loc[b - 1, "frame"]),
                        "wiser_time_start": str(hour_start + timedelta(seconds=float(a + L))),
                        "paddock_x_in": float(med[0]), "paddock_y_in": float(med[1]),
                        "pano_u": int(uv[0, 0]), "pano_v": int(uv[0, 1]), "grid_point_dist_in": float(gd[0]),
                        "imu_state": STATE_NAME.get(int(vals[np.argmax(cnt)]), "?"), "still_share": float(np.mean(stv == 1)),
                        "nearest_box_median_in": float(np.median(nb[np.isfinite(nb)])) if np.isfinite(nb).any() else np.nan,
                        "seconds_without_any_box": int((~np.isfinite(nb)).sum()),
                        "frames_with_box_within_20_share": float(np.mean(share))})
    ep = pd.DataFrame(eps, columns=["animal", "start_sec", "end_sec", "duration_s", "start_t_pc", "end_t_pc", "start_frame",
                                    "end_frame", "wiser_time_start", "paddock_x_in", "paddock_y_in", "pano_u", "pano_v",
                                    "grid_point_dist_in", "imu_state", "still_share", "nearest_box_median_in",
                                    "seconds_without_any_box", "frames_with_box_within_20_share"])
    if len(ep):
        ep = ep.sort_values(["start_sec", "animal"]).reset_index(drop=True)
        ep.insert(0, "episode_id", np.arange(1, len(ep) + 1))
    else:
        ep.insert(0, "episode_id", [])
    # a WISER proposal for the user's eyes: never a box or a label (an occluded animal must not get a box)
    ep.insert(1, "kind", "suspected_miss")
    in_ep = np.zeros_like(miss)
    ep_id = np.zeros(miss.shape, int)
    for r in ep.itertuples():
        in_ep[r.start_sec:r.end_sec + 1, tracks.labels.index(r.animal)] = True
        ep_id[r.start_sec:r.end_sec + 1, tracks.labels.index(r.animal)] = r.episode_id
    if seconds_out is not None:
        e_s, e_j = np.nonzero(elig)
        o = np.lexsort((e_s, e_j))
        e_s, e_j = e_s[o], e_j[o]
        seconds_out.append(pd.DataFrame({
            "sec": e_s, "t_pc": frs["t_pc"].to_numpy()[e_s], "frame": frs["frame"].to_numpy()[e_s],
            "animal": np.array(tracks.labels, dtype=object)[e_j], "wiser_x_in": X[e_s, e_j, 0], "wiser_y_in": X[e_s, e_j, 1],
            "paddock_x_in": P[e_s, e_j, 0], "paddock_y_in": P[e_s, e_j, 1],
            "imu_state": [STATE_NAME.get(int(v), "?") for v in S[e_s, e_j]],
            "nearest_box_in": np.where(np.isfinite(nbd[e_s, e_j]), nbd[e_s, e_j], np.nan), "miss": miss[e_s, e_j],
            "episode_id": ep_id[e_s, e_j]}))
    cs = prm.fn_cell
    e_s, e_j = np.nonzero(elig)
    cx, cy = np.floor(P[e_s, e_j, 0] / cs).astype(int), np.floor(P[e_s, e_j, 1] / cs).astype(int)
    gdf = pd.DataFrame({"cx": cx, "cy": cy, "miss": miss[e_s, e_j], "ep": in_ep[e_s, e_j]})
    grid = gdf.groupby(["cx", "cy"]).agg(eligible_animal_seconds=("miss", "size"), miss_seconds=("miss", "sum"),
                                         episode_seconds=("ep", "sum")).reset_index()
    grid.insert(0, "cell_x0_in", grid.pop("cx") * cs)
    grid.insert(1, "cell_y0_in", grid.pop("cy") * cs)
    grid["miss_share"] = grid["miss_seconds"] / grid["eligible_animal_seconds"]
    summary = {"animal_seconds_located_outside_houses": int((ok & ~h).sum()), "animal_seconds_eligible_in_support": int(elig.sum()),
               "miss_seconds": int(miss.sum()), "miss_share": float(miss.sum() / max(elig.sum(), 1)),
               "n_episodes": int(len(ep)), "episode_seconds": int(ep["duration_s"].sum()) if len(ep) else 0,
               "by_animal": {lab: {"eligible_s": int(elig[:, j].sum()), "miss_s": int(miss[:, j].sum()),
                                   "episodes": int((ep["animal"] == lab).sum()) if len(ep) else 0,
                                   "episode_s": int(ep.loc[ep["animal"] == lab, "duration_s"].sum()) if len(ep) else 0}
                             for j, lab in enumerate(tracks.labels)}}
    return ep, grid, summary


# ----------------------------------------------------------------------------------------------- pipeline
def prepare_boxes(fr: pd.DataFrame, det: pd.DataFrame, cells: pd.DataFrame, mapper, prm: Params, hour_start: datetime):
    """Frames sorted, one sampled frame per second, the boxes >= min(conf_a, conf_c) mapped per whole-second window, with
    the sampled-frame second and the fixed-spot flag. -> (fr, frs, d, last mapper info, fixed-spot cells). Extracted
    unchanged from run_pipeline (2026-10-06) so the occlusion step can rebuild part C's per-second table."""
    secs = np.arange(prm.n_sec)
    fr = fr.sort_values("frame").reset_index(drop=True)
    kf = sample_frames(fr["pts_s"].to_numpy(float), prm.n_sec)
    frs = fr.iloc[kf].reset_index(drop=True)
    frs["sec"] = secs
    d = det[det["conf"] >= min(prm.conf_a, prm.conf_c)].copy()
    d["cx"], d["cy"] = (d["x1"] + d["x2"]) / 2, (d["y1"] + d["y2"]) / 2
    d["win"] = np.floor(d["pts_s"].to_numpy(float) + 0.5).astype(int)
    d = d[(d["win"] >= 0) & (d["win"] < prm.n_sec)].reset_index(drop=True)
    xy, status, info = map_by_window(d, mapper, hour_start)
    d["px"], d["py"], d["status"] = xy[:, 0], xy[:, 1], status
    d["mapped"] = d["status"] == "ok"
    sec_of = pd.Series(secs, index=frs["frame"].to_numpy())
    d["sampled"] = d["frame"].isin(sec_of.index)
    d["sec"] = d["frame"].map(sec_of).fillna(-1).astype(int)
    spotcells = {(int(r.x0) // prm.cell_px, int(r.y0) // prm.cell_px) for r in cells.itertuples() if r.occupancy >= prm.spot_occ}
    d["in_spot"] = [(int(a // prm.cell_px), int(b // prm.cell_px)) in spotcells for a, b in zip(d["cx"], d["cy"])]
    return fr, frs, d, info, spotcells


def run_pipeline(fr: pd.DataFrame, det: pd.DataFrame, cells: pd.DataFrame, spots: pd.DataFrame, track_data: dict,
                 houses: list[dict], mapper, prm: Params, hour_start: datetime, out: Path, log=print) -> dict:
    """Parts A, B (sealed) and C on one hour. Writes the run-folder outputs; returns the results (no part-B numbers)."""
    t_start = time.perf_counter()
    out.mkdir(parents=True, exist_ok=True)
    tracks = Tracks(track_data, prm.gap_max)
    labels = tracks.labels
    secs = np.arange(prm.n_sec)
    fr, frs, d, info, spotcells = prepare_boxes(fr, det, cells, mapper, prm, hour_start)
    cand = d["sampled"] & (d["conf"] >= prm.conf_a)
    useA = cand & ~d["in_spot"] & d["mapped"]
    inputs = {"frames_total": int(len(fr)), "frames_sampled": int(len(frs)),
              "sampled_pts_offset_abs_max_s": float(np.max(np.abs(frs["pts_s"].to_numpy(float) - secs))),
              "boxes_conf_ge_a_sampled": int(cand.sum()), "dropped_in_fixed_spot_cells": int((cand & d["in_spot"]).sum()),
              "dropped_correction_flag": int((cand & ~d["in_spot"] & d["status"].str.startswith("flag")).sum()),
              "dropped_outside_support": int((cand & ~d["in_spot"] & (d["status"] == "outside support")).sum()),
              "a_detections_used": int(useA.sum()), "spot_cells": sorted([list(c) for c in spotcells]),
              "boxes_conf_ge_c_all_frames": int((d["conf"] >= prm.conf_c).sum()),
              "boxes_conf_ge_c_mapped": int(((d["conf"] >= prm.conf_c) & d["mapped"]).sum()),
              "correction_info": {k: v for k, v in info.items() if k in ("flag", "night", "used", "target_frame",
                                                                       "night_quality", "night_quality_px", "rain_mm_night")},
              "wiser_fixes_used": {lab: int(len(track_data[lab])) for lab in labels}}
    log(f"A: {inputs['a_detections_used']} detections used of {inputs['boxes_conf_ge_a_sampled']} "
        f"(spot cells {inputs['dropped_in_fixed_spot_cells']}, flag {inputs['dropped_correction_flag']}, "
        f"outside support {inputs['dropped_outside_support']})")
    dA = d[useA].copy()
    ctx = Ctx(dA[["px", "py"]].to_numpy(float), dA["sec"].to_numpy(int), tracks, houses, prm)
    dA = dA.iloc[ctx.order].reset_index(drop=True)

    # A1 (amendment 2): model and lag chosen on the fit blocks only - inner fit 1, 5, 9 / inner validation 3, 7, 11
    log(f"A1: model selection on the fit blocks only (inner fit {ctx.inner_fit_blocks}, inner validation {ctx.inner_val_blocks})")
    ci = ctx.view(ctx.inner_fit_blocks)
    tr_in = fit_translation(ci, 0.0, log)
    si_in = fit_similarity(ci, tr_in, log)
    vmask, vsecs = ctx.mask(ctx.inner_val_blocks), ctx.secs_det(ctx.inner_val_blocks)
    sel = {k: summarize(evaluate(ctx, f["map"], f["L"], 0.0, vsecs), vmask, labels, prm, f"inner validation, {k}")[0]
           for k, f in (("translation", tr_in), ("similarity", si_in))}
    med_t, med_s = sel["translation"]["resid_median_in"], sel["similarity"]["resid_median_in"]
    gain = (med_t - med_s) / med_t if np.isfinite(med_t) and med_t > 0 and np.isfinite(med_s) else float("nan")
    adopted = "similarity" if np.isfinite(gain) and gain >= prm.sim_gain else "translation"
    selection = {"inner_fit_blocks": list(ctx.inner_fit_blocks), "inner_val_blocks": list(ctx.inner_val_blocks),
                 "translation": sel["translation"], "similarity": sel["similarity"], "gain": gain, "chosen": adopted,
                 "rule": f"similarity adopted iff its inner-validation median residual is >= {100 * prm.sim_gain:.0f} % below "
                         "the translation's (amendment 2: the test blocks are not used for selection)"}
    log(f"A1: inner-validation median translation {med_t:.2f} in, similarity {med_s:.2f} in, gain {gain:.3f} -> {adopted}")
    # A2: the chosen model refitted on all six fit blocks (the translation fit is also the similarity's start)
    log(f"A2: refit on all fit blocks {ctx.fit_blocks}")
    real = fit_translation(ctx, 0.0, log)
    sim = fit_similarity(ctx, real, log) if adopted == "similarity" else None
    fa = sim if adopted == "similarity" else real
    m_acc, L_acc = fa["map"], fa["L"]
    log("A3: negative control (WISER + 1 h), fit blocks, translation (unchanged)")
    ctrl = fit_translation(ctx, prm.control_offset, log)
    # A4: the test blocks, used once - the chosen model and the control
    ev = {"chosen": evaluate(ctx, m_acc, L_acc, 0.0, ctx.test_secs_det),
          "control": evaluate(ctx, ctrl["map"], ctrl["L"], ctrl["offset_s"], ctx.test_secs_det)}
    tm = ctx.test_mask
    summ = {"chosen": summarize(ev["chosen"], tm, labels, prm, f"chosen ({adopted})"),
            "control": summarize(ev["control"], tm, labels, prm, "control")}
    a_real, a_ctrl = summ["chosen"][0], summ["control"][0]
    med_r = a_real["resid_median_in"]
    c1 = bool(np.isfinite(med_r) and med_r <= prm.within)
    c2 = bool(np.isfinite(a_ctrl["within_share"]) and np.isfinite(a_real["within_share"])
              and a_ctrl["within_share"] <= 0.5 * a_real["within_share"])
    acc = {"accepted": c1 and c2, "criterion_1_test_median_le_14": c1, "test_median_in": med_r,
           "criterion_2_control_within14_le_half_real": c2, "real_within14_share": a_real["within_share"],
           "control_within14_share": a_ctrl["within_share"], "adopted_model": adopted, "selection_gain_inner": gain,
           "rule": "chosen model's test median residual <= 14 in AND control within-14-in share <= 0.5 x the chosen "
                   "model's (plan A5; test blocks used once, amendment 2)"}
    log(f"A4: acceptance {acc['accepted']} (criterion 1 {c1}, criterion 2 {c2}); model {adopted}")

    # run-folder outputs of A
    eva = evaluate(ctx, m_acc, L_acc, 0.0, ctx.all_secs_det)
    lab_or = lambda j: labels[j] if j >= 0 else ""  # noqa: E731
    sec = ctx.sec
    ajs = np.maximum(eva["aj"], 0)
    role = np.where(ctx.test_mask, "test", np.where(ctx.mask(ctx.inner_fit_blocks), "fit (inner fit)", "fit (inner validation)"))
    pairs = pd.DataFrame({
        "sec": sec, "frame": dA["frame"].to_numpy(), "t_pc": dA["t_pc"].to_numpy(), "block": ctx.block[sec],
        "split": np.where(ctx.test_mask, "test", "fit"), "role": role, "conf": dA["conf"].to_numpy(), "u": dA["cx"].to_numpy(),
        "v": dA["cy"].to_numpy(), "paddock_x_in": ctx.xy[:, 0], "paddock_y_in": ctx.xy[:, 1],
        "matched_animal": [lab_or(j) for j in eva["aj"]],
        "wiser_x_in": np.where(eva["aj"] >= 0, eva["X"][sec, ajs, 0], np.nan),
        "wiser_y_in": np.where(eva["aj"] >= 0, eva["X"][sec, ajs, 1], np.nan),
        "mapped_x_in": np.where(eva["aj"] >= 0, eva["P"][sec, ajs, 0], np.nan),
        "mapped_y_in": np.where(eva["aj"] >= 0, eva["P"][sec, ajs, 1], np.nan),
        "residual_in": np.where(np.isfinite(eva["r"]), eva["r"], np.nan),
        "matched_imu_state": [STATE_NAME[int(s)] for s in eva["st_m"]],
        "nearest_animal": [lab_or(j) for j in eva["nj"]],
        "nearest_dist_in": np.where(np.isfinite(eva["nd"]), eva["nd"], np.nan),
        "nearest_imu_state": [STATE_NAME[int(s)] for s in eva["st_n"]],
        "nearest_dist_incl_houses_in": np.where(np.isfinite(eva["nd_all"]), eva["nd_all"], np.nan)})
    pairs.to_csv(out / "pairs.csv.gz", index=False)
    # descriptive diagnostics (amendment 3, after results; no decision depends on them)
    xb = x_band_table(pairs, prm.within)
    xb.to_csv(out / "residuals_test_by_x.csv", index=False)
    tp = pairs[pairs["split"] == "test"]
    far = tp["nearest_dist_in"].fillna(np.inf) > prm.within
    unmatched = {"test_detections": int(len(tp)), "no_outside_animal_within_14": int(far.sum()),
                 "of_which_animal_in_house_zone_within_14": int((far & (tp["nearest_dist_incl_houses_in"] <= prm.within)).sum())}
    fits_all = {"inner_translation": tr_in, "inner_similarity": si_in, "translation": real, "control": ctrl}
    if sim is not None:
        fits_all["similarity"] = sim
    lag_shape = {}
    for k, f in fits_all.items():
        c_ = np.asarray(f["lag_costs"], float)
        i0 = int(np.nanargmin(c_))
        nb = {f"{dl:+.1f}": float(c_[i0 + int(round(dl / prm.lag_step))] / c_[i0] - 1) for dl in (-0.5, 0.5)
              if 0 <= i0 + int(round(dl / prm.lag_step)) < len(c_)}
        w5 = ctx.lags[c_ <= 1.05 * c_[i0]]
        lag_shape[k] = {"L_min_s": float(ctx.lags[i0]), "rel_cost_at_neighbours": nb,
                        "L_range_within_5pct_s": [float(w5.min()), float(w5.max())]}
    rt = pd.DataFrame([r for k in ("chosen", "control") for r in summ[k]])
    rt.to_csv(out / "residuals_test.csv", index=False)
    pd.DataFrame([sel["translation"], sel["similarity"]]).assign(gain=gain, chosen=adopted).to_csv(
        out / "model_selection.csv", index=False)
    lp = {"L_s": ctx.lags}
    lp.update({f"cost_{k}": f["lag_costs"] for k, f in fits_all.items()})
    lp["L_control_wiser_shift_s"] = ctx.lags + prm.control_offset
    pd.DataFrame(lp).to_csv(out / "lag_profiles.csv", index=False)

    def fit_json(f):
        o = {k: v for k, v in f.items() if k not in ("map", "lag_costs", "coarse")}
        o["map"] = f["map"].as_dict()
        if "coarse" in f:
            o["coarse"] = {k: v for k, v in f["coarse"].items() if k in ("best", "best_score", "centre")}
        return o

    ref = house2_reference()
    mapping = {"plan": PLAN, "camera": CAM, "hour_start": str(hour_start), "units": "inches",
               "model": "paddock = s R(theta) (wiser - c) + c + d; translation: theta = 0, s = 1",
               "lag_convention": "WISER queried at frame nominal time (file-name start + PTS) + L; L > 0 = the video's "
                                 "nominal time runs L s behind the WISER / field-PC clock (incl. WISER latency tau* ~0.1-0.2 s)",
               "accepted": acc["accepted"], "acceptance": acc, "selection": selection, "adopted": adopted,
               "accepted_map": m_acc.as_dict(), "accepted_L_s": L_acc,
               "fits": {k: fit_json(f) for k, f in fits_all.items() if k != "control"},
               "test_chosen": a_real, "house2_reference": ref, "params": asdict(prm)}
    (out / "mapping.json").write_text(json.dumps(jsonable(mapping), indent=2), encoding="utf-8")
    control = {"wiser_shift_s": prm.control_offset, "fit": fit_json(ctrl), "test": summ["control"],
               "note": "WISER 1 h later placed on the same frames; L grid relative to the shift"}
    (out / "control.json").write_text(json.dumps(jsonable(control), indent=2), encoding="utf-8")

    res = {"params": asdict(prm), "inputs": inputs, "acceptance": acc, "adopted": adopted, "selection": selection,
           "fits": {k: fit_json(f) for k, f in fits_all.items()},
           "test": summ, "house2_reference": ref, "x_bands": xb.to_dict("records"), "unmatched": unmatched,
           "lag_shape": lag_shape, "_fits": fits_all, "_chosen_fit": fa,
           "_ev": ev, "_tm": tm, "B": {"produced": False}, "C": {"produced": False}}
    if not acc["accepted"]:
        res["B"]["reason"] = res["C"]["reason"] = "mapping not accepted (plan A5): B and C not produced"
        log(res["B"]["reason"])
        res["runtime_s"] = time.perf_counter() - t_start
        return res
    # C first (its support also documents where B's spots fall), then B sealed
    sup = Support(mapper, hour_start + timedelta(seconds=prm.n_sec / 2), prm)
    (out / "support_polygon.json").write_text(json.dumps(jsonable(sup.as_dict()), indent=2), encoding="utf-8")
    ep, grid, csum = part_c(d, frs, fr, tracks, houses, m_acc, L_acc, sup, prm, hour_start)
    ep.to_csv(out / "fn_episodes.csv", index=False)
    grid.to_csv(out / "fn_grid.csv", index=False)
    if len(grid) and grid["miss_seconds"].sum() > 0:                 # descriptive (amendment 3)
        tc = grid.sort_values("miss_seconds", ascending=False).iloc[0]
        x0, y0, cs = float(tc["cell_x0_in"]), float(tc["cell_y0_in"]), prm.fn_cell
        inc = pairs["paddock_x_in"].between(x0, x0 + cs, inclusive="left") & pairs["paddock_y_in"].between(y0, y0 + cs, inclusive="left")
        csum["top_cell"] = {"cell_x0_in": x0, "cell_y0_in": y0, "eligible": int(tc["eligible_animal_seconds"]),
                            "miss_seconds": int(tc["miss_seconds"]), "miss_share": float(tc["miss_share"]),
                            "share_of_all_miss": float(tc["miss_seconds"] / grid["miss_seconds"].sum()),
                            "a_detections_all_blocks": int(inc.sum()), "a_matched": int(pairs.loc[inc, "residual_in"].notna().sum()),
                            "a_resid_median_in": q(pairs.loc[inc, "residual_in"], 50)}
    res["C"] = {"produced": True, "summary": csum, "support": {k: v for k, v in sup.as_dict().items() if k != "polygons_in"},
                "_episodes": ep, "_grid": grid, "_support": sup}
    log(f"C: {csum['n_episodes']} episodes >= {prm.min_ep} s, {csum['episode_seconds']} s; miss seconds "
        f"{csum['miss_seconds']} of {csum['animal_seconds_eligible_in_support']} eligible animal-seconds")
    path, nrows = part_b(spots, fr, mapper, tracks, m_acc, L_acc, prm, hour_start, out)
    res["B"] = {"produced": True, "file": path.name, "rows": nrows, "sealed": True}
    log(f"B: {path.name} written ({nrows} rows) - sealed, no numbers shown")
    res["runtime_s"] = time.perf_counter() - t_start
    return res


def x_band_table(pairs: pd.DataFrame, within: float, width: float = 80.0) -> pd.DataFrame:
    """Test detections by 80-in paddock x band: matched residual median / p90, the signed median residual
    (detection - mapped animal, a local offset shows as non-zero) and the within-14-in shares."""
    t = pairs[pairs["split"] == "test"].copy()
    t["x_band_in"] = (np.floor(t["paddock_x_in"] / width) * width).astype(int)
    rows = []
    warnings.filterwarnings("ignore", message="Mean of empty slice")   # all-unmatched bands -> NaN medians, as intended
    for b, g in t.groupby("x_band_in"):
        r = g["residual_in"].dropna()
        rows.append({"x_band_in": int(b), "n_detections": int(len(g)), "n_pairs": int(len(r)),
                     "resid_median_in": q(r, 50), "resid_p90_in": q(r, 90),
                     "signed_dx_median_in": float((g["paddock_x_in"] - g["mapped_x_in"]).median()),
                     "signed_dy_median_in": float((g["paddock_y_in"] - g["mapped_y_in"]).median()),
                     "within_share": float(np.mean(g["nearest_dist_in"].fillna(np.inf) <= within)),
                     "within_share_incl_houses": float(np.mean(g["nearest_dist_incl_houses_in"].fillna(np.inf) <= within))})
    return pd.DataFrame(rows)


def house2_reference() -> dict:
    """d implied by house_2 (never moved): field_layout.json 'right' shelter centre (cm -> in) minus the WISER ROI centre.
    A reference only (layout from 09-18 imagery, ROI placed by hand), not part of any criterion."""
    try:
        lay = json.loads(LAYOUT.read_text(encoding="utf-8"))["shelters"]["right"]["center_cm"]
        h2 = {r["name"]: r for r in json.loads(ROIS.read_text(encoding="utf-8"))["rois"]}["house_2"]
        px, py = lay[0] / 2.54, lay[1] / 2.54
        return {"paddock_in": [px, py], "wiser_in": [h2["x"], h2["y"]], "d_in": [px - h2["x"], py - h2["y"]]}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


# ----------------------------------------------------------------------------------------------- figures + report
def make_figures(res: dict, figdir: Path) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figdir.mkdir(parents=True, exist_ok=True)
    out = []
    F = res["_fits"]
    fig, axs = plt.subplots(1, 2, figsize=(12, 5))
    for ax, key, title in zip(axs, ("translation", "control"), ("real: WISER 21:00-22:00", "negative control: WISER 22:00-23:00")):
        c = F[key]["coarse"]
        st = res["params"]["grid_step"]
        im = ax.imshow(c["score"], origin="lower", cmap="viridis", vmin=0,
                       extent=[c["gx"][0] - st / 2, c["gx"][-1] + st / 2, c["gy"][0] - st / 2, c["gy"][-1] + st / 2])
        ax.plot(*c["best"], "wx", ms=10, mew=2, label="coarse best")
        ax.plot(F[key]["map"].dx, F[key]["map"].dy, "r+", ms=14, mew=2, label="final d")
        ax.set_xlabel("dx (in)")
        ax.set_ylabel("dy (in)")
        ax.set_title(title, fontsize=10)
        ax.legend(fontsize=8, loc="upper right")
        fig.colorbar(im, ax=ax, shrink=0.8, label="share of fit detections with an animal within 20 in (L = 0)")
    fig.suptitle("A. Coarse grid over the offset d (fit blocks)", fontsize=11)
    fig.tight_layout()
    fig.savefig(figdir / "coarse_grid.png", dpi=110)
    plt.close(fig)
    out.append("coarse_grid.png")

    fig, ax = plt.subplots(figsize=(9, 4.5))
    lags = np.round(np.arange(-res["params"]["lag_max"], res["params"]["lag_max"] + res["params"]["lag_step"] / 2,
                              res["params"]["lag_step"]), 6)
    for key, col, ls, lab in (("inner_translation", "C0", "--", "translation, inner fit 1,5,9"),
                              ("inner_similarity", "C2", "--", "similarity, inner fit 1,5,9"),
                              ("translation", "C0", "-", "translation, fit blocks"), ("similarity", "C2", "-", "similarity, fit blocks"),
                              ("control", "C3", "-", "negative control (WISER + 1 h), fit blocks")):
        if key not in F:
            continue
        ax.plot(lags, F[key]["lag_costs"], color=col, ls=ls, lw=1.2, label=f"{lab}: L = {F[key]['L']:+.1f} s")
        ax.axvline(F[key]["L"], color=col, ls=":", lw=1)
    ax.set_xlabel("lag L (s): WISER queried at frame time + L")
    ax.set_ylabel("mean truncated Huber cost (in$^2$)")
    ax.set_title("A. Lag profile at each fit's final map (fit blocks only)", fontsize=11)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(figdir / "lag_profile.png", dpi=110)
    plt.close(fig)
    out.append("lag_profile.png")

    ev, tm = res["_ev"], res["_tm"]
    key = "chosen"
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.6))
    e = ev[key]
    pm = tm & (e["aj"] >= 0)
    for name, states, col in (("all pairs", None, "k"), ("still", (1,), "C0"), ("moving", (2, 3), "C1")):
        sel = pm if states is None else pm & np.isin(e["st_m"], states)
        x = np.sort(e["r"][sel])
        if x.size:
            axs[0].step(x, np.arange(1, x.size + 1) / x.size, where="post", color=col, label=f"{name} (n {x.size})")
    axs[0].axvline(res["params"]["within"], color="grey", ls="--", lw=1)
    axs[0].set_xlabel("matched-pair residual (in), Hungarian, gate 30 in")
    axs[0].set_ylabel("cumulative share")
    axs[0].set_title(f"Test blocks, chosen model ({res['adopted']})", fontsize=10)
    axs[0].legend(fontsize=8)
    for k2, col, lab in ((key, "C0", f"real, {res['adopted']}"), ("control", "C3", "negative control")):
        x = np.sort(np.minimum(ev[k2]["nd"][tm], 200.0))
        axs[1].step(x, np.arange(1, x.size + 1) / x.size, where="post", color=col, label=f"{lab} (n {x.size})")
    axs[1].axvline(res["params"]["within"], color="grey", ls="--", lw=1)
    axs[1].set_xlim(0, 200)
    axs[1].set_xlabel("distance to the nearest WISER animal outside the houses (in; capped at 200)")
    axs[1].set_ylabel("cumulative share of test detections")
    axs[1].set_title("Real vs negative control", fontsize=10)
    axs[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(figdir / "test_distances.png", dpi=110)
    plt.close(fig)
    out.append("test_distances.png")

    if res["C"].get("produced"):
        sup, grid, ep = res["C"]["_support"], res["C"]["_grid"], res["C"]["_episodes"]
        cs = res["params"]["fn_cell"]
        fig, ax = plt.subplots(figsize=(13, 6.8))
        if len(grid):
            x0, y0 = grid["cell_x0_in"].min(), grid["cell_y0_in"].min()
            nx, ny = int((grid["cell_x0_in"].max() - x0) / cs) + 1, int((grid["cell_y0_in"].max() - y0) / cs) + 1
            A = np.full((ny, nx), np.nan)
            for r in grid.itertuples():
                A[int((r.cell_y0_in - y0) / cs), int((r.cell_x0_in - x0) / cs)] = r.miss_seconds
            im = ax.imshow(A, origin="lower", extent=[x0, x0 + nx * cs, y0, y0 + ny * cs], cmap="magma_r", alpha=0.85)
            fig.colorbar(im, ax=ax, shrink=0.7, label=f"miss seconds per {cs:.0f}-in cell (all animals)")
        for poly in sup.polygons:
            p = np.asarray(poly)
            ax.plot(np.r_[p[:, 0], p[0, 0]], np.r_[p[:, 1], p[0, 1]], color="C0", lw=1.2)
        ax.plot([0, 480, 480, 0, 0], [0, 0, 240, 240, 0], color="k", lw=1)
        if len(ep):
            ax.scatter(ep["paddock_x_in"], ep["paddock_y_in"], s=6 + 4 * ep["duration_s"], facecolors="none",
                       edgecolors="C2", lw=1, label="miss episode (size ~ duration)")
            ax.legend(fontsize=8, loc="upper right")
        ax.set_xlim(-30, 510)
        ax.set_ylim(-30, 270)
        ax.set_aspect("equal")
        ax.set_xlabel("paddock x (in)")
        ax.set_ylabel("paddock y (in)")
        ax.set_title("C. Missed-rat candidates (WISER animal in CH01's support, no box within 20 in); blue = CH01 ground "
                     "support", fontsize=10)
        fig.tight_layout()
        fig.savefig(figdir / "fn_map.png", dpi=110)
        plt.close(fig)
        out.append("fn_map.png")
    return out


def f1(v, nd=1):
    return "–" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:.{nd}f}"


def pct(v):
    return "–" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{100 * v:.1f} %"


def write_report(res: dict, run: Path, rep_dir: Path, fig_dir: Path, figs: list[str], meta: dict,
                 superseded: dict | None = None) -> Path:
    prm = res["params"]
    acc, F, S = res["acceptance"], res["fits"], res["selection"]
    T = {k: {r["subset"]: r for r in rows} for k, rows in res["test"].items()}
    inp = res["inputs"]
    tr, co = F["translation"], F["control"]
    ti, si = F["inner_translation"], F["inner_similarity"]
    adopted = res["adopted"]
    ch = F["similarity"] if adopted == "similarity" else tr
    lsh = res.get("lag_shape", {})
    figrel = "../figures/" + FIG_SUB
    verdict = "**ACCEPTED**" if acc["accepted"] else "**NOT ACCEPTED**"
    blk = lambda b: ", ".join(map(str, b))  # noqa: E731

    def lagtxt(k):
        nb = lsh.get(k, {}).get("rel_cost_at_neighbours", {})
        return " / ".join(f"{100 * nb[x]:+.0f} %" for x in ("-0.5", "+0.5") if x in nb)

    def mapcell(f):
        m = f["map"]
        return f"({f1(m['dx_in'], 2)}, {f1(m['dy_in'], 2)})"

    L = ["# WISER-assisted YOLO, phase 0 — WISER → CH01 mapping, fixed-spot presence (sealed), suspected YOLO misses (2026c)",
         "",
         f"Driver `cv/cv_field/wiser_assist_p0.py`; plan `{PLAN}` (pre-registered, approved 2026-10-05; amendment 1 before "
         "results, amendments 2–3 after results, all dated in the plan); run "
         f"`{run.as_posix()}`; generated {datetime.now():%Y-%m-%d %H:%M}; code `{meta.get('git_commit')}`. Hour: CH01, "
         "field-PC 2026-09-06 21:00–22:00 (the step-2 hour; YOLO v5 detections from `cv_field_c1yolo_video_20261005_1848`). "
         "The agent did not look at any frame, video or figure; WISER positions are proposals, never boxes or labels; no "
         "training. This hour is now **WISER-touched** and cannot later serve as an independent CV-vs-WISER validation.", "",
         "## Verdict", "",
         f"- Mapping {verdict}. Rule fixed in the plan, judged once on the test blocks (2, 4, …, 12): the chosen model's "
         f"test median residual ≤ {prm['within']:.0f} in **and** the negative control's within-{prm['within']:.0f}-in share ≤ "
         f"half the chosen model's. Test median **{f1(acc['test_median_in'], 2)} in** (criterion 1 "
         f"{'met' if acc['criterion_1_test_median_le_14'] else 'not met'}); within-{prm['within']:.0f}-in share "
         f"**{pct(acc['real_within14_share'])}** vs control **{pct(acc['control_within14_share'])}** (criterion 2 "
         f"{'met' if acc['criterion_2_control_within14_le_half_real'] else 'not met'}).",
         f"- Model and lag chosen on the fit blocks only (amendment 2: inner fit {blk(S['inner_fit_blocks'])}, inner "
         f"validation {blk(S['inner_val_blocks'])}): inner-validation median residual translation "
         f"{f1(S['translation']['resid_median_in'], 2)} in vs similarity {f1(S['similarity']['resid_median_in'], 2)} in, gain "
         f"{pct(S['gain'])} → **{adopted}** (≥ {100 * prm['sim_gain']:.0f} % needed). Refitted on the six fit blocks: "
         f"**d = {mapcell(ch)} in**, θ = {f1(ch['map']['theta_deg'], 3)}°, s = {f1(ch['map']['scale'], 4)}"
         + (f" about c = ({f1(ch['map']['centre_wiser_in'][0])}, {f1(ch['map']['centre_wiser_in'][1])}) in (WISER frame)"
            if adopted == "similarity" else "") + f"; lag **L = {ch['L']:+.1f} s** (cost {lagtxt('similarity' if adopted == 'similarity' else 'translation')} "
         "at L − 0.5 / + 0.5 s). L is reported only, never written into a clock configuration (separate plan "
         "`2026-10-05-video-clock-sync.md`).", ""]
    if superseded:
        same = superseded.get("same_map")
        L += [f"- Before amendment 2 (run `{superseded['run']}`, superseded) the model was picked on the **test** blocks: "
              f"test median translation {f1(superseded['test_median_translation'], 2)} in vs similarity "
              f"{f1(superseded['test_median_similarity'], 2)} in (gain {pct(superseded['gain'])}) → "
              f"{superseded['adopted']}; acceptance was judged on the translation's test median "
              f"({f1(superseded['test_median_translation'], 2)} in; within-14 {pct(superseded['within_translation'])} vs "
              f"control {pct(superseded['within_control'])}) → {'accepted' if superseded['accepted'] else 'not accepted'}. "
              f"New selection: {adopted}; verdict **{'unchanged' if superseded['accepted'] == acc['accepted'] else 'CHANGED'}**"
              + ("; the final map and L equal the superseded run's" if same else
                 "; the final map differs from the superseded run's (B and C recomputed)")
              + (f"; B file byte-identical: {'yes' if superseded['b_file_identical'] else 'no'}" if "b_file_identical" in superseded else "")
              + (f"; C episodes identical (apart from the new `kind` column): {'yes' if superseded['c_episodes_identical'] else 'no'}"
                 if "c_episodes_identical" in superseded else "") + "."]
    if res["C"].get("produced"):
        cs_ = res["C"]["summary"]
        L += [f"- C: **{cs_['n_episodes']} suspected-miss episodes** (≥ {prm['min_ep']} consecutive seconds), "
              f"**{cs_['episode_seconds']} s** in episodes; all suspected-miss seconds {cs_['miss_seconds']} of "
              f"{cs_['animal_seconds_eligible_in_support']} eligible animal-seconds. Proposals for the user's eyes only — "
              "never boxes or labels.",
              "- B: produced and **sealed** (see B).", ""]
    else:
        L += [f"- B and C not produced: {res['B'].get('reason')}.", ""]
    ci = inp["correction_info"]
    L += ["## Inputs and exclusions", "",
          f"- Frames: {inp['frames_sampled']} sampled (one per whole second; the sampled PTS is at most "
          f"{inp['sampled_pts_offset_abs_max_s']:.3f} s from the second) of {inp['frames_total']}.",
          f"- A detections (sampled frames, conf ≥ {prm['conf_a']}): {inp['boxes_conf_ge_a_sampled']}; dropped "
          f"{inp['dropped_in_fixed_spot_cells']} with the centre in a fixed-spot cell (40-px cells with occupancy ≥ "
          f"{100 * prm['spot_occ']:.0f} %: {len(inp['spot_cells'])} cells), {inp['dropped_correction_flag']} for a correction "
          f"flag ≠ ok, {inp['dropped_outside_support']} outside CH01's verified calibration support; **used "
          f"{inp['a_detections_used']}**.",
          f"- Camera chain: `Corrections(\"2026c\").to_paddock(\"CH01\", t, uv, z_mm={prm['z_mm']:.0f}, units=\"in\")`; "
          f"night {ci.get('night')}, flag `{ci.get('flag')}`, samples {ci.get('used')}, night quality "
          f"{ci.get('night_quality')} {ci.get('night_quality_px')} px, rain 21:00–04:20 {ci.get('rain_mm_night')} mm.",
          "- WISER: default tracks SF07–SF12 of 2026-09-06 (V3 where the head IMU passes QC, B2 elsewhere), rows with "
          "`valid` and no `m_*` mask; no handling window falls in 20:58–23:02; fixes used per animal: "
          + ", ".join(f"{k} {v}" for k, v in inp["wiser_fixes_used"].items()) + ".", "",
          "## A. Mapping WISER → paddock", "",
          "Blocks of 5 min: odd = fit (1, 3, …, 11), even = test (2, 4, …, 12). The test blocks are used once, for the "
          "verdict and the reported test numbers.", "",
          f"### A1. Model and lag selection — fit blocks only (inner fit {blk(S['inner_fit_blocks'])}, inner validation "
          f"{blk(S['inner_val_blocks'])})", "",
          "| quantity | translation (d) | similarity (θ, s, d) |", "|---|---:|---:|",
          f"| d (in), inner fit | {mapcell(ti)} | {mapcell(si)} |",
          f"| θ (°), s | 0, 1 (fixed) | {f1(si['map']['theta_deg'], 3)}, {f1(si['map']['scale'], 4)} |",
          f"| lag L (s) | {ti['L']:+.1f} | {si['L']:+.1f} |",
          f"| iterations (converged) | {ti['n_iter']} ({ti['converged']}) | {si['n_iter']} ({si['converged']}) |",
          f"| inner-fit pairs | {ti['n_fit_pairs']} | {si['n_fit_pairs']} |"]
    a, b = S["translation"], S["similarity"]
    L += [f"| inner-validation detections | {a['n_detections']} | {b['n_detections']} |",
          f"| inner-validation matched pairs (share) | {a['n_pairs']} ({pct(a['matched_share'])}) | {b['n_pairs']} "
          f"({pct(b['matched_share'])}) |",
          f"| **inner-validation residual median / p90 (in)** | **{f1(a['resid_median_in'], 2)} / {f1(a['resid_p90_in'], 2)}** | "
          f"**{f1(b['resid_median_in'], 2)} / {f1(b['resid_p90_in'], 2)}** |",
          f"| inner-validation within-14-in share | {pct(a['within_share'])} | {pct(b['within_share'])} |",
          f"| gain of the similarity (rule ≥ {100 * prm['sim_gain']:.0f} %) | – | **{pct(S['gain'])} → {adopted}** |", "",
          "### A2–A4. Chosen model refitted on the six fit blocks; negative control; test blocks", "",
          f"| quantity | chosen: {adopted} (fit blocks 1–11 odd) | negative control: WISER + 1 h, translation |",
          "|---|---:|---:|",
          f"| d (in) | {mapcell(ch)} | {mapcell(co)} |",
          f"| θ (°), s | {f1(ch['map']['theta_deg'], 3)}, {f1(ch['map']['scale'], 4)} | 0, 1 (fixed) |",
          f"| lag L (s) | {ch['L']:+.1f} | {co['L']:+.1f} (relative to + 3600 s) |",
          f"| iterations (converged) | {ch['n_iter']} ({ch['converged']}) | {co['n_iter']} ({co['converged']}) |",
          f"| translation start: coarse best d (score) → refined d, L | ({f1(tr['coarse']['best'][0])}, {f1(tr['coarse']['best'][1])}) "
          f"({pct(tr['coarse']['best_score'])}) → {mapcell(tr)}, {tr['L']:+.1f} s | ({f1(co['coarse']['best'][0])}, "
          f"{f1(co['coarse']['best'][1])}) ({pct(co['coarse']['best_score'])}) |",
          f"| fit pairs | {ch['n_fit_pairs']} | {co['n_fit_pairs']} |"]
    a, c = T["chosen"]["all"], T["control"]["all"]
    k2 = "all (animals in houses counted for within-14)"
    L += [f"| test detections | {a['n_detections']} | {c['n_detections']} |",
          f"| test matched pairs (share of detections) | {a['n_pairs']} ({pct(a['matched_share'])}) | {c['n_pairs']} "
          f"({pct(c['matched_share'])}) |",
          f"| **test residual median / p90 (in)** | **{f1(a['resid_median_in'], 2)} / {f1(a['resid_p90_in'], 2)}** | "
          f"{f1(c['resid_median_in'], 2)} / {f1(c['resid_p90_in'], 2)} |",
          f"| **within-14-in share (all test detections)** | **{pct(a['within_share'])}** | **{pct(c['within_share'])}** |",
          f"| within-14-in share, animals in the houses also counted | {pct(T['chosen'][k2]['within_share'])} | "
          f"{pct(T['control'][k2]['within_share'])} |", "",
          f"The control's lag sits where its cost is flat (within 5 % of its minimum from "
          f"{lsh.get('control', {}).get('L_range_within_5pct_s', ['?', '?'])[0]} to "
          f"{lsh.get('control', {}).get('L_range_within_5pct_s', ['?', '?'])[1]} s), as expected without correspondence.", "",
          "By the WISER animal's head-IMU state (test blocks, chosen model; residuals by the matched animal's state, "
          "within-14 by the nearest animal's state):", "",
          "| subset | pairs | residual median (in) | residual p90 (in) | detections (nearest in this state) | within-14-in share |",
          "|---|---:|---:|---:|---:|---:|"]
    TT = T["chosen"]
    for name, _ in CLASSES:
        r = TT[name]
        L.append(f"| {name} | {r['n_pairs']} | {f1(r['resid_median_in'], 2)} | {f1(r['resid_p90_in'], 2)} | "
                 f"{r['n_detections']} | {pct(r['within_share'])} |")
    nst = TT["still"]["n_pairs"]
    L += ["", f"Only {nst} test pairs involve an IMU-still animal: at night the animals outside the houses were almost never "
          "IMU-still, so the still subset (free of timing error) is too small to separate timing error from spatial "
          "error here.", "",
          "Per animal (test blocks; pairs by the matched animal, within-14 by the nearest animal):", "",
          "| animal | pairs | residual median (in) | residual p90 (in) | detections nearest to it | within-14-in share |",
          "|---|---:|---:|---:|---:|---:|"]
    for lab in LABELS:
        if lab in TT:
            r = TT[lab]
            L.append(f"| {lab} | {r['n_pairs']} | {f1(r['resid_median_in'], 2)} | {f1(r['resid_p90_in'], 2)} | "
                     f"{r['n_detections']} | {pct(r['within_share'])} |")
    um = res.get("unmatched", {})
    L += ["", "Descriptive diagnostics (amendment 3, after results; nothing is decided on them):", "",
          f"- Of the {um.get('test_detections')} test detections, {um.get('no_outside_animal_within_14')} have no animal "
          f"outside the houses within 14 in; {um.get('of_which_animal_in_house_zone_within_14')} of those have an animal "
          "that WISER places inside a house zone (house rectangle + 14 in) within 14 in — boxes of animals at the house "
          "edges, which the plan's outside-the-houses rule leaves unmatched.",
          f"- Similarity scale s = {f1(ch['map']['scale'], 4) if adopted == 'similarity' else f1(si['map']['scale'], 4)}: "
          "a WISER displacement maps to a paddock displacement about "
          f"{f1(100 * (1 - (ch['map']['scale'] if adopted == 'similarity' else si['map']['scale'])), 1)} % shorter within "
          "CH01's view. Whether WISER's inch scale or the exploratory calibration is off is not determined here.",
          "- Test residuals by 80-in paddock x band (chosen model; signed = detection − mapped animal; a local mapping "
          "offset would show as a non-zero signed median):", "",
          "| x band (in) | detections | pairs | residual median / p90 (in) | signed dx / dy median (in) | within-14 | within-14 incl. houses |",
          "|---|---:|---:|---|---|---:|---:|"]
    for r in res.get("x_bands", []):
        L.append(f"| {r['x_band_in']}–{r['x_band_in'] + 80} | {r['n_detections']} | {r['n_pairs']} | "
                 f"{f1(r['resid_median_in'], 2)} / {f1(r['resid_p90_in'], 2)} | {f1(r['signed_dx_median_in'], 2)} / "
                 f"{f1(r['signed_dy_median_in'], 2)} | {pct(r['within_share'])} | {pct(r['within_share_incl_houses'])} |")
    ref = res.get("house2_reference", {})
    if "d_in" in ref:
        L += ["", f"- Reference only (not a criterion): house_2, which never moved, sits at paddock ({f1(ref['paddock_in'][0])}, "
              f"{f1(ref['paddock_in'][1])}) in in `cv/configs/field_layout.json` and at WISER ({f1(ref['wiser_in'][0])}, "
              f"{f1(ref['wiser_in'][1])}) in in `wiser_rois.json`, implying d ≈ ({f1(ref['d_in'][0])}, {f1(ref['d_in'][1])}) in; "
              f"the fitted translation d differs from it by "
              f"{f1(float(np.hypot(tr['map']['dx_in'] - ref['d_in'][0], tr['map']['dy_in'] - ref['d_in'][1])))} in "
              "(both reference positions are hand-placed rectangles, ± several inches)."]
    L += ["", "Figures (made by the driver; the agent did not look at them): "
          + ", ".join(f"[`{f}`]({figrel}/{f})" for f in figs if f != "fn_map.png") + ".", ""]
    L += ["## B. WISER presence at the fixed spots — sealed", "",
          "**Sealed until the user's verdicts in `fixed_spots_review.csv` are in.** "
          + ("The table was written only to the run folder (`wiser_spots.csv`); no B number appears in this report, the "
             "run log, the run's other files or the agent's messages. " if res["B"].get("produced") else
             f"Not produced: {res['B'].get('reason')}. ")
          + "Method (plan B): each spot's median pano centre (from `fixed_spots/fixed_spots.csv`) is mapped to paddock "
          "inches with `to_paddock` at the time of the spot's middle frame (z = 60 mm), then into the WISER frame by the "
          "inverse of the accepted map. Per minute of the hour: the spot is *on* if it has a box (conf ≥ 0.25) in ≥ 50 % of "
          "the minute's frames (the step-2 per-minute occupancy); per second, the distance from the spot to the nearest "
          "located tagged animal (all six, in or out of the houses) at second + L; the minute's distance is the median of "
          "those seconds; the minute's nearest animal is the most frequent per-second nearest one, with its share of "
          "`imu_state = still` seconds. Per spot: minutes on and off, of each those with the animal within 14 in and "
          "within 30 in, and with a *still* animal within 14 in (minute distance ≤ 14 in and still share ≥ 50 %); Spearman "
          "ρ between per-minute occupancy and the within-14-in indicator. A spot outside CH01's calibrated support gets NaN. "
          "**WISER can only add presence:** a minute with no tagged animal near a spot is not evidence that no rat is "
          "there (dropout, a failed tag, an untagged animal). The agreement table (user verdict vs WISER) is a separate "
          "later step, run only after the user's verdicts.", ""]
    if res["C"].get("produced"):
        cs_, sp = res["C"]["summary"], res["C"]["support"]
        ep, grid = res["C"]["_episodes"], res["C"]["_grid"]
        L += ["## C. Suspected YOLO misses (for the user's labelling; not a metric, never boxes)", "",
              f"- CH01 ground support: {sp['n_cells_mapped']} of the {prm['grid_px']}-px pixel cells map with all four "
              f"corners (to_paddock at {sp['time']}, z = 60 mm); area {sp['area_in2']:.0f} in², **{pct(sp['paddock_share'])} "
              "of the 480 × 240-in paddock** (outline in `support_polygon.json`).",
              f"- Animal-seconds located outside the houses: {cs_['animal_seconds_located_outside_houses']}; of those inside "
              f"the support: {cs_['animal_seconds_eligible_in_support']}; suspected-miss seconds (no box ≥ {prm['conf_c']} "
              f"within {prm['miss_r']:.0f} in in the sampled frame): **{cs_['miss_seconds']} ({pct(cs_['miss_share'])})**; "
              f"episodes ≥ {prm['min_ep']} s: **{cs_['n_episodes']}**, {cs_['episode_seconds']} s. (Step 2 found the YOLO "
              "count below the WISER outside-count in 69 % of 5-s bins.)",
              "- Per animal: " + "; ".join(f"{k} {v['episodes']} episodes / {v['episode_s']} s (suspected miss {v['miss_s']} of "
                                          f"{v['eligible_s']} s)" for k, v in cs_["by_animal"].items()) + "."]
        tc = cs_.get("top_cell")
        if tc:
            L += [f"- Where (descriptive, amendment 3): the 40-in cell x {tc['cell_x0_in']:.0f}–{tc['cell_x0_in'] + prm['fn_cell']:.0f}, "
                  f"y {tc['cell_y0_in']:.0f}–{tc['cell_y0_in'] + prm['fn_cell']:.0f} in holds {tc['miss_seconds']} suspected-miss "
                  f"seconds ({pct(tc['share_of_all_miss'])} of all; {pct(tc['miss_share'])} of its {tc['eligible']} eligible "
                  f"animal-seconds). The {tc['a_detections_all_blocks']} part-A detections that do fall in that cell match a "
                  f"WISER animal with median residual {f1(tc['a_resid_median_in'], 2)} in, so the mapping there is not off; "
                  "what hides or fails to box the animals there is for the user to judge. Top cells:", "",
                  "| cell x, y (in) | eligible animal-s | suspected-miss s | share | in episodes (s) |",
                  "|---|---:|---:|---:|---:|"]
            for r in grid.sort_values("miss_seconds", ascending=False).head(5).itertuples():
                L.append(f"| {r.cell_x0_in:.0f}–{r.cell_x0_in + prm['fn_cell']:.0f}, {r.cell_y0_in:.0f}–"
                         f"{r.cell_y0_in + prm['fn_cell']:.0f} | {r.eligible_animal_seconds} | {r.miss_seconds} | "
                         f"{pct(r.miss_share)} | {r.episode_seconds} |")
        L += ["", "Ten longest episodes (all in `fn_episodes.csv`; pano pixel = the nearest 40-px grid centre to the episode's "
              "median paddock position — a pointer for the user's eyes, not a box; *box frames* = share of the frames within "
              "± 0.5 s of each second that hold a box within 20 in — a flicker indicator):", "",
              "| # | start (field-PC, video nominal) | s | animal | paddock x, y (in) | pano u, v (px) | IMU state (still share) | box frames |",
              "|---:|---|---:|---|---|---|---|---:|"]
        for r in ep.sort_values(["duration_s", "start_sec"], ascending=[False, True]).head(10).itertuples():
            L.append(f"| {r.episode_id} | {r.start_t_pc[11:19]} | {r.duration_s} | {r.animal} | {r.paddock_x_in:.0f}, "
                     f"{r.paddock_y_in:.0f} | {r.pano_u}, {r.pano_v} | {r.imu_state} ({pct(r.still_share)}) | "
                     f"{pct(r.frames_with_box_within_20_share)} |")
        L += ["", "A suspected miss can also be occlusion (grass, a house roof), WISER error (≈ 3 in still, 4–7 in raw "
              "jitter) plus mapping error, an animal out of view near the support edge, or a box displaced > 20 in from "
              "the tag. Episodes are proposals for the user's eyes only: **never a box or a label — an occluded animal "
              "must not get a box.** "
              + (f"Map: [`fn_map.png`]({figrel}/fn_map.png)." if "fn_map.png" in figs else ""), ""]
    L += clip_section_md(run)
    L += ["## Definitions", "",
          "Units: paddock and WISER positions in **inches** (paddock = the 09-24 calibration frame, origin pole A0, "
          "480 × 240 in; WISER = the unverified native inch frame); pixels = upright pano pixels (7680 × 2160); times in "
          "seconds. $s \\in \\{0,\\dots,3599\\}$ = second of the hour after the file-name start; $k(s)$ = the frame with PTS "
          "nearest $s$; $i$ = a detection; $j$ = an animal; $\\mathbf p_i$ = paddock position of detection $i$; "
          "$\\mathbf w_j(t)$ = WISER position of animal $j$ at WISER time $t$; blocks $b(s)=\\lfloor s/300\\rfloor+1$.", "",
          "### Detection position ($\\mathbf p_i$)",
          "$$ \\mathbf p_i = \\mathrm{to\\_paddock}_{CH01}\\big(t_s,\\ ((x_1+x_2)/2,\\ (y_1+y_2)/2),\\ z=60\\,\\mathrm{mm}\\big) $$ "
          "**Text:** the YOLO box centre mapped through the per-night frame correction and the 09-24 calibration at the "
          "assumed height of a rat's back, evaluated at the whole second $t_s$ nearest the frame (the correction drifts by "
          "a fraction of a pixel per hour). Undefined outside CH01's verified support. Units: in.", "",
          "### WISER position at a query time ($\\mathbf w_j(t)$)",
          "$$ \\mathbf w_j(t) = \\mathbf w_{j,a} + \\frac{t-t_a}{t_b-t_a}(\\mathbf w_{j,b}-\\mathbf w_{j,a}),\\quad t_a\\le t<t_b,\\ "
          "t_b-t_a\\le 5\\,\\mathrm s $$ **Text:** linear interpolation of the default track between the two bracketing "
          "clean fixes (valid, no mask); not located if they are more than 5 s apart. IMU state = that of the nearer fix "
          "(0 unusable, 1 still, 2 active, 3 locomoting). *Outside the houses* = not inside either house rectangle of "
          "`wiser_rois.json` grown by 14 in. Units: in. A not-located animal is unknown, never absent.", "",
          "### Map and lag ($T$, $\\mathbf d$, $L$)",
          "$$ T(\\mathbf w) = s\\,R(\\theta)(\\mathbf w-\\mathbf c)+\\mathbf c+\\mathbf d,\\qquad \\text{translation: } \\theta=0,\\ s=1 "
          "\\Rightarrow T(\\mathbf w)=\\mathbf w+\\mathbf d $$ "
          "Detection $i$ in second $s$ is compared with $T(\\mathbf w_j(s+L))$. **Text:** $\\mathbf d$ (in) moves the WISER "
          "frame onto the paddock frame (the axes are known to align); $L$ (s) is the clock lag: $L>0$ means the video's "
          "nominal time (file-name start + PTS) runs $L$ s behind the WISER/field-PC clock (it also absorbs WISER's "
          "≈ 0.1–0.2 s fix latency). $\\mathbf c$ = the mean WISER position of the pairs of the translation fit the "
          "similarity starts from, so the similarity's $\\mathbf d$ is comparable with the translation's.", "",
          "### Coarse score ($G(\\mathbf d)$)",
          "$$ G(\\mathbf d)=\\frac{1}{|I_{fit}|}\\sum_{i\\in I_{fit}}\\mathbb 1\\Big[\\min_{j\\in J_{out}(s_i)}\\lVert \\mathbf p_i-"
          "\\mathbf w_j(s_i)-\\mathbf d\\rVert\\le 20\\Big] $$ on $\\mathbf d\\in\\bar{\\mathbf p}-\\bar{\\mathbf w}+\\{-100,-98,\\dots,100\\}^2$ "
          "**Text:** share of the fit's detections with an animal (outside the houses, at $L=0$) within 20 in; "
          "$\\bar{\\mathbf p}$ = mean of those detections, $\\bar{\\mathbf w}$ = mean WISER position of the outside animals over "
          "the fit's seconds. Only the starting point of the refinement. Range [0, 1].", "",
          "### Hungarian assignment and residual ($r_i$)",
          "$$ \\pi_s=\\arg\\min_{\\pi}\\sum_{(i,j)\\in\\pi}\\min(D_{ij},30),\\quad D_{ij}=\\lVert\\mathbf p_i-T(\\mathbf w_j(s+L))\\rVert,"
          "\\quad r_i=D_{i\\pi(i)}\\ \\text{if}\\ D_{i\\pi(i)}\\le 30 $$ **Text:** per second, the one-to-one matching of "
          "detections to animals outside the houses with the smallest total gated distance; pairs beyond the 30-in gate are "
          "dropped (the detection is unmatched). $r_i$ = matched-pair residual (in), truncated at 30 in by construction — "
          "read the median / p90 together with the matched share.", "",
          "### Lag cost ($C(L)$) and the fit",
          "$$ C(L)=\\frac{1}{|I_{fit}|}\\sum_{i\\in I_{fit}}\\rho_6\\big(\\min(r_i,30)\\big),\\quad \\rho_k(r)=\\begin{cases}r^2/2 & r\\le k\\\\ "
          "k(r-k/2) & r>k\\end{cases} $$ (unmatched $r_i=\\infty$ costs $\\rho_6(30)$), "
          "$$ \\hat{\\mathbf d}=\\arg\\min_{\\mathbf d}\\sum_{(i,j)}\\rho_6\\big(\\lVert\\mathbf p_i-\\mathbf w_j-\\mathbf d\\rVert\\big)\\ \\text{(IRLS)} $$ "
          "**Text:** from the coarse best $\\mathbf d$: choose $L$ on the 0.5-s grid in [−90, 90] s minimising $C(L)$ (ties → "
          "smallest $|L|$), match, re-fit $\\mathbf d$ by Huber least squares (k = 6 in ≈ the raw jitter, so jittery pairs "
          "count fully and outliers linearly), repeat until $\\mathbf d$ moves < 0.1 in; $L$ is re-chosen once at the final "
          "$\\mathbf d$. The similarity fit does the same with a weighted Umeyama similarity under Huber weights, starting "
          "from the translation fit on the same blocks. $I_{fit}$ = the detections of the blocks the fit may use. Units: "
          "$C$ in in².", "",
          "### Model selection (amendment 2)",
          "$$ g=\\frac{\\tilde r^{val}_{transl}-\\tilde r^{val}_{sim}}{\\tilde r^{val}_{transl}},\\qquad \\text{similarity chosen}\\iff g\\ge 0.10 $$ "
          "**Text:** both models (and their $L$) fitted on fit blocks 1, 5, 9; $\\tilde r^{val}$ = median matched residual on "
          "fit blocks 3, 7, 11. The chosen model is then refitted (with its $L$) on all six fit blocks. The test blocks "
          "play no part in the choice.", "",
          "### Test statistics",
          "$$ \\tilde r=\\operatorname{median}_{i\\in I_{test},\\,matched} r_i,\\quad r_{90}=P_{90}(r_i),\\quad "
          "f_{14}=\\frac{1}{|I_{test}|}\\sum_{i\\in I_{test}}\\mathbb 1\\Big[\\min_{j\\in J_{out}(s_i)}\\lVert\\mathbf p_i-"
          "T(\\mathbf w_j(s_i+L))\\rVert\\le 14\\Big] $$ **Text:** on the even blocks, once, with the chosen model: the median "
          "and 90th percentile of matched residuals (in) and the share of ALL test detections (denominator includes "
          "unmatched ones and seconds without any outside animal) with an animal within 14 in (nearest animal, no "
          "one-to-one constraint). By IMU state: residuals grouped by the matched animal's state, $f_{14}$ by the nearest "
          "animal's state (denominator = detections whose nearest animal is in that state). Signed residual by x band = "
          "$\\operatorname{median}(\\mathbf p_i-T(\\mathbf w_{\\pi(i)}))$ per axis. 14 in = twice the ≈ 7-in WISER jitter and the "
          "repo's minimum resolvable distance.", "",
          "### Negative control",
          "$$ \\mathbf w^{ctrl}_j(t)=\\mathbf w_j(t+3600\\,\\mathrm s) $$ **Text:** WISER from 22:00–23:00 placed on the "
          "21:00–22:00 frames and refitted identically (translation, six fit blocks, own coarse grid, $L$ grid relative to "
          "+3600 s). It keeps where the animals tend to be (the spatial density) but breaks the frame-by-frame "
          "correspondence; $f^{ctrl}_{14}$ measures how often a detection lands within 14 in of *some* animal by chance "
          "after a free fit.", "",
          "### Acceptance",
          "$$ \\text{accepted}\\iff \\tilde r_{chosen}\\le 14\\ \\wedge\\ f^{ctrl}_{14}\\le \\tfrac12 f_{14,chosen} $$ **Text:** "
          "fixed in the plan before any result; judged once on the test blocks.", "",
          "### B quantities (definitions only; values sealed)",
          "$$ \\mathrm{on}_m=\\mathbb 1[O_m\\ge 0.5],\\quad \\delta_m=\\operatorname{median}_{s\\in m}\\min_j\\lVert \\mathbf w^{spot}-"
          "\\mathbf w_j(s+L)\\rVert,\\quad \\mathrm{near}_{14,m}=\\mathbb 1[\\delta_m\\le 14],\\quad \\rho=\\mathrm{Spearman}(O_m,\\mathrm{near}_{14,m}) $$ "
          "**Text:** $O_m$ = the spot's step-2 occupancy in minute $m$ (share of the minute's frames with a box centre "
          "≥ 0.25 in the spot's cells); $\\mathbf w^{spot}=T^{-1}(\\mathbf p^{spot})$; the minimum runs over all located "
          "animals (in or out of houses); the still variant also needs the nearest animal's still share in the minute "
          "≥ 0.5. Units: in; $\\rho\\in[-1,1]$. $\\mathrm{near}_{14,m}=0$ means no *tagged* animal is near, not no rat.", "",
          "### C quantities",
          "$$ \\mathrm{miss}_{j,s}=\\mathbb 1\\big[j\\notin\\text{houses}\\ \\wedge\\ T(\\mathbf w_j(s+L))\\in\\mathcal S\\ \\wedge\\ "
          "\\min_{b\\in B_{k(s)}}\\lVert\\mathbf p_b-T(\\mathbf w_j(s+L))\\rVert>20\\big] $$ **Text:** a suspected miss: "
          "$\\mathcal S$ = CH01 ground support (union of the 40-px pixel cells whose four corners map, rasterised at 1 in); "
          "$B_{k(s)}$ = the sampled frame's boxes with conf ≥ 0.25 (fixed-spot boxes included). An episode = ≥ 3 "
          "consecutive suspected-miss seconds of one animal; its position = the median of $T(\\mathbf w_j)$ over its "
          "seconds; *box frames* = mean over its seconds of the share of frames within ± 0.5 s with a box within 20 in "
          "(0 = no frame of those seconds had one). Grid: suspected-miss seconds and eligible animal-seconds per 40-in "
          "paddock cell. Only tagged animals WISER locates can raise a suspected miss; WISER's silence never marks a "
          "frame or place as empty.", ""]
    L += ["## Caveats", "",
          "- One calm hour (rain 0.0 mm on night 09-06 per the correction table), one camera, six tagged animals; all "
          "numbers carry the WISER error (V3 still error ≈ 3 in, raw jitter 4–7 in), the calibration's exploratory error "
          "(cross-camera median 76 mm, p90 137 mm), the 60-mm height assumption (a box centre on a rat's flank or head is "
          "not at 60 mm) and the offset between a box centre and the tag on the animal.",
          "- WISER never creates a negative: a missing WISER animal (dropout, failed tag, untagged animal — e.g. the "
          "females from 09-11) does not mean no rat, so nothing here marks a frame, minute or place as empty.",
          "- The residual is truncated at the 30-in gate; the within-14-in share has no gate. YOLO false positives and "
          "duplicate boxes stay in the denominators (only fixed-spot cells are removed).",
          "- WISER positions are proposals (never boxes or labels). The lag $L$ is a fitted nuisance parameter here, not a "
          "clock measurement.", "",
          "## Outputs", "",
          f"Run folder `{run.as_posix()}`: `mapping.json` (selection, accepted map, d, L, θ, s, acceptance, fit histories, "
          "house_2 reference), `model_selection.csv` (inner validation), `pairs.csv.gz` (one row per A detection, all "
          "blocks with their role, chosen model: match, residual, nearest animal, IMU state), `residuals_test.csv` (test "
          "summaries of the chosen model and the control: all / IMU state / animal), `residuals_test_by_x.csv`, "
          "`control.json`, `lag_profiles.csv`, `run.json`, `run_log.txt`"
          + (", `support_polygon.json`, `fn_episodes.csv`, `fn_grid.csv`, `wiser_spots.csv` (**sealed**)" if res["C"].get("produced") else "")
          + f". Figures in `results/2026c/cv_field/figures/{FIG_SUB}/`. Pointer `{POINTER_NAME}`.", "",
          "## Rerun", "", "```", "C:/Python313/python.exe cv/cv_field/wiser_assist_p0.py --run", "```", ""]
    rep_dir.mkdir(parents=True, exist_ok=True)
    p = rep_dir / REPORT_NAME
    p.write_text("\n".join(L), encoding="utf-8")
    return p


# ----------------------------------------------------------------------------------------------- real run
def real_mapper():
    from frame_correction import Corrections
    C = Corrections(COHORT)

    def mapper(t, uv):
        return C.to_paddock(CAM, t, np.asarray(uv, float), z_mm=Params().z_mm, units="in")
    return mapper


def load_superseded(old: Path, new: Path, res: dict) -> dict | None:
    """The first run (model picked on the test blocks; superseded by amendment 2): its selection and verdict, and whether
    the new run reproduces its map, its sealed B file (sha256 only - the file is never read) and its C episodes."""
    try:
        m = json.loads((old / "mapping.json").read_text(encoding="utf-8"))
        rt = pd.read_csv(old / "residuals_test.csv")
    except (OSError, ValueError):
        return None
    row = lambda f: rt[(rt["fit"] == f) & (rt["subset"] == "all")].iloc[0]  # noqa: E731
    a = m["acceptance"]
    om, nm = m["accepted_map"], res["_chosen_fit"]["map"].as_dict()
    same = (all(abs(float(om[k]) - float(nm[k])) < 1e-6 for k in ("dx_in", "dy_in", "theta_deg", "scale"))
            and float(m["accepted_L_s"]) == float(res["_chosen_fit"]["L"]))
    out = {"run": old.as_posix(), "accepted": bool(a["accepted"]), "adopted": a.get("adopted_model"),
           "test_median_translation": float(row("translation")["resid_median_in"]),
           "test_median_similarity": float(row("similarity")["resid_median_in"]), "gain": float(a.get("similarity_gain", np.nan)),
           "within_translation": float(row("translation")["within_share"]),
           "within_similarity": float(row("similarity")["within_share"]), "within_control": float(row("control")["within_share"]),
           "map": om, "L_s": float(m["accepted_L_s"]), "same_map": bool(same)}
    if (old / "wiser_spots.csv").exists() and (new / "wiser_spots.csv").exists():
        out["b_file_identical"] = sha256(old / "wiser_spots.csv") == sha256(new / "wiser_spots.csv")
    if (old / "fn_episodes.csv").exists() and (new / "fn_episodes.csv").exists():
        e0 = pd.read_csv(old / "fn_episodes.csv")
        e1 = pd.read_csv(new / "fn_episodes.csv").drop(columns=["kind"], errors="ignore")
        out["c_episodes_identical"] = bool(e0.shape == e1.shape and e0.equals(e1[e0.columns]))
    return out


def run_real(step2: Path, out: Path | None) -> int:
    t0 = time.perf_counter()
    started = datetime.now().isoformat(timespec="seconds")
    prm = Params()
    if out is None:
        import output_paths as op
        out = op.run_dir(NAME, COHORT, make_figures=False)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    logf = open(out / "run_log.txt", "w", encoding="utf-8")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    log(f"run -> {out.as_posix()}")
    fr = pd.read_csv(step2 / "frames.csv.gz")
    det = pd.read_csv(step2 / "detections.csv.gz")
    cells = pd.read_csv(step2 / "fixed_spots" / "cells.csv.gz")
    spots = pd.read_csv(step2 / "fixed_spots" / "fixed_spots.csv")
    s2 = json.loads((step2 / "run.json").read_text(encoding="utf-8"))
    if not str(s2.get("video_name", "")).startswith("CH01_2026-09-06_21-00-00"):
        raise SystemExit(f"unexpected step-2 hour: {s2.get('video_name')}")
    track_data, tmeta = load_tracks_real(prm)
    houses = load_houses()
    res = run_pipeline(fr, det, cells, spots, track_data, houses, real_mapper(), prm, HOUR_START, out, log)
    import output_paths as op
    rep_dir = op.report_dir(COHORT, DIRECTION)
    fig_dir = op.figure_dir(COHORT, DIRECTION) / FIG_SUB
    figs = make_figures(res, fig_dir)
    rec = REPO.parent / "Field_2026_Social_Recording"
    meta = {"plan": PLAN, "driver": "cv/cv_field/wiser_assist_p0.py", "git_commit": git_commit(REPO),
            "recording_repo_commit": git_commit(rec), "started": started,
            "step2_run": step2.as_posix(), "video": s2.get("video"),
            "inputs_sha256": {n: sha256(step2 / n) for n in ("detections.csv.gz", "frames.csv.gz", "fixed_spots/fixed_spots.csv",
                                                             "fixed_spots/cells.csv.gz")},
            "frame_corrections_csv_sha256": sha256(REPO / "results" / COHORT / DIRECTION / "reports" / f"cv_field_frame_corrections_{COHORT}.csv"),
            "wiser_tracks": tmeta, "rois": ROIS.relative_to(REPO).as_posix(), "handling": HANDLING.relative_to(REPO).as_posix(),
            "versions": {"python": sys.version.split()[0], "numpy": np.__version__, "pandas": pd.__version__,
                         "scipy": __import__("scipy").__version__}}
    try:
        import landmark_guides
        cd = landmark_guides.calib_dir()
        meta["calibration_dir"] = cd.as_posix()
        meta["calibration_files_sha256"] = {n: sha256(cd / n) for n in ("camera_fit.npz", "ray_correction.json", "frame_correction.json")
                                            if (cd / n).exists()}
    except Exception as e:  # noqa: BLE001
        meta["calibration_dir_error"] = str(e)
    sup_info = load_superseded(SUPERSEDED_RUN, out, res) if SUPERSEDED_RUN.resolve() != out.resolve() else None
    rp = write_report(res, out, rep_dir, fig_dir, figs, meta, sup_info)
    runj = {**meta, "params": res["params"], "inputs": res["inputs"], "acceptance": res["acceptance"], "adopted": res["adopted"],
            "selection": res["selection"], "superseded": sup_info,
            "fits": res["fits"], "test_all": {k: v[0] for k, v in res["test"].items()},
            "B": {k: v for k, v in res["B"].items()},
            "C": {k: v for k, v in res["C"].items() if not k.startswith("_")},
            "report": rp.relative_to(REPO).as_posix(), "figures": [f"results/{COHORT}/{DIRECTION}/figures/{FIG_SUB}/{f}" for f in figs],
            "runtime_s": time.perf_counter() - t0}
    (out / "run.json").write_text(json.dumps(jsonable(runj), indent=2), encoding="utf-8")
    ptr = {"run_dir": out.resolve().as_posix(), "cohort": COHORT, "direction": DIRECTION, "analysis": "wiser_assist_p0",
           "driver": "cv/cv_field/wiser_assist_p0.py", "report": REPORT_NAME, "plan": PLAN, "step2_run": step2.as_posix(),
           "figures": f"results/{COHORT}/{DIRECTION}/figures/{FIG_SUB}/", "git_commit": meta["git_commit"],
           "accepted": res["acceptance"]["accepted"], "sealed_file": "wiser_spots.csv" if res["B"].get("produced") else None}
    (rep_dir / POINTER_NAME).write_text(json.dumps(ptr, indent=2) + "\n", encoding="utf-8")
    log(f"report -> {rp.as_posix()}; runtime {time.perf_counter() - t0:.0f} s")
    logf.close()
    return 0


# ----------------------------------------------------------------------------------------------- review clips (amendment 4)
CLIP_N, CLIP_PAD, CLIP_CAP, CLIP_FPS = 12, 5.0, 90.0, 20
HOTSPOT = (440.0, 480.0, 120.0, 160.0)               # paddock x0, x1, y0, y1 (in): the +x cell with the most misses
VERDICTS = ("visible_missed", "occluded", "not_there_wiser_wrong", "box_present", "unsure")
CLIP_NOTE = "WISER circles = position +/- ~14 in; absence of a box can be occlusion"   # Hershey fonts are ASCII-only
BLIND_LINE = ("Fill fixed_spots_review.csv (step-2 run, fixed_spots/) BEFORE opening these clips — the WISER circles "
              "reveal what part B tests.")
RED, CYAN, GREEN = (0, 0, 255), (255, 255, 0), (0, 255, 0)


def in_hotspot(x, y) -> bool:
    return bool(HOTSPOT[0] <= x < HOTSPOT[1] and HOTSPOT[2] <= y < HOTSPOT[3])


def select_clip_windows(ep: pd.DataFrame, n: int = CLIP_N, pad: float = CLIP_PAD, cap: float = CLIP_CAP,
                        n_sec: int = 3600) -> list[dict]:
    """Episodes ranked by duration (ties -> earlier start); window = [start - pad, end + pad] capped at `cap` s from its
    start (seconds of the hour, end exclusive); an episode whose window overlaps a chosen one is skipped; stop at n."""
    order = ep.sort_values(["duration_s", "start_sec", "episode_id"], ascending=[False, True, True])
    taken = []
    for r in order.itertuples():
        w0 = max(0.0, float(r.start_sec) - pad)
        w1 = min(float(n_sec), float(r.end_sec) + pad, w0 + cap)
        if any(w0 < t["w1"] and t["w0"] < w1 for t in taken):
            continue
        cov = ep[(ep["start_sec"] < w1) & (ep["end_sec"] + 1 > w0)]
        taken.append({"k": len(taken) + 1, "episode_id": int(r.episode_id), "animal": r.animal, "w0": w0, "w1": w1,
                      "episode_start_sec": int(r.start_sec), "episode_end_sec": int(r.end_sec),
                      "episode_duration_s": int(r.duration_s), "start_t_pc": str(r.start_t_pc),
                      "paddock_x_in": float(r.paddock_x_in), "paddock_y_in": float(r.paddock_y_in),
                      "pano_u": int(r.pano_u), "pano_v": int(r.pano_v),
                      "hotspot": in_hotspot(float(r.paddock_x_in), float(r.paddock_y_in)),
                      "episodes_covered": [int(v) for v in cov["episode_id"]],
                      "animals_covered": sorted(set(cov["animal"]))})
        if len(taken) == n:
            break
    return taken


def invert_mapper(fwd, P: np.ndarray, uv0: np.ndarray, tol: float = 0.02, max_it: int = 30, h: float = 1.0,
                  max_step: float = 300.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Numeric inverse of a pixel -> paddock map: Newton on the pixel with a finite-difference Jacobian (forward
    differences, backward where the forward step leaves the support). fwd(uv (n, 2)) -> paddock (n, 2), NaN where
    unsupported. -> (uv, J = d paddock / d uv at uv (n, 2, 2), round-trip error in paddock units); uv NaN where Newton
    fails or the round trip exceeds 1 in."""
    P = np.asarray(P, float).reshape(-1, 2)
    uv = np.asarray(uv0, float).reshape(-1, 2).copy()
    n = len(P)
    J = np.full((n, 2, 2), np.nan)
    act = np.isfinite(P).all(1) & np.isfinite(uv).all(1)

    def jac(idx, f0):
        Jm = np.full((len(idx), 2, 2), np.nan)
        for c, e in ((0, np.array([h, 0.0])), (1, np.array([0.0, h]))):
            fp = fwd(uv[idx] + e)
            bad = ~np.isfinite(fp).all(1)
            if bad.any():
                fp[bad] = 2 * f0[bad] - fwd(uv[idx][bad] - e)
            Jm[:, :, c] = (fp - f0) / h
        return Jm

    for _ in range(max_it):
        idx = np.flatnonzero(act)
        if not idx.size:
            break
        f0 = fwd(uv[idx])
        lost = ~np.isfinite(f0).all(1)
        act[idx[lost]] = False
        idx, f0 = idx[~lost], f0[~lost]
        if not idx.size:
            break
        r = f0 - P[idx]
        done = np.hypot(r[:, 0], r[:, 1]) < tol
        Jm = jac(idx, f0)
        J[idx] = Jm
        act[idx[done]] = False
        go = ~done & np.isfinite(Jm).all((1, 2))
        act[idx[~done & ~go]] = False
        if not go.any():
            continue
        Jg, rg = Jm[go], r[go]
        det = Jg[:, 0, 0] * Jg[:, 1, 1] - Jg[:, 0, 1] * Jg[:, 1, 0]
        det = np.where(np.abs(det) < 1e-12, np.nan, det)
        du = -(Jg[:, 1, 1] * rg[:, 0] - Jg[:, 0, 1] * rg[:, 1]) / det
        dv = -(-Jg[:, 1, 0] * rg[:, 0] + Jg[:, 0, 0] * rg[:, 1]) / det
        step = np.stack([du, dv], 1)
        sn = np.hypot(step[:, 0], step[:, 1])
        step *= np.minimum(1.0, max_step / np.maximum(sn, 1e-12))[:, None]
        bad = ~np.isfinite(step).all(1)
        act[idx[go][bad]] = False
        uv[idx[go][~bad]] += step[~bad]
    f = np.full((n, 2), np.nan)
    fin = np.isfinite(uv).all(1)
    if fin.any():
        f[fin] = fwd(uv[fin])
    err = np.hypot(f[:, 0] - P[:, 0], f[:, 1] - P[:, 1])
    fail = ~np.isfinite(err) | (err > 1.0)
    uv[fail] = np.nan
    J[fail] = np.nan
    return uv, J, err


def clip_overlays(frames: pd.DataFrame, boxes: pd.DataFrame, tracks: Tracks, houses, m: Map, L: float, sup: Support,
                  mapper, hour_start: datetime, prm: Params) -> dict:
    """Per frame of a clip: every animal's WISER -> paddock -> pixel (+ local 14-in ellipse), its house-zone flag and
    status, and its distance to the nearest mapped YOLO box (conf >= conf_c). frames: frame, pts_s; boxes: frame, x1..conf."""
    pts = frames["pts_s"].to_numpy(float)
    n, J = len(pts), len(tracks.labels)
    X, S, ok = tracks.at(pts + L)
    house = in_houses(X, houses, prm.house_buf)
    P = m.fwd(X.reshape(-1, 2)).reshape(X.shape)
    insup = sup.contains(P) & ok
    uv = np.full((n, J, 2), np.nan)
    Jm = np.full((n, J, 2, 2), np.nan)
    err = np.full((n, J), np.nan)
    sec = np.floor(pts + 0.5).astype(int)
    for s in np.unique(sec):
        rows = np.flatnonzero(sec == s)
        fi, fj = np.nonzero(insup[rows])
        if not fi.size:
            continue
        t = hour_start + timedelta(seconds=int(s))

        def fwd(q, t=t):
            p, info = mapper(t, q)
            return np.full((len(q), 2), np.nan) if p is None or info.get("flag") != "ok" else np.asarray(p, float).reshape(-1, 2)

        tgt = P[rows[fi], fj]
        u0, _ = sup.nearest_px(tgt)
        u_, J_, e_ = invert_mapper(fwd, tgt, u0.astype(float))
        uv[rows[fi], fj], Jm[rows[fi], fj], err[rows[fi], fj] = u_, J_, e_
    status = np.where(~ok, "not located", np.where(~insup, "out of view",
                      np.where(np.isfinite(uv).all(2), "ok", "inverse failed"))).astype(object)
    b = boxes[boxes["conf"] >= prm.conf_c].copy()
    b["cx"], b["cy"] = (b["x1"] + b["x2"]) / 2, (b["y1"] + b["y2"]) / 2
    fmap = pd.Series(np.arange(n), index=frames["frame"].to_numpy())
    b["row"] = b["frame"].map(fmap)
    b["win"] = np.floor(b["pts_s"].to_numpy(float) + 0.5).astype(int) if "pts_s" in b else sec[b["row"].to_numpy()]
    bxy, _, _ = map_by_window(b, mapper, hour_start) if len(b) else (np.zeros((0, 2)), None, None)
    b["px"], b["py"] = bxy[:, 0], bxy[:, 1]
    nbd = np.full((n, J), np.inf)
    by_row = {int(r): g for r, g in b.groupby("row")}
    for r, g in by_row.items():
        q = g[["px", "py"]].to_numpy(float)
        q = q[np.isfinite(q).all(1)]
        if len(q):
            D = np.hypot(P[r, :, 0][:, None] - q[None, :, 0], P[r, :, 1][:, None] - q[None, :, 1])
            nbd[r] = np.where(ok[r], D.min(1), np.inf)
    return {"X": X, "P": P, "ok": ok, "house": house, "insup": insup, "uv": uv, "J": Jm, "err": err, "status": status,
            "nbd": nbd, "boxes": {int(r): g[["x1", "y1", "x2", "y2", "conf"]].to_numpy(float) for r, g in by_row.items()},
            "n_boxes": np.array([len(by_row[r]) if r in by_row else 0 for r in range(n)])}


def crop_track(uv_e: np.ndarray, fallback: tuple[float, float], n_med: int, W: int, H: int, cw: int, ch: int) -> np.ndarray:
    """Crop origin per frame: the episode animal's pixel, gaps interpolated (edges held, all-NaN -> fallback), running
    median over n_med frames (centred), crop clamped to the pano. -> (n, 2) int x0, y0."""
    s = pd.DataFrame(uv_e, columns=["u", "v"])
    if s.notna().all(axis=1).sum() == 0:
        s["u"], s["v"] = float(fallback[0]), float(fallback[1])
    s = s.interpolate(limit_direction="both")
    s = s.rolling(n_med, center=True, min_periods=1).median()
    x0 = np.clip(np.round(s["u"].to_numpy() - cw / 2), 0, W - cw).astype(int)
    y0 = np.clip(np.round(s["v"].to_numpy() - ch / 2), 0, H - ch).astype(int)
    return np.stack([x0, y0], 1)


def _poly(img, pts, color, thick, dashed):
    import cv2
    p = np.round(pts).astype(np.int32)
    if not dashed:
        cv2.polylines(img, [p.reshape(-1, 1, 2)], True, color, thick, cv2.LINE_AA)
        return
    for i in range(0, len(p), 2):
        cv2.line(img, tuple(p[i]), tuple(p[(i + 1) % len(p)]), color, thick, cv2.LINE_AA)


def draw_view(img, ov: dict, r: int, labels, ep_j: int, scale: float, off: tuple[int, int], thick_box: int,
              thick_w: int, fs: float) -> None:
    """Boxes (green, conf) and WISER ellipses (14 in projected through the local Jacobian) on one view; view px =
    (pano px - off) * scale."""
    import cv2
    ox, oy = off
    for x1, y1, x2, y2, c in ov["boxes"].get(r, np.zeros((0, 5))):
        a, b, cc, d = int(round((x1 - ox) * scale)), int(round((y1 - oy) * scale)), int(round((x2 - ox) * scale)), int(round((y2 - oy) * scale))
        cv2.rectangle(img, (a, b), (cc, d), GREEN, thick_box)
        cv2.putText(img, f"{c:.2f}", (a, max(12, b - 4)), cv2.FONT_HERSHEY_SIMPLEX, fs * 0.8, GREEN, 1, cv2.LINE_AA)
    phi = np.linspace(0, 2 * np.pi, 33)[:-1]
    circ = 14.0 * np.stack([np.cos(phi), np.sin(phi)], 1)
    for j, lab in enumerate(labels):
        if ov["status"][r, j] != "ok":
            continue
        Jm = ov["J"][r, j]
        try:
            Ji = np.linalg.inv(Jm)
        except np.linalg.LinAlgError:
            continue
        e = ov["uv"][r, j] + circ @ Ji.T
        col = RED if j == ep_j else CYAN
        dim = bool(ov["house"][r, j])
        if dim:
            col = tuple(int(0.55 * v) for v in col)
        _poly(img, (e - [ox, oy]) * scale, col, thick_w, dim)
        u, v = (ov["uv"][r, j] - [ox, oy]) * scale
        cv2.putText(img, lab + (" (house)" if dim else ""), (int(u) + 6, int(v) - 6), cv2.FONT_HERSHEY_SIMPLEX, fs, col, 2, cv2.LINE_AA)


def compose_frame(img: np.ndarray, ov: dict, r: int, x0y0, labels, ep_j: int, clip: dict, t: datetime, fidx,
                  mapdesc: str) -> np.ndarray:
    """Canvas (W/2 x H): top = whole pano at 1/2; bottom left = native (W/4 x H/2) crop at x0y0; bottom right = text."""
    import cv2
    H, W = img.shape[:2]
    cw, ch = W // 4, H // 2
    canvas = np.zeros((H, W // 2, 3), np.uint8)
    top = cv2.resize(img, (W // 2, H // 2), interpolation=cv2.INTER_AREA)
    k = H / 2160.0
    draw_view(top, ov, r, labels, ep_j, 0.5, (0, 0), 1, 2, max(0.35, 0.7 * k))
    x0, y0 = int(x0y0[0]), int(x0y0[1])
    crop = np.ascontiguousarray(img[y0:y0 + ch, x0:x0 + cw])
    draw_view(crop, ov, r, labels, ep_j, 1.0, (x0, y0), 2, 2, max(0.35, 0.8 * k))
    cv2.rectangle(top, (x0 // 2, y0 // 2), ((x0 + cw) // 2, (y0 + ch) // 2), (255, 255, 255), 1)
    canvas[:H // 2] = top
    canvas[H // 2:, :cw] = crop
    panel = np.full((ch, W // 2 - cw, 3), 24, np.uint8)
    fs, lh, y = 1.0 * k, int(46 * k), int(50 * k)

    def put(txt, col=(235, 235, 235), s=1.0, th=2):
        nonlocal y
        cv2.putText(panel, txt, (int(24 * k), y), cv2.FONT_HERSHEY_SIMPLEX, fs * s, col, max(1, int(th * k + 0.5)), cv2.LINE_AA)
        y += int(lh * s)

    put(f"CH01  {t:%Y-%m-%d %H:%M:%S}.{t.microsecond // 1000:03d} field-PC   frame {fidx}")
    put(f"clip {clip['k']}   episode {clip['episode_id']}   {clip['animal']}", RED)
    put("SUSPECTED MISS (WISER proposal, not a box)", RED)
    s0, s1 = clip["episode_start_sec"], clip["episode_end_sec"]
    tt = (t - HOUR_START).total_seconds()
    phase = "inside episode" if s0 - 0.5 <= tt < s1 + 0.5 else ("before episode" if tt < s0 else "after episode")
    put(f"episode {fmt_hms(s0)} -> {fmt_hms(s1)} ({clip['episode_duration_s']} s)   now: {phase}", (200, 200, 200), 0.8)
    put(f"YOLO boxes (conf >= 0.25): {int(ov['n_boxes'][r])}", GREEN)
    y += int(10 * k)
    put("animal   zone             nearest YOLO box", (200, 200, 200), 0.85)
    for j, lab in enumerate(labels):
        st = ov["status"][r, j]
        zone = "house zone" if ov["house"][r, j] else "outside house"
        if st == "not located":
            txt = f"{lab}    not located (WISER)"
        elif st == "out of view":
            txt = f"{lab}    {zone:<16} out of view"
        else:
            d = ov["nbd"][r, j]
            dist = f"{d:5.1f} in" if np.isfinite(d) else "no box mapped"
            txt = f"{lab}    {zone:<16} {dist}" + ("   (no pixel: inverse failed)" if st == "inverse failed" else "")
        col = RED if j == ep_j else CYAN
        if ov["house"][r, j]:
            col = tuple(int(0.6 * v) for v in col)
        put(txt, col, 0.85)
    y = ch - int(130 * k)
    put(CLIP_NOTE, (255, 255, 255), 0.7, 1)
    put(mapdesc, (170, 170, 170), 0.6, 1)
    put("red = episode animal, cyan = others, dim/dashed = in a house zone; green = YOLO v5 boxes", (170, 170, 170), 0.6, 1)
    canvas[H // 2:, cw:] = panel
    return canvas


def fmt_hms(sec: float) -> str:
    return (HOUR_START + timedelta(seconds=float(sec))).strftime("%H:%M:%S")


def render_clip(video: Path, clip: dict, frames: pd.DataFrame, det: pd.DataFrame, tracks: Tracks, houses, m: Map, L: float,
                sup: Support, mapper, hour_start: datetime, prm: Params, out_path: Path, ff: str, mapdesc: str,
                fps: int = CLIP_FPS, encoder: str = "libx264") -> dict:
    """Decode every frame of [w0, w1) (PyAV, as step 2), draw, encode H.264 at fps. Returns stats."""
    import c1_yolo_video_test as cvt
    t0 = time.perf_counter()
    p0, p1 = clip["w0"], clip["w1"]
    fsel = frames[(frames["pts_s"] >= p0 - 1e-6) & (frames["pts_s"] < p1 - 1e-6)].reset_index(drop=True)
    dsel = det[det["frame"].isin(fsel["frame"]) & (det["conf"] >= prm.conf_c)]
    ov = clip_overlays(fsel, dsel, tracks, houses, m, L, sup, mapper, hour_start, prm)
    labels = tracks.labels
    ep_j = labels.index(clip["animal"])
    W, H = prm.width, prm.height
    org = crop_track(ov["uv"][:, ep_j], (clip["pano_u"], clip["pano_v"]), fps, W, H, W // 4, H // 2)
    want = {cvt.pts_key(v): i for i, v in enumerate(fsel["pts_s"])}
    cw, chh = W // 2, H
    enc = subprocess.Popen([ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
                            "-s", f"{cw}x{chh}", "-r", str(fps), "-i", "-", "-c:v", encoder, "-preset", "veryfast",
                            "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out_path)],
                           stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    n_w, n_un = 0, 0
    src = cvt.AvFrames(video, start_pts=p0, end_pts=p1)
    for pts, img in src:
        if not np.isfinite(pts) or pts < p0 - 1e-6:
            continue
        if pts >= p1 - 1e-6:
            break
        r = want.get(cvt.pts_key(pts))
        if r is None:
            n_un += 1
            continue
        t = hour_start + timedelta(seconds=float(pts))
        can = compose_frame(np.ascontiguousarray(img), ov, r, org[r], labels, ep_j, clip, t, int(fsel.loc[r, "frame"]), mapdesc)
        enc.stdin.write(can.tobytes())
        n_w += 1
    enc.stdin.close()
    enc.wait()
    err = enc.stderr.read().decode(errors="replace")[-300:]
    st = ov["status"]
    e = ov["err"][np.isfinite(ov["err"]) & (st == "ok")]
    return {"frames_expected": int(len(fsel)), "frames_written": n_w, "frames_unmatched_pts": n_un,
            "packet_errors": len(src.packet_errors), "encoder_rc": enc.returncode, "encoder_err": err,
            "bytes": out_path.stat().st_size if out_path.is_file() else 0,
            "animal_frames_ok": int((st == "ok").sum()), "animal_frames_out_of_view": int((st == "out of view").sum()),
            "animal_frames_inverse_failed": int((st == "inverse failed").sum()),
            "animal_frames_not_located": int((st == "not located").sum()),
            "episode_animal_frames_ok": int((st[:, ep_j] == "ok").sum()),
            "inverse_roundtrip_max_in": float(e.max()) if e.size else float("nan"),
            "inverse_roundtrip_p99_in": q(e, 99), "render_s": round(time.perf_counter() - t0, 1)}


def probe_frames(ffprobe: str, path: Path) -> int:
    o = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                        "stream=nb_read_packets", "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout.strip()
    try:
        return int(o.split(",")[0])
    except ValueError:
        return -1


CLIP_MARK0, CLIP_MARK1 = "<!-- review-clips:start -->", "<!-- review-clips:end -->"


def clip_section_md(run: Path) -> list[str]:
    """Report section for the amendment-4 review clips of `run` ([] if none rendered)."""
    cdir = run / "review_clips"
    if not (cdir / "clips.csv").exists() or not (cdir / "clips_summary.json").exists():
        return []
    c = pd.read_csv(cdir / "clips.csv")
    s = json.loads((cdir / "clips_summary.json").read_text(encoding="utf-8"))
    L = [CLIP_MARK0, "## Review clips of the suspected misses (amendment 4, after results, user request)", "",
         f"{s['n_clips']} clips chosen by rule only ({s['rule']}): **{s['n_hotspot']} in the +x hotspot cell** (paddock "
         f"x 440–480, y 120–160 in, by the episode's median position), **{s['n_elsewhere']} elsewhere**. Every frame of each "
         f"window, decoded with PyAV as in step 2 (pixel-identical to `grab_frames`), {s['fps']} fps H.264, canvas "
         f"{s['canvas'][0]} × {s['canvas'][1]}: top = whole pano at ½; bottom left = native 1920 × 1080 crop following the "
         "episode animal (1-s running median, clamped); bottom right = frame time, episode, per-animal house zone and "
         "distance to the nearest YOLO box, YOLO count. YOLO boxes (cached, conf ≥ 0.25) green; WISER animals SF07–SF12 "
         "projected with the accepted map and a Newton inverse of `to_paddock` (round trip ≤ 1 in, else not drawn), circle "
         "= 14 in projected through the local Jacobian; episode animal red, others cyan, house-zone animals dimmed and "
         "dashed, outside CH01's support \"out of view\". Burned-in: \"" + CLIP_NOTE + "\". "
         f"Frames written {s['frames_total']}; all frame checks (written = expected = ffprobe) **{s['all_frame_checks']}**; "
         f"render {s['runtime_s'] / 60:.1f} min. The agent did not look at any frame. Index "
         "`review_clips/index.html` (it asks the user to fill `fixed_spots_review.csv` first, since the WISER circles "
         "reveal what part B tests); verdicts in `review_clips/review_template.csv` (visible_missed / occluded / "
         "not_there_wiser_wrong / box_present / unsure).", "",
         "Definitions (clips): pixel of a WISER animal $\\hat{\\mathbf u}$ solves $F_t(\\hat{\\mathbf u})=T(\\mathbf w_j(t+L))$ by Newton, "
         "$F_t$ = `to_paddock` at the frame's whole second, $J=\\partial F_t/\\partial\\mathbf u$ by 1-px finite differences, "
         "started at the nearest mapped 40-px grid centre; kept only if the round trip $e=\\lVert F_t(\\hat{\\mathbf u})-T(\\mathbf w_j)\\rVert"
         "\\le 1$ in. **Text:** where WISER says the animal is, in pano pixels. Circle "
         "$\\{\\hat{\\mathbf u}+J^{-1}(14\\cos\\phi,\\,14\\sin\\phi)\\}$ = the 14-in ring around that position seen through the "
         "local camera geometry (an ellipse in pixels). Crop centre = running median of the episode animal's "
         "$\\hat{\\mathbf u}$ over 20 frames (≈ 1 s; gaps interpolated). Panel distance = $\\min_b\\lVert\\mathbf p_b-"
         "T(\\mathbf w_j)\\rVert$ over that frame's mapped boxes ≥ 0.25 (in). Hotspot = the episode's median paddock "
         "position in x ∈ [440, 480), y ∈ [120, 160) in. Window = [start − 5, end + 5] s capped at 90 s from its start.", "",
         "| # | clip | episode, animal | window (field-PC) | s | paddock x, y (in) | pano u, v (px) | hotspot | frames (ffprobe) | inverse max (in) |",
         "|---:|---|---|---|---:|---|---|---|---|---:|"]
    for r in c.itertuples():
        L.append(f"| {r.k} | `{r.file}` | {r.episode_id} {r.animal} (covers {str(r.episodes_covered).replace(';', ', ')}) | "
                 f"{r.window} | {r.duration_s:g} | {r.paddock_x_in:.0f}, {r.paddock_y_in:.0f} | {r.pano_u}, {r.pano_v} | "
                 f"{r.hotspot} | {r.frames_written} / {r.frames_expected} ({r.frames_probe}) | {r.inverse_roundtrip_max_in:.2f} |")
    L += ["", CLIP_MARK1, ""]
    return L


def update_report_clips(run: Path, report: Path) -> bool:
    """Put the clip section into the phase-0 report (replace between the markers, else before ## Definitions)."""
    if not report.exists() or run.as_posix() not in report.read_text(encoding="utf-8"):
        return False
    t = report.read_text(encoding="utf-8")
    sec = "\n".join(clip_section_md(run))
    if CLIP_MARK0 in t and CLIP_MARK1 in t:
        a, b = t.index(CLIP_MARK0), t.index(CLIP_MARK1) + len(CLIP_MARK1)
        t = t[:a] + sec.rstrip("\n") + t[b:]
    else:
        k = t.index("## Definitions")
        t = t[:k] + sec + "\n" + t[k:]
    report.write_text(t, encoding="utf-8")
    return True


def write_clip_index(cdir: Path, rows: list[dict], meta: dict) -> None:
    import html as _h
    cols = ["file", "k", "episode_id", "animal", "window", "duration_s", "episode_duration_s", "episodes_covered",
            "paddock_xy_in", "pano_uv", "hotspot", "frames"]
    H = ["<!doctype html><html><head><meta charset='utf-8'><title>CH01 suspected-miss clips</title><style>"
         "body{font-family:sans-serif;margin:16px;max-width:1950px}table{border-collapse:collapse;font-size:13px}"
         "td,th{border:1px solid #999;padding:3px 6px}video{width:100%;max-width:1920px}h2{margin-top:28px}"
         ".warn{font-size:20px;font-weight:bold;color:#b00;border:2px solid #b00;padding:8px}</style></head><body>",
         f"<p class='warn'>{_h.escape(BLIND_LINE)}</p>",
         "<h1>Cohort-3 CH01 2026-09-06 21:00–22:00 — WISER-flagged suspected YOLO misses (phase 0 part C)</h1>",
         "<p>Each clip: a tagged animal (WISER) inside CH01's view with no YOLO box (conf &ge; 0.25) within 20 in for "
         "&ge; 3 s. Chosen by rule only (longest first, ± 5 s, max 90 s, no overlap, 12 clips; plan amendment 4); the "
         "agent did not look at any frame. Top: whole panorama; bottom left: native crop following the episode animal; "
         "bottom right: per-animal status. <b>Red</b> = episode animal, <b>cyan</b> = other tagged animals, dimmed "
         "dashed = WISER places it in a house zone; circle = WISER position ± ~14 in (projected locally); green = YOLO "
         "v5 boxes. " + _h.escape(CLIP_NOTE) + ". WISER circles are proposals, never boxes or labels; an occluded animal "
         "must not get a box. Animals without a WISER tag (none before 09-11) would not be circled.</p>",
         "<p>Verdicts go in <code>review_template.csv</code> (one row per episode in a clip): "
         + ", ".join(f"<code>{v}</code>" for v in VERDICTS) + ".</p>",
         f"<p>Map: {_h.escape(meta.get('mapdesc', ''))}. Hotspot cell (paddock x 440–480, y 120–160 in): "
         f"{meta.get('n_hotspot')} clips; elsewhere: {meta.get('n_elsewhere')}.</p><table><tr>"]
    H += [f"<th>{c}</th>" for c in cols] + ["</tr>"]
    for r in rows:
        H.append("<tr>" + "".join(f"<td>{_h.escape(str(r.get(c, '')))}</td>" for c in cols) + "</tr>")
    H.append("</table>")
    for r in rows:
        H.append(f"<h2>{r['k']}. {_h.escape(r['file'])} — episode {r['episode_id']} {_h.escape(r['animal'])}, "
                 f"{_h.escape(r['window'])}{' (hotspot)' if r['hotspot'] == 'yes' else ''}</h2>"
                 f"<video controls preload='metadata' src='{_h.escape(r['file'])}'></video>")
    H.append("</body></html>")
    (cdir / "index.html").write_text("\n".join(H), encoding="utf-8")


def run_clips(run: Path, step2: Path = STEP2_RUN, only: int | None = None) -> int:
    """Amendment 4: render the review clips of run's suspected-miss episodes into <run>/review_clips/."""
    import c1_yolo_video_test as cvt
    t_start = time.perf_counter()
    prm = Params()
    cdir = run / "review_clips"
    cdir.mkdir(exist_ok=True)
    logf = open(cdir / "clips_log.txt", "a", encoding="utf-8")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    mj = json.loads((run / "mapping.json").read_text(encoding="utf-8"))
    am = mj["accepted_map"]
    m = Map(float(am["dx_in"]), float(am["dy_in"]), float(np.radians(am["theta_deg"])), float(am["scale"]),
            float(am["centre_wiser_in"][0]), float(am["centre_wiser_in"][1]))
    L = float(mj["accepted_L_s"])
    mapdesc = (f"accepted map ({mj['adopted']}): d ({am['dx_in']:.2f}, {am['dy_in']:.2f}) in, theta {am['theta_deg']:.3f} deg, "
               f"s {am['scale']:.4f}, L {L:+.1f} s")
    ep = pd.read_csv(run / "fn_episodes.csv")
    clips = select_clip_windows(ep, n_sec=prm.n_sec)
    n_hot = sum(c["hotspot"] for c in clips)
    log(f"clips: {len(clips)} selected (hotspot {n_hot}, elsewhere {len(clips) - n_hot}); {mapdesc}")
    s2 = json.loads((step2 / "run.json").read_text(encoding="utf-8"))
    video = Path(s2["video"])
    fr = pd.read_csv(step2 / "frames.csv.gz")
    det = pd.read_csv(step2 / "detections.csv.gz")
    track_data, _ = load_tracks_real(prm)
    tracks = Tracks(track_data, prm.gap_max)
    houses = load_houses()
    mapper = real_mapper()
    sup = Support(mapper, HOUR_START + timedelta(seconds=prm.n_sec / 2), prm)
    ff, ffprobe = cvt.gf.find_ffmpeg()
    rows = []
    for c in clips:
        name = f"{c['k']:02d}_ep{c['episode_id']}_{c['animal']}_{c['start_t_pc'][11:19].replace(':', '-')}.mp4"
        c["file"] = name
        if only is not None and c["k"] != only:
            continue
        st = render_clip(video, c, fr, det, tracks, houses, m, L, sup, mapper, HOUR_START, prm, cdir / name, ff, mapdesc)
        st["frames_probe"] = probe_frames(ffprobe, cdir / name)
        st["frames_check"] = bool(st["frames_probe"] == st["frames_expected"] == st["frames_written"] and st["encoder_rc"] == 0)
        log(f"  {name}: {st['frames_written']} / {st['frames_expected']} frames, ffprobe {st['frames_probe']}, check "
            f"{st['frames_check']}, inverse max {st['inverse_roundtrip_max_in']:.3f} in, episode animal drawn in "
            f"{st['episode_animal_frames_ok']} frames, {st['render_s']} s")
        rows.append({"file": name, "k": c["k"], "episode_id": c["episode_id"], "animal": c["animal"],
                     "window": f"{fmt_hms(c['w0'])} -> {fmt_hms(c['w1'])}", "window_start_sec": c["w0"], "window_end_sec": c["w1"],
                     "duration_s": round(c["w1"] - c["w0"], 1), "episode_duration_s": c["episode_duration_s"],
                     "episodes_covered": ";".join(map(str, c["episodes_covered"])), "animals": ";".join(c["animals_covered"]),
                     "paddock_x_in": round(c["paddock_x_in"], 1), "paddock_y_in": round(c["paddock_y_in"], 1),
                     "paddock_xy_in": f"{c['paddock_x_in']:.0f}, {c['paddock_y_in']:.0f}", "pano_u": c["pano_u"],
                     "pano_v": c["pano_v"], "pano_uv": f"{c['pano_u']}, {c['pano_v']}", "hotspot": "yes" if c["hotspot"] else "no",
                     "frames": f"{st['frames_written']} / {st['frames_expected']} (ffprobe {st['frames_probe']})", **st})
    if only is None:
        cols = ["file", "k", "episode_id", "episodes_covered", "animal", "animals", "window", "window_start_sec", "window_end_sec",
                "duration_s", "episode_duration_s", "paddock_x_in", "paddock_y_in", "pano_u", "pano_v", "hotspot",
                "frames_expected", "frames_written", "frames_probe", "frames_check", "frames_unmatched_pts", "packet_errors",
                "animal_frames_ok", "animal_frames_out_of_view", "animal_frames_inverse_failed", "animal_frames_not_located",
                "episode_animal_frames_ok", "inverse_roundtrip_max_in", "inverse_roundtrip_p99_in", "bytes", "render_s"]
        pd.DataFrame(rows)[cols].to_csv(cdir / "clips.csv", index=False)
        tmpl = [{"clip": r["file"], "episode_id": e, "animal": ep.loc[ep["episode_id"] == e, "animal"].iloc[0], "verdict": "", "notes": ""}
                for r in rows for e in map(int, r["episodes_covered"].split(";"))]
        pd.DataFrame(tmpl, columns=["clip", "episode_id", "animal", "verdict", "notes"]).to_csv(cdir / "review_template.csv", index=False)
        write_clip_index(cdir, rows, {"mapdesc": mapdesc, "n_hotspot": n_hot, "n_elsewhere": len(clips) - n_hot})
        summ = {"plan_amendment": 4, "n_clips": len(rows), "n_hotspot": n_hot, "n_elsewhere": len(clips) - n_hot,
                "all_frame_checks": bool(all(r["frames_check"] for r in rows)), "frames_total": int(sum(r["frames_written"] for r in rows)),
                "runtime_s": round(time.perf_counter() - t_start, 1), "video": video.as_posix(), "map": mapdesc,
                "rule": f"longest first, [start - {CLIP_PAD:g}, end + {CLIP_PAD:g}] s capped at {CLIP_CAP:g} s, no overlap, {CLIP_N} clips",
                "canvas": [prm.width // 2, prm.height], "fps": CLIP_FPS, "git_commit": git_commit(REPO)}
        (cdir / "clips_summary.json").write_text(json.dumps(jsonable(summ), indent=2), encoding="utf-8")
        log(f"clips done: {summ['frames_total']} frames, all checks {summ['all_frame_checks']}, {summ['runtime_s']} s")
        rep = REPO / "results" / COHORT / DIRECTION / "reports" / REPORT_NAME
        log(f"report section {'updated' if update_report_clips(run, rep) else 'NOT updated (report is of another run)'}: {rep.as_posix()}")
    logf.close()
    return 0


# ----------------------------------------------------------------------------------------------- selftest
def synth(prm: Params, seed: int = 0, d_true=(-270.0, -598.0), L_true: float = 7.5, wiser_seed: int | None = None,
          w_scale: float = 1.0):
    """Synthetic hour (+ control hour): 6 animals in paddock inches, WISER = paddock - d + noise at 4 Hz, a pixel <-> paddock
    camera (x = 160 + u / 20, y = 20 + v / 10 on a 6000 x 2000 frame), 3 frames per second, the frame at nominal time t
    showing true time t + L_true. Animal 0 rests at (250, 60) for true 180-480 s (the 'rat' spot), animal 1 rests at
    (300, 150) for true 370-450 s with its boxes removed at nominal 400-409 s (a miss episode), animal 5 sits in house_2;
    a fixed object at (420, 180) (no animal comes near); random false positives. wiser_seed != None: WISER from unrelated
    trajectories (the reject path)."""
    W, H = prm.width, prm.height

    def to_px(p):
        p = np.asarray(p, float)
        return np.stack([(p[..., 0] - 160) * 20, (p[..., 1] - 20) * 10], -1)

    def mapper(t, uv):
        uv = np.asarray(uv, float).reshape(-1, 2)
        xy = np.stack([160 + uv[:, 0] / 20, 20 + uv[:, 1] / 10], 1)
        bad = (uv[:, 0] < 0) | (uv[:, 0] > W - 0.5) | (uv[:, 1] < 0) | (uv[:, 1] > H - 0.5)
        xy[bad] = np.nan
        return xy, {"flag": "ok", "night": "synthetic"}

    houses = [{"name": "house_1", "x": 411.46, "y": 718.61, "width_in": 36.39, "height_in": 26.59, "orientation_deg": 90.0},
              {"name": "house_2", "x": 613.58, "y": 717.34, "width_in": 36.39, "height_in": 26.59, "orientation_deg": 90.0}]
    d_true = np.asarray(d_true, float)

    def trajectories(rs, special=True):
        dt = 0.25
        tt = np.arange(-prm.lag_max - 60, prm.control_offset + prm.n_sec + prm.lag_max + 60, dt)
        P = np.zeros((6, len(tt), 2))
        S = np.zeros((6, len(tt)), int)
        for j in range(6):
            p = np.array([rs.uniform(20, 360), rs.uniform(20, 220)])
            k = 0
            while k < len(tt):
                still = rs.random() < 0.5
                n = int(rs.uniform(20, 120) / dt) if still else int(rs.uniform(10, 60) / dt)
                hd, sp = rs.uniform(0, 2 * np.pi), rs.uniform(5, 15)
                for _ in range(n):
                    if k >= len(tt):
                        break
                    if not still:
                        hd += rs.normal(0, 0.15)
                        p = p + sp * dt * np.array([np.cos(hd), np.sin(hd)])
                        for ax, lo, hi in ((0, 10, 370), (1, 10, 230)):
                            if p[ax] < lo or p[ax] > hi:
                                p[ax] = np.clip(p[ax], lo, hi)
                                hd = np.pi - hd if ax == 0 else -hd
                    P[j, k], S[j, k] = p, 1 if still else 3
                    k += 1
        if special:
            P[0, (tt >= 180) & (tt < 480)] = [250.0, 60.0]
            S[0, (tt >= 180) & (tt < 480)] = 1
            P[1, (tt >= 370) & (tt < 450)] = [300.0, 150.0]
            S[1, (tt >= 370) & (tt < 450)] = 1
        P[5] = np.array([613.58, 717.34]) + d_true
        S[5] = 1
        return tt, P, S

    rng = np.random.default_rng(seed)
    tt, P, S = trajectories(rng)
    tw, Pw, Sw = (tt, P, S) if wiser_seed is None else trajectories(np.random.default_rng(wiser_seed), special=False)
    labels = list(LABELS)
    track_data = {}
    for j, lab in enumerate(labels):
        cw = np.array([500.0, 760.0])                    # w_scale != 1: WISER inch scale off about this WISER point
        w = cw + (Pw[j] - d_true - cw) * w_scale + rng.normal(0, 3.0, Pw[j].shape)
        track_data[lab] = pd.DataFrame({"s": tw, "x": w[:, 0], "y": w[:, 1], "imu_state": Sw[j]})
    # frames + detections
    pts = (np.arange(prm.n_sec)[:, None] + np.array([0.0, 0.33, 0.67])[None]).ravel()
    fr = pd.DataFrame({"frame": np.arange(len(pts)), "pts_s": pts})
    base = datetime(2026, 9, 6, 21, 0, 0)
    fr["t_pc"] = [(base + timedelta(seconds=float(p))).isoformat(sep=" ", timespec="milliseconds") for p in pts]
    rows = []
    obj_px = to_px([420.0, 180.0])
    for k, p in enumerate(pts):
        ti = np.clip(np.searchsorted(tt, p + L_true), 0, len(tt) - 1)
        for j in range(5):
            x = P[j, ti]
            if not (160 <= x[0] < 460 and 20 <= x[1] < 220):
                continue
            if j == 1 and 399.5 <= p < 409.9:          # nominal seconds 400-409 (and their +-0.5-s windows)
                continue
            if rng.random() > 0.92:
                continue
            c = to_px(x + rng.normal(0, 1.5, 2))
            rows.append((k, p, c[0] - 40, c[1] - 40, c[0] + 40, c[1] + 40, rng.uniform(0.5, 0.9)))
        if rng.random() < 0.6:
            rows.append((k, p, obj_px[0] - 30, obj_px[1] - 30, obj_px[0] + 30, obj_px[1] + 30, 0.6))
        if rng.random() < 0.1:
            c = np.array([rng.uniform(100, W - 100), rng.uniform(100, H - 100)])
            rows.append((k, p, c[0] - 30, c[1] - 30, c[0] + 30, c[1] + 30, 0.55))
    det = pd.DataFrame(rows, columns=["frame", "pts_s", "x1", "y1", "x2", "y2", "conf"])
    det["t_pc"] = fr["t_pc"].to_numpy()[det["frame"].to_numpy()]
    # fixed-spot cells + spots (as c1_yolo_fixed_spots computes them)
    cx, cy = (det["x1"] + det["x2"]) / 2, (det["y1"] + det["y2"]) / 2
    g = pd.DataFrame({"frame": det["frame"], "ix": (cx // prm.cell_px).astype(int), "iy": (cy // prm.cell_px).astype(int)})
    occ = g.drop_duplicates().groupby(["ix", "iy"]).size() / len(fr)
    cells = pd.DataFrame({"x0": [i * prm.cell_px for i, _ in occ.index], "y0": [j * prm.cell_px for _, j in occ.index],
                          "occupancy": occ.to_numpy()})
    rest_px = to_px([250.0, 60.0])
    n_min = prm.n_sec // 60
    minute = (fr["pts_s"] // 60).astype(int).to_numpy()
    sp_rows = []
    for sid, (u, v), occ_fn in ((1, obj_px, None), (2, rest_px, None), (3, (W + 100.0, 100.0), "half")):
        if occ_fn == "half":
            om = [0.5] * n_min
            mid = len(fr) // 2
        else:
            hit = det[(np.abs(cx - u) < 60) & (np.abs(cy - v) < 60)]["frame"].unique()
            om = [float(np.isin(np.flatnonzero(minute == mm), hit).mean()) for mm in range(n_min)]
            mid = int(hit[len(hit) // 2])
        sp_rows.append({"spot_id": sid, "cx_median": float(u), "cy_median": float(v), "frame_middle": mid,
                        **{f"occ_min{mm:02d}": om[mm] for mm in range(n_min)}})
    spots = pd.DataFrame(sp_rows)
    return fr, det, cells, spots, track_data, houses, mapper


def selftest() -> int:
    ok = True

    def rec(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}", flush=True)

    # units
    tr = Tracks({"A": pd.DataFrame({"s": [0.0, 1.0, 10.0], "x": [0.0, 2.0, 4.0], "y": [0.0, 0.0, 0.0], "imu_state": [1, 3, 1]})}, 5.0)
    X, S, okk = tr.at([0.5, 0.9, 5.0, 11.0])
    rec("Tracks.at: linear inside a <= 5 s gap, nearer fix's state, not located across a 9-s gap or past the end",
        np.allclose(X[:2, 0, 0], [1.0, 1.8]) and S[0, 0] == 1 and S[1, 0] == 3 and not okk[2, 0] and not okk[3, 0])
    m = Map(-270.0, -598.0, np.radians(1.5), 1.02, 500.0, 750.0)
    w = np.array([[400.0, 700.0], [620.0, 760.0]])
    rec("Map.inv(Map.fwd(w)) = w (similarity)", np.allclose(m.inv(m.fwd(w)), w))
    rng = np.random.default_rng(1)
    V = np.array([-270.0, -598.0]) + rng.normal(0, 3, (400, 2))
    V[:80] += rng.uniform(-60, 60, (80, 2))
    dh = huber_translation(V, 6.0, [0.0, 0.0])
    rec("huber_translation: 20 % outliers, d within 0.5 in", np.hypot(*(dh - [-270, -598])) < 0.5, f"{dh.round(2)}")
    Wp = rng.uniform(300, 700, (300, 2))
    Pp = m.fwd(Wp) + rng.normal(0, 0.5, Wp.shape)         # SE of theta ~ 0.015 deg at this noise
    ms = huber_similarity(Wp, Pp, 6.0, Map(-270.0, -598.0, 0.0, 1.0, 500.0, 750.0))
    rec("huber_similarity recovers theta, s, d from the identity start", abs(np.degrees(ms.theta) - 1.5) < 0.06
        and abs(ms.s - 1.02) < 0.001 and np.hypot(ms.dx + 270, ms.dy + 598) < 0.5,
        f"theta {np.degrees(ms.theta):.3f} s {ms.s:.4f} d ({ms.dx:.2f}, {ms.dy:.2f})")
    ra, rr = hungarian(np.array([[0.0, 0.0], [10.0, 0.0], [100.0, 0.0]]), np.array([0]), np.array([3]), [0],
                       np.array([[[9.0, 0.0], [1.0, 0.0]]]), np.array([[True, True]]), 30.0)
    rec("hungarian: one-to-one, gate drops the far detection", list(ra) == [1, 0, -1] and np.isinf(rr[2]))

    # amendment 4: clip-window rule
    epx = pd.DataFrame({"episode_id": [1, 2, 3, 4, 5, 6], "animal": ["SF07", "SF08", "SF09", "SF10", "SF11", "SF12"],
                        "start_sec": [50, 120, 140, 400, 3590, 500], "end_sec": [149, 149, 149, 409, 3599, 502],
                        "duration_s": [100, 30, 10, 10, 10, 3], "start_t_pc": ["2026-09-06 21:00:50.000"] * 6,
                        "paddock_x_in": [450.0, 300, 300, 300, 300, 300], "paddock_y_in": [130.0, 50, 50, 50, 50, 50],
                        "pano_u": [100] * 6, "pano_v": [100] * 6})
    cl = select_clip_windows(epx, n=4)
    rec("clip windows: longest first, +-5 s capped at 90 s, overlapping episode skipped, touching allowed, end clamped, "
        "stop at n, hotspot flag, covered episodes",
        [c["episode_id"] for c in cl] == [1, 3, 4, 5] and (cl[0]["w0"], cl[0]["w1"]) == (45.0, 135.0)
        and (cl[1]["w0"], cl[1]["w1"]) == (135.0, 154.0) and cl[3]["w1"] == 3600.0 and cl[0]["hotspot"] and not cl[1]["hotspot"]
        and cl[0]["episodes_covered"] == [1, 2], str([(c["episode_id"], c["w0"], c["w1"]) for c in cl]))

    # amendment 4: numeric inverse of a nonlinear pixel -> paddock map
    def fwd_nl(uv):
        uv = np.asarray(uv, float).reshape(-1, 2)
        u, v = uv[:, 0], uv[:, 1]
        xy = np.stack([160 + u / 20 + 2e-6 * (u - 3000) ** 2 + 0.002 * v, 20 + v / 10 + 0.004 * u + 1e-5 * (v - 1000) ** 2], 1)
        xy[(u < 0) | (u > 5999.5) | (v < 0) | (v > 1999.5)] = np.nan
        return xy
    rng2 = np.random.default_rng(3)
    true_uv = np.stack([rng2.uniform(50, 5950, 300), rng2.uniform(50, 1950, 300)], 1)
    Ptrue = fwd_nl(true_uv)
    Ptest = np.vstack([Ptrue, [[1000.0, 1000.0], [-50.0, 10.0]]])
    uv_i, J_i, e_i = invert_mapper(fwd_nl, Ptest, np.vstack([true_uv + rng2.uniform(-30, 30, true_uv.shape), [[3000, 1000], [10, 10]]]))
    back = fwd_nl(uv_i[:300])
    rt = np.hypot(*(back - Ptrue).T)
    Jt = np.array([[1 / 20 + 4e-6 * (true_uv[0, 0] - 3000), 0.002], [0.004, 1 / 10 + 2e-5 * (true_uv[0, 1] - 1000)]])
    rec("invert_mapper: round trip <= 1 in (here < 0.05) at 300 points, pixel recovered, Jacobian right, unreachable -> NaN",
        np.nanmax(rt) < 0.05 and np.isfinite(uv_i[:300]).all() and np.max(np.hypot(*(uv_i[:300] - true_uv).T)) < 2.0
        and np.allclose(J_i[0], Jt, rtol=0.02, atol=1e-4) and np.isnan(uv_i[300:]).all(),
        f"max round trip {np.nanmax(rt):.4f} in, max px error {np.max(np.hypot(*(uv_i[:300] - true_uv).T)):.3f}")

    # full pipeline on the synthetic hour
    prm = Params(n_sec=1200, block_s=100, lag_max=30.0, control_offset=1200.0, width=6000, height=2000)
    fr, det, cells, spots, track_data, houses, mapper = synth(prm)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "run"
        t0 = time.perf_counter()
        res = run_pipeline(fr, det, cells, spots, track_data, houses, mapper, prm, datetime(2026, 9, 6, 21, 0, 0), out,
                           log=lambda s: None)
        print(f"  (synthetic pipeline {time.perf_counter() - t0:.0f} s)")
        f = res["fits"]["translation"]
        rec("A: known offset recovered (< 1 in)", np.hypot(f["map"]["dx_in"] + 270, f["map"]["dy_in"] + 598) < 1.0,
            f"d ({f['map']['dx_in']:.2f}, {f['map']['dy_in']:.2f})")
        rec("A: known lag recovered (7.5 s)", f["L"] == 7.5, f"L {f['L']}")
        a = res["test"]["chosen"][0]
        c = res["test"]["control"][0]
        rec("A: test median <= 14 in, within-14 share high", a["resid_median_in"] <= 14 and a["within_share"] > 0.7,
            f"median {a['resid_median_in']:.2f}, within {a['within_share']:.3f}")
        rec("A: negative control fails (within-14 <= half the real)", c["within_share"] <= 0.5 * a["within_share"],
            f"control {c['within_share']:.3f}")
        S = res["selection"]
        rec("A: selection on the fit blocks only (inner fit 1,5,9 / validation 3,7,11); the test blocks hold only the chosen "
            "model and the control", S["inner_fit_blocks"] == [1, 5, 9] and S["inner_val_blocks"] == [3, 7, 11]
            and set(res["test"]) == {"chosen", "control"} and S["translation"]["fit"].startswith("inner validation")
            and res["fits"]["inner_translation"]["fit_blocks"] == [1, 5, 9] and res["fits"]["translation"]["fit_blocks"] == [1, 3, 5, 7, 9, 11])
        rec("A: accepted; inner similarity near identity, translation chosen", res["acceptance"]["accepted"]
            and abs(res["fits"]["inner_similarity"]["map"]["theta_deg"]) < 0.5 and abs(res["fits"]["inner_similarity"]["map"]["scale"] - 1) < 0.01
            and res["adopted"] == "translation" and "similarity" not in res["fits"], f"inner gain {S['gain']:.3f}")
        rec("A: fixed-spot boxes excluded", res["inputs"]["dropped_in_fixed_spot_cells"] > 0)
        names = {p.name for p in out.iterdir()}
        need = {"mapping.json", "pairs.csv.gz", "residuals_test.csv", "control.json", "lag_profiles.csv", "support_polygon.json",
                "wiser_spots.csv", "fn_episodes.csv", "fn_grid.csv", "model_selection.csv", "residuals_test_by_x.csv"}
        rec("outputs written", need <= names, str(sorted(need - names)))
        ws = pd.read_csv(out / "wiser_spots.csv")
        s1 = ws[(ws["level"] == "spot") & (ws["spot_id"] == 1)].iloc[0]
        s2 = ws[(ws["level"] == "spot") & (ws["spot_id"] == 2)].iloc[0]
        s3 = ws[(ws["level"] == "spot") & (ws["spot_id"] == 3)].iloc[0]
        rec("B: object spot - on every minute, never an animal within 14 in", s1["n_min_on"] == prm.n_sec // 60 and s1["n_on_within14"] == 0,
            f"on {s1['n_min_on']}, within {s1['n_on_within14']}")
        rec("B: rat spot - on minutes have the (still) animal within 14 in, off minutes rarely",
            s2["n_min_on"] >= 4 and s2["n_on_within14"] >= s2["n_min_on"] - 1 and s2["n_on_still_within14"] >= s2["n_min_on"] - 1
            and s2["n_off_within14"] <= 1 and s2["spearman_rho_occ_vs_within14"] > 0.6,
            f"on {s2['n_min_on']}, within {s2['n_on_within14']}, still {s2['n_on_still_within14']}, off-within {s2['n_off_within14']}, "
            f"rho {s2['spearman_rho_occ_vs_within14']:.2f}")
        rec("B: spot outside the support -> NaN", (not bool(s3["in_support"])) and pd.isna(s3["n_on_within14"]))
        ep = pd.read_csv(out / "fn_episodes.csv")
        hit = ep[(ep["animal"] == "SF08") & (ep["start_sec"].between(398, 401))]
        rec("C: the removed 10-s stretch of SF08 is one episode at the right place",
            len(hit) == 1 and 9 <= hit.iloc[0]["duration_s"] <= 12 and abs(hit.iloc[0]["paddock_x_in"] - 300) < 5
            and abs(hit.iloc[0]["paddock_y_in"] - 150) < 5 and abs(hit.iloc[0]["pano_u"] - 2800) <= 80
            and abs(hit.iloc[0]["pano_v"] - 1300) <= 80 and hit.iloc[0]["imu_state"] == "still",
            hit.to_dict("records").__str__()[:300])
        rec("C: the animal in house_2 never makes an episode; support covers the camera rectangle; episodes are "
            "suspected misses", (ep["animal"] == "SF12").sum() == 0 and abs(res["C"]["support"]["area_in2"] - 300 * 200) / 60000 < 0.05
            and set(ep["kind"]) == {"suspected_miss"} and "top_cell" in res["C"]["summary"],
            f"area {res['C']['support']['area_in2']:.0f}")
        figs = make_figures(res, Path(tmp) / "figs")
        fake_old = {"run": "old", "accepted": True, "adopted": "similarity", "test_median_translation": 5.0,
                    "test_median_similarity": 4.0, "gain": 0.2, "within_translation": 0.9, "within_similarity": 0.9,
                    "within_control": 0.03, "same_map": False, "b_file_identical": False, "c_episodes_identical": False}
        rp = write_report(res, out, Path(tmp) / "rep", Path(tmp) / "figs", figs, {"git_commit": "selftest"}, fake_old)
        txt = rp.read_text(encoding="utf-8")
        rec("report: sealed B section without B numbers; superseded selection stated; figures without a B figure",
            "Sealed until the user's verdicts" in txt and "n_on_within14" not in txt and "spearman_rho_occ" not in txt
            and "superseded" in txt and "never creates a negative" in txt and "suspected" in txt
            and set(figs) == {"coarse_grid.png", "lag_profile.png", "test_distances.png", "fn_map.png"})
        rec("run results carry no B numbers", set(res["B"]) <= {"produced", "file", "rows", "sealed", "reason"})
        # WISER with an 8 % scale error: the similarity must win on inner validation
        fr3, det3, cells3, spots3, td3, houses3, mapper3 = synth(prm, w_scale=1 / 0.9)
        res3 = run_pipeline(fr3, det3, cells3, spots3, td3, houses3, mapper3, prm, datetime(2026, 9, 6, 21, 0, 0),
                            Path(tmp) / "run3", log=lambda s: None)
        m3 = res3["fits"].get("similarity", {}).get("map", {})
        rec("A: scaled WISER -> similarity chosen on inner validation, s ~ 0.90, accepted",
            res3["adopted"] == "similarity" and abs(m3.get("scale", 0) - 0.9) < 0.01 and abs(m3.get("theta_deg", 9)) < 0.5
            and res3["acceptance"]["accepted"] and res3["fits"]["similarity"]["fit_blocks"] == [1, 3, 5, 7, 9, 11],
            f"gain {res3['selection']['gain']:.3f}, s {m3.get('scale')}, test median {res3['acceptance']['test_median_in']:.2f}")
        # reject path: WISER from unrelated trajectories
        fr2, det2, cells2, spots2, td2, houses2, mapper2 = synth(prm, wiser_seed=99)
        out2 = Path(tmp) / "run2"
        res2 = run_pipeline(fr2, det2, cells2, spots2, td2, houses2, mapper2, replace(prm, max_it=8),
                            datetime(2026, 9, 6, 21, 0, 0), out2, log=lambda s: None)
        names2 = {p.name for p in out2.iterdir()}
        rec("reject path: unrelated WISER -> not accepted, B and C not produced",
            not res2["acceptance"]["accepted"] and "wiser_spots.csv" not in names2 and "fn_episodes.csv" not in names2,
            f"median {res2['acceptance']['test_median_in']:.1f}, real {res2['acceptance']['real_within14_share']:.3f}, "
            f"control {res2['acceptance']['control_within14_share']:.3f}")
        # amendment 4: inverse through the pipeline's own Support start + a small render on a synthetic HEVC clip
        sup1 = Support(mapper, datetime(2026, 9, 6, 21, 10), prm)
        Pq = np.array([[300.0, 150.0], [200.3, 40.7], [455.0, 210.0]])
        u0, _ = sup1.nearest_px(Pq)
        uvq, _, eq = invert_mapper(lambda q: mapper(None, q)[0], Pq, u0.astype(float))
        rec("invert_mapper from the Support grid start: <= 1 in, exact pixel of a linear camera",
            np.nanmax(eq) < 1.0 and np.allclose(uvq[0], [2800, 1300], atol=0.5), f"{uvq.round(2).tolist()}")
        try:
            import av  # noqa: F401
            import c1_yolo_video_test as cvt
            have_av = True
        except ImportError:
            have_av = False
        if not have_av:
            print("[SKIP] synthetic render (PyAV not installed in this interpreter; run the self-test in the cv env)")
        else:
            ff, ffprobe = cvt.gf.find_ffmpeg()
            vid = Path(tmp) / "CH01_2026-09-06_21-00-00_to_21-00-04.mp4"
            subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=180x640:rate=20:duration=4", "-c:v", "libx265",
                            "-x265-params", "keyint=40:min-keyint=40:scenecut=0:log-level=error", "-pix_fmt", "yuv420p", str(vid)], check=True)
            pts_all = [p for p, _ in cvt.AvFrames(vid)]
            prs = replace(prm, width=640, height=180)
            frs_ = pd.DataFrame({"frame": np.arange(len(pts_all)), "pts_s": pts_all})
            map_s = lambda t, uv: (np.where(((np.asarray(uv)[:, :1] >= 0) & (np.asarray(uv)[:, :1] < 639.5)  # noqa: E731
                                             & (np.asarray(uv)[:, 1:] >= 0) & (np.asarray(uv)[:, 1:] < 179.5)),
                                            np.stack([160 + np.asarray(uv, float)[:, 0] / 2, 20 + np.asarray(uv, float)[:, 1]], 1), np.nan),
                                   {"flag": "ok"})
            sup_s = Support(map_s, datetime(2026, 9, 6, 21, 0, 2), prs)
            dsyn = pd.DataFrame({"frame": [10, 10, 30], "pts_s": [pts_all[10], pts_all[10], pts_all[30]], "x1": [270.0, 500, 270],
                                 "y1": [70.0, 20, 70], "x2": [290.0, 540, 290], "y2": [90.0, 60, 90], "conf": [0.6, 0.3, 0.7]})
            mp = Map(-270.0, -598.0)
            tdat = {lab: pd.DataFrame({"s": np.arange(-5, 10, 0.25), "x": np.full(60, xw), "y": np.full(60, yw), "imu_state": 1})
                    for lab, xw, yw in (("SF07", 440.0, 678.0), ("SF08", 1000.0, 1000.0), ("SF09", 613.6, 717.3))}
            trs = Tracks(tdat, 5.0)
            clip = {"k": 1, "episode_id": 7, "animal": "SF07", "w0": 0.5, "w1": 2.5, "episode_start_sec": 1, "episode_end_sec": 2,
                    "episode_duration_s": 2, "pano_u": 300, "pano_v": 80}
            outv = Path(tmp) / "clip.mp4"
            st = render_clip(vid, clip, frs_, dsyn, trs, houses, mp, 0.0, sup_s, map_s, HOUR_START, prs, outv, ff, "synthetic map")
            exp = int(np.sum((np.array(pts_all) >= 0.5 - 1e-6) & (np.array(pts_all) < 2.5 - 1e-6)))
            wh = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of",
                                 "csv=p=0", str(outv)], capture_output=True, text=True).stdout.strip()
            rec("render_clip: every window frame written, ffprobe count = expected, canvas W/2 x H, episode animal drawn, "
                "the WISER animal out of the paddock is out of view, the house animal is located",
                st["frames_written"] == exp == st["frames_expected"] and probe_frames(ffprobe, outv) == exp and wh == "320,180"
                and st["episode_animal_frames_ok"] == exp and st["animal_frames_out_of_view"] == exp
                and st["inverse_roundtrip_max_in"] < 1.0, f"{st['frames_written']}/{exp}, probe {probe_frames(ffprobe, outv)}, "
                f"size {wh}, ok {st['animal_frames_ok']}, oov {st['animal_frames_out_of_view']}")
    print(("PASS" if ok else "FAIL") + " — wiser_assist_p0 self-test")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--run", action="store_true", help="run phase 0 on the step-2 hour")
    ap.add_argument("--step2", default=str(STEP2_RUN), help="step-2 run folder (cv_field_c1yolo_video_<ts>)")
    ap.add_argument("--out", default=None, help="run folder (default: a new $OUT/2026c/cv_field_wiser_assist_p0_<ts>)")
    ap.add_argument("--clips", default=None, help="amendment 4: render the suspected-miss review clips of this phase-0 run "
                                                  "into <run>/review_clips/ (cv env: PyAV)")
    ap.add_argument("--clip-only", type=int, default=None, help="render only clip k (a timing check; writes no tables)")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.clips:
        return run_clips(Path(a.clips), Path(a.step2), a.clip_only)
    if not a.run:
        ap.error("nothing to do (--run or --selftest)")
    return run_real(Path(a.step2), Path(a.out) if a.out else None)


if __name__ == "__main__":
    sys.exit(main())
