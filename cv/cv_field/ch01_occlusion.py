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


def classify(scene: Scene, xy_in: np.ndarray) -> pd.DataFrame:
    """Per position: nominal h / class / occluder, and the robustness over 8 positions 7 in away."""
    xy = np.asarray(xy_in, float).reshape(-1, 2)
    h0, c0 = scene.assess(xy * IN)
    hs, cnt = [h0], c0.copy()
    for k in range(N_DIR):
        a = 2 * np.pi * k / N_DIR
        hk, ck = scene.assess((xy + PERTURB_IN * np.array([np.cos(a), np.sin(a)])) * IN)
        hs.append(hk)
        cnt += ck
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


# ----------------------------------------------------------------------------------------------- run
def build_scene(cams, cd, mj: dict, log=print) -> tuple[Scene, dict, pd.DataFrame, pd.DataFrame, dict]:
    import wiser_assist_p0 as wp
    sv = survey(cd)
    radii = {p: per * IN / (2 * np.pi) for p, per in sv["poles"]["perimeter"].items()}
    files = sorted(LM_DIR.glob("landmarks_CH0[1-4]_20260918_*.json"))
    poles, prow, tri = pole_lines(cams, files, radii)
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
    house1 = house_model(sv["houses"], "HOUSE_1", float(h1p[0]), float(h1p[1]), ridge1, -HOUSE1_SOIL_BELOW_MM)
    c1 = cams[CAM]
    scene = Scene(c1.centre, poles, [house1, house2], lambda xy: ground(c1, xy))
    place = {"house_1": {"source": "WISER ROI house_1 centre through the accepted map", "wiser_roi_in": h1w.tolist(),
                         "paddock_in": h1p.tolist(), "ridge_deg": ridge1, "soil_z_mm": -HOUSE1_SOIL_BELOW_MM,
                         "vs_calibration_postmove_in": float(np.hypot(*(h1p - [HOUSE1_CALIB_POSTMOVE['cx_in'], HOUSE1_CALIB_POSTMOVE['cy_in']])))},
             "house_2": {"source": "calibration house check (rev g)", "paddock_in": [HOUSE2_POSE["cx_in"], HOUSE2_POSE["cy_in"]],
                         "ridge_deg": HOUSE2_POSE["ridge_deg"], "soil_z_mm": -HOUSE2_POSE["soil_below_mm"],
                         "wiser_roi_in": h2w.tolist(), "wiser_roi_mapped_in": h2p.tolist(),
                         "map_check_in": float(np.hypot(*(h2p - [HOUSE2_POSE['cx_in'], HOUSE2_POSE['cy_in']])))},
             "terrain_at_house_2_mm": float(ground(c1, (np.array([HOUSE2_POSE["cx_in"], HOUSE2_POSE["cy_in"]]) * IN)[None])[0]),
             "terrain_at_house_1_mm": float(ground(c1, (h1p * IN)[None])[0])}
    log(f"house_1 placed at ({h1p[0]:.1f}, {h1p[1]:.1f}) in, ridge {ridge1:.1f} deg; house_2 map check: WISER ROI -> "
        f"({h2p[0]:.1f}, {h2p[1]:.1f}) in vs calibration ({HOUSE2_POSE['cx_in']}, {HOUSE2_POSE['cy_in']}) = {place['house_2']['map_check_in']:.1f} in")
    return scene, place, prow, tri, {"house_1": house1, "house_2": house2}


