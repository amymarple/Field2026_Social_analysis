r"""ch01_occlusion.py — CH01 occlusion geometry for the WISER-flagged suspected YOLO misses (poles, houses).

Plan (pre-registered, the specification): implementation_plan/2026-10-06-ch01-occlusion-geometry.md (+ dated amendments).
Data map: cv/cv_field/DATA_MAP_c1yolo_wiser.md (section H).

Inputs (read-only): the phase-0 run $OUT/2026c/cv_field_wiser_assist_p0_20261005_2211 (mapping.json = accepted WISER ->
paddock map; fn_episodes.csv; support_polygon.json); the per-second suspected-miss table, rebuilt here with the unchanged
phase-0 code (wiser_assist_p0.prepare_boxes + part_c) and checked byte-for-byte against fn_episodes.csv; the default
WISER tracks; the frozen calibration ../Field_2026_Social_Recording/calibration_qc/ (rev g: paddock_map.load(), its
terrain, survey_2026-10-03.json, HOUSE_CHECK_2026-10-04_revg.txt); the operator's pole / house edge labels
cv/configs/landmarks/2026c/landmarks_CH0*_20260918_*.json and landmarks_CH01_20260904_120002.json.

Geometry (absolute paddock mm; z as in the calibration: camera centre, terrain heights and the fitted house soil levels
share one datum):
  camera  CH01 = paddock_map.load()["CH01"].centre (RayCamera).
  poles   finite cylinders (capsule test) from the ground to 2.4 m above it; axis = the pole-check line re-measured on the
          rev g cameras where clean (amendment 1), else the vertical design-grid line (field_layout.json); radius =
          perimeter / 2 pi (survey: B1, B2, B3), else their mean.
  houses  convex parts as in calibration_qc/house_check.py: body box (footprint 62.55 x 45.72 cm, soil -> eave height)
          + gable-roof prism (ridge length 66 cm, eave lines +- run from the ridge, ridge height); house_2 at the rev g
          house-check pose (centre, ridge angle, soil level); house_1 at the WISER ROI centre through the accepted map
          (ridge angle = ROI orientation + map rotation, soil level of its own house-check fit).
  rat     9 sample points: heights 30 / 60 / 90 mm above the local ground x lateral 0 / +-40 mm across the horizontal
          line of sight. A point is hidden if the segment camera -> point meets an occluder. h = hidden share.
Classes per second: hidden h >= 0.8, partly 0 < h < 0.8, clear h = 0 (nominal position); robust over the nominal + 8
positions 7 in away: robustly hidden / robustly clear; the 4-way category (amendment 1): hidden (robustly hidden), clear
(robustly clear), partly (nominal 0 < h < 0.8), ambiguous (otherwise). Episode class = majority category (ties ->
ambiguous). Visibility mask: 2-in grid over CH01's support. Checks: model edges projected into CH01 (09-18 px) vs the
labelled edges, median px distance per object, flag > 20 px.

BLINDING: per-episode classes go only to episodes.csv (and seconds.csv.gz) in the run folder; the report, figures and
console show pooled numbers over all episodes and the mask only.

Usage (base Python C:/Python313):
  python cv/cv_field/ch01_occlusion.py --selftest
  python cv/cv_field/ch01_occlusion.py --poles-only          # the pole re-measurement table (an input; no occlusion result)
  python cv/cv_field/ch01_occlusion.py --run [--phase0 <run>] [--out <run dir>]
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
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _p in (str(HERE), str(HERE.parent), str(REPO / "wiser" / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
# the repo's frame_correction must be imported before calibration_qc/ (which has its own frame_correction.py) enters sys.path
import frame_correction as _fc  # noqa: E402

OUT_ROOT = Path(os.environ.get("FIELD2026_ANALYSIS_OUT_ROOT", "D:/Field2026_analysis_out"))
PHASE0_RUN = OUT_ROOT / "2026c" / "cv_field_wiser_assist_p0_20261005_2211"
COHORT, DIRECTION, NAME = "2026c", "cv_field", "cv_field_ch01_occlusion"
REPORT_NAME = "cv_field_ch01_occlusion_2026c.md"
POINTER_NAME = "run_manifest_ch01_occlusion_2026c.json"
FIG_SUB = "ch01_occlusion"
PLAN = "implementation_plan/2026-10-06-ch01-occlusion-geometry.md"
LM_DIR = REPO / "cv" / "configs" / "landmarks" / "2026c"
LM_0918 = "landmarks_CH01_20260918_135730.json"
LM_0904 = "landmarks_CH01_20260904_120002.json"
LAYOUT = REPO / "cv" / "configs" / "field_layout.json"
ROIS = REPO / "wiser" / "configs" / "wiser_rois.json"
CAM = "CH01"
IN, CM = 25.4, 10.0
IR2COL = {"CH01": (0.68, -0.39), "CH02": (0.90, 0.67)}      # 09-18 IR -> colour px, as calibration_qc/house_check.py
POLE_H = 2400.0                                             # occluder height above the ground (mm)
POLE_CHECK_TOP = 3000.0                                     # pole edges projected to this height for the label check
RAT_Z = (30.0, 60.0, 90.0)
RAT_HALF = 40.0
HIDDEN_T = 0.8
PERTURB_IN, N_DIR = 7.0, 8
MASK_STEP_IN = 2.0
FLAG_PX = 20.0
ZS = (0, 300, 600, 900, 1200, 1500, 1800, 2100)
# pole re-measurement on the rev g cameras: a pole's measured line is used only if clean (amendment 1, before results)
CLEAN = {"min_cams": 2, "min_angle_deg": 10.0, "max_cam_resid_mm": 50.0, "min_heights": 2, "max_line_resid_mm": 50.0,
         "max_from_design_mm": 400.0, "max_lean_deg": 15.0}   # lean bound added after the pole table, before any occlusion result
# house_2: rev g house check (HOUSE_CHECK_2026-10-04_revg.txt); house_1: its soil level from the same check
HOUSE2_POSE = {"cx_in": 342.4, "cy_in": 117.7, "ridge_deg": 92.0, "soil_below_mm": 93.0}
HOUSE1_SOIL_BELOW_MM = 58.0
HOUSE1_CALIB_POSTMOVE = {"cx_in": 147.5, "cy_in": 121.7, "ridge_deg": 90.3}    # 09-18 (post-move): checks only
CATS = ("hidden", "partly", "clear", "ambiguous")


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


# ----------------------------------------------------------------------------------------------- calibration access
def calib():
    """(cams, calib_dir) of the frozen release (rev g: RayCamera with terrain)."""
    import landmark_guides
    cd = landmark_guides.calib_dir()
    if str(cd) not in sys.path:
        sys.path.insert(0, str(cd))
    import paddock_map as pm
    return pm.load(), cd


def survey(cd: Path) -> dict:
    return json.loads((cd / "survey_2026-10-03.json").read_text(encoding="utf-8"))


def ground(cam, xy_mm) -> np.ndarray:
    """Local ground height (mm, the calibration's datum) under paddock points."""
    xy = np.asarray(xy_mm, float).reshape(-1, 2)
    return cam.terrain.height(xy) if getattr(cam, "terrain", None) is not None else np.zeros(len(xy))


def project3d(cam, P: np.ndarray) -> np.ndarray:
    """Absolute 3-D paddock points (mm) -> upright pixels via the camera's own inverse (z above the local ground per point).
    NaN where it does not converge or the ray direction misses the point by > 0.02 deg."""
    P = np.asarray(P, float).reshape(-1, 3)
    out = np.full((len(P), 2), np.nan)
    g = ground(cam, P[:, :2])
    for i, (p, gz) in enumerate(zip(P, g)):
        try:
            uv = np.asarray(cam.to_paddock_inv(p[:2][None], z_mm=float(p[2] - gz), units="mm"), float).reshape(-1, 2)[0]
        except Exception:  # noqa: BLE001
            continue
        if not np.isfinite(uv).all():
            continue
        d = cam.rays(uv[None])[0]
        v = p - cam.centre
        ang = np.degrees(np.arccos(np.clip(d @ v / np.linalg.norm(v) / np.linalg.norm(d), -1, 1)))
        if ang <= 0.02:
            out[i] = uv
    return out


def load_labels(name: str) -> dict:
    return json.loads((LM_DIR / name).read_text(encoding="utf-8"))


def densify(poly, step: float = 15.0) -> np.ndarray:
    """Polyline -> points every ~step px (as house_check.py)."""
    p = np.asarray(poly, float).reshape(-1, 2)
    if len(p) < 2:
        return p
    pts = []
    for a, b in zip(p[:-1], p[1:]):
        n = max(2, int(np.hypot(*(b - a)) / step))
        pts += list(a + (b - a) * np.linspace(0, 1, n, endpoint=False)[:, None])
    pts.append(p[-1])
    return np.array(pts)


# ----------------------------------------------------------------------------------------------- poles
def design_poles() -> dict:
    lay = json.loads(LAYOUT.read_text(encoding="utf-8"))["poles"]
    return {k: np.array(v, float) * CM for k, v in lay.items()}              # cm -> mm


def pole_rows(cams: dict, label_files: list[Path], design: dict) -> list[dict]:
    """pole_check.py's method on the given cameras: per camera, pole and height z, the pole's angular L / R edges at the
    design distance -> diameter and the axis's lateral offset (mm) perpendicular to the line of sight."""
    rows = []
    for f in label_files:
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        cam = d["camera"]
        if cam not in cams:
            continue
        c = cams[cam]
        W, H = c.upright_size
        fw, fh = d["frame_size_upright"]
        sc = np.array([W / fw, H / fh])
        off = np.array(IR2COL.get(cam, (0.0, 0.0))) if "20260918" in Path(f).name else np.zeros(2)
        for p, xy in design.items():
            Lp, Rp = d["landmarks"].get(f"POLE_{p}_L"), d["landmarks"].get(f"POLE_{p}_R")
            if not Lp or not Rp:
                continue
            v = xy - c.centre[:2]
            rho = float(np.linalg.norm(v))
            phi0 = np.arctan2(v[1], v[0])

            def edge(poly):
                pts = np.vstack([np.asarray(q, float).reshape(-1, 2) for q in poly])
                r = c.rays(pts * sc + off)
                h = np.hypot(r[:, 0], r[:, 1])
                z = c.centre[2] + rho * r[:, 2] / h
                az = np.unwrap(np.arctan2(r[:, 1], r[:, 0]) - phi0)
                az = (az + np.pi) % (2 * np.pi) - np.pi
                o = np.argsort(z)
                return z[o], az[o]
            zl, al = edge(Lp)
            zr, ar = edge(Rp)
            lo, hi = max(zl.min(), zr.min()), min(zl.max(), zr.max())
            for z in ZS:
                if lo <= z <= hi:
                    a1, a2 = np.interp(z, zl, al), np.interp(z, zr, ar)
                    rows.append({"cam": cam, "pole": p, "z": z, "rho": rho, "diam": abs(a2 - a1) * rho, "lat": (a1 + a2) / 2 * rho})
    return rows


def triangulate(cams: dict, rows: list[dict], design: dict) -> pd.DataFrame:
    """Per pole and height with >= 2 cameras: the axis point from the cameras' lateral offsets (least squares of the
    lines of sight, as pole_check.py), the largest camera residual and the smallest crossing angle."""
    out = []
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame()
    for (p, z), g in df.groupby(["pole", "z"]):
        if len(g) < 2:
            continue
        A, b, lines, dirs = [], [], [], []
        for r in g.itertuples():
            c = cams[r.cam]
            X = design[p]
            v = X - c.centre[:2]
            u = v / np.linalg.norm(v)
            nrm = np.array([-u[1], u[0]])
            q = X + nrm * r.lat
            A.append(nrm)
            b.append(nrm @ q)
            lines.append((nrm, q))
            dirs.append(u)
        sol = np.linalg.lstsq(np.array(A), np.array(b), rcond=None)[0]
        res = max(abs(n @ (sol - q)) for n, q in lines)
        ang = min(np.degrees(np.arccos(np.clip(abs(dirs[i] @ dirs[j]), -1, 1))) for i in range(len(dirs)) for j in range(i + 1, len(dirs)))
        out.append({"pole": p, "z": z, "cams": "+".join(sorted(g["cam"].str[2:])), "n_cams": len(g), "x": sol[0], "y": sol[1],
                    "dx_design": sol[0] - design[p][0], "dy_design": sol[1] - design[p][1], "cam_resid_max": res, "min_angle_deg": ang,
                    "diam_med": float(g["diam"].median())})
    return pd.DataFrame(out)


def pole_lines(cams: dict, label_files: list[Path], radii: dict) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """-> ({pole: {A, B (axis at ground-ish z and top, abs mm), r, source, ...}}, per-camera rows, triangulation table).
    A measured line needs >= min_heights heights each with >= 2 cameras crossing at >= min_angle_deg (camera residual
    <= max_cam_resid_mm when >= 3 cameras), a straight line in z through them with residuals <= max_line_resid_mm, and
    its 1.05-m point within max_from_design_mm of the design grid; else the vertical design line."""
    design = design_poles()
    rows = pole_rows(cams, label_files, design)
    tri = triangulate(cams, rows, design)
    c1 = cams[CAM]
    r_mean = float(np.mean(list(radii.values())))
    poles = {}
    for p, xy in design.items():
        g0 = ground(c1, xy[None])[0]
        rec = {"pole": p, "design_xy_mm": xy.tolist(), "radius_mm": radii.get(p, r_mean),
               "radius_source": "survey perimeter / 2 pi" if p in radii else "mean of the surveyed poles"}
        t = tri[(tri["pole"] == p)] if len(tri) else pd.DataFrame()
        if len(t):
            t = t[(t["min_angle_deg"] >= CLEAN["min_angle_deg"]) & ((t["n_cams"] < 3) | (t["cam_resid_max"] <= CLEAN["max_cam_resid_mm"]))]
        why = ""
        ok = len(t) >= CLEAN["min_heights"]
        if not ok:
            why = f"{len(t)} clean heights (< {CLEAN['min_heights']})"
        else:
            z = t["z"].to_numpy(float)
            cx = np.polyfit(z, t["x"].to_numpy(float), 1)
            cy = np.polyfit(z, t["y"].to_numpy(float), 1)
            res = np.hypot(np.polyval(cx, z) - t["x"], np.polyval(cy, z) - t["y"]).max()
            p105 = np.array([np.polyval(cx, 1050.0), np.polyval(cy, 1050.0)])
            dd = float(np.linalg.norm(p105 - xy))
            lean0 = float(np.degrees(np.arctan(np.hypot(cx[0], cy[0]))))
            if res > CLEAN["max_line_resid_mm"]:
                ok, why = False, f"line residual {res:.0f} mm > {CLEAN['max_line_resid_mm']:.0f}"
            elif dd > CLEAN["max_from_design_mm"]:
                ok, why = False, f"{dd:.0f} mm from design > {CLEAN['max_from_design_mm']:.0f}"
            elif lean0 > CLEAN["max_lean_deg"]:
                ok, why = False, f"fitted lean {lean0:.0f} deg > {CLEAN['max_lean_deg']:.0f} (not credible)"
        if ok:
            gz = ground(c1, p105[None])[0]
            za, zb = gz, gz + POLE_H
            A = np.array([np.polyval(cx, za), np.polyval(cy, za), za])
            B = np.array([np.polyval(cx, zb), np.polyval(cy, zb), zb])
            lean = float(np.degrees(np.arctan(np.hypot(cx[0], cy[0]))))
            rec.update({"source": "measured (pole-check method on rev g, " + ",".join(sorted(set(t["cams"]))) + ")", "A": A, "B": B,
                        "heights_mm": [int(v) for v in z], "line_resid_mm": float(res), "lean_deg": lean,
                        "at_1050_mm": p105.tolist(), "from_design_mm": dd})
        else:
            A = np.array([xy[0], xy[1], g0])
            B = np.array([xy[0], xy[1], g0 + POLE_H])
            rec.update({"source": f"design grid (field_layout.json): {why}", "A": A, "B": B, "lean_deg": 0.0})
        poles[p] = rec
    return poles, pd.DataFrame(rows), tri


# ----------------------------------------------------------------------------------------------- houses
def house_model(sv: dict, name: str, cx_in: float, cy_in: float, ridge_deg: float, soil_z: float) -> dict:
    """house_check.py's rigid house (survey values) at a pose: convex parts (half-spaces n.x <= c, absolute mm) for the
    occlusion test and the edge list (name, class, P0, P1) for the label check."""
    s = sv[name]
    L2, W2 = sv["body_footprint"]["length"] * CM / 2, sv["body_footprint"]["width"] * CM / 2
    he = np.mean([v for v in s["eave_height"].values() if v is not None]) * CM if isinstance(s["eave_height"], dict) else s["eave_height"] * CM
    rr = s["ridge_height"]
    hr = (np.mean(list(rr.values())) if isinstance(rr, dict) else rr) * CM
    run = np.sqrt((np.mean(s["roof_slope_ridge_to_eave"]) * CM) ** 2 - (hr - he) ** 2)
    R2 = s["ridge_length"] * CM / 2
    th = np.radians(ridge_deg)
    Rm = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    c = np.array([cx_in, cy_in]) * IN

    def to_abs(P):
        P = np.asarray(P, float).reshape(-1, 3)
        return np.c_[P[:, :2] @ Rm.T + c, P[:, 2] + soil_z]

    def halfspaces(local_planes):
        """local planes (n_local (3,), point (3,)) with n pointing out -> absolute (N, C)."""
        Ns, Cs = [], []
        for n, p in local_planes:
            n = np.asarray(n, float)
            na = np.r_[Rm @ n[:2], n[2]]
            pa = to_abs(np.asarray(p, float))[0]
            Ns.append(na / np.linalg.norm(na))
            Cs.append(Ns[-1] @ pa)
        return np.array(Ns), np.array(Cs)

    body = halfspaces([((1, 0, 0), (L2, 0, 0)), ((-1, 0, 0), (-L2, 0, 0)), ((0, 1, 0), (0, W2, 0)), ((0, -1, 0), (0, -W2, 0)),
                       ((0, 0, 1), (0, 0, he)), ((0, 0, -1), (0, 0, 0))])
    k = (hr - he) / run                                                    # roof planes: z = hr - k |v|
    roof = halfspaces([((1, 0, 0), (R2, 0, 0)), ((-1, 0, 0), (-R2, 0, 0)), ((0, 0, -1), (0, 0, he)),
                       ((0, k, 1), (0, 0, hr)), ((0, -k, 1), (0, 0, hr))])
    E = [("ridge", "ru", (-R2, 0, hr), (R2, 0, hr)), ("eave+", "ru", (-R2, run, he), (R2, run, he)),
         ("eave-", "ru", (-R2, -run, he), (R2, -run, he))]
    wall = he - 30.0
    for su in (-1, 1):
        for sv_ in (-1, 1):
            E.append((f"rake{su:+d}{sv_:+d}", "rv", (su * R2, sv_ * run, he), (su * R2, 0, hr)))
            E.append((f"corner{su:+d}{sv_:+d}", "bz", (su * L2, sv_ * W2, 0), (su * L2, sv_ * W2, wall)))
        E.append((f"base_v{su:+d}", "bv", (su * L2, -W2, 0), (su * L2, W2, 0)))
    for sv_ in (-1, 1):
        E.append((f"base_u{sv_:+d}", "bu", (-L2, sv_ * W2, 0), (L2, sv_ * W2, 0)))
    edges = [(n, cl, to_abs(a)[0], to_abs(b)[0]) for n, cl, a, b in E]
    foot = to_abs([(-L2, -W2, 0), (L2, -W2, 0), (L2, W2, 0), (-L2, W2, 0)])[:, :2]
    return {"name": name, "parts": [body, roof], "edges": edges, "footprint_mm": foot, "centre_in": [cx_in, cy_in],
            "ridge_deg": ridge_deg, "soil_z_mm": soil_z, "eave_mm": float(he), "ridge_mm": float(hr), "run_mm": float(run),
            "ridge_len_mm": float(2 * R2), "footprint_cm": [2 * L2 / CM, 2 * W2 / CM]}


# ----------------------------------------------------------------------------------------------- segment tests
def seg_seg_dist(C: np.ndarray, Q: np.ndarray, A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Distance between each segment C -> Q_i and the segment A -> B (Ericson, closest points of two segments)."""
    d1 = Q - C
    d2 = B - A
    r = C - A
    a = np.einsum("ij,ij->i", d1, d1)
    e = float(d2 @ d2)
    f = float(r @ d2)
    c = d1 @ r
    b = d1 @ d2
    den = a * e - b * b
    s = np.where(den > 1e-12, np.clip((b * f - c * e) / np.where(den > 1e-12, den, 1), 0, 1), 0.0)
    t = (b * s + f) / e
    lo, hi = t < 0, t > 1
    t = np.clip(t, 0, 1)
    s = np.where(lo, np.clip(-c / np.maximum(a, 1e-12), 0, 1), s)
    s = np.where(hi, np.clip((b - c) / np.maximum(a, 1e-12), 0, 1), s)
    p1 = C + d1 * s[:, None]
    p2 = A + np.outer(t, d2)
    return np.linalg.norm(p1 - p2, axis=1)


def seg_hits_convex(C: np.ndarray, Q: np.ndarray, N: np.ndarray, Cc: np.ndarray, eps: float = 1e-9) -> np.ndarray:
    """Does each segment C -> Q_i pass through the convex solid {x: N x <= Cc}? (Cyrus-Beck clipping.)"""
    d = Q - C
    t0 = np.zeros(len(Q))
    t1 = np.ones(len(Q))
    ok = np.ones(len(Q), bool)
    for n, cc in zip(N, Cc):
        num = cc - n @ C
        den = d @ n
        par = np.abs(den) < eps
        ok &= ~(par & (num < 0))
        with np.errstate(divide="ignore", invalid="ignore"):
            t = num / den
        t1 = np.where(~par & (den > 0), np.minimum(t1, t), t1)
        t0 = np.where(~par & (den < 0), np.maximum(t0, t), t0)
    return ok & (t0 < t1 - 1e-9)


class Scene:
    """Camera centre + occluders (cylinders and convex houses)."""

    def __init__(self, C: np.ndarray, poles: dict, houses: list[dict], ground_fn):
        self.C = np.asarray(C, float)
        self.poles = poles
        self.houses = houses
        self.ground = ground_fn
        self.names = [f"pole_{p}" for p in poles] + [h["name"].lower() for h in houses]

    def hidden_by(self, Q: np.ndarray) -> np.ndarray:
        """(n, n_objects) bool: is the segment camera -> Q_i blocked by each object."""
        Q = np.asarray(Q, float).reshape(-1, 3)
        out = np.zeros((len(Q), len(self.names)), bool)
        k = 0
        for p, rec in self.poles.items():
            if rec.get("planes") is not None:                                # v2: CH01's own L / R edge planes
                out[:, k] = planes_hidden(self.C, Q, rec["planes"])
            else:
                out[:, k] = seg_seg_dist(self.C, Q, rec["A"], rec["B"]) <= rec["radius_mm"]
            k += 1
        for h in self.houses:
            hit = np.zeros(len(Q), bool)
            for N, Cc in h["parts"]:
                hit |= seg_hits_convex(self.C, Q, N, Cc)
            out[:, k] = hit
            k += 1
        return out

    def rat_points(self, xy_mm: np.ndarray) -> np.ndarray:
        """(n, 9, 3): 3 heights x 3 lateral offsets across the horizontal line of sight."""
        xy = np.asarray(xy_mm, float).reshape(-1, 2)
        g = self.ground(xy)
        u = xy - self.C[:2]
        u = u / np.maximum(np.linalg.norm(u, axis=1, keepdims=True), 1e-9)
        nrm = np.stack([-u[:, 1], u[:, 0]], 1)
        pts = np.zeros((len(xy), 9, 3))
        k = 0
        for z in RAT_Z:
            for o in (-RAT_HALF, 0.0, RAT_HALF):
                pts[:, k, :2] = xy + o * nrm
                pts[:, k, 2] = g + z
                k += 1
        return pts

    def assess(self, xy_mm: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """-> (h (n,), hidden counts per object (n, n_objects))."""
        pts = self.rat_points(xy_mm)
        n = len(pts)
        hb = self.hidden_by(pts.reshape(-1, 3)).reshape(n, 9, -1)
        return hb.any(2).mean(1), hb.sum(1)


PADDOCK_IN = (0.0, 480.0, 0.0, 240.0)
CLAMP_INSET_IN = 1.0


def classify(scene: Scene, xy_in: np.ndarray, clamp: bool = False, stats: dict | None = None) -> pd.DataFrame:
    """Per position: nominal h / class / occluder, and the robustness over 8 positions 7 in away. clamp (v2): a perturbed
    position outside the paddock inset by 1 in is clamped to that boundary (stats['clamped'] counts them)."""
    xy = np.asarray(xy_in, float).reshape(-1, 2)
    h0, c0 = scene.assess(xy * IN)
    hs, cnt = [h0], c0.copy()
    lo = np.array([PADDOCK_IN[0] + CLAMP_INSET_IN, PADDOCK_IN[2] + CLAMP_INSET_IN])
    hi = np.array([PADDOCK_IN[1] - CLAMP_INSET_IN, PADDOCK_IN[3] - CLAMP_INSET_IN])
    n_cl = 0
    for k in range(N_DIR):
        a = 2 * np.pi * k / N_DIR
        pk = xy + PERTURB_IN * np.array([np.cos(a), np.sin(a)])
        if clamp:
            pc = np.clip(pk, lo, hi)
            n_cl += int(np.any(pc != pk, axis=1).sum())
            pk = pc
        hk, ck = scene.assess(pk * IN)
        hs.append(hk)
        cnt += ck
    if stats is not None:
        stats["clamped"] = stats.get("clamped", 0) + n_cl
        stats["perturbations"] = stats.get("perturbations", 0) + N_DIR * len(xy)
    H = np.stack(hs, 1)
    nominal = np.where(h0 >= HIDDEN_T, "hidden", np.where(h0 > 0, "partly", "clear"))
    rob_h = (H >= HIDDEN_T).all(1)
    rob_c = (H == 0).all(1)
    cat = np.where(rob_h, "hidden", np.where(rob_c, "clear", np.where((h0 > 0) & (h0 < HIDDEN_T), "partly", "ambiguous")))
    names = np.array(scene.names, dtype=object)
    occ = np.where(cnt.sum(1) > 0, names[np.argmax(cnt, 1)], "none")
    occ_nom = np.where(c0.sum(1) > 0, names[np.argmax(c0, 1)], "none")
    return pd.DataFrame({"h": h0, "h_min9": H.min(1), "h_max9": H.max(1), "nominal_class": nominal, "robust_hidden": rob_h,
                         "robust_clear": rob_c, "category": cat, "occluder_nominal": occ_nom, "occluder": occ})


def episode_classes(sec: pd.DataFrame) -> pd.DataFrame:
    """Per episode: shares of the 4 categories, class = the unique majority (ties -> ambiguous), occluder = the most
    frequent occluder among its non-clear seconds."""
    rows = []
    for eid, g in sec[sec["episode_id"] > 0].groupby("episode_id"):
        cnt = g["category"].value_counts()
        sh = {c: float(cnt.get(c, 0) / len(g)) for c in CATS}
        mx = max(cnt.values)
        top = [c for c in CATS if cnt.get(c, 0) == mx]
        cls = top[0] if len(top) == 1 else "ambiguous"
        nc = g[g["category"] != "clear"]["occluder"]
        occ = nc.value_counts().index[0] if len(nc) and cls != "clear" else "none"
        rows.append({"episode_id": int(eid), "animal": g["animal"].iloc[0], "n_seconds": int(len(g)),
                     **{f"share_{c}": sh[c] for c in CATS}, "class": cls, "occluder": occ,
                     "h_mean": float(g["h"].mean())})
    return pd.DataFrame(rows)


def pooled(ep: pd.DataFrame, sec: pd.DataFrame) -> dict:
    """Pooled shares over all episodes / suspected-miss seconds (the only numbers that leave the run folder)."""
    out = {"n_episodes": int(len(ep)), "n_seconds": int(len(sec))}
    out["episodes_by_class"] = {c: {"n": int((ep["class"] == c).sum()), "share": float((ep["class"] == c).mean())} for c in CATS}
    out["seconds_by_category"] = {c: {"n": int((sec["category"] == c).sum()), "share": float((sec["category"] == c).mean())} for c in CATS}
    out["seconds_by_nominal_class"] = {c: float((sec["nominal_class"] == c).mean()) for c in ("hidden", "partly", "clear")}
    occ_e = ep[ep["class"] != "clear"].groupby(["occluder", "class"]).size().unstack(fill_value=0)
    out["episodes_by_occluder"] = {o: {c: int(occ_e.loc[o].get(c, 0)) for c in CATS if c != "clear"} for o in occ_e.index}
    occ_s = sec[sec["category"] != "clear"].groupby(["occluder", "category"]).size().unstack(fill_value=0)
    out["seconds_by_occluder"] = {o: {c: int(occ_s.loc[o].get(c, 0)) for c in CATS if c != "clear"} for o in occ_s.index}
    out["episode_seconds_weighted"] = {c: float(ep[f"share_{c}"].mul(ep["n_seconds"]).sum() / max(ep["n_seconds"].sum(), 1)) for c in CATS}
    if "ring_crosses_wall" in sec:
        nc = sec[sec["category"] != "clear"]
        out["ring_crosses_wall"] = {"ambiguous_share": float(sec.loc[sec["category"] == "ambiguous", "ring_crosses_wall"].mean()),
                                    "by_occluder_share": {o: float(g["ring_crosses_wall"].mean()) for o, g in nc.groupby("occluder")}}
    return out


# ----------------------------------------------------------------------------------------------- mask
def support_path(phase0: Path):
    from matplotlib.path import Path as MPath
    sp = json.loads((phase0 / "support_polygon.json").read_text(encoding="utf-8"))
    return [MPath(np.asarray(p, float)) for p in sp["polygons_in"]], sp


def visibility_mask(scene: Scene, paths) -> dict:
    xs = np.arange(MASK_STEP_IN / 2, 480, MASK_STEP_IN)
    ys = np.arange(MASK_STEP_IN / 2, 240, MASK_STEP_IN)
    X, Y = np.meshgrid(xs, ys)
    P = np.stack([X.ravel(), Y.ravel()], 1)
    ins = np.zeros(len(P), bool)
    for pth in paths:
        ins |= pth.contains_points(P)
    h = np.full(len(P), np.nan)
    hb = np.full((len(scene.names), len(P)), np.nan)
    idx = np.flatnonzero(ins)
    for i0 in range(0, len(idx), 4000):
        ii = idx[i0:i0 + 4000]
        hh, cnt = scene.assess(P[ii] * IN)
        h[ii] = hh
        hb[:, ii] = (cnt / 9.0).T
    return {"x_in": xs, "y_in": ys, "in_support": ins.reshape(X.shape), "h": h.reshape(X.shape),
            "h_by_object": hb.reshape(len(scene.names), *X.shape), "objects": np.array(scene.names)}


# ----------------------------------------------------------------------------------------------- landmark checks
def point_poly_dist(pts: np.ndarray, poly: np.ndarray) -> np.ndarray:
    """Distance of each point to a polyline (px)."""
    pts = np.asarray(pts, float).reshape(-1, 2)
    poly = np.asarray(poly, float).reshape(-1, 2)
    poly = poly[np.isfinite(poly).all(1)]
    if len(poly) < 2:
        return np.full(len(pts), np.nan)
    a, b = poly[:-1], poly[1:]
    ab = b - a
    L2 = np.maximum((ab ** 2).sum(1), 1e-12)
    t = np.clip(((pts[:, None, :] - a[None]) * ab[None]).sum(2) / L2[None], 0, 1)
    proj = a[None] + t[..., None] * ab[None]
    return np.sqrt(((pts[:, None, :] - proj) ** 2).sum(2)).min(1)


def pole_silhouette(cam, rec: dict, top: float = POLE_CHECK_TOP, step: float = 50.0) -> tuple[np.ndarray, np.ndarray]:
    """The pole's two silhouette edges seen from the camera, projected (px): left (smaller mean u), right."""
    A, B = rec["A"], rec["B"]
    zz = np.arange(A[2], A[2] + top + 1e-6, step)
    w = (zz - A[2]) / (B[2] - A[2])
    ax = A[None] + w[:, None] * (B - A)[None]
    u = ax[:, :2] - cam.centre[:2]
    u = u / np.linalg.norm(u, axis=1, keepdims=True)
    nrm = np.stack([-u[:, 1], u[:, 0]], 1)
    e1 = np.c_[ax[:, :2] + rec["radius_mm"] * nrm, ax[:, 2]]
    e2 = np.c_[ax[:, :2] - rec["radius_mm"] * nrm, ax[:, 2]]
    p1, p2 = project3d(cam, e1), project3d(cam, e2)
    return (p1, p2) if np.nanmean(p1[:, 0]) <= np.nanmean(p2[:, 0]) else (p2, p1)


def house_edges_px(cam, house: dict, step: float = 10.0) -> list[tuple[str, str, np.ndarray]]:
    out = []
    for n, cl, a, b in house["edges"]:
        k = max(2, int(np.linalg.norm(b - a) / step) + 1)
        P = a[None] + np.linspace(0, 1, k)[:, None] * (b - a)[None]
        out.append((n, cl, project3d(cam, P)))
    return out


def label_class(key: str) -> tuple[str, ...]:
    """house_check.py's rule: roof labels -> any roof edge; BASE_Z -> vertical corners; other base labels -> base edges."""
    if key.startswith("ROOF"):
        return ("ru", "rv")
    if key.endswith("_Z"):
        return ("bz",)
    return ("bu", "bv")


def check_house(cam, house: dict, labels: dict, prefix: str, to18=None, offset=(0.0, 0.0)) -> dict:
    """Each label piece -> the allowed projected edge with the smallest median distance; per object the median over all
    label points. to18: maps label px -> 09-18 px (cohort labels)."""
    E = house_edges_px(cam, house)
    dists, pieces = [], []
    for key in ("ROOF_X", "ROOF_Y", "BASE_X", "BASE_Y", "BASE_Z"):
        for p in labels.get(f"{prefix}_{key}", []):
            pts = densify(p)
            if len(pts) < 2:
                continue
            pts = (to18(pts) if to18 is not None else pts) + np.asarray(offset)
            best = None
            for n, cl, poly in E:
                if cl not in label_class(key):
                    continue
                dd = point_poly_dist(pts, poly)
                if np.isfinite(dd).any() and (best is None or np.nanmedian(dd) < np.nanmedian(best[1])):
                    best = (n, dd)
            if best is not None:
                dists.append(best[1])
                pieces.append(f"{key}:{best[0]} {np.nanmedian(best[1]):.0f}")
    d = np.concatenate(dists) if dists else np.array([np.nan])
    return {"n_points": int(np.isfinite(d).sum()), "median_px": float(np.nanmedian(d)), "p90_px": float(np.nanpercentile(d, 90)),
            "pieces": "; ".join(pieces)}


def check_pole(cam, rec: dict, labels: dict, p: str, offset=(0.0, 0.0)) -> dict | None:
    Lp, Rp = labels.get(f"POLE_{p}_L"), labels.get(f"POLE_{p}_R")
    if not Lp or not Rp:
        return None
    left, right = pole_silhouette(cam, rec)
    d = []
    for pieces, poly in ((Lp, left), (Rp, right)):
        for q in pieces:
            d.append(point_poly_dist(densify(q) + np.asarray(offset), poly))
    d = np.concatenate(d)
    return {"n_points": int(np.isfinite(d).sum()), "median_px": float(np.nanmedian(d)), "p90_px": float(np.nanpercentile(d, 90)), "pieces": ""}


# ----------------------------------------------------------------------------------------------- per-second table
def rebuild_seconds(phase0: Path, log=print) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Phase-0 part C re-run with the unchanged code (prepare_boxes + part_c) -> (per-second table of every eligible
    animal-second, the regenerated episodes, checks). The episodes must equal fn_episodes.csv byte for byte."""
    import wiser_assist_p0 as wp
    prm = wp.Params()
    mj = json.loads((phase0 / "mapping.json").read_text(encoding="utf-8"))
    am = mj["accepted_map"]
    m = wp.Map(float(am["dx_in"]), float(am["dy_in"]), float(np.radians(am["theta_deg"])), float(am["scale"]),
               float(am["centre_wiser_in"][0]), float(am["centre_wiser_in"][1]))
    L = float(mj["accepted_L_s"])
    s2 = wp.STEP2_RUN
    fr = pd.read_csv(s2 / "frames.csv.gz")
    det = pd.read_csv(s2 / "detections.csv.gz")
    cells = pd.read_csv(s2 / "fixed_spots" / "cells.csv.gz")
    track_data, _ = wp.load_tracks_real(prm)
    tracks = wp.Tracks(track_data, prm.gap_max)
    houses = wp.load_houses()
    mapper = wp.real_mapper()
    fr, frs, d, _, _ = wp.prepare_boxes(fr, det, cells, mapper, prm, wp.HOUR_START)
    sup = wp.Support(mapper, wp.HOUR_START + timedelta(seconds=prm.n_sec / 2), prm)
    secs_out = []
    ep, grid, summ = wp.part_c(d, frs, fr, tracks, houses, m, L, sup, prm, wp.HOUR_START, seconds_out=secs_out)
    with tempfile.TemporaryDirectory() as tmp:
        p_ep = Path(tmp) / "fn_episodes.csv"
        ep.to_csv(p_ep, index=False)
        same_ep = sha256(p_ep) == sha256(phase0 / "fn_episodes.csv")
        p_gr = Path(tmp) / "fn_grid.csv"
        grid.to_csv(p_gr, index=False)
        same_grid = sha256(p_gr) == sha256(phase0 / "fn_grid.csv")
    sec = secs_out[0]
    chk = {"episodes_byte_identical": bool(same_ep), "grid_byte_identical": bool(same_grid), "n_eligible": int(len(sec)),
           "n_miss": int(sec["miss"].sum()), "n_episodes": int(len(ep)), "episode_seconds": int((sec["episode_id"] > 0).sum()),
           "map": am, "L_s": L}
    log(f"per-second table rebuilt: {chk['n_miss']} suspected-miss seconds of {chk['n_eligible']} eligible; episodes "
        f"byte-identical {same_ep}, grid byte-identical {same_grid}")
    return sec, ep, chk


# ----------------------------------------------------------------------------------------------- house_1 cohort pose (v2)
HOUSE1_POSE_JSON = REPO / "cv" / "configs" / "house1_cohort_pose_2026c.json"
NOON_POINTER = REPO / "results" / COHORT / DIRECTION / "reports" / "run_manifest_landmark_track_ch0102_0904noon_2026c.json"
HC_FUNCS = ("house_edges", "to_paddock", "ray_seg_dist", "cls", "fit", "assign")


def load_house_check(cd: Path) -> dict:
    """calibration_qc/house_check.py's functions, read-only: its source is parsed and only the function definitions (and
    the literal constants IR2COL, DESIGN_XY, IN, CM) are executed - importing it would run its whole fit and write into the
    QC folder. Returns the namespace plus the file's sha256."""
    import ast
    from scipy.optimize import least_squares
    p = cd / "house_check.py"
    src = p.read_text(encoding="utf-8")
    tree = ast.parse(src)
    ns = {"np": np, "least_squares": least_squares, "SV": survey(cd)["houses"]}
    for n in tree.body:
        if isinstance(n, ast.Assign):
            tg = ast.unparse(n.targets[0])
            if tg in ("IR2COL", "DESIGN_XY"):
                ns[tg] = ast.literal_eval(n.value)
            elif tg == "(IN, CM)":
                ns["IN"], ns["CM"] = ast.literal_eval(n.value)
    mod = ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in HC_FUNCS], type_ignores=[])
    exec(compile(mod, str(p), "exec"), ns)
    missing = [f for f in HC_FUNCS if f not in ns]
    if missing:
        raise RuntimeError(f"house_check.py lacks {missing}")
    ns["_sha256"] = sha256(p)
    return ns


