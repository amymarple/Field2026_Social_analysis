r"""build_wiser_pixel_kit.py — the WISER pixel kit for the cohort-3 CH01/CH02 panoramas (plan A).

Specification: implementation_plan/2026-10-06-wiser-label-loop.md (part A; pre-registered, approved 2026-10-06) + its
dated amendments. Data map: cv/cv_field/DATA_MAP_c1yolo_wiser.md (section I).

What it writes ($OUT/2026c/wiser_pixel_kit_<ts>/, ~150 MB; the user copies it to Q: with the label package):
  kit.json, README.md
  <CAM>/support.json          {"camera", "frame_size":[7680,2160], "by_night": {night: {"polygon":[[u,v],...], ...}}}
  <CAM>/occluders.json        {"camera", "by_night": {night: {"occluders":[{"name","kind":"pole|house","polygon",...}]}}}
  <CAM>/<YYYY-MM-DD>.csv.gz   one per night, 1 Hz x 6 animals: t_pc, animal, tracked, in_house, u, v, r_px, hidden_share,
                              in_support, motion, all_tracked, map_validated (booleans 0/1)
  <CAM>/visibility_mask.npz   the 2-in paddock grid of hidden shares h (+ per object) the hidden_share column is read from
  <CAM>/checks.csv            occluder model vs the user's labels (px)
Nights: D 21:00 -> D+1 04:20 for D = 08-30 ... 09-10 (the population change 09-11 19:40 cuts 09-11), minus the frozen
test night 09-05 (no model may run on its frames, so it cannot be validated, and no WISER pixels are written for it).
Handling windows +- 5 min have no rows.

Chain for one animal-second (all inputs read-only):
  WISER default track (wiser/src/default_tracks.py; clean fixes = valid, no m_* mask, outside handling windows; linear
  between the two bracketing fixes <= 5 s apart; SF12's second tag SF12_tag12376 where its main tag has none)
  -> paddock inches by the ACCEPTED map of phase 0 (similarity, L = 0; $OUT/2026c/cv_field_wiser_assist_p0_20261005_2211/
  mapping.json) -> 09-18 calibration px by the rev g RayCamera's inverse at z = 60 mm (../Field_2026_Social_Recording/
  calibration_qc, paddock_map.load()) -> upright cohort px by the night's frame correction A(t) (frame_correction.py's
  table, interpolated per second exactly as Corrections.correction does).
  r_px = 14 sqrt(|det J|), J = d(cohort px) / d(paddock in) at the position (radius of the circle with the area of the
  14-in ring's image). hidden_share = the CH0x visibility mask (ch01_occlusion.py's v2 scene: poles from that camera's own
  09-18 L/R edge labels where labelled, else capsules; house_2 at the calibration pose, house_1 at its cohort pose) at the
  nominal position. in_support = the cohort pixel is in the frame and the camera's verified mapping covers it.
  motion = head-IMU state where its QC passes (still / active / locomoting), else the track's speed (< 2 in/s still,
  2-10 active, >= 10 locomoting); unknown when not tracked. all_tracked = all six animals tracked (before 09-11 19:40).
Map validation per camera-night (plan A2, amendment 1): from the round-1 pool frames of that camera-night (made by
  select_label_round1.py --pool): YOLO v5 boxes conf >= 0.5 -> paddock (Corrections.to_paddock, z = 60 mm) vs WISER
  animals outside the house zones at the frame time; median matched residual (per-frame Hungarian, gate 30 in) <= 14 in
  AND within-14-in share >= 2 x that of WISER + 1 h (same map) -> map_validated = 1. Failed nights keep their rows but
  get map_validated = 0 (no overlay, no WISER-dependent quota).
WISER positions are proposals, never boxes; WISER never makes a negative. The agent never looks at images.

Usage (cv env or base Python with OpenCV + scipy + matplotlib):
  python cv/cv_field/build_wiser_pixel_kit.py --selftest
  python cv/cv_field/build_wiser_pixel_kit.py --build --pool <$OUT/2026c/label_round1_pool_<ts>> [--out <dir>] [--cameras CH01 CH02]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _p in (str(HERE), str(HERE.parent), str(REPO / "wiser" / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
# the repo's frame_correction must be imported before calibration_qc/ (which has its own frame_correction.py) enters sys.path
import frame_correction as fc  # noqa: E402

OUT_ROOT = Path(os.environ.get("FIELD2026_ANALYSIS_OUT_ROOT", "D:/Field2026_analysis_out"))
P0_RUN = OUT_ROOT / "2026c" / "cv_field_wiser_assist_p0_20261005_2211"
COHORT, DIRECTION, NAME = "2026c", "cv_field", "wiser_pixel_kit"
PLAN = "implementation_plan/2026-10-06-wiser-label-loop.md"
ROIS = REPO / "wiser" / "configs" / "wiser_rois.json"
HANDLING = REPO / "cv" / "configs" / "cohort3_handling_windows.json"
IDENTITIES = REPO / "wiser" / "configs" / "rat_identities_2026c.csv"
CAMS = ("CH01", "CH02")
ANIMALS = ("SF07", "SF08", "SF09", "SF10", "SF11", "SF12")
EXTRA_LABEL = {"SF12": "SF12_tag12376"}                  # SF12's second tag (08-30 19:00 -> 08-31 19:24)
TEST_NIGHT = date(2026, 9, 5)                            # frozen test night: no kit table
NIGHTS = tuple(d for d in (date(2026, 8, 30) + timedelta(days=i) for i in range(12)) if d != TEST_NIGHT)   # 08-30 .. 09-10
NIGHT_START = dtime(21, 0)
NIGHT_SEC = 7 * 3600 + 20 * 60                           # 21:00 -> 04:20
EDT_H = 4                                                # field-PC local (EDT) = UTC - 4 h
POPCHANGE = datetime(2026, 9, 11, 19, 40)
SF11_TAG_OFF = datetime(2026, 9, 7, 6, 10, 45)           # SF11's implant + tag came off; the animal stayed in the paddock
HANDLING_MARGIN_S = 300.0
GAP_MAX = 5.0                                            # WISER interpolation: bracketing fixes at most this far apart (s)
HOUSE_BUF = 14.0
Z_MM = 60.0
RING_IN = 14.0
STILL_SPEED, LOCO_SPEED = 2.0, 10.0                      # in/s, motion where the head IMU is not usable
MOTION_NAME = {0: "unknown", 1: "still", 2: "active", 3: "locomoting"}
MASK_COLS = ("m_handling", "m_silence", "m_tag_validity", "m_adc_lane", "m_off_animal")
# validation (plan A2 + amendment 1)
VAL_CONF, VAL_GATE, VAL_WITHIN, VAL_CONTROL_S, VAL_RATIO = 0.5, 30.0, 14.0, 3600.0, 2.0
VAL_MIN_DET, VAL_MIN_PAIRS = 20, 10
PERTURB_IN, N_DIR, CLAMP_INSET_IN = 7.0, 8, 1.0
SUPPORT_STEP_PX = 16
KIT_COLUMNS = ["t_pc", "animal", "tracked", "in_house", "u", "v", "r_px", "hidden_share", "in_support", "motion",
               "all_tracked", "map_validated"]
LABELLED_POLES = {"CH01": ("A0", "B0", "B1", "B2", "B3", "C0", "C1"), "CH02": ("A0", "A4", "B0", "B1", "B2", "B3", "B4")}
LM_DIR = REPO / "cv" / "configs" / "landmarks" / "2026c"
LM_0918 = {"CH01": "landmarks_CH01_20260918_135730.json", "CH02": "landmarks_CH02_20260918_152230.json"}
LM_0904 = {"CH01": "landmarks_CH01_20260904_120002.json", "CH02": "landmarks_CH02_20260904_120002.json"}
HOUSE_EDGE_KEYS = ("ROOF_X", "ROOF_Y", "BASE_X", "BASE_Y", "BASE_Z")
FMT = "%Y-%m-%d %H:%M:%S"


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
    if isinstance(o, np.ndarray):
        return jsonable(o.tolist())
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        v = float(o)
        return v if np.isfinite(v) else None
    if isinstance(o, (Path, datetime, date)):
        return str(o)
    return o


def night_start(night: date) -> datetime:
    return datetime.combine(night, NIGHT_START)


def night_of(t: datetime) -> date | None:
    """Night D = D 21:00 -> D+1 04:20 (None outside)."""
    m = t.hour * 60 + t.minute
    if m >= 21 * 60:
        return t.date()
    if m < 4 * 60 + 20:
        return t.date() - timedelta(days=1)
    return None


def load_handling(path: Path = HANDLING) -> list[tuple[datetime, datetime]]:
    return [(datetime.fromisoformat(a), datetime.fromisoformat(b)) for a, b, _ in
            json.loads(Path(path).read_text(encoding="utf-8"))["windows"]]


def in_windows(t: np.ndarray, windows, margin_s: float = 0.0) -> np.ndarray:
    """t: datetime64[ns] array -> inside any window grown by margin_s."""
    t = np.asarray(t, "datetime64[ns]")
    out = np.zeros(t.shape, bool)
    m = np.timedelta64(int(margin_s * 1e9), "ns")
    for a, b in windows:
        out |= (t >= np.datetime64(a) - m) & (t < np.datetime64(b) + m)
    return out


# ----------------------------------------------------------------------------------------------- WISER
def load_night_fixes(night: date, pre_s: float = 180.0, post_s: float = VAL_CONTROL_S + 240.0, handling=None,
                     root=None) -> dict:
    """Clean fixes (valid, no m_* mask, outside handling windows - phase 0's rule) of every label around night D:
    s = seconds since D 21:00 field-PC local, x, y (in, WISER frame), imu_state, vx, vy."""
    from default_tracks import load_default_track
    handling = load_handling() if handling is None else handling
    t0 = night_start(night)
    t0_ms = int((pd.Timestamp(t0) + pd.Timedelta(hours=EDT_H)).value // 10**6)
    lo, hi = -pre_s, NIGHT_SEC + post_s
    cols = ["t_ms", "x", "y", "vx", "vy", "valid", *MASK_COLS, "imu_state"]
    out, meta = {}, {}
    for lab in (*ANIMALS, *EXTRA_LABEL.values()):
        parts, paths = [], []
        for d in (night, night + timedelta(days=1)):
            try:
                df = load_default_track(lab, d, root=root, columns=cols)
            except FileNotFoundError:
                continue
            parts.append(df)
            paths.append(df.attrs.get("path"))
        if not parts:
            continue
        df = pd.concat(parts, ignore_index=True)
        s = (df["t_ms"].to_numpy(np.int64) - t0_ms) / 1000.0
        w = df[(s >= lo) & (s <= hi)].copy()
        w["s"] = (w["t_ms"].to_numpy(np.int64) - t0_ms) / 1000.0
        clean = w["valid"].to_numpy(bool) & ~w[list(MASK_COLS)].to_numpy(bool).any(axis=1)
        loc = np.datetime64(t0) + (w["s"].to_numpy() * 1e9).astype("timedelta64[ns]")
        keep = clean & ~in_windows(loc, handling)
        g = w.loc[keep, ["s", "x", "y", "imu_state", "vx", "vy"]].sort_values("s").drop_duplicates("s")
        out[lab] = g.reset_index(drop=True)
        meta[lab] = {"files": paths, "rows_window": int(len(w)), "clean_used": int(keep.sum())}
    return {"fixes": out, "meta": meta, "night": night}


def interp_fixes(df: pd.DataFrame | None, tq: np.ndarray, gap_max: float = GAP_MAX):
    """Phase 0's Tracks.at rule for one label (linear between the two bracketing fixes <= gap_max apart, IMU state of
    the nearer fix) + the speed of the nearer fix. -> x, y, imu_state, speed, ok."""
    tq = np.asarray(tq, float)
    n = len(tq)
    x = np.full(n, np.nan)
    y = np.full(n, np.nan)
    st = np.full(n, -1, np.int8)
    sp = np.full(n, np.nan)
    ok = np.zeros(n, bool)
    if df is None or len(df) < 2:
        return x, y, st, sp, ok
    t = df["s"].to_numpy(float)
    X, Y = df["x"].to_numpy(float), df["y"].to_numpy(float)
    S = df["imu_state"].to_numpy(int)
    V = np.hypot(df["vx"].to_numpy(float), df["vy"].to_numpy(float))
    i = np.searchsorted(t, tq, side="right")
    il = np.clip(i - 1, 0, len(t) - 1)
    ir = np.clip(i, 0, len(t) - 1)
    gap = t[ir] - t[il]
    v = (i > 0) & (i < len(t)) & (gap <= gap_max) & (gap > 0)
    a = np.where(v, (tq - t[il]) / np.where(gap > 0, gap, 1.0), 0.0)
    x[v] = (X[il] + a * (X[ir] - X[il]))[v]
    y[v] = (Y[il] + a * (Y[ir] - Y[il]))[v]
    near = np.where(tq - t[il] <= t[ir] - tq, il, ir)
    st[v] = S[near][v]
    sp[v] = V[near][v]
    ok[:] = v
    return x, y, st, sp, ok


def motion_codes(ok: np.ndarray, imu: np.ndarray, speed: np.ndarray) -> np.ndarray:
    """0 unknown, 1 still, 2 active, 3 locomoting: head-IMU state where QC-ok (1-3), else the track speed."""
    m = np.zeros(ok.shape, np.int8)
    use_imu = ok & np.isin(imu, (1, 2, 3))
    m[use_imu] = imu[use_imu]
    rest = ok & ~use_imu & np.isfinite(speed)
    with np.errstate(invalid="ignore"):
        m[rest & (speed < STILL_SPEED)] = 1
        m[rest & (speed >= STILL_SPEED) & (speed < LOCO_SPEED)] = 2
        m[rest & (speed >= LOCO_SPEED)] = 3
    return m


def load_map(p0: Path = P0_RUN):
    import wiser_assist_p0 as wp
    mj = json.loads((p0 / "mapping.json").read_text(encoding="utf-8"))
    if not mj.get("accepted"):
        raise SystemExit("phase-0 map not accepted - refusing")
    am = mj["accepted_map"]
    m = wp.Map(float(am["dx_in"]), float(am["dy_in"]), float(np.radians(am["theta_deg"])), float(am["scale"]),
               float(am["centre_wiser_in"][0]), float(am["centre_wiser_in"][1]))
    return m, float(mj["accepted_L_s"]), mj


def wiser_state(nf: dict, tq: np.ndarray, m, houses, shift_s: float = 0.0, L: float = 0.0) -> dict:
    """WISER at query times tq (s since the night start; frame time) + L + shift_s: per animal (n, 6) position (WISER in),
    paddock position (in, accepted map), tracked, in_house (rectangle + 14 in), motion code; all_tracked (n,)."""
    import wiser_assist_p0 as wp
    night = nf["night"]
    tq = np.asarray(tq, float)
    tw = tq + L + shift_s
    n, J = len(tq), len(ANIMALS)
    X = np.full((n, J, 2), np.nan)
    ok = np.zeros((n, J), bool)
    imu = np.full((n, J), -1, np.int8)
    sp = np.full((n, J), np.nan)
    for j, a in enumerate(ANIMALS):
        x, y, st, s_, k = interp_fixes(nf["fixes"].get(a), tw)
        if a in EXTRA_LABEL:
            x2, y2, st2, s2, k2 = interp_fixes(nf["fixes"].get(EXTRA_LABEL[a]), tw)
            f = ~k & k2
            x[f], y[f], st[f], s_[f], k[f] = x2[f], y2[f], st2[f], s2[f], True
        X[:, j, 0], X[:, j, 1], imu[:, j], sp[:, j], ok[:, j] = x, y, st, s_, k
    t_abs = np.datetime64(night_start(night)) + (tw * 1e9).astype("timedelta64[ns]")
    j11 = ANIMALS.index("SF11")
    ok[t_abs >= np.datetime64(SF11_TAG_OFF), j11] = False       # tag off: the animal is in the paddock, untracked
    X[~ok] = np.nan
    house = wp.in_houses(X, houses, HOUSE_BUF) & ok
    P = m.fwd(X.reshape(-1, 2)).reshape(X.shape)
    mot = motion_codes(ok, imu, sp)
    all_tr = ok.all(1) & (t_abs < np.datetime64(POPCHANGE))
    return {"X": X, "P": P, "ok": ok, "house": house, "motion": mot, "imu": imu, "speed": sp, "all_tracked": all_tr,
            "t_abs": t_abs}


def kit_seconds(night: date, handling=None) -> tuple[np.ndarray, np.ndarray]:
    """Whole seconds of the night [21:00, 04:20) outside the handling windows +- 5 min -> (seconds, datetime64)."""
    handling = load_handling() if handling is None else handling
    s = np.arange(NIGHT_SEC, dtype=float)
    t = np.datetime64(night_start(night)) + (s * 1e9).astype("timedelta64[ns]")
    keep = ~in_windows(t, handling, HANDLING_MARGIN_S)
    return s[keep], t[keep]


# ----------------------------------------------------------------------------------------------- camera geometry
def correction_samples(C, cam: str, night: date):
    """The night's usable correction samples exactly as Corrections.correction selects them -> (ts s since the night
    start, A (k, 2, 3), flags, times)."""
    allr = C.samples(cam, night)
    use = [r for r in allr if r["flag"] not in ("sample", "lid", "outlier")] or allr
    if not use:
        return None
    t0 = night_start(night)
    ts = np.array([(r["_t"] - t0).total_seconds() for r in use], float)
    mats = np.array([fc.mat(r) for r in use], float)
    return {"ts": ts, "mats": mats, "flags": [r["flag"] for r in use], "times": [r["time"] for r in use],
            "n_all": len(allr), "n_used": len(use)}


def affines_at(cs: dict, tq: np.ndarray) -> np.ndarray:
    """A (09-18 px -> frame px) at query seconds: Corrections.correction's rule (linear between the two nearest usable
    samples, the nearest sample beyond them), vectorised."""
    ts, M = cs["ts"], cs["mats"]
    tq = np.asarray(tq, float)
    if len(ts) == 1:
        return np.repeat(M[:1], len(tq), 0)
    i = np.clip(np.searchsorted(ts, tq, side="right") - 1, 0, len(ts) - 2)
    w = np.clip((tq - ts[i]) / (ts[i + 1] - ts[i]), 0.0, 1.0)
    A = (1 - w)[:, None, None] * M[i] + w[:, None, None] * M[i + 1]
    A[tq <= ts[0]] = M[0]
    A[tq >= ts[-1]] = M[-1]
    return A


def apply_affine(A: np.ndarray, uv: np.ndarray) -> np.ndarray:
    """A (n, 2, 3) or (2, 3) applied to uv (n, 2)."""
    uv = np.asarray(uv, float).reshape(-1, 2)
    if A.ndim == 2:
        return uv @ A[:, :2].T + A[:, 2]
    return np.einsum("nij,nj->ni", A[:, :, :2], uv) + A[:, :, 2]


def ground_mm(cam, uv18: np.ndarray) -> np.ndarray:
    """Where the 09-18-px rays meet z = 60 mm above the local ground, without the support check (mm)."""
    if hasattr(cam, "_ground"):
        return cam._ground(np.asarray(uv18, float).reshape(-1, 2), Z_MM)
    return np.asarray(cam.to_paddock(uv18, z_mm=Z_MM, units="mm"), float).reshape(-1, 2)


def to_pixels(cam, P_in: np.ndarray, A: np.ndarray) -> dict:
    """Paddock inches -> 09-18 px (calibration inverse, z = 60 mm) -> cohort px (A per point); in_frame, in_support,
    r_px = 14 sqrt(|det J|) with J = d(cohort px)/d(paddock in)."""
    P_in = np.asarray(P_in, float).reshape(-1, 2)
    n = len(P_in)
    u18 = np.full((n, 2), np.nan)
    fin = np.isfinite(P_in).all(1)
    if fin.any():
        u18[fin] = np.asarray(cam.to_paddock_inv(P_in[fin], z_mm=Z_MM, units="in"), float).reshape(-1, 2)
    u = apply_affine(A, u18) if n else np.zeros((0, 2))
    W, H = cam.upright_size
    with np.errstate(invalid="ignore"):
        in_frame = np.isfinite(u).all(1) & (u[:, 0] >= 0) & (u[:, 0] < W) & (u[:, 1] >= 0) & (u[:, 1] < H)
    in_sup = np.zeros(n, bool)
    if in_frame.any():
        q = np.asarray(cam.to_paddock(u18[in_frame], z_mm=Z_MM, units="in"), float).reshape(-1, 2)
        in_sup[in_frame] = np.isfinite(q).all(1)
    r = np.full(n, np.nan)
    if in_frame.any():
        k = np.flatnonzero(in_frame)
        g0 = ground_mm(cam, u18[k])
        gu = ground_mm(cam, u18[k] + [1.0, 0.0])
        gv = ground_mm(cam, u18[k] + [0.0, 1.0])
        Jf = np.stack([gu - g0, gv - g0], 2) / 25.4                 # paddock in per 09-18 px
        det = Jf[:, 0, 0] * Jf[:, 1, 1] - Jf[:, 0, 1] * Jf[:, 1, 0]
        Aa = A[k, :, :2] if A.ndim == 3 else np.repeat(A[None, :, :2], len(k), 0)
        detA = Aa[:, 0, 0] * Aa[:, 1, 1] - Aa[:, 0, 1] * Aa[:, 1, 0]
        with np.errstate(divide="ignore", invalid="ignore"):
            r[k] = RING_IN * np.sqrt(np.abs(detA / det))
    u[~in_frame] = np.nan
    return {"u": u, "u18": u18, "in_frame": in_frame, "in_support": in_sup, "r_px": r}


def support_mask_0918(cam, step: int = SUPPORT_STEP_PX) -> tuple[np.ndarray, int]:
    """09-18 px cells (step px) whose centre maps (frame + verified support + ground) at z = 60 mm."""
    W, H = cam.upright_size
    cu, cv_ = np.arange(step / 2, W, step), np.arange(step / 2, H, step)
    UU, VV = np.meshgrid(cu, cv_)
    q = np.asarray(cam.to_paddock(np.stack([UU.ravel(), VV.ravel()], 1), z_mm=Z_MM, units="in"), float)
    return np.isfinite(q).all(1).reshape(UU.shape), step


def support_polygon(mask: np.ndarray, step: int, A: np.ndarray, W: int, H: int) -> dict:
    """Largest outer contour of the support cells (09-18 px) -> cohort px by A, clipped to the frame."""
    import cv2
    m8 = mask.astype(np.uint8)
    cs, _ = cv2.findContours(m8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cs:
        return {"polygon": [], "share_of_support_cells": 0.0, "n_contours": 0}
    areas = [cv2.contourArea(c) for c in cs]
    big = cs[int(np.argmax(areas))]
    inside = np.zeros_like(m8)
    cv2.drawContours(inside, [big], -1, 1, thickness=-1)
    share = float((inside & m8).sum() / max(m8.sum(), 1))
    poly = cv2.approxPolyDP(big, 0.5, True).reshape(-1, 2).astype(float)
    poly18 = (poly + 0.5) * step
    pc = apply_affine(A, poly18)
    pc[:, 0] = np.clip(pc[:, 0], 0, W)
    pc[:, 1] = np.clip(pc[:, 1], 0, H)
    return {"polygon": np.round(pc, 1).tolist(), "share_of_support_cells": share, "n_contours": int(len(cs))}


def hull(pts: np.ndarray) -> np.ndarray:
    import cv2
    pts = np.asarray(pts, float).reshape(-1, 2)
    pts = pts[np.isfinite(pts).all(1)]
    if len(pts) < 3:
        return np.zeros((0, 2))
    return cv2.convexHull(pts.astype(np.float32)).reshape(-1, 2).astype(float)


def clip_poly(poly: np.ndarray, W: float, H: float) -> np.ndarray:
    """Sutherland-Hodgman clip of a polygon to the frame [0, W] x [0, H]."""
    out = [tuple(p) for p in np.asarray(poly, float).reshape(-1, 2)]
    for axis, lim, keep_ge in ((0, 0.0, True), (0, float(W), False), (1, 0.0, True), (1, float(H), False)):
        if not out:
            break
        inp, out = out, []
        inside = (lambda p: p[axis] >= lim) if keep_ge else (lambda p: p[axis] <= lim)
        for i, cur in enumerate(inp):
            prev = inp[i - 1]
            if inside(cur):
                if not inside(prev):
                    t = (lim - prev[axis]) / (cur[axis] - prev[axis])
                    out.append(tuple(np.asarray(prev) + t * (np.asarray(cur) - np.asarray(prev))))
                out.append(cur)
            elif inside(prev):
                t = (lim - prev[axis]) / (cur[axis] - prev[axis])
                out.append(tuple(np.asarray(prev) + t * (np.asarray(cur) - np.asarray(prev))))
    return np.asarray(out, float).reshape(-1, 2)


MAX_POLE_WIDTH_PX = 1500.0     # a projected pole wider than this wraps around the panorama (garbage) -> dropped


def occluders_0918(cam_name: str, cam, scene, noon_A: dict | None) -> list[dict]:
    """Occluder outlines in 09-18 px: labelled poles = hull of their L/R edge labels (09-18); other poles = hull of the
    projected capsule silhouette (ground -> 2.4 m); house_2 = hull of its 09-18 edge labels; house_1 = hull of its
    09-04 noon edge labels mapped to 09-18 px by the inverse noon affine (house_1 moved on 09-18)."""
    import ch01_occlusion as oc
    lab = json.loads((LM_DIR / LM_0918[cam_name]).read_text(encoding="utf-8"))["landmarks"]
    W, H = cam.upright_size
    out = []
    for p, rec in scene.poles.items():
        Lp, Rp = lab.get(f"POLE_{p}_L"), lab.get(f"POLE_{p}_R")
        if Lp and Rp:
            pts = np.vstack([np.asarray(q, float).reshape(-1, 2) for q in (*Lp, *Rp)])
            src = f"labels {LM_0918[cam_name]} (L/R edges, visible stretch)"
        else:
            l_, r_ = oc.pole_silhouette(cam, rec, top=oc.POLE_H)
            pts = np.vstack([l_, r_])
            pts = pts[np.isfinite(pts).all(1)]
            pts = pts[(pts[:, 0] >= 0) & (pts[:, 0] < W) & (pts[:, 1] >= 0) & (pts[:, 1] < H)]   # in-frame points only
            if len(pts) and np.ptp(pts[:, 0]) > MAX_POLE_WIDTH_PX:                              # wraps around the pano
                continue
            src = "projected capsule (calibration rev g, ground -> 2.4 m; in-frame points)"
        h = hull(pts)
        if len(h) < 3:
            continue
        if not ((h[:, 0].max() >= 0) & (h[:, 0].min() < W) & (h[:, 1].max() >= 0) & (h[:, 1].min() < H)):
            continue
        out.append({"name": f"pole_{p}", "kind": "pole", "polygon18": h, "source": src})
    for hn in ("HOUSE_1", "HOUSE_2"):
        if hn == "HOUSE_1":
            l4 = json.loads((LM_DIR / LM_0904[cam_name]).read_text(encoding="utf-8"))["landmarks"]
            pts = [np.asarray(q, float).reshape(-1, 2) for k in HOUSE_EDGE_KEYS for q in l4.get(f"{hn}_{k}", [])]
            if not pts or noon_A is None:
                continue
            Ai = oc.inv_affine(noon_A[cam_name])
            pts18 = apply_affine(Ai, np.vstack(pts))
            src = f"cohort labels {LM_0904[cam_name]} -> 09-18 px (inverse noon affine)"
        else:
            pts = [np.asarray(q, float).reshape(-1, 2) for k in HOUSE_EDGE_KEYS for q in lab.get(f"{hn}_{k}", [])]
            if not pts:
                continue
            pts18 = np.vstack(pts)
            src = f"labels {LM_0918[cam_name]} (edges, visible stretch)"
        h = hull(pts18)
        if len(h) >= 3:
            out.append({"name": hn.lower(), "kind": "house", "polygon18": h, "source": src})
    return out


def occluders_for(occ18: list[dict], A: np.ndarray, W: int = 7680, H: int = 2160) -> list[dict]:
    """09-18-px outlines -> this frame (A), clipped to the frame; outlines left with < 3 vertices are dropped."""
    out = []
    for o in occ18:
        pg = clip_poly(apply_affine(A, o["polygon18"]), W, H)
        if len(pg) >= 3:
            out.append({"name": o["name"], "kind": o["kind"], "polygon": np.round(pg, 1).tolist(), "source": o["source"]})
    return out


def paddock_mask_path():
    from matplotlib.path import Path as MPath
    return [MPath(np.array([[0.0, 0.0], [480.0, 0.0], [480.0, 240.0], [0.0, 240.0]]))]


def mask_lookup(mk: dict, P: np.ndarray) -> np.ndarray:
    """h of the 2-in cell holding each paddock position (clamped into the paddock inset by 1 in); NaN where P is NaN."""
    P = np.asarray(P, float)
    sh = P.shape[:-1]
    P = P.reshape(-1, 2)
    out = np.full(len(P), np.nan)
    f = np.isfinite(P).all(1)
    x = np.clip(P[f, 0], CLAMP_INSET_IN, 480 - CLAMP_INSET_IN)
    y = np.clip(P[f, 1], CLAMP_INSET_IN, 240 - CLAMP_INSET_IN)
    xs, ys = np.asarray(mk["x_in"], float), np.asarray(mk["y_in"], float)
    step = xs[1] - xs[0]
    ix = np.clip(np.floor((x - (xs[0] - step / 2)) / step).astype(int), 0, len(xs) - 1)
    iy = np.clip(np.floor((y - (ys[0] - step / 2)) / step).astype(int), 0, len(ys) - 1)
    out[f] = np.asarray(mk["h"], float)[iy, ix]
    return out.reshape(sh)


def robust_hidden(mk: dict, P: np.ndarray) -> np.ndarray:
    """max h over the nominal position and the 8 positions 7 in away (clamped into the paddock inset by 1 in): 0 =
    robustly unhidden (the occlusion v2 rule)."""
    P = np.asarray(P, float)
    hs = [mask_lookup(mk, P)]
    for k in range(N_DIR):
        a = 2 * np.pi * k / N_DIR
        hs.append(mask_lookup(mk, P + PERTURB_IN * np.array([np.cos(a), np.sin(a)])))
    with np.errstate(invalid="ignore"):
        return np.max(np.stack(hs, -1), -1)


# ----------------------------------------------------------------------------------------------- validation
def validate_camera_night(frames: pd.DataFrame, dets: pd.DataFrame, box_mapper, state_fn) -> dict:
    """frames: image, sec (s since the night start of the frame time); dets: image, x1..y2, conf (>= VAL_CONF used).
    box_mapper(sec, uv) -> paddock in (NaN outside support); state_fn(secs, shift_s) -> wiser_state dict.
    -> stats incl. pass."""
    import wiser_assist_p0 as wp
    fr = frames.sort_values("sec").reset_index(drop=True)
    d = dets[dets["conf"] >= VAL_CONF]
    rows_xy, rows_k = [], []
    for k, r in enumerate(fr.itertuples()):
        g = d[d["image"] == r.image]
        if not len(g):
            continue
        uv = np.c_[(g["x1"] + g["x2"]) / 2, (g["y1"] + g["y2"]) / 2]
        P = np.asarray(box_mapper(float(r.sec), uv), float).reshape(-1, 2)
        f = np.isfinite(P).all(1)
        rows_xy.append(P[f])
        rows_k.append(np.full(int(f.sum()), k))
    xy = np.vstack(rows_xy) if rows_xy else np.zeros((0, 2))
    kk = np.concatenate(rows_k) if rows_k else np.zeros(0, int)
    o = np.argsort(kk, kind="stable")
    xy, kk = xy[o], kk[o]
    nfr = len(fr)
    secs_fr = fr["sec"].to_numpy(float)
    res = {"n_frames": int(nfr), "n_boxes_conf_ge_0_5": int(d["image"].isin(fr["image"]).sum()), "n_det_mapped": int(len(xy))}
    start = np.searchsorted(kk, np.arange(nfr), "left")
    end = np.searchsorted(kk, np.arange(nfr), "right")
    for tag, shift in (("real", 0.0), ("control", VAL_CONTROL_S)):
        st = state_fn(secs_fr, shift)
        avail = st["ok"] & ~st["house"]
        aj, r = wp.hungarian(xy, start, end, np.flatnonzero(end > start), st["P"], avail, VAL_GATE)
        _, nd = wp.nearest(xy, kk, st["P"], avail) if len(xy) else (None, np.zeros(0))
        m = aj >= 0
        res[f"{tag}_n_pairs"] = int(m.sum())
        res[f"{tag}_median_in"] = float(np.median(r[m])) if m.any() else float("nan")
        res[f"{tag}_p90_in"] = float(np.percentile(r[m], 90)) if m.any() else float("nan")
        res[f"{tag}_within14_share"] = float(np.mean(nd <= VAL_WITHIN)) if len(xy) else float("nan")
        res[f"{tag}_animals_outside_mean"] = float(avail.sum(1).mean()) if nfr else float("nan")
    enough = res["n_det_mapped"] >= VAL_MIN_DET and res["real_n_pairs"] >= VAL_MIN_PAIRS
    c1 = bool(np.isfinite(res["real_median_in"]) and res["real_median_in"] <= VAL_WITHIN)
    c2 = bool(np.isfinite(res["real_within14_share"]) and np.isfinite(res["control_within14_share"])
              and res["real_within14_share"] >= VAL_RATIO * res["control_within14_share"] and res["real_within14_share"] > 0)
    res.update({"enough_data": bool(enough), "criterion_median": c1, "criterion_control": c2,
                "map_validated": bool(enough and c1 and c2),
                "verdict": "pass" if (enough and c1 and c2) else ("insufficient data" if not enough else "fail")})
    return res


# ----------------------------------------------------------------------------------------------- kit table
def kit_rows(night: date, secs: np.ndarray, st: dict, pix: dict, hidden: np.ndarray, validated: bool) -> pd.DataFrame:
    """The 1-Hz table of one camera-night: rows (second, animal), KIT_COLUMNS, booleans 0/1."""
    n, J = st["ok"].shape
    t = np.datetime64(night_start(night)) + (np.asarray(secs) * 1e9).astype("timedelta64[ns]")
    t_str = pd.to_datetime(t).strftime(FMT).to_numpy()
    ok = st["ok"]
    u = pix["u"].reshape(n, J, 2)
    df = pd.DataFrame({
        "t_pc": np.repeat(t_str, J), "animal": np.tile(np.array(ANIMALS, dtype=object), n),
        "tracked": ok.ravel().astype(np.int8), "in_house": (st["house"] & ok).ravel().astype(np.int8),
        "u": np.round(u[..., 0].ravel(), 1), "v": np.round(u[..., 1].ravel(), 1),
        "r_px": np.round(pix["r_px"].reshape(n, J).ravel(), 1),
        "hidden_share": np.round(np.where(ok, hidden, np.nan).ravel(), 3),
        "in_support": (pix["in_support"].reshape(n, J) & ok).ravel().astype(np.int8),
        "motion": np.vectorize(MOTION_NAME.get)(np.where(ok, st["motion"], 0)).ravel(),
        "all_tracked": np.repeat(st["all_tracked"].astype(np.int8), J),
        "map_validated": np.int8(1 if validated else 0)})
    return df[KIT_COLUMNS]


# ----------------------------------------------------------------------------------------------- build
def calib():
    import ch01_occlusion as oc
    return oc.calib()


def landmark_checks_cam(cam_name: str, cams: dict, scene, houses: dict) -> pd.DataFrame:
    """Occluder model vs the user's labels in this camera (ch01_occlusion's checks, camera-generic): label-plane fit
    residuals of the labelled poles, capsule checks of the others, house_2 (09-18 labels) and house_1 (09-04 cohort
    labels through the inverse noon affine; they are the house_1 fit's data, so that row is a fit residual)."""
    import ch01_occlusion as oc
    cam = cams[cam_name]
    lab18 = json.loads((LM_DIR / LM_0918[cam_name]).read_text(encoding="utf-8"))["landmarks"]
    off = oc.IR2COL.get(cam_name, (0.0, 0.0))
    rows = []
    for p, rec in scene.poles.items():
        if rec.get("planes") is not None:
            rows.append({"object": f"pole_{p}", "model": "label planes", "kind": "fit residual (not independent)",
                         **oc.plane_resid_px(cam, lab18, p, rec["planes"], off)})
        r = oc.check_pole(cam, rec, lab18, p, off)
        if r is not None:
            rows.append({"object": f"pole_{p}", "model": "capsule (" + rec["source"].split(" (")[0] + ")",
                         "kind": "check" if rec.get("planes") is None else "reference", **r})
    rows.append({"object": "house_2", "model": "calibration pose", "kind": "check",
                 **oc.check_house(cam, houses["house_2"], lab18, "HOUSE_2", offset=off)})
    A, _ = oc.noon_affines()
    labc = json.loads((LM_DIR / LM_0904[cam_name]).read_text(encoding="utf-8"))["landmarks"]
    Ai = oc.inv_affine(A[cam_name])
    rows.append({"object": "house_1 (09-04 labels)", "model": "fitted cohort pose", "kind": "fit residual (labels are the fit data)",
                 **oc.check_house(cam, houses["house_1"], labc, "HOUSE_1",
                                  to18=lambda pts: np.asarray(pts, float) @ Ai[:, :2].T + Ai[:, 2], offset=off)})
    df = pd.DataFrame(rows)
    df["flagged"] = (df["median_px"] > oc.FLAG_PX) & (df["kind"] != "reference")
    return df


MAX_SNAP_S = 0.5      # amendment 3: a pool frame more than 0.5 s after its target second (video gap) is not used


def usable_pool_frames(fr: pd.DataFrame) -> pd.DataFrame:
    """Pool frames that were grabbed (ok) and lie within MAX_SNAP_S after their target second (so the WISER row of that
    second describes them); one row per image (two targets in a video gap can land on the same frame)."""
    f = fr[(fr["ok"] == 1) & (fr["snap_s"].astype(float) <= MAX_SNAP_S)]
    return f.drop_duplicates("image").copy()


def load_pool(pool: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    fr = usable_pool_frames(pd.read_csv(pool / "pool_frames.csv"))
    det = pd.read_csv(pool / "pool_detections.csv.gz")
    return fr, det


def build(pool: Path, out: Path | None, cams_sel=CAMS, log=print) -> Path:
    import ch01_occlusion as oc
    import wiser_assist_p0 as wp
    t_start = time.perf_counter()
    started = datetime.now().isoformat(timespec="seconds")
    if out is None:
        import output_paths as op
        out = op.run_dir(NAME, COHORT, make_figures=False)
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} exists and is not empty - never overwritten")
    out.mkdir(parents=True, exist_ok=True)
    logf = open(out / "build_log.txt", "w", encoding="utf-8")

    def lg(msg):
        log(msg)
        logf.write(msg + "\n")
        logf.flush()

    lg(f"kit -> {out.as_posix()}")
    m, L, mj = load_map()
    if L != 0.0:
        raise SystemExit("accepted L is not 0 - the kit assumes the phase-0 lag 0")
    cams, cd = calib()
    C = fc.Corrections(COHORT)
    houses = wp.load_houses()
    handling = load_handling()
    fr_pool, det_pool = load_pool(pool)
    fr_pool["t_frame_dt"] = pd.to_datetime(fr_pool["t_frame"])
    noon_A, noon_meta = oc.noon_affines()
    geo, val_rows, files_used = {}, [], {}
    for cam_name in cams_sel:
        cam = cams[cam_name]
        scene, place, prow, tri, hh = oc.build_scene(cams, cd, mj, lg, v2=True, cam=cam_name)
        mk = oc.visibility_mask(scene, paddock_mask_path())
        sm, step = support_mask_0918(cam)
        occ18 = occluders_0918(cam_name, cam, scene, noon_A)
        chk = landmark_checks_cam(cam_name, cams, scene, hh)
        d = out / cam_name
        d.mkdir(exist_ok=True)
        np.savez_compressed(d / "visibility_mask.npz", x_in=mk["x_in"], y_in=mk["y_in"], h=mk["h"].astype(np.float32),
                            h_by_object=mk["h_by_object"].astype(np.float32), objects=mk["objects"])
        chk.drop(columns=["pieces"], errors="ignore").to_csv(d / "checks.csv", index=False)
        geo[cam_name] = {"scene": scene, "mask": mk, "support_mask": sm, "step": step, "occ18": occ18, "checks": chk,
                         "place": place, "pole_models": {p: r["model"] for p, r in scene.poles.items()},
                         "pole_sources": {p: r["source"] for p, r in scene.poles.items()}}
        lg(f"{cam_name}: scene ({sum(r.get('planes') is not None for r in scene.poles.values())} label-plane poles), mask "
           f"{np.isfinite(mk['h']).sum()} cells, support cells {int(sm.sum())}, occluders {len(occ18)}; checks: "
           + "; ".join(f"{r.object} {r.median_px:.1f} px{' FLAG' if r.flagged else ''}" for r in chk.itertuples()))
        if cam_name == "CH01":                              # reproduction check vs the occlusion v2 run's mask
            v2 = OUT_ROOT / "2026c" / "cv_field_ch01_occlusion_20261006_1555" / "visibility_mask.npz"
            if v2.exists():
                z = np.load(v2)
                sup = z["in_support"]
                same = np.allclose(np.asarray(z["h"])[sup], mk["h"][sup], equal_nan=True)
                geo[cam_name]["v2_mask_reproduced"] = bool(same)
                lg(f"CH01 mask vs occlusion v2 run on its {int(sup.sum())} support cells: identical {same}")
    support_by, occ_by = {c: {} for c in cams_sel}, {c: {} for c in cams_sel}
    rain = {}
    for night in NIGHTS:
        t_n = time.perf_counter()
        nf = load_night_fixes(night, handling=handling)
        files_used[str(night)] = nf["meta"]
        secs, tdt = kit_seconds(night, handling)
        st = wiser_state(nf, secs, m, houses)
        n, J = st["ok"].shape
        for cam_name in cams_sel:
            cam = cams[cam_name]
            g = geo[cam_name]
            cs = correction_samples(C, cam_name, night)
            if cs is None:
                lg(f"{cam_name} {night}: no correction samples - skipped")
                continue
            # the night-level geometry at the median correction of the night
            A_med = np.median(cs["mats"], axis=0)
            W, H = cam.upright_size
            support_by[cam_name][str(night)] = {**support_polygon(g["support_mask"], g["step"], A_med, W, H),
                                                "correction": "median of the night's usable samples"}
            occ_by[cam_name][str(night)] = {"occluders": occluders_for(g["occ18"], A_med, W, H),
                                            "correction": "median of the night's usable samples"}
            # validation from the pool frames of this camera-night
            fp = fr_pool[(fr_pool["camera"] == cam_name) & (fr_pool["night"] == str(night))].copy()
            fp["sec"] = (fp["t_frame_dt"] - pd.Timestamp(night_start(night))).dt.total_seconds()
            cache: dict = {}

            def box_mapper(sec, uv, cam_name=cam_name, night=night):
                t = night_start(night) + timedelta(seconds=float(sec))
                p, info = C.to_paddock(cam_name, t, uv, z_mm=Z_MM, units="in")
                return np.full((len(uv), 2), np.nan) if p is None else np.asarray(p, float).reshape(-1, 2)

            def state_fn(s, shift, nf=nf):
                key = (shift, tuple(np.round(s, 4)))
                if key not in cache:
                    cache[key] = wiser_state(nf, s, m, houses, shift_s=shift)
                return cache[key]

            v = validate_camera_night(fp[["image", "sec"]], det_pool[det_pool["image"].isin(fp["image"])], box_mapper, state_fn)
            flag = "ok" if all(f == "ok" for f in cs["flags"]) else "+".join(sorted(set(cs["flags"])))
            rows0 = C.samples(cam_name, night)
            rain_mm = float(rows0[0]["rain_mm_night"]) if rows0 and rows0[0].get("rain_mm_night") not in ("", None) else np.nan
            rain[str(night)] = rain_mm
            val_rows.append({"camera": cam_name, "night": str(night), "correction_flag": flag,
                             "dawn_closure_px": rows0[0].get("night_quality_px") if rows0 else None,
                             "correction_samples_used": cs["n_used"], "rain_mm_night": rain_mm, **v})
            # pixels of every tracked animal-second
            A = affines_at(cs, secs)
            AA = np.repeat(A, J, 0)
            P = st["P"].reshape(-1, 2).copy()
            P[~st["ok"].ravel()] = np.nan
            pix = to_pixels(cam, P, AA)
            hidden = np.where(pix["in_frame"].reshape(n, J), mask_lookup(g["mask"], st["P"]), np.nan)
            df = kit_rows(night, secs, st, pix, hidden, v["map_validated"])
            df.to_csv(out / cam_name / f"{night}.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
            lg(f"{cam_name} {night}: {len(secs)} s, tracked {st['ok'].mean():.3f}, in support "
               f"{(pix['in_support'] & st['ok'].ravel()).sum()} animal-s; validation {v['verdict']} (median "
               f"{v['real_median_in']:.2f} in, within-14 {v['real_within14_share']:.3f} vs control {v['control_within14_share']:.3f}, "
               f"{v['n_det_mapped']} det, {v['real_n_pairs']} pairs); correction {flag}")
        lg(f"night {night}: {time.perf_counter() - t_n:.0f} s")
    for cam_name in cams_sel:
        W, H = cams[cam_name].upright_size
        (out / cam_name / "support.json").write_text(json.dumps(jsonable(
            {"camera": cam_name, "frame_size": [W, H], "by_night": support_by[cam_name],
             "about": "outline of the image region where the camera's verified calibration maps the ground at z = 60 mm "
                      "(largest outer contour of 16-px cells of the 09-18 frame, carried into each night by the median "
                      "frame correction; upright cohort px)"}), indent=1), encoding="utf-8")
        (out / cam_name / "occluders.json").write_text(json.dumps(jsonable(
            {"camera": cam_name, "frame_size": [W, H], "by_night": occ_by[cam_name],
             "about": "image outlines (upright cohort px) of what can hide a rat: pole strips and house silhouettes = "
                      "convex hulls of the user's edge labels (poles not labelled in this camera: the projected 2.4-m "
                      "capsule); carried into each night by the median frame correction. Hidden = do not box."}), indent=1),
            encoding="utf-8")
    val = pd.DataFrame(val_rows)
    val.to_csv(out / "validation.csv", index=False)
    write_kit_json(out, pool, val, geo, files_used, mj, started, time.perf_counter() - t_start, cams_sel, cd, noon_meta)
    write_readme(out, val, geo, cams_sel)
    lg(f"kit done in {time.perf_counter() - t_start:.0f} s")
    logf.close()
    from select_label_round1 import VERIFY_PY, write_manifest_sha     # same manifest format as the label package
    (out / "verify_manifest.py").write_text(VERIFY_PY, encoding="utf-8")
    n = write_manifest_sha(out)
    log(f"kit MANIFEST_sha256.csv: {n} files")
    return out


def write_kit_json(out: Path, pool: Path, val: pd.DataFrame, geo: dict, files_used: dict, mj: dict, started: str,
                   runtime: float, cams_sel, cd: Path, noon_meta: dict) -> None:
    import cv2
    import scipy
    rec = REPO.parent / "Field_2026_Social_Recording"
    track_files = sorted({f for nm in files_used.values() for lab in nm.values() for f in lab["files"]})
    cal = {}
    import paddock_map as pm
    fit = Path(pm.FIT)
    for p in (fit, fit.parent / "ray_correction.json", cd / "terrain_2026-10-02.json", cd / "survey_2026-10-03.json",
              cd / "paddock_map.py", cd / "raymap.py", cd / "HOUSE_CHECK_2026-10-04_revg.txt"):
        if p.exists():
            cal[p.as_posix()] = sha256(p)
    inputs = {"phase0_mapping_json": {"path": (P0_RUN / "mapping.json").as_posix(), "sha256": sha256(P0_RUN / "mapping.json")},
              "frame_corrections_csv": {"path": f"results/{COHORT}/{DIRECTION}/reports/cv_field_frame_corrections_{COHORT}.csv",
                                        "sha256": sha256(REPO / "results" / COHORT / DIRECTION / "reports" / f"cv_field_frame_corrections_{COHORT}.csv")},
              "wiser_rois": {"path": ROIS.relative_to(REPO).as_posix(), "sha256": sha256(ROIS)},
              "handling_windows": {"path": HANDLING.relative_to(REPO).as_posix(), "sha256": sha256(HANDLING)},
              "identities": {"path": IDENTITIES.relative_to(REPO).as_posix(), "sha256": sha256(IDENTITIES)},
              "house1_cohort_pose": {"path": "cv/configs/house1_cohort_pose_2026c.json",
                                     "sha256": sha256(REPO / "cv" / "configs" / "house1_cohort_pose_2026c.json")},
              "landmark_labels": {f"cv/configs/landmarks/2026c/{f}": sha256(LM_DIR / f) for c in cams_sel for f in (LM_0918[c], LM_0904[c])},
              "noon_affines": noon_meta.get("run_dir"),
              "calibration_files": cal,
              "default_tracks": {f: sha256(Path(f)) for f in track_files},
              "pool_frames_csv": {"path": (pool / "pool_frames.csv").as_posix(), "sha256": sha256(pool / "pool_frames.csv")},
              "pool_detections": {"path": (pool / "pool_detections.csv.gz").as_posix(), "sha256": sha256(pool / "pool_detections.csv.gz")}}
    pj = pool / "pool_run.json"
    if pj.exists():
        inputs["pool_run_json"] = {"path": pj.as_posix(), "sha256": sha256(pj)}
        try:
            inputs["yolo_v5"] = json.loads(pj.read_text(encoding="utf-8")).get("weights")
        except Exception:  # noqa: BLE001
            pass
    kit = {"schema": "wiser_pixel_kit/1", "cohort": COHORT, "plan": PLAN, "made_by": "cv/cv_field/build_wiser_pixel_kit.py --build",
           "started": started, "runtime_s": runtime,
           "commits": {"analysis_repo": git_commit(REPO), "recording_repo": git_commit(rec)},
           "versions": {"python": sys.version.split()[0], "numpy": np.__version__, "pandas": pd.__version__,
                        "scipy": scipy.__version__, "opencv": cv2.__version__},
           "map": {"accepted_map": mj["accepted_map"], "L_s": mj["accepted_L_s"], "adopted": mj.get("adopted"),
                   "acceptance": mj.get("acceptance"), "source": (P0_RUN / "mapping.json").as_posix(),
                   "model": "paddock = s R(theta) (wiser - c) + c + d (inches)"},
           "cameras": list(cams_sel), "nights": [str(n) for n in NIGHTS],
           "excluded_nights": {str(TEST_NIGHT): "frozen test night: no model on its frames, no validation, no WISER pixels",
                               "2026-09-11": "population change 09-11 19:40 (five untagged females) - after the cut"},
           "night_window": "D 21:00:00 -> D+1 04:20:00 field-PC local (EDT), whole seconds; handling windows +- 5 min have no rows",
           "columns": KIT_COLUMNS, "booleans": "0/1",
           "units": {"u": "upright cohort px (7680 x 2160)", "v": "upright cohort px", "r_px": "px", "hidden_share": "0-1"},
           "params": {"z_mm": Z_MM, "ring_in": RING_IN, "gap_max_s": GAP_MAX, "house_zone_buffer_in": HOUSE_BUF,
                      "still_speed_in_s": STILL_SPEED, "loco_speed_in_s": LOCO_SPEED, "handling_margin_s": HANDLING_MARGIN_S,
                      "validation": {"conf": VAL_CONF, "gate_in": VAL_GATE, "within_in": VAL_WITHIN, "control_shift_s": VAL_CONTROL_S,
                                     "ratio": VAL_RATIO, "min_mapped_detections": VAL_MIN_DET, "min_pairs": VAL_MIN_PAIRS},
                      "robust_hidden": {"perturbation_in": PERTURB_IN, "directions": N_DIR, "clamp_inset_in": CLAMP_INSET_IN}},
           "population": {"animals": list(ANIMALS), "extra_tag_labels": EXTRA_LABEL,
                          "rules": ["before 09-11 19:40 the paddock holds the six tagged animals SF07-SF12",
                                    "SF12 has no track on night 08-30 (its second tag SF12_tag12376 is used where it has fixes)",
                                    "SF11 untracked 09-02 00:03 -> 08:20 (tag battery) and from 09-07 06:10:45 (implant + tag off; "
                                    "the animal stayed in the paddock)",
                                    "all_tracked = all six tracked at that second (only then may 'no WISER animal near' or "
                                    "'all animals in houses' be used)"]},
           "validation_table": val.to_dict("records"),
           "geometry": {c: {"pole_models": g["pole_models"], "pole_sources": g["pole_sources"], "placement": g["place"],
                            "v2_mask_reproduced": g.get("v2_mask_reproduced"),
                            "checks": g["checks"].drop(columns=["pieces"], errors="ignore").to_dict("records")}
                        for c, g in geo.items()},
           "inputs": inputs}
    (out / "kit.json").write_text(json.dumps(jsonable(kit), indent=1), encoding="utf-8")


def write_readme(out: Path, val: pd.DataFrame, geo: dict, cams_sel) -> None:
    L = ["# WISER pixel kit — cohort 2026c, CH01 / CH02 panoramas", "",
         f"Made by `cv/cv_field/build_wiser_pixel_kit.py --build` (analysis repo, plan `{PLAN}`, part A). Everything needed to "
         "draw WISER hints on a cohort-3 CH01/CH02 night frame and to choose frames for labelling, without the WISER "
         "database, the calibration or the frame corrections. `kit.json` holds the versions, commits, the WISER → paddock "
         "map, the sha256 of every input and the camera-night validation table.", "",
         "**WISER positions are proposals (± ~14 in), never boxes. WISER never makes a negative: an untagged or untracked "
         "animal is not shown, so an empty frame is only ever the labeller's verdict. Only visible animals get a box.**", "",
         "## Layout", "",
         "- `kit.json`, `README.md`, `validation.csv` (one row per camera-night), `build_log.txt`.",
         "- `<CAM>/<YYYY-MM-DD>.csv.gz` — one per night D (D 21:00:00 → D+1 04:20:00, field-PC local), one row per whole second "
         "and animal (SF07–SF12). Handling windows ± 5 min have no rows. Nights 08-30 … 09-10 except **09-05 (frozen test "
         "night: no table)**; 09-11 is after the population change.",
         "- `<CAM>/support.json` — `{camera, frame_size, by_night: {night: {polygon: [[u, v], …]}}}`: the image region where the "
         "camera's verified calibration maps the ground (night-specific because the camera moves a little between nights).",
         "- `<CAM>/occluders.json` — `{camera, frame_size, by_night: {night: {occluders: [{name, kind: pole|house, polygon, "
         "source}]}}}`: what can hide a rat, as image outlines. **Hidden = do not box.**",
         "- `<CAM>/visibility_mask.npz` — `x_in`, `y_in` (2-in cell centres, paddock inches), `h` (hidden share of a rat at "
         "each cell as seen from this camera, 9 sample points at 30/60/90 mm × 3 lateral), `h_by_object`, `objects`.",
         "- `<CAM>/checks.csv` — occluder model vs the user's labels (px).", "",
         "## Table columns (booleans are 0/1)", "",
         "| column | meaning |", "|---|---|",
         "| `t_pc` | field-PC local time `YYYY-MM-DD HH:MM:SS` (the video file names' clock; never the OSD) |",
         "| `animal` | SF07 … SF12 |",
         "| `tracked` | 1 = WISER locates the animal at this second (two clean fixes ≤ 5 s apart bracket it) |",
         "| `in_house` | 1 = inside a house zone (WISER house rectangle + 14 in); 0 when untracked |",
         "| `u`, `v` | upright pano pixel (7680 × 2160) of the animal's back (z = 60 mm); empty when untracked or outside the frame |",
         "| `r_px` | radius in px of a 14-in circle at that position (area-equivalent radius of the 14-in ring's image) |",
         "| `hidden_share` | share of the rat's 9 sample points hidden by a pole or house at the nominal position (visibility mask); empty when untracked or outside the frame |",
         "| `in_support` | 1 = in the frame and inside the camera's verified calibration support (pixel trustworthy) |",
         "| `motion` | still / active / locomoting (head IMU where its QC passes, else the WISER track speed: < 2 in/s still, 2–10 active, ≥ 10 locomoting) / unknown (untracked) |",
         "| `all_tracked` | 1 = all six animals tracked at this second — only then may 'no WISER animal near a box' or 'all animals in houses' be used |",
         "| `map_validated` | 1 = this camera-night passed the map validation; **0 = draw no WISER circles and use no WISER-dependent quota** |", "",
         "## How a pixel is made", "",
         "WISER default track (V3 for the implanted animals, B2 where the head IMU fails; clean fixes only; linear between the "
         "two fixes around the second) → paddock inches by the accepted phase-0 map (similarity, lag 0; `kit.json` → `map`) → "
         "09-18 calibration pixel by the rev g camera's inverse at z = 60 mm above the local ground → this night's pixel by "
         "the frame-correction affine interpolated to the second (cohort cameras move up to ~30 px between nights). "
         "Precision: WISER ± 3–7 in (+ the map's 4.4-in test median on 09-06), the calibration's exploratory error (76 mm "
         "cross-camera median), CH01/CH02 corrections ≤ 3 px on passing nights.", "",
         "## Selection rules that use the kit (plan B3; how `select_label_round1.py` reads it)", "",
         "- Use WISER only where `map_validated` = 1. Rain nights (≥ 1 mm 21:00–04:20: 08-31, 09-03, 09-09) feed strata only, "
         "not the suspected-miss quota.",
         "- *Visible suspected miss*: an animal with `tracked` 1, `in_house` 0, `in_support` 1, hidden share 0 **robustly** "
         "(the mask is 0 at the nominal position and at the 8 positions 7 in away, clamped 1 in inside the paddock) and no "
         "YOLO box (conf ≥ 0.25) within 20 in. Code that has only this kit (no paddock coordinates) can approximate: "
         "`hidden_share` = 0 and no occluder outline within `r_px / 2` of (u, v) (conservative: also drops animals in front "
         "of an occluder), and 'within 20 in' ≈ a box centre within `20 / 14 × r_px` px of (u, v).",
         "- *Social*: ≥ 2 animals tracked, in support and outside the house zones within 20 in of each other.",
         "- *Hard negative*: `all_tracked` 1 and every animal `in_house` 1.", "",
         "## Camera-night validation (plan A2)", "",
         "From the round-1 pool frames of each camera-night: YOLO v5 boxes (conf ≥ 0.5) mapped to paddock inches vs the WISER "
         "animals outside the house zones at the frame time; pass = median matched residual (per-frame Hungarian, gate 30 in) "
         "≤ 14 in AND within-14-in share ≥ 2 × that of WISER shifted + 1 h (same map); at least 20 mapped detections and 10 "
         "pairs.", "",
         "| camera | night | detections | pairs | median (in) | within-14 | control | verdict |", "|---|---|---:|---:|---:|---:|---:|---|"]
    for r in val.itertuples():
        L.append(f"| {r.camera} | {r.night} | {r.n_det_mapped} | {r.real_n_pairs} | {r.real_median_in:.2f} | "
                 f"{r.real_within14_share:.3f} | {r.control_within14_share:.3f} | {r.verdict} |")
    L += ["", "## Population (carry into every use)", "",
          "Before 09-11 19:40 the paddock holds six tagged animals. SF12 has no track on night 08-30 (its second tag is used "
          "where it has fixes); SF11 is untracked 09-02 00:03 → 08:20 and from 09-07 06:10:45 (its implant and tag came off; "
          "the animal stayed in the paddock). Before the 09-03 13:59 WISER restart the WISER frame was shifted 7–18 in "
          "(the validation decides whether those nights are usable).", "",
          "## Copy to Q: and verify", "",
          "Copy the whole folder next to the label package (same parent), e.g. `robocopy <kit folder> <Q: target> /E /COPY:DAT`. "
          "Verify the copy with `python <copied kit folder>/verify_manifest.py`: it checks every file against "
          "`MANIFEST_sha256.csv` (path, bytes, sha256) and prints `OK`. Q: is written only by the user."]
    (out / "README.md").write_text("\n".join(L) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------------------------- selftest
class SynthCam:
    """Synthetic camera: 09-18 px = 10 x paddock in + (100, 50), frame 7680 x 2160, support = x in [5, 470]."""
    upright_size = (7680, 2160)
    centre = np.array([0.0, 0.0, 2000.0])

    def to_paddock_inv(self, xy, z_mm=0.0, units="in"):
        return np.asarray(xy, float).reshape(-1, 2) * 10.0 + [100.0, 50.0]

    def _ground(self, uv, z_mm):
        return (np.asarray(uv, float).reshape(-1, 2) - [100.0, 50.0]) / 10.0 * 25.4

    def to_paddock(self, uv, z_mm=0.0, units="in"):
        p = (np.asarray(uv, float).reshape(-1, 2) - [100.0, 50.0]) / 10.0
        p[~((p[:, 0] >= 5) & (p[:, 0] <= 470))] = np.nan
        return p if units == "in" else p * 25.4


def selftest() -> int:
    import csv
    import tempfile
    ok = True

    def rec(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}", flush=True)

    import wiser_assist_p0 as wp
    rng = np.random.default_rng(0)
    # 1. interpolation = phase 0's Tracks.at
    s = np.sort(rng.uniform(0, 200, 300))
    s = np.r_[s[:100], s[100:] + 30]                       # a 30-s gap
    df = pd.DataFrame({"s": s, "x": rng.normal(0, 5, len(s)), "y": rng.normal(0, 5, len(s)),
                       "imu_state": rng.integers(0, 4, len(s)), "vx": rng.normal(0, 3, len(s)), "vy": rng.normal(0, 3, len(s))})
    tq = np.linspace(-5, 240, 1000)
    X, S, okk = wp.Tracks({"a": df[["s", "x", "y", "imu_state"]]}, GAP_MAX).at(tq)
    x, y, st, sp, k = interp_fixes(df, tq)
    rec("interp_fixes = phase-0 Tracks.at (positions, IMU state, located)",
        np.array_equal(okk[:, 0], k) and np.allclose(X[k, 0, 0], x[k]) and np.allclose(X[k, 0, 1], y[k]) and np.array_equal(S[k, 0], st[k])
        and not k[(tq > s[99] + 1) & (tq < s[100] - 1)].any())
    # 2. motion codes
    okm = np.array([True, True, True, True, True, False])
    imu = np.array([1, 3, 0, 0, -1, 2], np.int8)
    spd = np.array([20.0, 0.1, 1.0, 5.0, 12.0, 1.0])
    rec("motion: IMU state where usable, else speed < 2 still / 2-10 active / >= 10 locomoting; untracked unknown",
        motion_codes(okm, imu, spd).tolist() == [1, 3, 1, 2, 3, 0])
    # 3. vectorised correction = Corrections.correction (synthetic table incl. a flagged sample)
    A1 = np.array([[1.001, 0.002, 10.0], [-0.002, 0.999, -4.0]])
    A2 = np.array([[1.000, 0.004, 14.0], [-0.004, 1.000, -2.0]])
    A3 = np.array([[0.999, 0.001, 17.0], [-0.001, 1.001, 1.0]])
    with tempfile.TemporaryDirectory() as tmp:
        tab = Path(tmp) / "t.csv"
        keys = ["camera", "night", "time", "flag", "night_quality", "night_quality_px", "rain_mm_night", *fc.A_KEYS]
        with open(tab, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for t, A, flag in (("2026-09-03 21:00:00", A1, "ok"), ("2026-09-04 00:00:00", A2 + 3, "sample"),
                               ("2026-09-04 01:00:00", A2, "ok"), ("2026-09-04 04:20:00", A3, "ok")):
                w.writerow({"camera": "CH01", "night": "2026-09-03", "time": t, "flag": flag, "night_quality": "dawn closure",
                            "night_quality_px": 1.5, "rain_mm_night": 0.0, **dict(zip(fc.A_KEYS, A.ravel()))})
        C = fc.Corrections(table=tab)
        cs = correction_samples(C, "CH01", date(2026, 9, 3))
        tq = np.r_[rng.uniform(-600, NIGHT_SEC + 600, 300), 0.0, 4 * 3600.0, NIGHT_SEC]
        Av = affines_at(cs, tq)
        worst = 0.0
        for t, A in zip(tq, Av):
            B, _ = C.correction("CH01", night_start(date(2026, 9, 3)) + timedelta(seconds=float(t)))
            worst = max(worst, float(np.abs(fc.invert(A) - B).max()))
        rec("vectorised night affines = Corrections.correction at 303 times (flagged sample skipped)", worst < 1e-9,
            f"max |diff| {worst:.2e}; used {cs['n_used']} of {cs['n_all']}")
    # 4. pixels on a synthetic camera: round trip, support, r_px = 14 x 10 px/in x det(A)^(1/2)
    cam = SynthCam()
    P = np.array([[100.0, 100.0], [480.0, 100.0], [np.nan, np.nan], [2.0, 50.0]])
    A = np.repeat(np.array([[[1.0, 0.0, 5.0], [0.0, 1.0, -3.0]]]), len(P), 0)
    px = to_pixels(cam, P, A)
    rec("pixels: round trip, in-frame / support flags, r_px = 140 px",
        np.allclose(px["u"][0], [1105.0, 1047.0]) and px["in_support"].tolist() == [True, False, False, False]
        and px["in_frame"].tolist() == [True, True, False, True] and abs(px["r_px"][0] - 140.0) < 1e-6)
    # 5. support polygon of a rectangle of cells
    msk = np.zeros((135, 480), bool)
    msk[20:100, 50:400] = True
    sp_ = support_polygon(msk, 16, np.array([[1.0, 0.0, 10.0], [0.0, 1.0, 0.0]]), 7680, 2160)
    pg = np.asarray(sp_["polygon"])
    rec("support polygon: outer contour of the support cells, shifted by the correction",
        abs(pg[:, 0].min() - (50 * 16 + 8 + 10)) < 1e-6 and abs(pg[:, 1].max() - (99 * 16 + 8)) < 1e-6 and sp_["share_of_support_cells"] == 1.0,
        f"{pg.min(0)} {pg.max(0)}")
    sq = clip_poly(np.array([[-10.0, -10.0], [20.0, -10.0], [20.0, 20.0], [-10.0, 20.0]]), 15, 15)
    area = 0.5 * abs(np.dot(sq[:, 0], np.roll(sq[:, 1], 1)) - np.dot(sq[:, 1], np.roll(sq[:, 0], 1)))
    occ = occluders_for([{"name": "pole_X", "kind": "pole", "polygon18": np.array([[-50.0, 5.0], [10.0, 5.0], [10.0, 9.0]]),
                          "source": "s"}, {"name": "pole_Y", "kind": "pole", "polygon18": np.array([[-50.0, 5.0], [-40.0, 5.0],
                                                                                                    [-40.0, 9.0]]), "source": "s"}],
                        np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]), 100, 100)
    rec("occluder outlines clipped to the frame; an outline fully outside is dropped",
        abs(area - 225.0) < 1e-9 and [o["name"] for o in occ] == ["pole_X"] and min(p[0] for p in occ[0]["polygon"]) == 0.0)
    # 6. robust hidden from a mask: a hidden strip at x 100-110 in
    xs, ys = np.arange(1, 480, 2.0), np.arange(1, 240, 2.0)
    h = np.zeros((len(ys), len(xs)))
    h[:, (xs > 100) & (xs < 110)] = 1.0
    mk = {"x_in": xs, "y_in": ys, "h": h}
    Pq = np.array([[105.0, 50.0], [95.0, 50.0], [80.0, 50.0], [np.nan, 1.0]])
    rec("mask lookup nominal + robust (+- 7 in): inside 1, 5 in from the strip robust 1 but nominal 0, 25 in away 0",
        np.nan_to_num(mask_lookup(mk, Pq), nan=-1).tolist() == [1.0, 0.0, 0.0, -1.0]
        and np.nan_to_num(robust_hidden(mk, Pq), nan=-1).tolist() == [1.0, 1.0, 0.0, -1.0])
    # 7. validation: aligned boxes pass; boxes 25 in off fail; too few -> insufficient
    nfr = 60
    secs = np.arange(nfr) * 10.0
    truth = rng.uniform([50, 30], [430, 210], (nfr, 6, 2))
    house = np.zeros((nfr, 6), bool)
    house[:, 5] = True

    def mk_state(shift):
        Pp = truth if shift == 0 else np.roll(truth, 17, axis=0)[:, ::-1]
        return {"P": Pp, "ok": np.ones((nfr, 6), bool), "house": house}
    frames = pd.DataFrame({"image": [f"f{i}" for i in range(nfr)], "sec": secs})
    det = []
    for i in range(nfr):
        for j in range(4):
            q = truth[i, j] + rng.normal(0, 3, 2)
            det.append({"image": f"f{i}", "x1": q[0] - 2, "y1": q[1] - 2, "x2": q[0] + 2, "y2": q[1] + 2, "conf": 0.8})
    det = pd.DataFrame(det)
    v_ok = validate_camera_night(frames, det, lambda s_, uv: np.asarray(uv, float), lambda s_, sh: mk_state(sh))
    v_bad = validate_camera_night(frames, det, lambda s_, uv: np.asarray(uv, float) + [25.0, 0.0], lambda s_, sh: mk_state(sh))
    v_few = validate_camera_night(frames.iloc[:3], det, lambda s_, uv: np.asarray(uv, float), lambda s_, sh: {k: v[:3] for k, v in mk_state(sh).items()})
    rec("validation: aligned -> pass (median ~3.8 in, control far lower); 25 in off -> fail; 3 frames -> insufficient",
        v_ok["verdict"] == "pass" and v_ok["real_median_in"] < 6 and v_ok["control_within14_share"] < 0.5 * v_ok["real_within14_share"]
        and v_bad["verdict"] == "fail" and v_few["verdict"] == "insufficient data",
        f"ok {v_ok['real_median_in']:.2f} / {v_ok['real_within14_share']:.2f} vs {v_ok['control_within14_share']:.2f}; "
        f"bad {v_bad['verdict']}; few {v_few['verdict']}")
    # 8. kit rows: columns, booleans 0/1, untracked rows empty, handling seconds excluded
    n = 4
    stt = {"ok": np.array([[True] * 6, [True] * 5 + [False], [False] * 6, [True] * 6]),
           "house": np.zeros((n, 6), bool), "motion": np.full((n, 6), 2, np.int8)}
    stt["all_tracked"] = stt["ok"].all(1)
    pix = {"u": np.full((n * 6, 2), 100.0), "r_px": np.full(n * 6, 50.0), "in_support": np.ones(n * 6, bool)}
    dfk = kit_rows(date(2026, 9, 6), np.array([0.0, 1.0, 2.0, 3.0]), stt, pix, np.zeros((n, 6)), True)
    rec("kit rows: exact columns, 6 rows per second, booleans 0/1, untracked -> motion unknown / in_support 0",
        list(dfk.columns) == KIT_COLUMNS and len(dfk) == 24 and set(dfk["tracked"].unique()) <= {0, 1}
        and dfk.loc[11, "motion"] == "unknown" and dfk.loc[11, "in_support"] == 0 and dfk["t_pc"].iloc[0] == "2026-09-06 21:00:00"
        and dfk["all_tracked"].tolist()[6:12] == [0] * 6 and dfk["map_validated"].eq(1).all())
    s_k, _ = kit_seconds(date(2026, 8, 30), [(datetime(2026, 8, 31, 3, 30), datetime(2026, 8, 31, 7, 30))])
    rec("kit seconds: 21:00 -> 04:20 minus the handling window - 5 min (03:25 on)",
        s_k[0] == 0 and s_k[-1] == (6 * 3600 + 25 * 60) - 1 and len(s_k) == 6 * 3600 + 25 * 60)
    rec("nights: 08-30 .. 09-10 without the test night 09-05", len(NIGHTS) == 11 and TEST_NIGHT not in NIGHTS
        and NIGHTS[0] == date(2026, 8, 30) and NIGHTS[-1] == date(2026, 9, 10))
    rec("night_of: 03:00 -> previous date; 12:00 -> None", night_of(datetime(2026, 9, 7, 3)) == date(2026, 9, 6)
        and night_of(datetime(2026, 9, 7, 12)) is None)
    print(("PASS" if ok else "FAIL") + " — build_wiser_pixel_kit self-test")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--pool", default=None, help="label_round1_pool run folder (select_label_round1.py --pool)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--cameras", nargs="+", default=list(CAMS))
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.build:
        if not a.pool:
            ap.error("--build needs --pool")
        build(Path(a.pool), Path(a.out) if a.out else None, tuple(a.cameras))
        return 0
    ap.error("nothing to do (--selftest or --build)")


if __name__ == "__main__":
    raise SystemExit(main())