def landmark_checks(cams, scene: Scene, houses: dict, log=print) -> tuple[pd.DataFrame, dict]:
    """09-18 labels in 09-18 px (+ IR -> colour offset, as house_check); the 09-04 cohort house_1 labels -> 09-18 px with
    Corrections.to_09_18 at the label frame time."""
    Corrections = _fc.Corrections
    c1 = cams[CAM]
    lab18 = load_labels(LM_0918)
    lab04 = load_labels(LM_0904)
    off = IR2COL[CAM]
    rows = []
    for p, rec in scene.poles.items():
        r = check_pole(c1, rec, lab18["landmarks"], p, off)
        if r is not None:
            rows.append({"object": f"pole_{p}", "labels": "09-18", "model": rec["source"].split(" (")[0], **r})
    r = check_house(c1, houses["house_2"], lab18["landmarks"], "HOUSE_2", offset=off)
    rows.append({"object": "house_2", "labels": "09-18", "model": "house check rev g pose", **r})
    t04 = datetime.strptime(lab04["time"], "%Y-%m-%d %H:%M:%S")
    C = Corrections(COHORT)
    info_holder = {}

    def to18(pts):
        q, info = C.to_09_18(CAM, t04, pts)
        info_holder.update(info)
        return np.asarray(q, float)
    r = check_house(c1, houses["house_1"], lab04["landmarks"], "HOUSE_1", to18=to18)
    rows.append({"object": "house_1", "labels": "09-04 cohort (-> 09-18 px)", "model": "WISER ROI through the map", **r})
    # code check (not a result): the calibration's own post-move house_1 against the 09-18 labels
    sv = survey(calib()[1])["houses"]
    h1post = house_model(sv, "HOUSE_1", HOUSE1_CALIB_POSTMOVE["cx_in"], HOUSE1_CALIB_POSTMOVE["cy_in"],
                         HOUSE1_CALIB_POSTMOVE["ridge_deg"], -HOUSE1_SOIL_BELOW_MM)
    r = check_house(c1, h1post, lab18["landmarks"], "HOUSE_1", offset=off)
    rows.append({"object": "house_1 (09-18 post-move pose; code check only)", "labels": "09-18", "model": "house check rev g pose", **r})
    df = pd.DataFrame(rows)
    df["flagged"] = df["median_px"] > FLAG_PX
    df.loc[df["object"].str.contains("code check"), "flagged"] = False
    B, binfo = C.correction(CAM, t04)
    ctr = np.array([c1.upright_size[0] / 2, c1.upright_size[1] / 2])
    bshift = (B[:, :2] @ ctr + B[:, 2]) - ctr
    corr = {"label_time": lab04["time"], "correction_used": binfo.get("used"), "flag": binfo.get("flag"),
            "B_shift_at_centre_px": bshift.tolist(),
            "note": "Corrections covers CH01 at night only; the 12:00 label frame gets the nearest sample of night 09-04 "
                    "(21:00). Cross-check: the daily 12:00 track (cv_field_landmark_track_20261001_1819) puts this frame at "
                    "tx, ty = +10.13, +1.96 px from 09-18 at the frame centre, i.e. 09-18 px = frame px - (10.13, 1.96)."}
    log("landmark checks: " + "; ".join(f"{r.object} {r.median_px:.1f} px{' FLAG' if r.flagged else ''}" for r in df.itertuples()))
    return df, corr