def noon_affines() -> tuple[dict, dict]:
    """The 09-04 12:00 noon affines A (09-18 px -> frame px) of CH01 / CH02 from the ch0102_0904noon landmark-track run."""
    ptr = json.loads(NOON_POINTER.read_text(encoding="utf-8"))
    run = Path(ptr["run_dir"])
    tf = pd.read_csv(run / "track_frames.csv")
    out, meta = {}, {"run_dir": run.as_posix(), "pointer": NOON_POINTER.relative_to(REPO).as_posix()}
    for cam in ("CH01", "CH02"):
        r = tf[(tf["camera"] == cam) & (tf["frame"] != "REF") & tf["frame_time"].str.startswith("2026-09-04 12:00")].iloc[0]
        A = np.array([[r.a11, r.a12, r.a13], [r.a21, r.a22, r.a23]], float)
        out[cam] = A
        meta[cam] = {"frame_time": r.frame_time, "status": r.status, "held_med_px": float(r.held_med_px),
                     "held_p90_px": float(r.held_p90_px), "A_0918_to_frame": A.round(8).tolist()}
    return out, meta


def inv_affine(A: np.ndarray) -> np.ndarray:
    return np.linalg.inv(np.vstack([A, [0, 0, 1.0]]))[:2]


def cohort_house1_pieces(cams: dict, hc: dict, A: dict) -> list[dict]:
    """house_check.pieces() for the 09-04 12:00 cohort house_1 labels: the same densification, then cohort px -> 09-18 px
    with the inverse NOON affine, + IR2COL (the converted pixels are IR 09-18 pixels like the 09-18 labels). LABEL excluded."""
    out = []
    for cam in ("CH01", "CH02"):
        lab = json.loads((LM_DIR / f"landmarks_{cam}_20260904_120002.json").read_text(encoding="utf-8"))["landmarks"]
        Ai = inv_affine(A[cam])
        for key in ("ROOF_X", "ROOF_Y", "BASE_X", "BASE_Y", "BASE_Z"):
            for p in lab.get(f"HOUSE_1_{key}", []):
                p = np.asarray(p, float).reshape(-1, 2)
                if len(p) < 2:
                    continue
                pts = []
                for a, b in zip(p[:-1], p[1:]):
                    n = max(2, int(np.hypot(*(b - a)) / 15))
                    pts += list(a + (b - a) * np.linspace(0, 1, n, endpoint=False)[:, None])
                pts.append(p[-1])
                uv = np.array(pts) @ Ai[:, :2].T + Ai[:, 2] + np.asarray(hc["IR2COL"].get(cam, (0.0, 0.0)))
                d = cams[cam].rays(uv)
                ok = np.isfinite(d).all(1)
                if ok.sum() >= 3:
                    out.append(dict(cam=cam, key=key, d=d[ok], C=np.asarray(cams[cam].centre, float), t="0904_120002"))
    return out


def fit_house1_cohort(cams: dict, cd: Path, log=print) -> dict:
    """house_check.py's joint fit (4 free: x, y, theta, dz) on the converted cohort pieces, with its coarse start grid;
    per-camera fits (dz fixed); sensitivities dz = 58 / 93 mm; roof-only vs BASE_Z-only (dz fixed at the main value)."""
    hc = load_house_check(cd)
    A, nmeta = noon_affines()
    PC = cohort_house1_pieces(cams, hc, A)
    edges, he, hr, run = hc["house_edges"]("HOUSE_1")
    starts = []
    for th0 in (0.0, 90.0, 180.0, 270.0):
        for dx in np.arange(-12, 13, 3.0):
            for dy in np.arange(-9, 10, 3.0):
                x = np.array([hc["DESIGN_XY"]["HOUSE_1"][0] + dx, hc["DESIGN_XY"]["HOUSE_1"][1] + dy, th0, 50.0])
                starts.append((np.median(np.concatenate([a[2] for a in hc["assign"](PC, edges, x)])), x))
    starts.sort(key=lambda t: t[0])
    best = None
    for _, x0 in starts[:6]:
        x = hc["fit"](PC, edges, x0)
        r = np.concatenate([a[2] for a in hc["assign"](PC, edges, x)])
        if best is None or np.median(r) < best[1]:
            best = (x, np.median(r))
    x = best[0]

    def summ(PCs, xx):
        asg = hc["assign"](PCs, edges, xx)
        per = {}
        for c in sorted({p["cam"] for p in PCs}):
            r = np.concatenate([d for pc, n, d in asg if pc["cam"] == c])
            per[c] = {"ray_miss_median_mm": float(np.median(r)), "ray_miss_p90_mm": float(np.percentile(r, 90)), "n_rays": int(len(r)),
                      "pieces": [f"{pc['key'].replace('ROOF_', 'R').replace('BASE_', 'B')}:{n} {np.median(d):.0f}" for pc, n, d in asg if pc["cam"] == c]}
        return per

    def pose(xx):
        return {"centre_in": [float(xx[0]), float(xx[1])], "ridge_deg": float(xx[2] % 180), "soil_below_mm": float(xx[3])}

    res = {"main": {**pose(x), "free": "x, y, ridge angle, soil offset", "per_camera_residual": summ(PC, x)}}
    per = {}
    for c in ("CH01", "CH02"):
        sub = [p for p in PC if p["cam"] == c]
        if len(sub) >= 2:
            per[c] = hc["fit"](sub, edges, x, free=(0, 1, 2))
    P = np.array([[v[0], v[1]] for v in per.values()]) * IN
    res["per_camera"] = {c: pose(v) for c, v in per.items()}
    res["per_camera_spread_mm"] = float(np.max(np.linalg.norm(P - P.mean(0), axis=1))) if len(P) else float("nan")
    res["per_camera_pairwise_mm"] = float(np.linalg.norm((per["CH01"][:2] - per["CH02"][:2]) * IN)) if len(per) == 2 else float("nan")
    sens = {}
    for dz in (58.0, 93.0):
        xs = x.copy()
        xs[3] = dz
        xs = hc["fit"](PC, edges, xs, free=(0, 1, 2))
        sens[f"soil_fixed_{dz:.0f}mm"] = {**pose(xs), "centre_shift_mm": float(np.linalg.norm((xs[:2] - x[:2]) * IN))}
    sub_r = [p for p in PC if p["key"].startswith("ROOF")]
    sub_b = [p for p in PC if p["key"] == "BASE_Z"]
    xr = hc["fit"](sub_r, edges, x.copy(), free=(0, 1, 2))
    xb = hc["fit"](sub_b, edges, x.copy(), free=(0, 1, 2))
    sens["roof_only"] = {**pose(xr), "n_pieces": len(sub_r), "per_camera_residual": summ(sub_r, xr)}
    sens["base_z_only"] = {**pose(xb), "n_pieces": len(sub_b), "per_camera_residual": summ(sub_b, xb)}
    sens["roof_vs_base_z_mm"] = float(np.linalg.norm((xr[:2] - xb[:2]) * IN))
    sens["roof_vs_base_z_ridge_deg"] = float(((xr[2] - xb[2] + 90) % 180) - 90)
    sens["lid_rule"] = ("roof-only and BASE_Z-only fits (soil offset fixed at the main value) differ by more than the 09-18 "
                        "per-camera spread (30 mm) -> the lid offset matters")
    sens["lid_offset_matters"] = bool(sens["roof_vs_base_z_mm"] > 30.0)
    res["sensitivity"] = sens
    res["model"] = {"eaves_mm": float(he), "ridge_mm": float(hr), "eave_run_mm": float(run), "edges": "house_check.house_edges('HOUSE_1')"}
    res["n_pieces"] = {c: sum(p["cam"] == c for p in PC) for c in ("CH01", "CH02")}
    res["inputs"] = {"labels": {c: f"cv/configs/landmarks/2026c/landmarks_{c}_20260904_120002.json" for c in ("CH01", "CH02")},
                     "labels_sha256": {c: sha256(LM_DIR / f"landmarks_{c}_20260904_120002.json") for c in ("CH01", "CH02")},
                     "label_keys": "HOUSE_1_ROOF_X / _ROOF_Y / _BASE_Z (no BASE_X / BASE_Y labelled; HOUSE_1_LABEL excluded)",
                     "noon_correction": nmeta, "ir2col_px": hc["IR2COL"], "house_check_py_sha256": hc["_sha256"],
                     "start_grid": f"DESIGN_XY HOUSE_1 {hc['DESIGN_XY']['HOUSE_1']} +-12 / +-9 in, theta 0/90/180/270, dz 50; best 6 refined"}
    log(f"house_1 cohort fit: centre ({x[0]:.2f}, {x[1]:.2f}) in, ridge {x[2] % 180:.1f} deg, soil {x[3]:+.0f} mm; "
        f"per-camera spread {res['per_camera_spread_mm']:.0f} mm; roof vs BASE_Z {sens['roof_vs_base_z_mm']:.0f} mm")
    return res