def run(phase0: Path, out: Path | None) -> int:
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
    scene, place, prow, tri, houses = build_scene(cams, cd, mj, log)
    prow.to_csv(out / "pole_edges_revg.csv", index=False)
    tri.to_csv(out / "pole_triangulation_revg.csv", index=False)
    occl = {"camera": {"name": CAM, "centre_mm": scene.C.tolist(), "centre_in": (scene.C[:2] / IN).tolist(), "source": "RayCamera.centre (rev g)"},
            "poles": {p: {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in r.items()} for p, r in scene.poles.items()},
            "houses": {k: {kk: (vv.tolist() if isinstance(vv, np.ndarray) else vv) for kk, vv in h.items() if kk not in ("parts", "edges")}
                       for k, h in houses.items()},
            "placement": place, "clean_rule": CLEAN, "pole_height_mm": POLE_H,
            "rat_model": {"heights_mm": RAT_Z, "lateral_mm": [-RAT_HALF, 0, RAT_HALF], "hidden_threshold": HIDDEN_T,
                          "perturbation_in": PERTURB_IN, "directions": N_DIR}}
    (out / "occluders.json").write_text(json.dumps(occl, indent=2, default=float), encoding="utf-8")
    log("poles: " + "; ".join(f"{p} {r['source'].split(':')[0].split(' (')[0]}" for p, r in scene.poles.items()))
    # occlusion of every suspected-miss second
    sec = sec_all[sec_all["miss"]].reset_index(drop=True)
    cl = classify(scene, sec[["paddock_x_in", "paddock_y_in"]].to_numpy(float))
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
    chkdf, corr = landmark_checks(cams, scene, houses, log)
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
            "cohort_label_correction": corr, "placement": place,
            "pole_sources": {p: r["source"] for p, r in scene.poles.items()},
            "sealed_files": ["episodes.csv", "seconds.csv.gz"], "figures": figs, "runtime_s": time.perf_counter() - t0}
    (out / "run.json").write_text(json.dumps(runj, indent=2, default=float), encoding="utf-8")
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
        ax.add_patch(plt.Circle(a, r["radius_mm"] / IN, color="C2" if r["source"].startswith("measured") else "C1", fill=True))
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
    ax.set_title("CH01 visibility mask (2-in cells in CH01's support): shadows of the poles (green = measured line, orange = "
                 "design grid) and houses (cyan)", fontsize=9)
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
    figrel = "../figures/" + FIG_SUB
    L = ["# CH01 occlusion geometry for the WISER-flagged suspected misses (poles, houses) — 2026c", "",
         f"Driver `cv/cv_field/ch01_occlusion.py`; plan `{PLAN}` (pre-registered, approved 2026-10-06 \"行上吧\"; amendment 1 "
         f"before results, amendment 2 after results = descriptive only); run `{run.as_posix()}`; generated {datetime.now():%Y-%m-%d %H:%M}; code `{rj['git_commit']}`; "
         f"calibration `{rj['calibration_dir']}` at recording-repo commit `{rj['recording_repo_commit']}` (frozen rev g; files "
         f"identical to phase 0's: {rj['calibration_same_as_phase0']}). Hour: CH01 2026-09-06 21:00–22:00, the phase-0 "
         "suspected misses. The agent did not look at any frame or figure. Geometry says *hidden*; it never makes a label — a "
         "hidden animal gets no box and a *clear* suspected miss is still only a proposal.", "",
         "**Blinding.** The user is filling `review_template.csv` of the phase-0 review clips. Per-episode and per-second "
         "classes are sealed in the run folder (`episodes.csv`, `seconds.csv.gz`); this report shows only pooled numbers over "
         "all episodes and the visibility mask. The phase-0 `wiser_spots.csv` stays unopened.", "",
         "## Pooled result", ""]
    L += [f"Suspected-miss episodes (n {pool['n_episodes']}) by geometry class: "
          + ", ".join(f"**{c} {pool['episodes_by_class'][c]['n']} ({pct(pool['episodes_by_class'][c]['share'])})**" for c in CATS) + ".",
          f"Suspected-miss seconds (n {pool['n_seconds']}) by category: "
          + ", ".join(f"{c} {pool['seconds_by_category'][c]['n']} ({pct(pool['seconds_by_category'][c]['share'])})" for c in CATS)
          + "; at the nominal WISER position alone: " + ", ".join(f"{c} {pct(v)}" for c, v in pool["seconds_by_nominal_class"].items()) + ".", "",
          "By occluder (episodes whose class is not *clear*; occluder = the most frequent occluder of their non-clear seconds; "
          "*landmark check* = the object's own check below — results of a flagged object carry the flag):", "",
          "| occluder | source | landmark check | hidden | partly | ambiguous | total |", "|---|---|---|---:|---:|---:|---:|"]

    def status(o):
        r = chk[chk["object"] == o]
        return "not checked (no CH01 labels)" if r.empty else (f"**flagged** ({r['median_px'].iloc[0]:.0f} px)" if r["flagged"].iloc[0]
                                                               else f"ok ({r['median_px'].iloc[0]:.0f} px)")

    def source(o):
        if o.startswith("pole_"):
            s = scene.poles[o[5:]]["source"]
            return "measured line" if s.startswith("measured") else "design grid"
        return pl.get(o, {}).get("source", "")
    for o, v in sorted(pool["episodes_by_occluder"].items(), key=lambda kv: -sum(kv[1].values())):
        L.append(f"| {o} | {source(o)} | {status(o)} | {v.get('hidden', 0)} | {v.get('partly', 0)} | {v.get('ambiguous', 0)} | {sum(v.values())} |")
    rw = pool.get("ring_crosses_wall", {}).get("by_occluder_share", {})
    L += ["", "Seconds by occluder (non-clear seconds; last column = share of them whose 7-in WISER ring crosses a paddock wall, "
          "amendment 2):", "", "| occluder | hidden | partly | ambiguous | total | ring crosses a wall |", "|---|---:|---:|---:|---:|---:|"]
    for o, v in sorted(pool["seconds_by_occluder"].items(), key=lambda kv: -sum(kv[1].values())):
        L.append(f"| {o} | {v.get('hidden', 0)} | {v.get('partly', 0)} | {v.get('ambiguous', 0)} | {sum(v.values())} | {pct(rw.get(o))} |")
    if "ring_crosses_wall" in pool:
        L += ["", f"Reading guide (amendment 2, descriptive): the 8 perturbed positions are not clipped to the paddock, so along a "
              "wall a 7-in move can put the animal outside, behind a wall-line pole; such seconds count as *ambiguous* "
              f"({pct(pool['ring_crosses_wall']['ambiguous_share'])} of all ambiguous seconds have a ring crossing a wall). A thin "
              "pole a few metres from CH01 throws a shadow narrower than the 7-in WISER uncertainty at the animal's distance, so "
              "it yields *partly* / *ambiguous*, almost never robustly *hidden*; the houses and the near pole B2 can hide robustly."]
    mk = rj["mask"]
    L += ["", f"Visibility mask: {mk['cells_in_support']} 2-in cells in CH01's support; a rat is hidden (h ≥ 0.8) in "
          f"{pct(mk['share_hidden_ge_0_8'])} of them and partly hidden in {pct(mk['share_partly'])}. Hidden share by object: "
          + ", ".join(f"{k} {pct(v)}" for k, v in sorted(mk["by_object_hidden_ge_0_8"].items(), key=lambda kv: -kv[1]) if v > 0) + ". "
          f"Figure [`visibility_mask.png`]({figrel}/visibility_mask.png); pooled classes [`class_shares.png`]({figrel}/class_shares.png); "
          "array `visibility_mask.npz` in the run folder.", "",
          "## Inputs and the rebuilt per-second table", "",
          f"The phase-0 per-second suspected-miss table had not been saved; it was rebuilt with the unchanged phase-0 code "
          f"(`wiser_assist_p0.prepare_boxes` + `part_c`, accepted map d ({rb['map']['dx_in']:.2f}, {rb['map']['dy_in']:.2f}) in, "
          f"θ {rb['map']['theta_deg']:.3f}°, s {rb['map']['scale']:.4f}, L {rb['L_s']:+.1f} s): {rb['n_miss']} suspected-miss seconds of "
          f"{rb['n_eligible']} eligible animal-seconds; the regenerated `fn_episodes.csv` is **byte-identical** to phase 0's: "
          f"{rb['episodes_byte_identical']} (`fn_grid.csv` too: {rb['grid_byte_identical']}). Saved as `miss_seconds_rebuilt.csv.gz`.", "",
          "## Occluders", "",
          f"Camera CH01 centre ({scene.C[0] / IN:.1f}, {scene.C[1] / IN:.1f}) in, {scene.C[2]:.0f} mm (`RayCamera.centre`). "
          f"Poles: capsules of the surveyed radius from the local ground to {POLE_H / 1000:.1f} m. Houses: the house check's rigid "
          "model (body box to the eave height + gable-roof prism with the 66-cm ridge and the roof overhang).", "",
          "| object | position (in) | source | size | lean |", "|---|---|---|---|---|"]
    for p, r in scene.poles.items():
        a = r["A"][:2] / IN
        L.append(f"| pole {p} | ({a[0]:.1f}, {a[1]:.1f}) at the ground | {r['source']} | r {r['radius_mm']:.0f} mm ({r['radius_source']}) | "
                 f"{r.get('lean_deg', 0):.1f}° |")
    for k, h in houses.items():
        L.append(f"| {k} | ({h['centre_in'][0]:.1f}, {h['centre_in'][1]:.1f}), ridge {h['ridge_deg']:.1f}° | "
                 f"{pl[k]['source']} | {h['footprint_cm'][0]:.2f} × {h['footprint_cm'][1]:.2f} cm, eaves {h['eave_mm'] / 10:.1f} cm, ridge "
                 f"{h['ridge_mm'] / 10:.1f} cm, soil at z {h['soil_z_mm']:.0f} mm | – |")
    L += ["", f"house_1 (moved on 09-18) is placed from the WISER ROI `house_1` ({pl['house_1']['wiser_roi_in'][0]:.1f}, "
          f"{pl['house_1']['wiser_roi_in'][1]:.1f}) through the accepted map → ({pl['house_1']['paddock_in'][0]:.1f}, "
          f"{pl['house_1']['paddock_in'][1]:.1f}) in, {pl['house_1']['vs_calibration_postmove_in']:.1f} in from the calibration's "
          "post-move position (147.5, 121.7) — not used. Map check on house_2: its WISER ROI through the same map lands at "
          f"({pl['house_2']['wiser_roi_mapped_in'][0]:.1f}, {pl['house_2']['wiser_roi_mapped_in'][1]:.1f}) in, "
          f"**{pl['house_2']['map_check_in']:.1f} in** from the calibration's (342.4, 117.7): the ROI rectangles are hand-placed, so "
          "house_1's WISER placement carries an error of that order.", ""]
    good = tri.copy()
    L += ["### Pole re-measurement (amendment 1)", "",
          "The pole check (`calibration_qc/pole_check.py`, `session_2026-09-18_pole_check.txt`, 2026-10-01) ran on a fit "
          "before revisions e–g, so its method was re-run read-only on the frozen rev g cameras with the operator's 09-18 "
          "pole-edge labels (CH01–CH04): per camera and height the axis offset across the line of sight, then per height the "
          "least-squares crossing of the cameras' lines. Clean rule (fixed before any occlusion result): ≥ "
          f"{CLEAN['min_heights']} heights each seen by ≥ 2 cameras crossing at ≥ {CLEAN['min_angle_deg']:.0f}° (camera residual ≤ "
          f"{CLEAN['max_cam_resid_mm']:.0f} mm with ≥ 3 cameras), a straight line in height through them with residuals ≤ "
          f"{CLEAN['max_line_resid_mm']:.0f} mm, its 1.05-m point ≤ {CLEAN['max_from_design_mm']:.0f} mm from the design grid, "
          f"and a lean ≤ {CLEAN['max_lean_deg']:.0f}° (this bound was added after the pole table, before any occlusion result; it "
          "removes only A4, whose two-height line leaned 23°); else the vertical design-grid line. Per-height triangulations: "
          "`pole_triangulation_revg.csv`. Check against the operator's tape (survey, centre to centre at ≈ 1.05 m), measured "
          "lines at 1.05 m above the ground: " + tape_txt(scene) + ".", ""]
    L += ["## Landmark checks (model projected into CH01 vs the user's labels)", "",
          f"Median pixel distance from the labelled edges to the projected model edges (poles: left / right silhouette; houses: "
          f"each label piece to its nearest allowed rigid edge, house_check's classes). Flag > {FLAG_PX:.0f} px (results then "
          "flagged, not refitted). 09-18 labels compared in 09-18 px (+ the IR → colour offset (0.68, −0.39) px, as "
          "house_check); the 09-04 cohort house_1 labels mapped to 09-18 px with `Corrections.to_09_18` at the label time "
          f"({rj['cohort_label_correction']['label_time']}; correction sample {rj['cohort_label_correction']['correction_used']}, "
          f"flag {rj['cohort_label_correction']['flag']}; its shift at the frame centre "
          f"({rj['cohort_label_correction']['B_shift_at_centre_px'][0]:+.1f}, {rj['cohort_label_correction']['B_shift_at_centre_px'][1]:+.1f}) px; "
          "the daily 12:00 track of that frame gives (−10.1, −2.0) px — the night sample is used as instructed, the "
          "difference is stated).", "",
          "| object | labels | model | label points | median px | p90 px | flagged |", "|---|---|---|---:|---:|---:|---|"]
    for r in chk.itertuples():
        L.append(f"| {r.object} | {r.labels} | {r.model} | {r.n_points} | {r.median_px:.1f} | {r.p90_px:.1f} | {'**yes**' if r.flagged else 'no'} |")
    fl = chk[chk["flagged"]]["object"].tolist()
    L += ["", ("Flagged: " + ", ".join(fl) + ". The occlusion results involving a flagged object carry that flag (the pooled "
               "by-occluder rows above name the object)." if fl else "No object is flagged."), "",
          "Why (descriptive, amendment 2): the design-grid poles A0, B0, C0, C1 miss their labels by 25–58 px, i.e. ≈ 0.6–1.4° "
          "or ≈ 8–15 cm across the line of sight at 4.9–8.2 m — the 10-ft grid is not control (the calibration says so). "
          "B2 stands 0.82 m from CH01, and CH01 and CH02 see it from nearly opposite sides (17° from collinear), so its "
          "position along that line is poorly constrained; its 45 px are ≈ 1° ≈ 15 mm across CH01's line of sight (a "
          "diagnostic exact-ray triangulation, not used, is far less stable). house_1's 125 px is the WISER-ROI placement "
          "error (house_2's ROI through the same map lands 7.2 in from its calibrated position). The code check (the "
          "calibration's own post-move house_1 against the 09-18 labels, 19.5 px; house_2 9.8 px) matches the calibration's "
          "reported fit (rays miss by a median 24 / 11 mm), so the projection itself is sound. The 3-px agreement of B1 and B3 "
          "is not an independent test: CH01's own pole-edge labels entered their triangulation. The 09-04 label correction "
          "(night sample) and the daily 12:00 track differ by ≈ 5 px at the frame centre, immaterial next to house_1's miss.", ""]
    L += ["## Definitions", "",
          "Units: paddock mm / inches (origin pole A0); z = the calibration's absolute height datum (camera centre, terrain, "
          "house soil levels). $\\mathbf C$ = CH01's centre; $\\mathbf p$ = an animal's paddock position (WISER through the "
          "accepted map); $g(\\mathbf p)$ = local ground height (terrain).", "",
          "### Rat sample points",
          "$$ \\mathbf q_{kl}=\\big(\\mathbf p+o_l\\,\\hat{\\mathbf n},\\ g(\\mathbf p)+z_k\\big),\\quad z_k\\in\\{30,60,90\\}\\,\\mathrm{mm},"
          "\\ o_l\\in\\{-40,0,40\\}\\,\\mathrm{mm} $$ **Text:** a rat's body as 9 points; $\\hat{\\mathbf n}$ = horizontal unit "
          "normal to the line of sight from CH01.", "",
          "### Hidden share $h$",
          "$$ h(\\mathbf p)=\\frac{1}{9}\\sum_{k,l}\\mathbb 1\\big[\\exists\\,O:\\ [\\mathbf C,\\mathbf q_{kl}]\\cap O\\neq\\emptyset\\big] $$ "
          "**Text:** share of the body points whose line of sight to the camera passes through a pole capsule (segment–axis "
          "distance ≤ radius) or a house part (Cyrus–Beck clipping of the segment by the convex part). Range [0, 1].", "",
          "### Classes",
          "nominal: hidden $h\\ge0.8$, partly $0<h<0.8$, clear $h=0$. Robust over the nominal position and 8 positions "
          "7 in away (WISER uncertainty): robustly hidden = hidden at all 9, robustly clear = $h=0$ at all 9. **Category** "
          "(amendment 1): hidden = robustly hidden; clear = robustly clear; partly = nominal $0<h<0.8$; ambiguous = otherwise. "
          "**Episode class** = the unique majority category of its seconds (ties → ambiguous). **Occluder** of a second = the "
          "object blocking the most sample points summed over the 9 positions; of an episode = the most frequent occluder of "
          "its non-clear seconds.", "",
          "### Landmark distance",
          "$$ d_i=\\min_{\\mathbf s\\in\\pi(E)}\\lVert \\mathbf u_i-\\mathbf s\\rVert $$ **Text:** pixel distance from a densified "
          "label point $\\mathbf u_i$ (every ≈ 15 px) to the projected model edge $\\pi(E)$ (3-D edge points projected with the "
          "calibration's own inverse, each verified to 0.02°); median per object.", "",
          "## Caveats", "",
          "- Grass, other rats, the animal's posture and objects not surveyed (water dish, feeders, cables) are not modelled: "
          "they can hide a *clear* animal. One hour, one camera.",
          "- house_1's cohort position comes from a hand-placed WISER ROI through the map (house_2's ROI lands "
          f"{pl['house_2']['map_check_in']:.1f} in from its calibrated position); its landmark check says how far off the box is.",
          "- Poles not measured cleanly stand vertical at the design grid; the survey shows the B row 11 in short (B0 / B4 "
          "inside the line).",
          "- The 7-in perturbation is the WISER error scale; WISER's own error is larger in some seconds.", "",
          "## Outputs", "",
          f"Run folder `{run.as_posix()}`: `occluders.json`, `checks.csv`, `visibility_mask.npz`, `miss_seconds_rebuilt.csv.gz`, "
          "`pole_edges_revg.csv`, `pole_triangulation_revg.csv`, `run.json`, `run_log.txt`; **sealed**: `episodes.csv`, "
          "`seconds.csv.gz` (`SEALED_README.txt`). Figures `results/2026c/cv_field/figures/ch01_occlusion/`. Pointer "
          f"`{POINTER_NAME}`.", "",
          "## Rerun", "", "```", "C:/Python313/python.exe cv/cv_field/ch01_occlusion.py --run", "```", ""]
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
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--phase0", default=str(PHASE0_RUN))
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.poles_only:
        return poles_only()
    if a.run:
        return run(Path(a.phase0), Path(a.out) if a.out else None)
    ap.error("nothing to do (--selftest, --poles-only or --run)")


if __name__ == "__main__":
    sys.exit(main())