def write_house1_json(res: dict, cd: Path) -> Path:
    rec = REPO.parent / "Field_2026_Social_Recording"
    out = {"_about": ("Cohort-3 (2026c) pose of house_1 (roof number 4, by pole B1) while the rats were in the field (08-30 -> 09-12): "
                      "house_1 was moved on 09-18, so the calibration's 09-18 house fit (147.5, 121.7) in is post-move. Fitted with "
                      "calibration_qc/house_check.py's rigid model and fit (functions reused read-only) on the user's 09-04 12:00 "
                      "house_1 edge labels from CH01 and CH02, converted to 09-18 px with the noon affines (not the night-only table), "
                      "+ IR -> colour offset. Frame: paddock inches of the rev g calibration, origin pole A0. Soil offset = mm below "
                      "the calibration's z = 0 (house_check's dz; the house's soil level is z = -dz)."),
           "house": "HOUSE_1", "roof_number": 4, "centre_in": res["main"]["centre_in"], "ridge_deg": res["main"]["ridge_deg"],
           "soil_below_calibration_ground_mm": res["main"]["soil_below_mm"],
           "residuals": res["main"]["per_camera_residual"], "per_camera": res["per_camera"],
           "per_camera_spread_mm": res["per_camera_spread_mm"], "per_camera_pairwise_mm": res["per_camera_pairwise_mm"],
           "sensitivity": res["sensitivity"], "model": res["model"], "n_pieces": res["n_pieces"], "inputs": res["inputs"],
           "commits": {"analysis_repo": git_commit(REPO), "recording_repo": git_commit(rec)},
           "calibration_files_sha256": {n: sha256(cd / n) for n in ("camera_fit.npz", "ray_correction.json", "survey_2026-10-03.json")},
           "made_by": "cv/cv_field/ch01_occlusion.py --house1-fit (plan implementation_plan/2026-10-06-ch01-occlusion-geometry.md, amendment 3)",
           "made": datetime.now().isoformat(timespec="seconds")}
    HOUSE1_POSE_JSON.write_text(json.dumps(out, indent=2, default=float) + "\n", encoding="utf-8")
    return HOUSE1_POSE_JSON


# ----------------------------------------------------------------------------------------------- pole planes (v2)
CH01_LABELLED_POLES = ("A0", "B0", "B1", "B2", "B3", "C0", "C1")
# per camera (2026-10-06, the WISER pixel kit): the poles with both L / R edges in that camera's own 09-18 labels, and the
# label file; CH01 unchanged (build_scene(cam="CH01") reproduces v2)
LABELLED_POLES = {"CH01": CH01_LABELLED_POLES, "CH02": ("A0", "A4", "B0", "B1", "B2", "B3", "B4")}
LM_0918_BY_CAM = {"CH01": LM_0918, "CH02": "landmarks_CH02_20260918_152230.json"}


def pole_planes(cam, rec: dict, labels: dict, p: str, offset=(0.0, 0.0)) -> dict | None:
    """The pole's angular extent from CH01's own L / R edge labels: each edge -> a plane through the camera centre (least
    squares of its rays), normals oriented towards the other edge; vertical span = the heights where the labelled rays pass
    the pole's horizontal distance (the grass-hidden foot is not labelled, so not included)."""
    Lp, Rp = labels.get(f"POLE_{p}_L"), labels.get(f"POLE_{p}_R")
    if not Lp or not Rp:
        return None
    rays = {}
    for side, pieces in (("L", Lp), ("R", Rp)):
        uv = np.vstack([densify(q) for q in pieces]) + np.asarray(offset)
        d = cam.rays(uv)
        rays[side] = d[np.isfinite(d).all(1)]
    nrm = {}
    for side in ("L", "R"):
        _, _, Vt = np.linalg.svd(rays[side])
        n = Vt[-1]
        other = rays["R" if side == "L" else "L"].mean(0)
        nrm[side] = n if n @ other > 0 else -n
    ax = axis_at(rec, 1050.0)
    rho = float(np.linalg.norm(ax[:2] - cam.centre[:2]))
    allr = np.vstack([rays["L"], rays["R"]])
    z = cam.centre[2] + rho * allr[:, 2] / np.hypot(allr[:, 0], allr[:, 1])
    planar = {s: np.degrees(np.abs(np.arcsin(np.clip(rays[s] @ nrm[s], -1, 1)))) for s in ("L", "R")}
    azL = np.arctan2(*rays["L"].mean(0)[[1, 0]])
    azR = np.arctan2(*rays["R"].mean(0)[[1, 0]])
    width = float(abs(np.degrees((azR - azL + np.pi) % (2 * np.pi) - np.pi)))   # azimuth between the two edges (descriptive)
    return {"nL": nrm["L"], "nR": nrm["R"], "rho_mm": rho, "z_lo": float(z.min()), "z_hi": float(z.max()),
            "planarity_med_deg": float(np.median(np.r_[planar["L"], planar["R"]])), "planarity_max_deg": float(np.max(np.r_[planar["L"], planar["R"]])),
            "angular_width_deg": width, "n_rays": int(len(allr))}


def planes_hidden(C: np.ndarray, Q: np.ndarray, pl: dict) -> np.ndarray:
    d = Q - C
    rq = np.hypot(d[:, 0], d[:, 1])
    with np.errstate(divide="ignore", invalid="ignore"):
        z_at = C[2] + pl["rho_mm"] * d[:, 2] / rq
    return (d @ pl["nL"] >= 0) & (d @ pl["nR"] >= 0) & (z_at >= pl["z_lo"]) & (z_at <= pl["z_hi"]) & (rq > pl["rho_mm"])


# ----------------------------------------------------------------------------------------------- run
def tojson(o):
    if isinstance(o, dict):
        return {str(k): tojson(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [tojson(v) for v in o]
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.floating, np.integer, np.bool_)):
        return o.item()
    return o


def build_scene(cams, cd, mj: dict, log=print, v2: bool = True, cam: str = CAM) -> tuple[Scene, dict, pd.DataFrame, pd.DataFrame, dict]:
    """v2 (amendment 3): house_1 at the fitted cohort pose (house1_cohort_pose_2026c.json); poles labelled in CH01 hide by
    CH01's own L / R edge planes. v1: house_1 from the WISER ROI, all poles capsules. cam (2026-10-06, WISER pixel kit):
    the same scene seen from another camera (CH02: its own 09-18 L / R labels of A0, A4, B0-B4); CH01 is unchanged."""
    import wiser_assist_p0 as wp
    sv = survey(cd)
    radii = {p: per * IN / (2 * np.pi) for p, per in sv["poles"]["perimeter"].items()}
    files = sorted(LM_DIR.glob("landmarks_CH0[1-4]_20260918_*.json"))
    poles, prow, tri = pole_lines(cams, files, radii)
    for p, rec in poles.items():
        rec["model"] = "cylinder (capsule)"
        rec["planes"] = None
    if v2:
        lab18 = load_labels(LM_0918_BY_CAM[cam])["landmarks"]
        for p in LABELLED_POLES[cam]:
            pl = pole_planes(cams[cam], poles[p], lab18, p, IR2COL[cam])
            if pl is not None:
                poles[p]["planes"] = pl
                poles[p]["model"] = f"{cam} L/R label planes"
    am = mj["accepted_map"]
    m = wp.Map(float(am["dx_in"]), float(am["dy_in"]), float(np.radians(am["theta_deg"])), float(am["scale"]),
               float(am["centre_wiser_in"][0]), float(am["centre_wiser_in"][1]))
    R = {r["name"]: r for r in json.loads(ROIS.read_text(encoding="utf-8"))["rois"]}
    h1w = np.array([R["house_1"]["x"], R["house_1"]["y"]])
    h2w = np.array([R["house_2"]["x"], R["house_2"]["y"]])
    h1p, h2p = m.fwd(h1w[None])[0], m.fwd(h2w[None])[0]
    ridge1 = (float(R["house_1"].get("orientation_deg", 90.0)) + float(am["theta_deg"])) % 180
    house2 = house_model(sv["houses"], "HOUSE_2", HOUSE2_POSE["cx_in"], HOUSE2_POSE["cy_in"], HOUSE2_POSE["ridge_deg"],
                         -HOUSE2_POSE["soil_below_mm"])
    post = np.array([HOUSE1_CALIB_POSTMOVE["cx_in"], HOUSE1_CALIB_POSTMOVE["cy_in"]])
    if v2:
        hp = json.loads(HOUSE1_POSE_JSON.read_text(encoding="utf-8"))
        c_fit = np.array(hp["centre_in"], float)
        house1 = house_model(sv["houses"], "HOUSE_1", float(c_fit[0]), float(c_fit[1]), float(hp["ridge_deg"]),
                             -float(hp["soil_below_calibration_ground_mm"]))
        h1 = {"source": "fitted cohort pose (house_check on the CH01 + CH02 09-04 noon labels; house1_cohort_pose_2026c.json)",
              "paddock_in": c_fit.tolist(), "ridge_deg": float(hp["ridge_deg"]), "soil_z_mm": -float(hp["soil_below_calibration_ground_mm"]),
              "vs_calibration_postmove_in": float(np.hypot(*(c_fit - post))), "vs_wiser_roi_placement_in": float(np.hypot(*(c_fit - h1p))),
              "wiser_roi_in": h1w.tolist(), "wiser_roi_mapped_in": h1p.tolist(), "wiser_roi_ridge_deg": ridge1,
              "pose_json_sha256": sha256(HOUSE1_POSE_JSON)}
    else:
        house1 = house_model(sv["houses"], "HOUSE_1", float(h1p[0]), float(h1p[1]), ridge1, -HOUSE1_SOIL_BELOW_MM)
        h1 = {"source": "WISER ROI house_1 centre through the accepted map", "wiser_roi_in": h1w.tolist(),
              "paddock_in": h1p.tolist(), "ridge_deg": ridge1, "soil_z_mm": -HOUSE1_SOIL_BELOW_MM,
              "vs_calibration_postmove_in": float(np.hypot(*(h1p - post)))}
    c1 = cams[cam]
    scene = Scene(c1.centre, poles, [house1, house2], lambda xy: ground(c1, xy))
    place = {"house_1": h1,
             "house_2": {"source": "calibration house check (rev g)", "paddock_in": [HOUSE2_POSE["cx_in"], HOUSE2_POSE["cy_in"]],
                         "ridge_deg": HOUSE2_POSE["ridge_deg"], "soil_z_mm": -HOUSE2_POSE["soil_below_mm"],
                         "wiser_roi_in": h2w.tolist(), "wiser_roi_mapped_in": h2p.tolist(),
                         "map_check_in": float(np.hypot(*(h2p - [HOUSE2_POSE['cx_in'], HOUSE2_POSE['cy_in']])))},
             "terrain_at_house_2_mm": float(ground(c1, (np.array([HOUSE2_POSE["cx_in"], HOUSE2_POSE["cy_in"]]) * IN)[None])[0]),
             "terrain_at_house_1_mm": float(ground(c1, (np.array(h1["paddock_in"]) * IN)[None])[0])}
    log(f"house_1 at ({h1['paddock_in'][0]:.1f}, {h1['paddock_in'][1]:.1f}) in, ridge {h1['ridge_deg']:.1f} deg ({h1['source'].split(' (')[0]}); "
        f"house_2 map check: WISER ROI -> ({h2p[0]:.1f}, {h2p[1]:.1f}) in vs calibration ({HOUSE2_POSE['cx_in']}, {HOUSE2_POSE['cy_in']}) = "
        f"{place['house_2']['map_check_in']:.1f} in")
    return scene, place, prow, tri, {"house_1": house1, "house_2": house2}


def plane_resid_px(cam, labels: dict, p: str, pl: dict, offset=(0.0, 0.0)) -> dict:
    """How far CH01's own L / R pole-edge labels lie from the planes built from them (px across the plane): the plane
    model's fit residual, not an independent check."""
    out = []
    for side, n in (("L", pl["nL"]), ("R", pl["nR"])):
        uv = np.vstack([densify(q) for q in labels[f"POLE_{p}_{side}"]]) + np.asarray(offset)
        r = cam.rays(uv)
        r1 = cam.rays(uv + [1.0, 0.0])
        ok = np.isfinite(r).all(1) & np.isfinite(r1).all(1)
        ang = np.abs(np.arcsin(np.clip(r[ok] @ n, -1, 1)))
        dpp = np.arccos(np.clip(np.einsum("ij,ij->i", r[ok], r1[ok]), -1, 1))
        out.append(ang / np.maximum(dpp, 1e-12))
    d = np.concatenate(out)
    return {"n_points": int(len(d)), "median_px": float(np.median(d)), "p90_px": float(np.percentile(d, 90)), "pieces": ""}


def landmark_checks(cams, scene: Scene, houses: dict, log=print, v2: bool = True, place: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """09-18 labels in 09-18 px (+ IR -> colour offset, as house_check). v2: the 09-04 cohort house_1 labels of CH01 and CH02
    -> 09-18 px with the inverse NOON affine (+ IR2COL); they are the house_1 fit's data, so that row is a fit residual.
    v1: CH01's 09-04 labels with Corrections.to_09_18 (night sample)."""
    Corrections = _fc.Corrections
    c1 = cams[CAM]
    lab18 = load_labels(LM_0918)
    lab04 = load_labels(LM_0904)
    off = IR2COL[CAM]
    rows = []
    for p, rec in scene.poles.items():
        if rec.get("planes") is not None:
            r = plane_resid_px(c1, lab18["landmarks"], p, rec["planes"], off)
            rows.append({"object": f"pole_{p}", "labels": "09-18", "model": "CH01 L/R label planes (v2; built from these labels)",
                         "kind": "fit residual (not independent)", **r})
        r = check_pole(c1, rec, lab18["landmarks"], p, off)
        if r is not None:
            rows.append({"object": f"pole_{p}" + (" (capsule, v1 model; v2 uses it only for the distance)" if rec.get("planes") is not None else ""),
                         "labels": "09-18", "model": "cylinder, " + rec["source"].split(" (")[0],
                         "kind": "check" if rec.get("planes") is None else "reference", **r})
    r = check_house(c1, houses["house_2"], lab18["landmarks"], "HOUSE_2", offset=off)
    rows.append({"object": "house_2", "labels": "09-18", "model": "house check rev g pose", "kind": "check", **r})
    if v2:
        A, nmeta = noon_affines()
        sv = survey(calib()[1])["houses"]
        for cam in ("CH01", "CH02"):
            labc = json.loads((LM_DIR / f"landmarks_{cam}_20260904_120002.json").read_text(encoding="utf-8"))["landmarks"]
            Ai = inv_affine(A[cam])
            to18n = (lambda Ai_: (lambda pts: np.asarray(pts, float) @ Ai_[:, :2].T + Ai_[:, 2]))(Ai)
            r = check_house(cams[cam], houses["house_1"], labc, "HOUSE_1", to18=to18n, offset=IR2COL.get(cam, (0.0, 0.0)))
            rows.append({"object": f"house_1 ({cam} 09-04 labels)", "labels": "09-04 cohort (noon affine -> 09-18 px)",
                         "model": "fitted cohort pose", "kind": "fit residual (labels are the fit data)", **r})
        # reference: how far v1's WISER-ROI placement was from the same (noon-converted) CH01 labels
        h1pl = (place or {}).get("house_1", {})
        roi_box = (house_model(sv, "HOUSE_1", float(h1pl["wiser_roi_mapped_in"][0]), float(h1pl["wiser_roi_mapped_in"][1]),
                               float(h1pl["wiser_roi_ridge_deg"]), -HOUSE1_SOIL_BELOW_MM) if "wiser_roi_mapped_in" in h1pl else None)
        if roi_box is not None:
            Ai = inv_affine(A["CH01"])
            r = check_house(c1, roi_box, lab04["landmarks"], "HOUSE_1", to18=lambda pts: np.asarray(pts, float) @ Ai[:, :2].T + Ai[:, 2], offset=off)
            rows.append({"object": "house_1 WISER-ROI placement (v1 model)", "labels": "09-04 cohort (noon affine -> 09-18 px)",
                         "model": "WISER ROI through the map", "kind": "reference", **r})
        corr = {"label_time": lab04["time"], "conversion": "inverse noon affine (ch0102_0904noon) + IR2COL", "noon": nmeta,
                "note": "the night-only correction table is not used for the 12:00 labels (CH02 would be ~30 px off)"}
    else:
        t04 = datetime.strptime(lab04["time"], "%Y-%m-%d %H:%M:%S")
        C = Corrections(COHORT)
        r = check_house(c1, houses["house_1"], lab04["landmarks"], "HOUSE_1", to18=lambda pts: np.asarray(C.to_09_18(CAM, t04, pts)[0], float))
        rows.append({"object": "house_1", "labels": "09-04 cohort (-> 09-18 px)", "model": "WISER ROI through the map", "kind": "check", **r})
        B, binfo = C.correction(CAM, t04)
        ctr = np.array([c1.upright_size[0] / 2, c1.upright_size[1] / 2])
        corr = {"label_time": lab04["time"], "correction_used": binfo.get("used"), "flag": binfo.get("flag"),
                "B_shift_at_centre_px": ((B[:, :2] @ ctr + B[:, 2]) - ctr).tolist()}
    sv = survey(calib()[1])["houses"]
    h1post = house_model(sv, "HOUSE_1", HOUSE1_CALIB_POSTMOVE["cx_in"], HOUSE1_CALIB_POSTMOVE["cy_in"],
                         HOUSE1_CALIB_POSTMOVE["ridge_deg"], -HOUSE1_SOIL_BELOW_MM)
    r = check_house(c1, h1post, lab18["landmarks"], "HOUSE_1", offset=off)
    rows.append({"object": "house_1 (09-18 post-move pose; code check only)", "labels": "09-18", "model": "house check rev g pose",
                 "kind": "code check", **r})
    df = pd.DataFrame(rows)
    df["flagged"] = (df["median_px"] > FLAG_PX) & df["kind"].isin(["check", "fit residual (labels are the fit data)",
                                                                    "fit residual (not independent)"])
    log("landmark checks: " + "; ".join(f"{r.object} {r.median_px:.1f} px{' FLAG' if r.flagged else ''}" for r in df.itertuples()))
    return df, corr


V1_RUN = OUT_ROOT / "2026c" / "cv_field_ch01_occlusion_20261006_1445"     # v1 (superseded by amendment 3)


def run(phase0: Path, out: Path | None, v2: bool = True) -> int:
    t0 = time.perf_counter()
    started = datetime.now().isoformat(timespec="seconds")
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
    cams, cd = calib()
    mj = json.loads((phase0 / "mapping.json").read_text(encoding="utf-8"))
    sec_all, ep_regen, chk = rebuild_seconds(phase0, log)
    if not chk["episodes_byte_identical"]:
        raise SystemExit("rebuilt episodes differ from fn_episodes.csv - refusing")
    sec_all.to_csv(out / "miss_seconds_rebuilt.csv.gz", index=False)
    scene, place, prow, tri, houses = build_scene(cams, cd, mj, log, v2=v2)
    prow.to_csv(out / "pole_edges_revg.csv", index=False)
    tri.to_csv(out / "pole_triangulation_revg.csv", index=False)
    occl = {"version": "v2" if v2 else "v1", "camera": {"name": CAM, "centre_mm": scene.C.tolist(), "centre_in": (scene.C[:2] / IN).tolist(),
                                                         "source": "RayCamera.centre (rev g)"},
            "poles": tojson(scene.poles),
            "houses": tojson({k: {kk: vv for kk, vv in h.items() if kk not in ("parts", "edges")} for k, h in houses.items()}),
            "placement": tojson(place), "clean_rule": CLEAN, "pole_height_mm": POLE_H,
            "rat_model": {"heights_mm": RAT_Z, "lateral_mm": [-RAT_HALF, 0, RAT_HALF], "hidden_threshold": HIDDEN_T,
                          "perturbation_in": PERTURB_IN, "directions": N_DIR,
                          "perturbation_clamp": f"inside the paddock inset by {CLAMP_INSET_IN:g} in" if v2 else "none"}}
    (out / "occluders.json").write_text(json.dumps(occl, indent=2, default=float), encoding="utf-8")
    log("poles: " + "; ".join(f"{p} {r['model'].split(' (')[0]}, {r['source'].split(':')[0].split(' (')[0]}" for p, r in scene.poles.items()))
    # occlusion of every suspected-miss second
    sec = sec_all[sec_all["miss"]].reset_index(drop=True)
    cstats = {}
    cl = classify(scene, sec[["paddock_x_in", "paddock_y_in"]].to_numpy(float), clamp=v2, stats=cstats)
    log(f"perturbations clamped to the paddock: {cstats.get('clamped', 0)} of {cstats.get('perturbations', 0)}")
    sec = pd.concat([sec, cl], axis=1)
    # descriptive (amendment 2, after results): the 7-in ring crosses a paddock wall (perturbed positions are not clipped)
    x, y = sec["paddock_x_in"].to_numpy(float), sec["paddock_y_in"].to_numpy(float)
    sec["ring_crosses_wall"] = (x < PERTURB_IN) | (x > 480 - PERTURB_IN) | (y < PERTURB_IN) | (y > 240 - PERTURB_IN)
    sec.to_csv(out / "seconds.csv.gz", index=False)
    ep = episode_classes(sec)
    ep.to_csv(out / "episodes.csv", index=False)
    pool = pooled(ep, sec)
    (out / "SEALED_README.txt").write_text(
        "episodes.csv and seconds.csv.gz hold per-episode / per-second geometry classes. They are SEALED until the user's\n"
        "verdicts in the phase-0 review_clips/review_template.csv are in (plan 2026-10-06-ch01-occlusion-geometry.md,\n"
        "Outputs and blinding). Only pooled numbers over all episodes and the visibility mask may be reported.\n", encoding="utf-8")
    log(f"classified {len(sec)} suspected-miss seconds and {len(ep)} episodes (per-episode classes sealed in episodes.csv)")
    # mask
    paths, spj = support_path(phase0)
    mk = visibility_mask(scene, paths)
    np.savez_compressed(out / "visibility_mask.npz", **mk)
    # checks
    chkdf, corr = landmark_checks(cams, scene, houses, log, v2=v2, place=place)
    chkdf.to_csv(out / "checks.csv", index=False)
    figs = make_figures(out, scene, houses, mk, pool, paths)
    rec = REPO.parent / "Field_2026_Social_Recording"
    p0run = json.loads((phase0 / "run.json").read_text(encoding="utf-8"))
    calsha = {n: sha256(cd / n) for n in ("camera_fit.npz", "ray_correction.json", "frame_correction.json", "survey_2026-10-03.json",
                                          "HOUSE_CHECK_2026-10-04_revg.txt") if (cd / n).exists()}
    same_cal = all(calsha.get(k) == v for k, v in p0run.get("calibration_files_sha256", {}).items())
    mask_stats = {"cells_in_support": int(mk["in_support"].sum()),
                  "share_hidden_ge_0_8": float(np.nanmean(mk["h"][mk["in_support"]] >= HIDDEN_T)),
                  "share_partly": float(np.nanmean((mk["h"][mk["in_support"]] > 0) & (mk["h"][mk["in_support"]] < HIDDEN_T))),
                  "by_object_hidden_ge_0_8": {str(o): float(np.nanmean(mk["h_by_object"][i][mk["in_support"]] >= HIDDEN_T))
                                              for i, o in enumerate(mk["objects"])}}
    runj = {"plan": PLAN, "driver": "cv/cv_field/ch01_occlusion.py", "started": started, "git_commit": git_commit(REPO),
            "recording_repo_commit": git_commit(rec), "calibration_dir": cd.as_posix(), "calibration_files_sha256": calsha,
            "calibration_same_as_phase0": bool(same_cal), "phase0_run": phase0.as_posix(), "rebuild_check": chk,
            "pooled": pool, "mask": mask_stats, "landmark_checks": chkdf.drop(columns=["pieces"]).to_dict("records"),
            "cohort_label_correction": tojson(corr), "placement": tojson(place),
            "pole_sources": {p: r["source"] for p, r in scene.poles.items()},
            "pole_models": {p: r["model"] for p, r in scene.poles.items()},
            "pole_planes": {p: {k: v for k, v in r["planes"].items() if k not in ("nL", "nR")} for p, r in scene.poles.items()
                            if r.get("planes") is not None},
            "version": "v2" if v2 else "v1", "perturbation_clamp": cstats,
            "house1_pose": json.loads(HOUSE1_POSE_JSON.read_text(encoding="utf-8")) if v2 else None,
            "v1_run": V1_RUN.as_posix() if v2 else None,
            "v1_pooled": (json.loads((V1_RUN / "run.json").read_text(encoding="utf-8"))["pooled"]
                          if v2 and (V1_RUN / "run.json").exists() else None),
            "sealed_files": ["episodes.csv", "seconds.csv.gz"], "figures": figs, "runtime_s": time.perf_counter() - t0}
    (out / "run.json").write_text(json.dumps(tojson(runj), indent=2, default=float), encoding="utf-8")
    import output_paths as op
    rep_dir = op.report_dir(COHORT, DIRECTION)
    rp = write_report(rep_dir, out, runj, scene, houses, chkdf, tri, figs)
    ptr = {"run_dir": out.resolve().as_posix(), "cohort": COHORT, "direction": DIRECTION, "analysis": "ch01_occlusion",
           "driver": "cv/cv_field/ch01_occlusion.py", "report": REPORT_NAME, "plan": PLAN, "phase0_run": phase0.as_posix(),
           "figures": f"results/{COHORT}/{DIRECTION}/figures/{FIG_SUB}/", "git_commit": runj["git_commit"],
           "sealed_files": runj["sealed_files"]}
    (rep_dir / POINTER_NAME).write_text(json.dumps(ptr, indent=2) + "\n", encoding="utf-8")
    log(f"report -> {rp.as_posix()}; runtime {time.perf_counter() - t0:.0f} s")
    logf.close()
    return 0


# ----------------------------------------------------------------------------------------------- figures + report
def make_figures(out: Path, scene: Scene, houses: dict, mk: dict, pool: dict, paths) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import output_paths as op
    fd = op.figure_dir(COHORT, DIRECTION) / FIG_SUB
    fd.mkdir(parents=True, exist_ok=True)
    figs = []
    fig, ax = plt.subplots(figsize=(13, 7))
    H = np.where(mk["in_support"], mk["h"], np.nan)
    s = MASK_STEP_IN / 2
    im = ax.imshow(H, origin="lower", extent=[mk["x_in"][0] - s, mk["x_in"][-1] + s, mk["y_in"][0] - s, mk["y_in"][-1] + s],
                   cmap="magma_r", vmin=0, vmax=1, interpolation="nearest")
    fig.colorbar(im, ax=ax, shrink=0.7, label="hidden share h of a rat (9 sample points) as seen from CH01")
    for pth in paths:
        v = pth.vertices
        ax.plot(np.r_[v[:, 0], v[0, 0]], np.r_[v[:, 1], v[0, 1]], color="C0", lw=1)
    for p, r in scene.poles.items():
        a = r["A"][:2] / IN
        col = "C4" if r.get("planes") is not None else ("C2" if r["source"].startswith("measured") else "C1")
        ax.add_patch(plt.Circle(a, r["radius_mm"] / IN, color=col, fill=True))
        ax.text(a[0] + 4, a[1] + 4, p, fontsize=8, color="k")
    for k, h in houses.items():
        f = np.asarray(h["footprint_mm"]) / IN
        ax.fill(f[:, 0], f[:, 1], facecolor="none", edgecolor="C9", lw=1.5)
        ax.text(f[:, 0].mean(), f[:, 1].max() + 4, k, fontsize=8, ha="center")
    ax.plot(*(scene.C[:2] / IN), marker="^", color="C3", ms=10, label="CH01 camera")
    ax.plot([0, 480, 480, 0, 0], [0, 0, 240, 240, 0], color="k", lw=0.8)
    ax.set_xlim(-20, 500)
    ax.set_ylim(-20, 260)
    ax.set_aspect("equal")
    ax.set_xlabel("paddock x (in)")
    ax.set_ylabel("paddock y (in)")
    ax.legend(fontsize=8, loc="upper right")
    ax.set_title("CH01 visibility mask (2-in cells in CH01's support): shadows of the poles (purple = CH01 label planes, green = "
                 "capsule on a measured line, orange = capsule at the design grid) and houses (cyan)", fontsize=9)
    fig.tight_layout()
    fig.savefig(fd / "visibility_mask.png", dpi=110)
    plt.close(fig)
    figs.append("visibility_mask.png")
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.2))
    cats = list(CATS)
    for ax, key, title in ((axs[0], "episodes_by_class", f"episodes (n {pool['n_episodes']})"),
                           (axs[1], "seconds_by_category", f"suspected-miss seconds (n {pool['n_seconds']})")):
        v = [pool[key][c]["share"] for c in cats]
        ax.bar(cats, v, color=["C3", "C1", "C2", "C7"])
        for i, x in enumerate(v):
            ax.text(i, x + 0.01, f"{100 * x:.1f} %", ha="center", fontsize=9)
        ax.set_ylim(0, 1)
        ax.set_ylabel("share")
        ax.set_title(f"Pooled geometry classes, {title}", fontsize=10)
    fig.tight_layout()
    fig.savefig(fd / "class_shares.png", dpi=110)
    plt.close(fig)
    figs.append("class_shares.png")
    return figs


def pct(v):
    return "–" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{100 * v:.1f} %"


def axis_at(rec: dict, z_above_ground: float) -> np.ndarray:
    A, B = rec["A"], rec["B"]
    w = z_above_ground / (B[2] - A[2])
    return A + w * (B - A)


def tape_txt(scene: Scene) -> str:
    """Spacings at the tape height between adjacent measured poles vs the operator's tape (survey_2026-10-03.json)."""
    try:
        sv = survey(calib()[1])["poles"]["spacing"]
    except Exception:  # noqa: BLE001
        return "(survey not readable)"
    out = []
    for a, b in (("B1", "B2"), ("B2", "B3")):
        ra, rb = scene.poles.get(a), scene.poles.get(b)
        if ra and rb and ra["source"].startswith("measured") and rb["source"].startswith("measured"):
            d = np.linalg.norm(axis_at(rb, 1050.0)[:2] - axis_at(ra, 1050.0)[:2]) / IN
            out.append(f"{a}–{b} {d:.1f} in (tape {sv.get(f'{a}-{b}')} in)")
    return "; ".join(out) if out else "(no adjacent measured poles)"


def write_report(rep_dir: Path, run: Path, rj: dict, scene: Scene, houses: dict, chk: pd.DataFrame, tri: pd.DataFrame,
                 figs: list[str]) -> Path:
    pool, pl, rb = rj["pooled"], rj["placement"], rj["rebuild_check"]
    v1 = rj.get("v1_pooled")
    hp = rj.get("house1_pose") or {}
    cst = rj.get("perturbation_clamp", {})
    figrel = "../figures/" + FIG_SUB
    L = ["# CH01 occlusion geometry for the WISER-flagged suspected misses (poles, houses) — 2026c, v2", "",
         f"Driver `cv/cv_field/ch01_occlusion.py`; plan `{PLAN}` (pre-registered, approved 2026-10-06 \"行上吧\"; amendment 1 "
         "before results; amendment 2 after results, descriptive; **amendment 3 after results = v2**: house_1 at its fitted cohort "
         "pose, CH01-labelled poles hide by CH01's own edge planes, the 7-in perturbations clamped to the paddock); run "
         f"`{run.as_posix()}`; v1 run `{rj.get('v1_run')}` (superseded, `SUPERSEDED.txt`); generated {datetime.now():%Y-%m-%d %H:%M}; "
         f"code `{rj['git_commit']}`; calibration `{rj['calibration_dir']}` at recording-repo commit `{rj['recording_repo_commit']}` "
         f"(the calibration files are byte-identical to phase 0's and v1's: {rj['calibration_same_as_phase0']}). Hour: CH01 "
         "2026-09-06 21:00–22:00, the phase-0 suspected misses. The agent did not look at any frame or figure. Geometry says "
         "*hidden*; it never makes a label — a hidden animal gets no box and a *clear* suspected miss is still only a proposal.", "",
         "**Blinding.** The user is filling `review_template.csv` of the phase-0 review clips. Per-episode and per-second "
         "classes are sealed in the run folder (`episodes.csv`, `seconds.csv.gz`); this report shows only pooled numbers over "
         "all episodes and the visibility mask. The phase-0 `wiser_spots.csv` stays unopened.", "",
         "## Pooled result (v2)", "",
         "| | n | hidden | partly | clear | ambiguous |", "|---|---:|---:|---:|---:|---:|"]
    if v1:
        L.append(f"| episodes, v1 | {v1['n_episodes']} | " + " | ".join(pct(v1['episodes_by_class'][c]['share']) for c in CATS) + " |")
    L.append(f"| **episodes, v2** | {pool['n_episodes']} | " + " | ".join(f"**{pct(pool['episodes_by_class'][c]['share'])}**" for c in CATS) + " |")
    if v1:
        L.append(f"| seconds, v1 | {v1['n_seconds']} | " + " | ".join(pct(v1['seconds_by_category'][c]['share']) for c in CATS) + " |")
    L.append(f"| **seconds, v2** | {pool['n_seconds']} | " + " | ".join(f"**{pct(pool['seconds_by_category'][c]['share'])}**" for c in CATS) + " |")
    L += ["", "Episode counts v2: " + ", ".join(f"{c} {pool['episodes_by_class'][c]['n']}" for c in CATS)
          + ". Seconds at the nominal WISER position alone (v2): " + ", ".join(f"{c} {pct(v)}" for c, v in pool["seconds_by_nominal_class"].items())
          + f". Perturbed positions clamped to the paddock (inset 1 in): **{cst.get('clamped', 0)} of {cst.get('perturbations', 0)}** "
          f"({pct(cst.get('clamped', 0) / max(cst.get('perturbations', 1), 1))}).", "",
          "By occluder (episodes whose class is not *clear*; occluder = the most frequent occluder of their non-clear seconds; "
          "*model* = how that object hides in v2; *check* = its landmark check below):", "",
          "| occluder | v2 model | check | hidden | partly | ambiguous | total | v1 total |", "|---|---|---|---:|---:|---:|---:|---:|"]

    def status(o):
        r = chk[(chk["object"] == o) | chk["object"].str.startswith(o + " (C")]
        if r.empty:
            return "not checked (no CH01 labels)"
        r0 = r.iloc[0]
        tag = "fit residual" if "fit residual" in r0["kind"] else "check"
        return (f"**flagged** ({tag} {r0['median_px']:.0f} px)" if r0["flagged"] else f"{tag} {r0['median_px']:.1f} px")

    def model(o):
        if o.startswith("pole_"):
            r = scene.poles[o[5:]]
            return r["model"] + ("" if r.get("planes") is not None else (", measured line" if r["source"].startswith("measured") else ", design grid"))
        return "house check rev g pose" if o == "house_2" else "fitted cohort pose"
    v1occ = (v1 or {}).get("episodes_by_occluder", {})
    for o, v in sorted(pool["episodes_by_occluder"].items(), key=lambda kv: -sum(kv[1].values())):
        L.append(f"| {o} | {model(o)} | {status(o)} | {v.get('hidden', 0)} | {v.get('partly', 0)} | {v.get('ambiguous', 0)} | "
                 f"{sum(v.values())} | {sum(v1occ.get(o, {}).values())} |")
    for o in sorted(set(v1occ) - set(pool["episodes_by_occluder"])):
        L.append(f"| {o} | {model(o)} | {status(o)} | 0 | 0 | 0 | 0 | {sum(v1occ[o].values())} |")
    v1s = (v1 or {}).get("seconds_by_occluder", {})
    L += ["", "Seconds by occluder (non-clear seconds):", "", "| occluder | hidden | partly | ambiguous | total | v1 total |", "|---|---:|---:|---:|---:|---:|"]
    for o, v in sorted(pool["seconds_by_occluder"].items(), key=lambda kv: -sum(kv[1].values())):
        L.append(f"| {o} | {v.get('hidden', 0)} | {v.get('partly', 0)} | {v.get('ambiguous', 0)} | {sum(v.values())} | {sum(v1s.get(o, {}).values())} |")
    for o in sorted(set(v1s) - set(pool["seconds_by_occluder"])):
        L.append(f"| {o} | 0 | 0 | 0 | 0 | {sum(v1s[o].values())} |")
    mk = rj["mask"]
    L += ["", f"Visibility mask (v2): {mk['cells_in_support']} 2-in cells in CH01's support; a rat is hidden (h ≥ 0.8) in "
          f"{pct(mk['share_hidden_ge_0_8'])} and partly hidden in {pct(mk['share_partly'])}. Hidden share by object: "
          + ", ".join(f"{k} {pct(v)}" for k, v in sorted(mk["by_object_hidden_ge_0_8"].items(), key=lambda kv: -kv[1]) if v > 0) + ". "
          f"Figure [`visibility_mask.png`]({figrel}/visibility_mask.png); pooled classes [`class_shares.png`]({figrel}/class_shares.png); "
          "array `visibility_mask.npz` in the run folder.", ""]
    # house_1
    if hp:
        s = hp["sensitivity"]
        res = hp["residuals"]
        pc = hp["per_camera"]
        L += ["## house_1 cohort pose (v2 fix 1)", "",
              "Fitted with `calibration_qc/house_check.py`'s rigid model and fit (its functions reused read-only; file sha256 "
              f"`{hp['inputs']['house_check_py_sha256'][:12]}…`) on the user's 09-04 12:00:02 house_1 edge labels of CH01 and CH02 "
              f"({hp['n_pieces']['CH01']} + {hp['n_pieces']['CH02']} pieces: ROOF_X, ROOF_Y, BASE_Z; the number plate LABEL excluded), "
              "converted to 09-18 px with the inverse **noon** affines (CH01 held-out "
              f"{hp['inputs']['noon_correction']['CH01']['held_med_px']:.2f} px, CH02 {hp['inputs']['noon_correction']['CH02']['held_med_px']:.2f} px; "
              "not the night-only table) + the IR → colour offset; 4 free parameters (x, y, ridge angle, soil offset), house_check's start "
              f"grid. Written to `cv/configs/house1_cohort_pose_2026c.json` (pointer added to `cv/cv_field/CAMERA_GEOMETRY_2026c.md` §4).", "",
              f"- **Centre ({hp['centre_in'][0]:.2f}, {hp['centre_in'][1]:.2f}) in, ridge {hp['ridge_deg']:.1f}° from x, soil "
              f"{hp['soil_below_calibration_ground_mm']:.0f} mm below the calibration's z = 0.**",
              "- Rays miss the rigid house by: " + "; ".join(f"{c} median {v['ray_miss_median_mm']:.1f} mm, p90 {v['ray_miss_p90_mm']:.1f} mm "
                                                            f"(n {v['n_rays']})" for c, v in res.items()) + ".",
              "- Each camera alone (soil fixed at the joint value): " + "; ".join(f"{c} ({v['centre_in'][0]:.2f}, {v['centre_in'][1]:.2f}) in, "
                                                                                 f"{v['ridge_deg']:.1f}°" for c, v in pc.items())
              + f" → spread {hp['per_camera_spread_mm']:.1f} mm from their mean, CH01–CH02 {hp['per_camera_pairwise_mm']:.1f} mm.",
              f"- Soil sensitivity: soil fixed at 58 mm → centre ({s['soil_fixed_58mm']['centre_in'][0]:.2f}, {s['soil_fixed_58mm']['centre_in'][1]:.2f}) in, "
              f"shift {s['soil_fixed_58mm']['centre_shift_mm']:.0f} mm; at 93 mm → ({s['soil_fixed_93mm']['centre_in'][0]:.2f}, "
              f"{s['soil_fixed_93mm']['centre_in'][1]:.2f}) in, shift {s['soil_fixed_93mm']['centre_shift_mm']:.0f} mm (with two cameras the soil "
              "level and the centre trade along the viewing rays).",
              f"- Lid (the roof is lifted at every round): roof-only fit ({s['roof_only']['n_pieces']} pieces) "
              f"({s['roof_only']['centre_in'][0]:.2f}, {s['roof_only']['centre_in'][1]:.2f}) in vs BASE_Z-only ({s['base_z_only']['n_pieces']} pieces) "
              f"({s['base_z_only']['centre_in'][0]:.2f}, {s['base_z_only']['centre_in'][1]:.2f}) in, soil fixed at the joint value: "
              f"**{s['roof_vs_base_z_mm']:.0f} mm apart**, ridge {s['roof_vs_base_z_ridge_deg']:+.2f}° — below the 30-mm 09-18 per-camera "
              f"spread, so by the note's rule the lid offset does {'' if s['lid_offset_matters'] else 'not '}matter here.",
              f"- Distance from the calibration's 09-18 post-move position (147.5, 121.7) in: **{pl['house_1']['vs_calibration_postmove_in']:.2f} in** "
              f"(the move on 09-18, \"farther from its pole\"); from v1's WISER-ROI placement ({pl['house_1']['wiser_roi_mapped_in'][0]:.1f}, "
              f"{pl['house_1']['wiser_roi_mapped_in'][1]:.1f}) in: **{pl['house_1']['vs_wiser_roi_placement_in']:.2f} in**.", ""]
    # poles
    L += ["## Poles (v2 fix 2)", "",
          "Poles labelled in CH01's 09-18 reference (A0, B0, B1, B2, B3, C0, C1) hide by **CH01's own L / R edge labels**: each "
          "edge's rays (09-18 px + IR → colour offset, rev g rays) define a plane through CH01's centre; a sample point is hidden "
          "if its ray lies between the two planes, within the labelled vertical span (the heights where the labelled rays pass "
          "the pole's horizontal distance; the grass-hidden foot is not labelled, so not included), and it is farther from "
          "the camera than the pole. The pole's distance comes from the measured line (B1–B3) or the design grid; only the "
          "front / behind decision uses it. The planes are fixed in the world (camera centre + pole edges), so the cohort "
          "hour needs no pixel correction for them. Poles CH01 did not label keep the v1 capsule.", "",
          "| pole | v2 model | distance source | distance (m) | angular width | labelled span (m, at the pole) | label planarity median / max |",
          "|---|---|---|---:|---:|---|---|"]
    for p, r in scene.poles.items():
        if r.get("planes") is not None:
            q = r["planes"]
            L.append(f"| {p} | label planes | {r['source'].split(':')[0].split(' (')[0]} | {q['rho_mm'] / 1000:.2f} | {q['angular_width_deg']:.2f}° | "
                     f"{q['z_lo'] / 1000:.2f}–{q['z_hi'] / 1000:.2f} | {q['planarity_med_deg']:.3f}° / {q['planarity_max_deg']:.3f}° |")
    others = [p for p, r in scene.poles.items() if r.get("planes") is None]
    L += ["", "Capsule (v1 model): " + ", ".join(f"{p} ({'measured line' if scene.poles[p]['source'].startswith('measured') else 'design grid'})"
                                                 for p in others) + ".", ""]
    L += ["## Inputs and the rebuilt per-second table", "",
          f"The phase-0 per-second suspected-miss table, rebuilt with the unchanged phase-0 code (`wiser_assist_p0.prepare_boxes` + "
          f"`part_c`, accepted map d ({rb['map']['dx_in']:.2f}, {rb['map']['dy_in']:.2f}) in, θ {rb['map']['theta_deg']:.3f}°, s "
          f"{rb['map']['scale']:.4f}, L {rb['L_s']:+.1f} s): {rb['n_miss']} suspected-miss seconds of {rb['n_eligible']} eligible "
          f"animal-seconds; the regenerated `fn_episodes.csv` is byte-identical to phase 0's: {rb['episodes_byte_identical']} "
          f"(`fn_grid.csv`: {rb['grid_byte_identical']}).", "",
          "## Occluders", "",
          f"Camera CH01 centre ({scene.C[0] / IN:.1f}, {scene.C[1] / IN:.1f}) in, {scene.C[2]:.0f} mm (`RayCamera.centre`). Houses: the "
          "house check's rigid model (body box to the eave height + gable-roof prism with the 66-cm ridge and the roof overhang).", "",
          "| object | position (in) | source | size / model |", "|---|---|---|---|"]
    for p, r in scene.poles.items():
        a = r["A"][:2] / IN
        L.append(f"| pole {p} | ({a[0]:.1f}, {a[1]:.1f}) at the ground | {r['source']} | {r['model']}; r {r['radius_mm']:.0f} mm; lean {r.get('lean_deg', 0):.1f}° |")
    for k, h in houses.items():
        L.append(f"| {k} | ({h['centre_in'][0]:.1f}, {h['centre_in'][1]:.1f}), ridge {h['ridge_deg']:.1f}° | {pl[k]['source']} | "
                 f"{h['footprint_cm'][0]:.2f} × {h['footprint_cm'][1]:.2f} cm, eaves {h['eave_mm'] / 10:.1f} cm, ridge {h['ridge_mm'] / 10:.1f} cm, "
                 f"soil at z {h['soil_z_mm']:.0f} mm |")
    L += ["", f"Map check on house_2 (unchanged): its WISER ROI through the accepted map lands {pl['house_2']['map_check_in']:.1f} in from "
          "its calibrated position — the hand-placed ROI rectangles carry errors of that order, which is why v1's house_1 was off.", "",
          "Pole re-measurement (amendment 1, unchanged): the pole-check method re-run read-only on the rev g cameras; B1, B2, B3 "
          "measured (CH01 + CH02), the other 12 at the design grid; per-height triangulations in `pole_triangulation_revg.csv`; "
          "tape check at 1.05 m: " + tape_txt(scene) + ".", ""]
    L += ["## Landmark checks (v2)", "",
          f"Median pixel distance from the user's labels to the model (flag > {FLAG_PX:.0f} px on checks and fit residuals; results "
          "of a flagged object carry the flag). *kind*: **check** = labels not used to build the object; **fit residual** = "
          "the labels built the object (the 09-04 house_1 labels are now the house_1 fit's data, so their row is no longer an "
          "independent check; the label-plane poles reproduce their own labels up to the edges' straightness); **reference** = "
          "a model v2 does not use for hiding; **code check** = projection sanity check.", "",
          "| object | labels | model | kind | label points | median px | p90 px | flagged |", "|---|---|---|---|---:|---:|---:|---|"]
    for r in chk.itertuples():
        L.append(f"| {r.object} | {r.labels} | {r.model} | {r.kind} | {r.n_points} | {r.median_px:.1f} | {r.p90_px:.1f} | "
                 f"{'**yes**' if r.flagged else 'no'} |")
    fl = chk[chk["flagged"]]["object"].tolist()
    L += ["", ("Flagged in v2: " + ", ".join(fl) + "." if fl else "Nothing is flagged in v2.") + " The capsule rows of the "
          "label-plane poles show how far v1's cylinders were from CH01's labels (v2 keeps them only for the front / behind "
          "distance).", ""]
    L += ["## Definitions", "",
          "Units: paddock mm / inches (origin pole A0); z = the calibration's absolute height datum (camera centre, terrain, "
          "house soil levels). $\\mathbf C$ = CH01's centre; $\\mathbf p$ = an animal's paddock position (WISER through the "
          "accepted map); $g(\\mathbf p)$ = local ground height (terrain).", "",
          "### Rat sample points",
          "$$ \\mathbf q_{kl}=\\big(\\mathbf p+o_l\\,\\hat{\\mathbf n},\\ g(\\mathbf p)+z_k\\big),\\quad z_k\\in\\{30,60,90\\}\\,\\mathrm{mm},"
          "\\ o_l\\in\\{-40,0,40\\}\\,\\mathrm{mm} $$ **Text:** a rat's body as 9 points; $\\hat{\\mathbf n}$ = horizontal unit "
          "normal to the line of sight from CH01.", "",
          "### Hidden share $h$",
          "$$ h(\\mathbf p)=\\frac{1}{9}\\sum_{k,l}\\mathbb 1\\big[\\exists\\,O:\\ \\mathbf q_{kl}\\ \\text{hidden by}\\ O\\big] $$ **Text:** share "
          "of the body points hidden from CH01. Range [0, 1]. *Hidden by a house*: the segment $[\\mathbf C,\\mathbf q]$ passes "
          "through a convex house part (Cyrus–Beck). *Hidden by a capsule pole*: segment–axis distance ≤ radius. *Hidden by a "
          "label-plane pole*: $\\mathbf n_L\\cdot\\mathbf d\\ge0\\ \\wedge\\ \\mathbf n_R\\cdot\\mathbf d\\ge0\\ \\wedge\\ z_\\rho\\in[z_{lo},z_{hi}]\\ "
          "\\wedge\\ \\lVert\\mathbf d_{xy}\\rVert>\\rho$ with $\\mathbf d=\\mathbf q-\\mathbf C$, $\\mathbf n_{L,R}$ = the edge planes' normals "
          "(least squares of the labelled rays, oriented towards the other edge), $\\rho$ = the pole's horizontal distance, "
          "$z_\\rho=C_z+\\rho\\,d_z/\\lVert\\mathbf d_{xy}\\rVert$ = the ray's height at the pole, $[z_{lo},z_{hi}]$ = the same for the "
          "labelled rays.", "",
          "### Classes",
          "nominal: hidden $h\\ge0.8$, partly $0<h<0.8$, clear $h=0$. Robust over the nominal position and 8 positions 7 in away "
          "(v2: each clamped to $[1,479]\\times[1,239]$ in): robustly hidden = hidden at all 9, robustly clear = $h=0$ at all 9. "
          "**Category**: hidden = robustly hidden; clear = robustly clear; partly = nominal $0<h<0.8$; ambiguous = otherwise. "
          "**Episode class** = the unique majority category of its seconds (ties → ambiguous). **Occluder** of a second = the "
          "object blocking the most sample points summed over the 9 positions; of an episode = the most frequent occluder of "
          "its non-clear seconds.", "",
          "### house_1 fit",
          "$$ \\hat{\\mathbf x}=\\arg\\min_{x,y,\\theta,dz}\\sum_{\\text{label rays}}\\rho_{\\text{soft-}\\ell_1}\\big(\\min_{e\\in E(\\text{class})}"
          "\\mathrm{dist}(\\text{ray},\\,e(x,y,\\theta,dz))\\big) $$ **Text:** house_check's fit: the rigid edges $E$ of the surveyed "
          "house posed at centre $(x,y)$, ridge angle $\\theta$, soil $dz$ below z = 0; each label piece is matched to the nearest "
          "allowed edge (roof labels → roof edges, BASE_Z → vertical corners). Ray miss = the 3-D distance between a label ray "
          "and its edge (mm).", "",
          "### Landmark distance",
          "$$ d_i=\\min_{\\mathbf s\\in\\pi(E)}\\lVert \\mathbf u_i-\\mathbf s\\rVert $$ **Text:** pixel distance from a densified "
          "label point $\\mathbf u_i$ (every ≈ 15 px) to the projected model edge $\\pi(E)$ (3-D points projected with the "
          "calibration's own inverse, verified to 0.02°); for a label-plane pole, the angle of each label ray from its plane "
          "converted to px with the local pixel scale. Median per object.", "",
          "## Caveats", "",
          "- Grass, other rats, the animal's posture and objects not surveyed (water dish, feeders, cables) are not modelled: "
          "they can hide a *clear* animal. One hour, one camera.",
          "- house_1's pose rests on two cameras about 40° apart: the soil level and the centre trade along the rays (sensitivity "
          "above); the roof is the lid, set back after each round.",
          "- Label-plane poles hide only within the labelled span; the grass-hidden pole foot is not modelled (grass hides an "
          "animal there anyway). Poles CH01 did not label stay capsules (vertical at the design grid unless measured).",
          "- The 7-in perturbation is the WISER error scale; WISER's own error is larger in some seconds.", "",
          "## Outputs", "",
          f"Run folder `{run.as_posix()}`: `occluders.json`, `checks.csv`, `visibility_mask.npz`, `miss_seconds_rebuilt.csv.gz`, "
          "`pole_edges_revg.csv`, `pole_triangulation_revg.csv`, `run.json`, `run_log.txt`; **sealed**: `episodes.csv`, "
          "`seconds.csv.gz` (`SEALED_README.txt`). house_1 pose `cv/configs/house1_cohort_pose_2026c.json`. Figures "
          f"`results/2026c/cv_field/figures/ch01_occlusion/`. Pointer `{POINTER_NAME}`.", "",
          "## Rerun", "", "```", "C:/Python313/python.exe cv/cv_field/ch01_occlusion.py --house1-fit   # the house_1 pose JSON",
          "C:/Python313/python.exe cv/cv_field/ch01_occlusion.py --run          # v2 (--v1 reproduces v1)", "```", ""]
    rep_dir.mkdir(parents=True, exist_ok=True)
    p = rep_dir / REPORT_NAME
    p.write_text("\n".join(L), encoding="utf-8")
    return p


# ----------------------------------------------------------------------------------------------- selftest
def selftest() -> int:
    ok = True

    def rec(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}", flush=True)

    rng = np.random.default_rng(0)
    # segment-segment distance vs dense sampling
    C = np.array([0.0, 0.0, 2000.0])
    Q = rng.uniform(-3000, 3000, (200, 3))
    A, B = np.array([1000.0, 200.0, 0.0]), np.array([1100.0, 150.0, 2400.0])
    d = seg_seg_dist(C, Q, A, B)
    s = np.linspace(0, 1, 801)
    brute = np.array([np.min(np.linalg.norm((C + s[:, None] * (q - C))[:, None, :] - (A + s[:, None] * (B - A))[None], axis=2)) for q in Q[:40]])
    rec("seg_seg_dist = brute-force minimum (40 segments)", np.max(np.abs(d[:40] - brute)) < 5.0, f"max diff {np.max(np.abs(d[:40] - brute)):.2f} mm")
    # convex clipping vs sampling
    Nb = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1.0]])
    Cb = np.array([1500, -1000, 300, 300, 600, 0.0])
    hit = seg_hits_convex(C, Q, Nb, Cb)
    pts = C[None, None] + s[None, :, None] * (Q - C)[:, None, :]
    inside = ((pts @ Nb.T) <= Cb + 1e-9).all(2).any(1)
    rec("seg_hits_convex = sampled segment inside the box (200 segments)", np.mean(hit == inside) > 0.99, f"agree {np.mean(hit == inside):.3f}")
    # synthetic scene: camera at the origin 2 m up, a pole at x = 1 m, a house box + roof further out
    poles = {"P": {"A": np.array([1000.0, 0.0, 0.0]), "B": np.array([1000.0, 0.0, 2400.0]), "radius_mm": 70.0, "source": "synthetic"}}
    sv = {"body_footprint": {"length": 62.55, "width": 45.72},
          "H": {"eave_height": {"a": 60.8}, "ridge_height": 87.8, "roof_slope_ridge_to_eave": [38.65], "ridge_length": 66}}
    house = house_model(sv, "H", 120.0, 60.0, 90.0, 0.0)                    # centre (3048, 1524) mm
    sc = Scene(C, poles, [house], lambda xy: np.zeros(len(np.asarray(xy).reshape(-1, 2))))
    xy_in = np.array([[3000.0, 0.0], [3000.0, 300.0], [3000.0, 200.0], [500.0, 0.0], [5000.0, 2500.0], [4000.0, 2000.0]]) / IN
    h, cnt = sc.assess(xy_in * IN)
    rec("pole: rat straight behind -> hidden (h 1); 300 mm aside -> clear; 200 mm aside -> partly; in front -> clear",
        h[0] == 1.0 and h[1] == 0.0 and 0 < h[2] < 1 and h[3] == 0.0, str(h[:4].round(3)))
    rec("house: a rat on the far side along the line of sight -> hidden by the house", h[4] >= 0.8 or h[5] >= 0.8,
        f"{h[4:].round(3)} (occluder {sc.names[int(np.argmax(cnt[4]))]})")
    # gable roof: a ray passing above the eave height but under the ridge, through the roof prism
    roofN, roofC = house["parts"][1]
    top = np.array([[3048.0, 1524.0, 800.0]])
    rec("roof prism contains a point under the ridge above the eaves; the body box does not",
        bool(((roofN @ top[0]) <= roofC + 1e-9).all()) and not bool(((house["parts"][0][0] @ top[0]) <= house["parts"][0][1] + 1e-9).all()))
    # classification and robustness: a pole 0.5 m from the camera throws a shadow +-420 mm wide at 3 m (> 7 in + 40 mm);
    # the same pole 1 m away (+-210 mm) cannot hide a rat robustly against a 7-in move
    sc2 = Scene(C, {"P": {**poles["P"], "A": np.array([500.0, 0.0, 0.0]), "B": np.array([500.0, 0.0, 2400.0])}}, [house], sc.ground)
    df = classify(sc2, np.array([[3000.0, 0.0], [3000.0, -1500.0], [3000.0, 425.0]]) / IN)   # shadow edge at ~424 mm
    df1 = classify(sc, np.array([[3000.0, 0.0]]) / IN)
    rec("classify: straight behind a near pole = robustly hidden; far aside = robustly clear; at the shadow edge = partly; "
        "behind a pole 1 m away = hidden at the nominal position but not robust (ambiguous)",
        df.loc[0, "category"] == "hidden" and df.loc[1, "category"] == "clear" and df.loc[2, "category"] == "partly"
        and df.loc[0, "occluder"] == "pole_P" and df1.loc[0, "nominal_class"] == "hidden" and df1.loc[0, "category"] == "ambiguous",
        df[["h", "h_min9", "h_max9", "category", "occluder"]].to_dict("records").__str__()[:300])
    # 7-in perturbation: a point 120 mm from the shadow edge flips under a 178-mm move
    df2 = classify(sc, np.array([[3000.0, 330.0]]) / IN)
    rec("7-in perturbation: clear at the nominal position but within 7 in of the shadow -> ambiguous",
        df2.loc[0, "nominal_class"] == "clear" and df2.loc[0, "category"] == "ambiguous", df2[["h", "h_max9", "category"]].to_dict("records").__str__())
    # episode majority and ties
    sec = pd.DataFrame({"episode_id": [1, 1, 1, 2, 2, 3, 3, 3, 3], "animal": ["SF07"] * 9,
                        "category": ["hidden", "hidden", "clear", "clear", "hidden", "partly", "partly", "ambiguous", "clear"],
                        "occluder": ["pole_P", "pole_P", "none", "none", "house_1", "pole_B2", "pole_B2", "pole_B1", "none"],
                        "h": [1, 1, 0, 0, 1, 0.5, 0.4, 0, 0], "nominal_class": ["hidden"] * 9})
    ep = episode_classes(sec)
    rec("episode class = unique majority, ties -> ambiguous; occluder = mode of non-clear seconds",
        ep["class"].tolist() == ["hidden", "ambiguous", "partly"] and ep["occluder"].tolist() == ["pole_P", "house_1", "pole_B2"],
        str(ep[["class", "occluder"]].to_dict("records")))
    pool = pooled(ep, sec)
    rec("pooled: shares sum to 1 and carry no episode id", abs(sum(v["share"] for v in pool["episodes_by_class"].values()) - 1) < 1e-9
        and "episode_id" not in json.dumps(pool))
    # mask on the synthetic scene: the pole's shadow is hidden behind it, not in front
    from matplotlib.path import Path as MPath
    mk = visibility_mask(sc, [MPath(np.array([[0.0, -100.0], [480.0, -100.0], [480.0, 240.0], [0.0, 240.0]]))])
    iy0 = int(np.argmin(np.abs(mk["y_in"] - 1.0)))
    behind = mk["h"][iy0, (mk["x_in"] > 60) & (mk["x_in"] < 150)]
    front = mk["h"][iy0, (mk["x_in"] > 5) & (mk["x_in"] < 30)]
    rec("visibility mask: the pole's shadow behind it (h 1 on the line), clear in front", np.all(behind == 1.0) and np.all(front == 0.0),
        f"behind min {behind.min()}, front max {front.max()}")
    # point-to-polyline distance
    rec("point_poly_dist", np.allclose(point_poly_dist(np.array([[0.0, 5.0], [15.0, 0.0]]), np.array([[0.0, 0.0], [10.0, 0.0]])), [5.0, 5.0]))
    # v2 label-plane pole: planes through C containing the pole's edge lines (x = 1000, y = -+70), span 0.3-1.8 m at the pole
    class _Cam:
        centre = C

        @staticmethod
        def rays(uv):                                   # synthetic: uv = (y, z) of a point on the plane x = 1000
            uv = np.asarray(uv, float).reshape(-1, 2)
            d = np.c_[np.full(len(uv), 1000.0), uv[:, 0], uv[:, 1]] - C
            return d / np.linalg.norm(d, axis=1, keepdims=True)
    labs = {"POLE_P_L": [[[-70.0, 300.0], [-70.0, 1800.0]]], "POLE_P_R": [[[70.0, 300.0], [70.0, 1800.0]]]}
    rec_p = {"A": np.array([1000.0, 0.0, 0.0]), "B": np.array([1000.0, 0.0, 2400.0]), "radius_mm": 70.0}
    pl = pole_planes(_Cam(), rec_p, labs, "P")
    Qp = np.array([[3000.0, 0.0, 60.0], [500.0, 0.0, 60.0], [3000.0, 600.0, 60.0], [1100.0, 0.0, 60.0], [3000.0, 150.0, 60.0]])
    hp_ = planes_hidden(C, Qp, pl)
    rec("label planes: behind the pole hidden; in front, outside the wedge and below the labelled span not; the plane "
        "edge at 3 m lies at +-210 mm", list(hp_) == [True, False, False, False, True]
        and planes_hidden(C, np.array([[3000.0, 230.0, 60.0]]), pl)[0] == False and abs(pl["rho_mm"] - 1000) < 1e-6,  # noqa: E712
        f"{hp_.tolist()}, span {pl['z_lo']:.0f}-{pl['z_hi']:.0f} mm, width {pl['angular_width_deg']:.2f} deg")
    # v2 clamp: perturbations near a wall are clamped inside the paddock (inset 1 in)
    st = {}
    df3 = classify(sc, np.array([[3.0, 120.0], [240.0, 120.0]]), clamp=True, stats=st)
    rec("clamp: a position 3 in from the x = 0 wall has 3 perturbations clamped (x - 7 cos a < 1); one in mid-field none",
        st["clamped"] == 3 and st["perturbations"] == 16 and len(df3) == 2, str(st))
    # house_check.py functions reused read-only (smoke test, needs the recording repo)
    try:
        cams_, cd_ = calib()
        hc = load_house_check(cd_)
        E, he, hr, run_ = hc["house_edges"]("HOUSE_1")
        rec("house_check.py loaded read-only (functions only): 15 rigid edges, eaves ~59 cm, ridge ~88 cm",
            len(E) == 15 and 580 < he < 600 and 870 < hr < 890 and set(HC_FUNCS) <= set(hc), f"{len(E)} edges, {he:.0f} / {hr:.0f} mm")
    except SystemExit as e:
        print(f"[SKIP] house_check smoke test ({e})")
    print(("PASS" if ok else "FAIL") + " — ch01_occlusion self-test")
    return 0 if ok else 1


def poles_only() -> int:
    cams, cd = calib()
    sv = survey(cd)
    radii = {p: per * IN / (2 * np.pi) for p, per in sv["poles"]["perimeter"].items()}
    files = sorted(LM_DIR.glob("landmarks_CH0[1-4]_20260918_*.json"))
    poles, prow, tri = pole_lines(cams, files, radii)
    pd.set_option("display.width", 250)
    print(tri.round(1).to_string())
    for p, r in poles.items():
        print(p, r["source"], "lean", round(r.get("lean_deg", 0), 2), "A", np.round(r["A"] / IN, 1), "r_mm", round(r["radius_mm"], 1))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--poles-only", action="store_true")
    ap.add_argument("--house1-fit", action="store_true", help="fit house_1's cohort pose -> cv/configs/house1_cohort_pose_2026c.json")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--v1", action="store_true", help="reproduce v1 (WISER-ROI house_1, capsule poles, no clamp)")
    ap.add_argument("--phase0", default=str(PHASE0_RUN))
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.poles_only:
        return poles_only()
    if a.house1_fit:
        cams, cd = calib()
        res = fit_house1_cohort(cams, cd)
        p = write_house1_json(res, cd)
        print(json.dumps({k: res[k] for k in ("main", "per_camera", "per_camera_spread_mm", "per_camera_pairwise_mm")}, indent=1, default=float)[:3000])
        print(json.dumps({k: (v if not isinstance(v, dict) else {kk: vv for kk, vv in v.items() if kk != "per_camera_residual"})
                          for k, v in res["sensitivity"].items()}, indent=1, default=float))
        print(f"-> {p}")
        return 0
    if a.run:
        return run(Path(a.phase0), Path(a.out) if a.out else None, v2=not a.v1)
    ap.error("nothing to do (--selftest, --poles-only or --run)")


if __name__ == "__main__":
    sys.exit(main())
