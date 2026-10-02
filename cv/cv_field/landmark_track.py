"""landmark_track.py — track the user's rigid landmarks from the 09-18 reference into every review frame and fit the
image correction cohort pixel -> calibration-epoch pixel (per camera, per frame).

Plan: implementation_plan/2026-09-28-cohort3-camera-stability.md (revision 2). Labels: cv/configs/landmarks/2026c/
landmarks_<CH>_20260918_*.json (the user's, on the 09-18 IR reference frames; format "pieces").

Method (no visual judgement; the user reviews the overlays):
  1. Reference = the labelled 09-18 IR frame (re-grabbed from the calibration session); targets = raw frames grabbed with
     cv/cv_field/grab_frames.py (no overlays drawn on them) at the review times (default 03:01 / 12:00 / 21:30 daily).
  2. Both images -> CLAHE, Gaussian blur (sigma 1.5), gradient magnitude. Gradient magnitude ignores edge polarity, so
     two parallel edges (a pole's L and R, a box's top and bottom) look alike: matching is therefore COARSE-TO-FINE.
     Coarse: a few ~120-px patches per fit-set landmark (they contain ends/corners/context) at half resolution, +/-120 px,
     as 2-D matches -> Huber affine A0. Fine: points sampled along every labelled piece (every STEP px, at most
     MAX_PER_LM per landmark), each a (2H+1)^2 patch matched by normalised cross-correlation (cv2.TM_CCOEFF_NORMED,
     parabolic sub-pixel) within +/-R = 8 px of A0's prediction — too small a window to jump to a neighbouring edge.
  3. Constraints: on lines (pole edges, wall tops, house edges, tower outline) only the displacement component along the
     local NORMAL is informative (aperture problem) -> one equation n.(A p) = n.(p + d); at the labelled corners of BOX_*,
     PCBOX and HOUSE_*_LABEL the full 2-D displacement -> two equations A p = p + d. Samples with NCC < S_MIN are dropped.
  4. Fit an affine map A (ref -> target, 6 parameters) by iteratively re-weighted least squares (Huber, k = 2 px) on the
     FIT SET, in two tiers (user, 2026-10-01: nails are very stable; patches sit low on the wall and a rat can hide them;
     people can stand in front of the distant building):
       stable      POLE_*, BOX_*, WALLTOP_*, TOWER_*, PCBOX, NAILS, SEAM(S)  -> fitted first (A_s; also the coarse stage)
       occludable  PATCH_* / PATCHES, BUILDING, WOOD -> every PIECE is its own unit ("NAME#k"), at most OCC_CAP samples, and
                   enters the final fit only if >= OCC_MATCH_MIN of its samples matched and its median residual under
                   A_s is <= OCC_RES_MAX px; otherwise it is DROPPED for that frame (listed per frame).
     PATCHES are matched as BLOCKS (user, 2026-10-01: a patch is a dark block on the white wall): the labelled outline
     is closed (ends joined; an end gap > BLOCK_OPEN_GAP px = a grass-hidden bottom, whose joining band is masked out),
     and the whole block plus a BLOCK_MARGIN-px rim is one masked NCC template -> one 2-D displacement per patch.
     If the stable tier alone does not pin both image directions, a provisional fit on both tiers stands in for A_s
     (basis = "all"). Houses are VALIDATION only (HOUSE_1 = roof 4 was moved on 09-18 -> used only on frames dated
     >= 09-18; HOUSE_2 = roof 7 never moved -> all frames).
  5. Held-out error: leave-one-landmark-out over the fit set — refit without landmark L, residuals of L's samples; per
     frame the median and p90 over landmarks of their median |residual|.
Definitions: residual r = n.(A p - (p + d)) for line samples, |A p - (p + d)| for corners [px, full-res upright];
held_med / held_p90 = median / 90th percentile over fit units (landmarks; occludable pieces count singly) of median|r|
under leave-one-out [px]; dropped = occludable pieces left out of the fit in that frame;
status = ok if >= 4 fit units matched, both near-vertical and near-horizontal constraints present, held_med <= 3 px
and held_p90 <= 6 px; else unreliable. tx, ty = A applied to the frame centre minus the centre [px]; rot = mean rotation
of A's columns [deg]; sx, sy = column norms of A's linear part.

Cohort reference + tie (user, 2026-10-01; CH04's 09-18 frame had people in view and daily tracking from it failed):
  --ref-labels <landmarks_CHxx_<date>_<time>.json> makes a user-labelled COHORT frame the reference for its camera, and
  --tie fits the map 09-18 px -> reference px directly from the two label sets (tie_labels: ICP point-to-curve on the
  named landmarks, then unnamed items — nails, patches, seams, building, wood — paired by nearest neighbour and gated at
  TIE_GATE px; leave-one-unit-out held-out error). The reported shift is then that of A_track o A_tie (09-18 -> frame).
  house_1 is usable only when the reference and the frame lie on the same side of its 09-18 move.

Usage: python cv/cv_field/landmark_track.py --cohort 2026c [--cameras CH01 CH02 CH03 CH04] [--start 2026-08-30 --end 2026-09-17]
                                            [--times 12:00] [--ref-labels <json> ...] [--tie] [--tag <name>]
       python cv/cv_field/landmark_track.py --selftest
Output: $FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/cv_field_landmark_track[_<tag>]_<ts>/ (frames, overlays, <CH>_track.mp4,
CSVs) and results/<cohort>/cv_field/reports/cv_field_landmark_track_<cohort>[_<tag>].md (+ run_manifest.json, or
run_manifest_landmark_track_<tag>_<cohort>.json with --tag).
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _p in (str(HERE), str(HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

H, R, STEP, MAX_PER_LM, S_MIN = 20, 8, 14, 40, 0.45      # fine stage: small patch, +/-8 px around the coarse prediction
H1, R1, COARSE_SCALE, COARSE_PER_LM = 30, 60, 0.5, 4      # coarse stage (half resolution): ~120 px patches, +/-120 px search
CORNER_PREFIXES = ("BOX_", "PCBOX", "NAILS", "CORNERS", "LABELS")              # NAILS = unnumbered points (each a 2-D constraint)
# PATCH_<wall>_<n> = a visible patch on a wall sheet: an OPEN, bumpy polyline (corrugation; the bottom is often hidden by
# grass) -> normal-only constraints like the wall tops, in the fit set (user, 2026-10-01)
# SEAM_<wall>_<n> = a vertical seam between wall panels (straight, vertical): normal-only like the pole edges
# BUILDING = edges of a building wall outside the paddock (CH04; user, 2026-10-01): normal-only like the wall tops
# WOOD = a piece of wood in CH04's view (user, 2026-10-01): near the ground -> occludable tier
FIT_PREFIXES = ("POLE_", "BOX_", "WALLTOP_", "TOWER_", "PCBOX", "PATCH_", "SEAM_", "NAILS", "PATCHES", "SEAMS",
                "BUILDING", "WOOD", "FOODBOX", "DOORFRAME", "INNER_EDGES", "CORNERS", "LABELS")   # CH07/CH08 in-box items (user, 2026-10-02)
# Occludable tier (user, 2026-10-01): patches sit low on the wall (a rat can hide one), people can stand in front of the
# distant building -> each piece is checked against the stable tier before it may enter the fit
OCCLUDABLE_PREFIXES = ("PATCH", "BUILDING", "WOOD")       # PATCH_<wall>_<n>, PATCHES, BUILDING, WOOD
OCC_CAP, OCC_MATCH_MIN, OCC_RES_MAX = 12, 0.6, 3.0
# Patches = dark blocks on the white wall (user, 2026-10-01) -> one masked 2-D template per patch
BLOCK_PREFIXES = ("PATCH",)
BLOCK_MARGIN, BLOCK_OPEN_GAP = 6, 30
# Label-to-label tie (--tie): items without a correspondence across frames are paired by nearest neighbour
UNNAMED_PREFIXES = ("NAILS", "PATCH", "SEAM", "BUILDING", "WOOD")
TIE_STEP, TIE_PAIR_MAX, TIE_GATE = 10.0, 15.0, 3.0
HELD_MED_MAX, HELD_P90_MAX = 3.0, 6.0
PRIOR_W = 1e4                                             # weak identity prior on the affine's linear part
HOUSE1_MOVED = date(2026, 9, 18)
IR_REF = {"CH01": "2026-09-18 13:57:30", "CH02": "2026-09-18 15:22:30", "CH03": "2026-09-18 15:45:00", "CH04": "2026-09-18 14:32:30"}


def base(unit: str) -> str:
    """Landmark name of a fit unit ("PATCHES#2" -> "PATCHES")."""
    return unit.split("#")[0]


def is_corner_lm(name: str) -> bool:
    name = base(name)
    return name.startswith(CORNER_PREFIXES) or name.endswith("_LABEL")


# Per camera (user, 2026-10-02): CH05 / CH06 hang from a crossbeam on top of pole B1 / B3, so that pole and its box move
# WITH the camera (validation only — they check that beam and camera are one piece); the house below is their main
# rigid structure (in the fit; house_1 only on the reference's side of its 09-18 move, see usable()).
CAM_FIT_PREFIXES = {"CH05": ("HOUSE_1_",), "CH06": ("HOUSE_2_", "BLUETOOTH_ANTENNA")}
CAM_ATTACHED = {"CH05": ("POLE_B1_", "BOX_B1"), "CH06": ("POLE_B3_", "BOX_B3")}
_CAM = None


def set_camera(cam: str | None) -> None:
    """Select the per-camera fit rules (CAM_FIT_PREFIXES / CAM_ATTACHED) for the following calls."""
    global _CAM
    _CAM = cam


def in_fit(name: str) -> bool:
    b = base(name)
    if _CAM in CAM_ATTACHED and b.startswith(CAM_ATTACHED[_CAM]):
        return False
    if _CAM in CAM_FIT_PREFIXES and b.startswith(CAM_FIT_PREFIXES[_CAM]):
        return True
    return b.startswith(FIT_PREFIXES)


def occludable(name: str) -> bool:
    return base(name).startswith(OCCLUDABLE_PREFIXES)


def usable(name: str, frame_day: date, ref_day: date = HOUSE1_MOVED) -> bool:
    """house_1 was moved on 09-18: its labels hold only for frames on the same side of the move as the reference."""
    return not (base(name).startswith("HOUSE_1_") and (frame_day >= HOUSE1_MOVED) != (ref_day >= HOUSE1_MOVED))


def is_block(name: str) -> bool:
    return base(name).startswith(BLOCK_PREFIXES)


def block_of(p: np.ndarray) -> dict | None:
    """A patch piece as a block: the labelled outline closed by joining its ends; centroid = polygon centroid. An end
    gap > BLOCK_OPEN_GAP px = an open (grass-hidden) bottom: the joining segment is not a real edge."""
    if len(p) < 3:
        return None
    m = cv2.moments(p.astype(np.float32))
    c = np.array([m["m10"] / m["m00"], m["m01"] / m["m00"]]) if abs(m["m00"]) > 1.0 else p.mean(0)
    return {"poly": p, "c": c, "open": float(np.hypot(*(p[-1] - p[0]))) > BLOCK_OPEN_GAP}


def block_template(ref_g: np.ndarray, blk: dict):
    """(template, mask, top-left) of a block: its bounding box + BLOCK_MARGIN; mask = the closed outline filled and
    dilated by BLOCK_MARGIN (so the rim of white wall and the outline's edges are in), minus a band along the joining
    segment of an open block (grass there)."""
    P = blk["poly"]
    Hh, Ww = ref_g.shape
    x0, y0 = (np.floor(P.min(0)) - BLOCK_MARGIN).astype(int)
    x1, y1 = (np.ceil(P.max(0)) + BLOCK_MARGIN + 1).astype(int)
    if x0 < 0 or y0 < 0 or x1 > Ww or y1 > Hh:
        return None
    mask = np.zeros((y1 - y0, x1 - x0), np.uint8)
    q = np.round(P - (x0, y0)).astype(np.int32).reshape(-1, 1, 2)
    cv2.fillPoly(mask, [q], 255)
    cv2.polylines(mask, [q], False, 255, 1)
    mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * BLOCK_MARGIN + 1,) * 2))
    if blk["open"]:
        cv2.line(mask, tuple(int(v) for v in q[-1, 0]), tuple(int(v) for v in q[0, 0]), 0, 3 * BLOCK_MARGIN)
    return ref_g[y0:y1, x0:x1], (mask > 0).astype(np.float32), (x0, y0)


def match_block(ref_g: np.ndarray, tgt_g: np.ndarray, blk: dict, pred_c, r: int = R) -> tuple[float, float, float] | None:
    """Masked NCC of the whole block within +/-r px of its predicted position -> displacement of its centroid + score."""
    bt = block_template(ref_g, blk)
    if bt is None:
        return None
    tpl, mask, (x0, y0) = bt
    if mask.sum() < 50 or float(tpl[mask > 0].std()) < 0.02:
        return None
    h, w = tpl.shape
    ox, oy = int(round(x0 + pred_c[0] - blk["c"][0])) - r, int(round(y0 + pred_c[1] - blk["c"][1])) - r
    Hh, Ww = tgt_g.shape
    if ox < 0 or oy < 0 or ox + w + 2 * r > Ww or oy + h + 2 * r > Hh:
        return None
    res = np.nan_to_num(cv2.matchTemplate(tgt_g[oy:oy + h + 2 * r, ox:ox + w + 2 * r], tpl, cv2.TM_CCOEFF_NORMED, mask=mask),
                        nan=-1.0, posinf=-1.0, neginf=-1.0)
    _, score, _, (px, py) = cv2.minMaxLoc(res)

    sub = subpix
    fx = px + (sub(res[py, px], res[py, px - 1], res[py, px + 1]) if 0 < px < res.shape[1] - 1 else 0.0)
    fy = py + (sub(res[py, px], res[py - 1, px], res[py + 1, px]) if 0 < py < res.shape[0] - 1 else 0.0)
    return float(ox + fx - x0), float(oy + fy - y0), float(score)


def units_of(landmarks: dict, frame_day: date, ref_day: date = HOUSE1_MOVED) -> dict[str, list[np.ndarray]]:
    """Fit units: a landmark is one unit, except that every piece of a multi-piece occludable landmark is its own unit
    ("NAME#k", k from 1), so one hidden patch or building edge is dropped without losing the others."""
    out = {}
    for name, v in landmarks.items():
        if not usable(name, frame_day, ref_day):
            continue
        ps = pieces_of(v)
        if occludable(name) and len(ps) > 1:
            out.update({f"{name}#{k}": [p] for k, p in enumerate(ps, 1)})
        else:
            out[name] = ps
    return out


def prep(img: np.ndarray) -> np.ndarray:
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    g = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(g)
    g = cv2.GaussianBlur(g, (0, 0), 1.5).astype(np.float32)
    mag = cv2.magnitude(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))
    return (mag / (np.percentile(mag, 99) + 1e-6)).astype(np.float32)


def pieces_of(v) -> list[np.ndarray]:
    ps = v if (v and isinstance(v[0][0], (list, tuple))) else [v]
    return [np.asarray(p, float) for p in ps if len(p) >= 1]


def samples(name: str, kind: str, pieces: list[np.ndarray], cap: int | None = None) -> list[tuple[float, float, float, float, bool]]:
    """(x, y, nx, ny, is_corner) along a landmark. Corners: the labelled vertices of BOX_/PCBOX/_LABEL outlines."""
    out = []
    corner_lm = is_corner_lm(name)
    closed = kind == "outline" and len(pieces) == 1
    for p in pieces:
        if len(p) < 2:
            if corner_lm and len(p) == 1:                     # a single labelled point (NAILS): a 2-D constraint
                out.append((float(p[0][0]), float(p[0][1]), 0.0, 0.0, True))
            continue
        pts = np.vstack([p, p[:1]]) if closed and len(p) > 2 else p
        segs = []
        for a, b in zip(pts[:-1], pts[1:]):
            d = b - a
            L = float(np.hypot(*d))
            if L < 1e-6:
                continue
            n = np.array([-d[1], d[0]]) / L
            k = max(1, int(L // STEP))
            for t in (np.arange(k) + 0.5) / k:
                q = a + t * d
                segs.append((float(q[0]), float(q[1]), float(n[0]), float(n[1]), False))
        if corner_lm:
            segs += [(float(x), float(y), 0.0, 0.0, True) for x, y in p]
        out += segs
    cap = cap or max(MAX_PER_LM, 12 * len(pieces))            # multi-item landmarks (NAILS, SEAMS) keep ~12 per item
    if len(out) > cap:
        keep = np.linspace(0, len(out) - 1, cap).round().astype(int)
        corners = [s for s in out if s[4]]
        out = [out[i] for i in keep if not out[i][4]] + corners
    return out


def subpix(c: float, l: float, rr: float) -> float:
    """Sub-pixel offset of a correlation peak c between neighbours l and rr: 3-point Gaussian fit when all three are
    positive (a parabola pulls small shifts towards the integer pixel — "pixel locking", ~0.2 px at a 0.45-px shift,
    which accumulates over chained frames), else a parabola."""
    if c > 0 and l > 0 and rr > 0:
        a, b, d = np.log(l), np.log(c), np.log(rr)
        den = a - 2 * b + d
        if den < -1e-12:
            return float(np.clip(0.5 * (a - d) / den, -0.5, 0.5))
    den = l - 2 * c + rr
    return 0.0 if abs(den) < 1e-9 else float(np.clip(0.5 * (l - rr) / den, -0.5, 0.5))


def match(ref_g: np.ndarray, tgt_g: np.ndarray, x: float, y: float, cx: float | None = None, cy: float | None = None,
          h: int = H, r: int = R) -> tuple[float, float, float] | None:
    """NCC of the (2h+1)^2 reference patch at (x, y) searched within +/-r px of (cx, cy) in the target (default: the same
    place). Returns the displacement (dx, dy) of (x, y) and the peak score."""
    cx = x if cx is None else cx
    cy = y if cy is None else cy
    xi, yi, ci, cj = int(round(x)), int(round(y)), int(round(cx)), int(round(cy))
    Hh, Ww = ref_g.shape
    if not (h <= xi < Ww - h and h <= yi < Hh - h and h + r <= ci < Ww - h - r and h + r <= cj < Hh - h - r):
        return None
    tpl = ref_g[yi - h:yi + h + 1, xi - h:xi + h + 1]
    if float(tpl.std()) < 0.02:
        return None
    win = tgt_g[cj - h - r:cj + h + r + 1, ci - h - r:ci + h + r + 1]
    res = cv2.matchTemplate(win, tpl, cv2.TM_CCOEFF_NORMED)
    _, score, _, (px, py) = cv2.minMaxLoc(res)

    sub = subpix
    ox = px + (sub(res[py, px], res[py, px - 1], res[py, px + 1]) if 0 < px < res.shape[1] - 1 else 0.0) - r
    oy = py + (sub(res[py, px], res[py - 1, px], res[py + 1, px]) if 0 < py < res.shape[0] - 1 else 0.0) - r
    return float(ci + ox - x), float(cj + oy - y), float(score)


def coarse_affine(ref_g, tgt_g, landmarks: dict, frame_day: date, stable_only: bool = True,
                  ref_day: date = HOUSE1_MOVED) -> np.ndarray:
    """Stage 1: a few large patches per fit-set landmark (they include ends/corners/context, so parallel edges cannot be
    confused) matched at half resolution over +/-R1/scale px, treated as 2-D matches -> Huber affine. Stable tier first,
    both tiers if that gives too few; identity if still too few."""
    s = COARSE_SCALE
    rs = cv2.resize(ref_g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    ts = cv2.resize(tgt_g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    obs = []
    for name, v in landmarks.items():
        if not (in_fit(name) and usable(name, frame_day, ref_day)) or (stable_only and occludable(name)):
            continue
        pts = np.vstack([p for p in pieces_of(v) if len(p)])
        for q in pts[np.linspace(0, len(pts) - 1, min(COARSE_PER_LM, len(pts))).round().astype(int)]:
            m = match(rs, ts, q[0] * s, q[1] * s, h=H1, r=R1)
            if m and m[2] >= S_MIN:
                obs.append(((float(q[0]), float(q[1]), 0.0, 0.0, True), (m[0] / s, m[1] / s), m[2]))
    A = fit_affine(obs) if len({o[0][:2] for o in obs}) >= 3 else None
    if A is None and stable_only:
        return coarse_affine(ref_g, tgt_g, landmarks, frame_day, stable_only=False, ref_day=ref_day)
    return A if A is not None else np.array([[1.0, 0, 0], [0, 1.0, 0]])


def constrained(obs: list) -> bool:
    """Do these observations pin both image directions? (corners, or near-vertical AND near-horizontal lines)"""
    v = any(not s[4] and abs(s[2]) > 0.7 for s, _, _ in obs)
    hz = any(not s[4] and abs(s[3]) > 0.7 for s, _, _ in obs)
    c = sum(1 for s, _, _ in obs if s[4]) >= 2
    return (v and hz) or c


def rows_for(s, d):
    """Linear equations in the affine parameters a = [a11 a12 a13 a21 a22 a23] for one sample."""
    x, y, nx, ny, corner = s
    dx, dy = d
    if corner:
        return [([x, y, 1, 0, 0, 0], x + dx), ([0, 0, 0, x, y, 1], y + dy)]
    return [([nx * x, nx * y, nx, ny * x, ny * y, ny], nx * (x + dx) + ny * (y + dy))]


def fit_affine(obs: list) -> np.ndarray | None:
    """obs = [(sample, (dx, dy), weight)] -> 2x3 affine by Huber IRLS (k = 2 px), with a weak prior (PRIOR_W) pulling the
    linear part to the identity: negligible where the data constrain it (hundreds of samples with ~1000-px lever arms),
    it keeps a direction the data leave free (e.g. vertical scale from two vertical poles and one wall top) from drifting."""
    rows = [(r, b, w) for s, d, w in obs for r, b in rows_for(s, d)]
    if len(rows) < 6:
        return None
    rows += [([1, 0, 0, 0, 0, 0], 1.0, PRIOR_W), ([0, 1, 0, 0, 0, 0], 0.0, PRIOR_W),
             ([0, 0, 0, 1, 0, 0], 0.0, PRIOR_W), ([0, 0, 0, 0, 1, 0], 1.0, PRIOR_W)]
    M = np.array([r for r, _, _ in rows], float)
    b = np.array([v for _, v, _ in rows], float)
    w0 = np.array([w for _, _, w in rows], float)
    wt = w0.copy()
    a = None
    for _ in range(10):
        sw = np.sqrt(wt)
        a, *_ = np.linalg.lstsq(M * sw[:, None], b * sw, rcond=None)
        r = np.abs(M @ a - b)
        wt = w0 * np.where(r <= 2.0, 1.0, 2.0 / np.maximum(r, 1e-9))
    return np.array([[a[0], a[1], a[2]], [a[3], a[4], a[5]]])


def residual(A: np.ndarray, s, d) -> float:
    x, y, nx, ny, corner = s
    p = np.array([x, y])
    q = A[:, :2] @ p + A[:, 2]
    e = q - (p + np.asarray(d))
    return float(np.hypot(*e)) if corner else float(abs(nx * e[0] + ny * e[1]))


def track_frame(ref_g, tgt_g, landmarks: dict, kinds: dict, frame_day: date, ref_day: date = HOUSE1_MOVED) -> dict:
    A0 = coarse_affine(ref_g, tgt_g, landmarks, frame_day, ref_day=ref_day)       # stage 1
    per, n_samp = {}, {}
    for u, ps in units_of(landmarks, frame_day, ref_day).items():                 # stage 2: fine, around A0's prediction
        name = base(u)
        obs = []
        if is_block(name):                                                        # a patch: one 2-D block match
            blks = [b for b in (block_of(p) for p in ps) if b is not None]
            n_samp[u] = len(blks)
            for b in blks:
                pc = A0[:, :2] @ b["c"] + A0[:, 2]
                m = match_block(ref_g, tgt_g, b, pc)
                if m and m[2] >= S_MIN:
                    obs.append(((float(b["c"][0]), float(b["c"][1]), 0.0, 0.0, True), (m[0], m[1]), m[2]))
        else:
            ss = samples(name, kinds.get(name, "polyline"), ps, cap=OCC_CAP if occludable(name) else None)
            n_samp[u] = len(ss)
            for s in ss:
                pc = A0[:, :2] @ np.array(s[:2]) + A0[:, 2]
                m = match(ref_g, tgt_g, s[0], s[1], pc[0], pc[1])
                if m and m[2] >= S_MIN:
                    obs.append((s, (m[0], m[1]), m[2]))
        if obs:
            per[u] = obs
    stable = [u for u in per if in_fit(u) and not occludable(u)]                  # tier 1, then gate tier 2 against it
    occ = [u for u in per if in_fit(u) and occludable(u)]
    st_obs = [o for u in stable for o in per[u]]
    basis, A_s = "stable", (fit_affine(st_obs) if constrained(st_obs) else None)
    if A_s is None:
        all_obs = st_obs + [o for u in occ for o in per[u]]
        basis, A_s = "all", (fit_affine(all_obs) if constrained(all_obs) else None)
    dropped = {u: "no match" for u, n in n_samp.items() if n and in_fit(u) and occludable(u) and u not in per}
    accepted = []
    for u in occ:
        frac = len(per[u]) / max(1, n_samp[u])
        med = float(np.median([residual(A_s, s, d) for s, d, _ in per[u]])) if A_s is not None else np.inf
        if frac >= OCC_MATCH_MIN and med <= OCC_RES_MAX:
            accepted.append(u)
        else:
            dropped[u] = f"matched {frac:.0%}, residual {med:.1f} px"
    fit_names = stable + accepted
    fit_obs = [o for n in fit_names for o in per[n]]
    A = fit_affine(fit_obs) if A_s is not None and constrained(fit_obs) else None
    out = {"A": A, "A0": A0, "per": per, "fit_names": fit_names, "dropped": dropped, "basis": basis}
    if A is None:
        out["status"] = "unreliable"
        return out
    held = {}
    for n in fit_names:                       # leave one out — only where the rest still pins both directions
        rest = [o for m in fit_names if m != n for o in per[m]]
        if len({m for m in fit_names if m != n}) >= 2 and constrained(rest):
            A_lo = fit_affine(rest)
            if A_lo is not None:
                held[n] = float(np.median([residual(A_lo, s, d) for s, d, _ in per[n]]))
    out["held"] = held
    out["valid"] = {n: float(np.median([residual(A, s, d) for s, d, _ in per[n]])) for n in per if not in_fit(n)}
    out["dropped_res"] = {n: float(np.median([residual(A, s, d) for s, d, _ in per[n]])) for n in dropped if n in per}
    out["fit_res"] = {n: float(np.median([residual(A, s, d) for s, d, _ in per[n]])) for n in fit_names}
    hv = np.array(list(held.values())) if held else np.array([np.inf])
    out["held_med"], out["held_p90"] = float(np.median(hv)), float(np.percentile(hv, 90))
    out["n_held"] = len(held)
    out["status"] = ("ok" if len(fit_names) >= 4 and len(held) >= 2
                     and out["held_med"] <= HELD_MED_MAX and out["held_p90"] <= HELD_P90_MAX else "unreliable")
    return out


def unnamed(name: str) -> bool:
    return base(name).startswith(UNNAMED_PREFIXES)


def _closest(pieces: list[np.ndarray], q: np.ndarray):
    """Closest point on a set of polylines to q -> (point, unit normal, distance, at_end). at_end = the projection is
    clipped to a polyline's first or last vertex (labelled extents differ there -> no constraint)."""
    best = None
    for P in pieces:
        if len(P) < 2:
            continue
        a, b = P[:-1], P[1:]
        d = b - a
        L2 = np.maximum((d ** 2).sum(1), 1e-9)
        t = np.clip(((q - a) * d).sum(1) / L2, 0.0, 1.0)
        c = a + t[:, None] * d
        dist = np.hypot(*(c - q).T)
        i = int(np.argmin(dist))
        if best is None or dist[i] < best[2]:
            n = np.array([-d[i][1], d[i][0]]) / np.sqrt(L2[i])
            at_end = (i == 0 and t[i] <= 0.0) or (i == len(a) - 1 and t[i] >= 1.0)
            best = (c[i], n, float(dist[i]), bool(at_end))
    return best


def _curve_pts(p: np.ndarray, step: float = TIE_STEP) -> np.ndarray:
    out = []
    for a, b in zip(p[:-1], p[1:]):
        k = max(1, int(np.hypot(*(b - a)) // step))
        out += [a + t * (b - a) for t in np.arange(k) / k]
    out.append(p[-1])
    return np.array(out)


def _tie_obs(A: np.ndarray, R_pieces: list[np.ndarray], T_pieces: list[np.ndarray], corner: bool) -> list:
    """Constraints mapping R onto T under the current A: point pairs (corner) or point-to-curve (normal) rows."""
    obs = []
    if corner:
        for p, q in zip(R_pieces, T_pieces):
            obs.append(((float(p[0]), float(p[1]), 0.0, 0.0, True), (float(q[0] - p[0]), float(q[1] - p[1])), 1.0))
        return obs
    for P in R_pieces:
        for p in _curve_pts(P) if len(P) >= 2 else []:
            hit = _closest(T_pieces, A[:, :2] @ p + A[:, 2])
            if hit is None or hit[3] or hit[2] > 3 * TIE_PAIR_MAX:
                continue
            c, n, _, _ = hit
            obs.append(((float(p[0]), float(p[1]), float(n[0]), float(n[1]), False), (float(c[0] - p[0]), float(c[1] - p[1])), 1.0))
    return obs


def _pair_unnamed(A: np.ndarray, Rl: dict, Tl: dict, day_R: date, day_T: date) -> dict:
    """Unnamed items paired by nearest neighbour after A: each R nail / block centroid / curve piece -> the closest T item
    of the same landmark (mutual, within TIE_PAIR_MAX px). Returns unit -> (R pieces, T pieces, corner?)."""
    out = {}
    for name, v in Rl.items():
        if not (unnamed(name) and name in Tl and in_fit(name) and usable(name, day_T, day_R)):
            continue
        Rp, Tp = pieces_of(v), pieces_of(Tl[name])
        if name.startswith("NAILS"):                         # patches: outline point-to-curve (extents differ)
            rc = [p[0] if len(p) == 1 else (block_of(p) or {"c": p.mean(0)})["c"] for p in Rp]
            tc = [p[0] if len(p) == 1 else (block_of(p) or {"c": p.mean(0)})["c"] for p in Tp]
            if not rc or not tc:
                continue
            rm = np.array([A[:, :2] @ c + A[:, 2] for c in rc])
            D = np.hypot(rm[:, None, 0] - np.array(tc)[None, :, 0], rm[:, None, 1] - np.array(tc)[None, :, 1])
            for i in range(len(rc)):
                j = int(np.argmin(D[i]))
                if D[i, j] <= TIE_PAIR_MAX and int(np.argmin(D[:, j])) == i:
                    out[f"{name}#{i + 1}"] = ([rc[i]], [tc[j]], True)
        else:
            for i, P in enumerate(Rp):
                if len(P) < 2:
                    continue
                pts = np.array([A[:, :2] @ p + A[:, 2] for p in _curve_pts(P)])
                best, bj = np.inf, None
                for j, Q in enumerate(Tp):
                    ds = [h[2] for h in (_closest([Q], q) for q in pts) if h is not None and not h[3]]
                    if len(ds) >= 2 and np.median(ds) < best:
                        best, bj = float(np.median(ds)), j
                if bj is not None and best <= TIE_PAIR_MAX:
                    out[f"{name}#{i + 1}"] = ([P], [Tp[bj]], False)
    return out


def pole_centrelines(lab: dict) -> dict:
    """POLE_xx_L + POLE_xx_R -> POLE_xx_C, the pole's centre line: midpoints between L samples and their closest points
    on R. The user, 2026-10-01: at night a pole's edges are not clear, so its apparent THICKNESS is unreliable (IR bloom
    widens it on both sides) — the centre line is not affected. Edges labelled without their partner are kept."""
    out = {k: v for k, v in lab.items() if not (k.startswith("POLE_") and k[-2:] in ("_L", "_R")
                                              and k[:-2] + ("_R" if k.endswith("_L") else "_L") in lab)}
    for k in lab:
        if k.startswith("POLE_") and k.endswith("_L") and k[:-2] + "_R" in lab:
            Rp = pieces_of(lab[k[:-2] + "_R"])
            mids = []
            for P in pieces_of(lab[k]):
                for q in (_curve_pts(P) if len(P) >= 2 else []):
                    h = _closest(Rp, q)
                    if h is not None and not h[3]:
                        mids.append(((q + h[0]) / 2).tolist())
            if len(mids) >= 2:
                out[k[:-2] + "_C"] = [mids]
    return out


def tie_labels(Rl: dict, Tl: dict, day_R: date, day_T: date, centre_poles: bool = True) -> dict:
    """Affine map R px -> T px from two label sets of the same camera (no image matching). Named fit-set landmarks:
    ICP point-to-curve (R samples every TIE_STEP px onto T's same-named curve, normal constraints, Huber), from the median
    centroid offset. Then unnamed items paired by nearest neighbour and kept if their median residual under the named fit
    is <= TIE_GATE px; final fit on both; leave-one-unit-out held-out error. centre_poles: poles enter as centre lines
    (pole_centrelines), not as their two edges (labelled thickness is unreliable at night)."""
    if centre_poles:
        Rl, Tl = pole_centrelines(Rl), pole_centrelines(Tl)
    named = [n for n in Rl if n in Tl and in_fit(n) and not unnamed(n) and usable(n, day_T, day_R)]
    if not named:
        return {"A": None, "status": "no common named landmarks"}
    off = np.median([np.vstack(pieces_of(Tl[n])).mean(0) - np.vstack(pieces_of(Rl[n])).mean(0) for n in named], axis=0)
    A = np.array([[1.0, 0.0, off[0]], [0.0, 1.0, off[1]]])

    def icp(A, units):
        for _ in range(40):
            obs = [o for u, (rp, tp, cn) in units.items() for o in _tie_obs(A, rp, tp, cn)]
            if not constrained(obs):
                return None, obs
            A_new = fit_affine(obs)
            if A_new is None:
                return None, obs
            done = np.abs(A_new - A).max() < 1e-3
            A = A_new
            if done:
                break
        return A, [o for u, (rp, tp, cn) in units.items() for o in _tie_obs(A, rp, tp, cn)]

    units = {n: (pieces_of(Rl[n]), pieces_of(Tl[n]), False) for n in named}
    A_named, _ = icp(A, units)
    if A_named is None:
        return {"A": None, "status": "named landmarks do not constrain both directions"}
    cand = _pair_unnamed(A_named, Rl, Tl, day_R, day_T)
    accepted, rejected = {}, {}
    for u, (rp, tp, cn) in cand.items():
        ob = _tie_obs(A_named, rp, tp, cn)
        med = float(np.median([residual(A_named, s, d) for s, d, _ in ob])) if ob else np.inf
        (accepted if med <= TIE_GATE else rejected)[u] = (rp, tp, cn) if med <= TIE_GATE else round(med, 1)
    units.update(accepted)
    A_all, _ = icp(A_named, units)
    A_all = A_named if A_all is None else A_all
    held = {}
    for u in units:
        rest = {k: v for k, v in units.items() if k != u}
        A_lo, _ = icp(A_all, rest)
        ob = _tie_obs(A_all, *units[u])
        if A_lo is not None and ob:
            held[u] = float(np.median([residual(A_lo, s, d) for s, d, _ in ob]))
    hv = np.array(list(held.values())) if held else np.array([np.inf])
    out = {"A": A_all, "A_named": A_named, "named": named, "units": list(units), "rejected": rejected, "held": held,
           "held_med": float(np.median(hv)), "held_p90": float(np.percentile(hv, 90))}
    out["status"] = ("ok" if len(units) >= 4 and len(held) >= 2 and out["held_med"] <= HELD_MED_MAX
                     and out["held_p90"] <= HELD_P90_MAX else "unreliable")
    return out


def apply_A(A: np.ndarray, P: np.ndarray) -> np.ndarray:
    return np.asarray(P, float) @ A[:, :2].T + A[:, 2]


def compose(A2: np.ndarray, A1: np.ndarray) -> np.ndarray:
    """p -> A2(A1(p))."""
    return (np.vstack([A2, [0, 0, 1.0]]) @ np.vstack([A1, [0, 0, 1.0]]))[:2]


def affine_cols(A: np.ndarray | None) -> dict:
    """a11..a23 of a 2x3 affine (NaN when there is no fit), for CSV rows."""
    v = np.full(6, np.nan) if A is None else np.asarray(A, float).ravel()
    return {k: float(x) for k, x in zip(("a11", "a12", "a13", "a21", "a22", "a23"), v)}


def params(A: np.ndarray, size) -> dict:
    W, Hh = size
    c = np.array([W / 2, Hh / 2])
    t = A[:, :2] @ c + A[:, 2] - c
    sx, sy = float(np.hypot(*A[:, 0])), float(np.hypot(*A[:, 1]))
    rot = float(np.degrees((np.arctan2(A[1, 0], A[0, 0]) + np.arctan2(-A[0, 1], A[1, 1])) / 2))
    return {"tx": float(t[0]), "ty": float(t[1]), "rot_deg": rot, "sx": sx, "sy": sy}


def draw_overlay(img: np.ndarray, landmarks: dict, A: np.ndarray | None, frame_day: date, caption: str,
                 dropped=(), ref_day: date = HOUSE1_MOVED) -> np.ndarray:
    """red = labels as drawn on the reference; moved by A: green = fit, cyan = validation, orange = dropped occludable
    piece. Single points (NAILS) are circles."""
    out = img.copy()
    th = max(2, img.shape[1] // 1600)
    for name, v in landmarks.items():
        if not usable(name, frame_day, ref_day):
            continue
        ps = pieces_of(v)
        for k, p in enumerate(ps, 1):
            unit = f"{name}#{k}" if occludable(name) and len(ps) > 1 else name
            if len(p) == 1 and not is_corner_lm(name):    # a stray single click on an edge/curve: unused, not drawn
                continue
            if len(p) == 1:
                cv2.circle(out, tuple(np.round(p[0]).astype(int)), 4 * th, (0, 0, 255), max(1, th // 2), cv2.LINE_AA)
            else:
                q = p.reshape(-1, 1, 2)
                cv2.polylines(out, [np.round(q).astype(np.int32)], False, (0, 0, 255), max(1, th // 2), cv2.LINE_AA)
            if A is not None:
                pa = p @ A[:, :2].T + A[:, 2]
                col = (0, 165, 255) if unit in dropped else (0, 255, 0) if in_fit(name) else (255, 255, 0)
                if len(p) == 1:
                    cv2.circle(out, tuple(np.round(pa[0]).astype(int)), 6 * th, col, th, cv2.LINE_AA)
                else:
                    cv2.polylines(out, [np.round(pa.reshape(-1, 1, 2)).astype(np.int32)], False, col, th, cv2.LINE_AA)
    (tw, tht), _ = cv2.getTextSize(caption, cv2.FONT_HERSHEY_SIMPLEX, 1.2, 3)
    cv2.rectangle(out, (0, 0), (tw + 24, tht + 24), (0, 0, 0), -1)
    cv2.putText(out, caption, (12, tht + 12), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 3, cv2.LINE_AA)
    return out


def selftest() -> int:
    rng = np.random.default_rng(1)
    h, w = 900, 1600
    base = cv2.GaussianBlur((rng.random((h, w)) * 120).astype(np.uint8), (0, 0), 2)
    for x in (300, 700, 1200):
        cv2.line(base, (x, 150), (x + 10, 750), 255, 9)
    cv2.line(base, (100, 420), (1500, 400), 230, 5)
    cv2.rectangle(base, (850, 200), (930, 260), 255, -1)
    img = cv2.cvtColor(base, cv2.COLOR_GRAY2BGR)
    lms = {"POLE_A0_L": [[[296, 200], [304, 700]]], "POLE_A1_L": [[[696, 200], [704, 700]]], "POLE_A2_L": [[[1196, 200], [1204, 700]]],
           "WALLTOP_Y0": [[[150, 419], [1450, 401]]], "BOX_A1": [[[850, 200], [930, 200], [930, 260], [850, 260]]]}
    kinds = {"POLE_A0_L": "edge", "POLE_A1_L": "edge", "POLE_A2_L": "edge", "WALLTOP_Y0": "polyline", "BOX_A1": "outline"}
    true = cv2.getRotationMatrix2D((w / 2, h / 2), 0.4, 1.003)
    true[:, 2] += (6.5, -4.0)
    tgt = cv2.warpAffine(img, true, (w, h), borderMode=cv2.BORDER_REFLECT)
    r = track_frame(prep(img), prep(tgt), lms, kinds, date(2026, 9, 4))
    err = float(np.abs(r["A"] @ np.array([w / 2, h / 2, 1.0]) - true @ np.array([w / 2, h / 2, 1.0])).max())
    ok = r["A"] is not None and err < 0.5 and r.get("status") == "ok"
    print(f"[{'PASS' if ok else 'FAIL'}] affine recovered: centre error {err:.2f} px, held-out median {r.get('held_med', np.nan):.2f} px, status {r.get('status')}")
    nails = samples("NAILS", "point", pieces_of([[[100, 100]], [[200, 150]], [[300, 120]]]))
    okn = len(nails) == 3 and all(s[4] for s in nails) and in_fit("NAILS") and in_fit("PATCHES") and in_fit("SEAMS") and in_fit("BUILDING") and occludable("WOOD")
    print(f"[{'PASS' if okn else 'FAIL'}] NAILS: each single point is a 2-D constraint; NAILS/PATCHES/SEAMS/BUILDING in the fit set")
    # occlusion + blocks: two dark bumpy patches on a white wall band (patch 2 open at the bottom = grass) and a building
    # edge; in the target a "rat" (noise) covers patch 1's twin, a "person" the building edge -> both dropped, the affine
    # still exact, the visible patch measured as one 2-D block
    occ = base.copy()
    cv2.rectangle(occ, (330, 560), (1400, 760), 215, -1)
    cv2.line(occ, (330, 560), (1400, 560), 255, 3)
    blob1 = np.array([[420 + 6 * np.cos(a) * (8 + 2 * (k % 2)), 650 + 6 * np.sin(a) * (7 + 2 * (k % 2))]
                      for k, a in enumerate(np.linspace(0, 2 * np.pi, 24, endpoint=False))])
    blob2 = blob1 + (600, -10)
    for b in (blob1, blob2):
        cv2.fillPoly(occ, [np.round(b).astype(np.int32).reshape(-1, 1, 2)], 70)
    cv2.line(occ, (1450, 120), (1450, 330), 240, 6)
    occ_img = cv2.cvtColor(occ, cv2.COLOR_GRAY2BGR)
    tgt2 = cv2.warpAffine(occ_img, true, (w, h), borderMode=cv2.BORDER_REFLECT)
    tb = (true[:, :2] @ blob2.T + true[:, 2:]).T
    x0, y0 = tb.min(0).astype(int) - 25
    x1, y1 = tb.max(0).astype(int) + 25
    tgt2[y0:y1, x0:x1] = rng.integers(0, 255, (y1 - y0, x1 - x0, 1), dtype=np.uint8)
    tq = (true[:, :2] @ np.array([[1450, 120], [1450, 330]], float).T + true[:, 2:]).T
    tgt2[int(tq[:, 1].min()) - 25:int(tq[:, 1].max()) + 25, int(tq[:, 0].min()) - 25:int(tq[:, 0].max()) + 25] = 90
    open1 = blob1[[k for k in range(24) if not 3 <= k <= 9]]            # bottom arc (sin > 0 side) left out = grass
    lms2 = dict(lms, PATCHES=[np.roll(open1, -3, axis=0).tolist(), blob2.tolist()], BUILDING=[[[1450, 130], [1450, 320]]])
    kinds2 = dict(kinds, PATCHES="polyline", BUILDING="polyline")
    r2 = track_frame(prep(occ_img), prep(tgt2), lms2, kinds2, date(2026, 9, 4))
    err2 = float(np.abs(r2["A"] @ np.array([w / 2, h / 2, 1.0]) - true @ np.array([w / 2, h / 2, 1.0])).max()) if r2["A"] is not None else np.inf
    b1 = r2["per"].get("PATCHES#1", [])
    berr = (float(np.hypot(*(np.array(b1[0][0][:2]) + b1[0][1] - (true[:, :2] @ np.array(b1[0][0][:2]) + true[:, 2]))))
            if len(b1) == 1 else np.inf)
    oko = (err2 < 0.5 and "PATCHES#2" in r2["dropped"] and "BUILDING" in r2["dropped"] and "PATCHES#1" in r2["fit_names"]
           and r2["basis"] == "stable" and berr < 0.3 and block_of(np.array(lms2["PATCHES"][0]))["open"])
    print(f"[{'PASS' if oko else 'FAIL'}] blocks + occlusion: open-bottom patch matched as one block ({berr:.2f} px), "
          f"dropped {sorted(r2['dropped'])}, centre error {err2:.2f} px")
    # label-to-label tie: T = the same structures (points taken ON R's curves, other extents and click spacing) moved by
    # a known affine + 0.4-px click noise; nails / patches in another order, one unmatched nail on each side
    Rl = {"POLE_A0_L": [[[296, 200], [304, 700]]], "POLE_A2_L": [[[1196, 250], [1204, 690]]],
          "WALLTOP_Y0": [[[150, 419], [800, 410], [1450, 401]]], "NAILS": [[[500, 300]], [[900, 320]], [[1300, 280]], [[50, 50]]],
          "PATCHES": [blob1.tolist(), blob2.tolist()], "SEAMS": [[[640, 560], [642, 700]]]}
    At = np.array([[1.002, 0.006, 24.0], [-0.005, 0.998, -11.0]])

    def on(pl, a, b, n):                       # n points along polyline pl between length fractions a and b
        pl = np.asarray(pl, float)
        L = np.r_[0, np.cumsum(np.hypot(*np.diff(pl, axis=0).T))]
        f = np.linspace(a, b, n) * L[-1]
        return np.c_[np.interp(f, L, pl[:, 0]), np.interp(f, L, pl[:, 1])]

    def mv(pts):
        return (np.asarray(pts, float) @ At[:, :2].T + At[:, 2] + rng.normal(0, 0.4, np.shape(pts))).tolist()
    Tl = {"POLE_A0_L": [mv(on(Rl["POLE_A0_L"][0], 0.1, 0.9, 3))], "POLE_A2_L": [mv(on(Rl["POLE_A2_L"][0], 0.05, 1.0, 4))],
          "WALLTOP_Y0": [mv(on(Rl["WALLTOP_Y0"][0], 0.15, 0.85, 5))],
          "NAILS": [mv([[1300, 280]]), mv([[500, 300]]), mv([[900, 320]]), mv([[1500, 900]])],
          "PATCHES": [mv(blob2), mv(blob1)], "SEAMS": [mv(on(Rl["SEAMS"][0], 0.2, 0.9, 3))]}
    tie = tie_labels(Rl, Tl, date(2026, 9, 18), date(2026, 9, 4))
    inside = np.array([[300, 300], [800, 450], [1200, 650], [500, 600], [1300, 300]])      # within the labelled area
    terr = float(np.hypot(*(apply_A(tie["A"], inside) - apply_A(At, inside)).T).max()) if tie["A"] is not None else np.inf
    okt = terr < 0.6 and tie["status"] == "ok" and sum(u.startswith("NAILS") for u in tie["units"]) == 3 and \
        sum(u.startswith("PATCHES") for u in tie["units"]) == 2
    print(f"[{'PASS' if okt else 'FAIL'}] label tie: affine recovered to {terr:.2f} px within the labelled area, "
          f"{len(tie.get('units', []))} units (3 nails, 2 patches paired), held-out {tie.get('held_med', np.nan):.2f}/"
          f"{tie.get('held_p90', np.nan):.2f} px")
    Rp = {"POLE_A0_L": [[[280, 200], [288, 700]]], "POLE_A0_R": [[[312, 200], [320, 700]]],
          "POLE_A2_L": [[[1180, 250], [1188, 690]]], "POLE_A2_R": [[[1212, 250], [1220, 690]]],
          "WALLTOP_Y0": [[[150, 419], [800, 410], [1450, 401]]], "WALLTOP_Y240": [[[150, 819], [1450, 801]]]}
    Tp = {k: [(np.asarray(v[0], float) + (12.0 if k.endswith("_R") else -12.0 if k.endswith("_L") else 0.0, 0.0) + (5.0, -3.0)).tolist()]
          for k, v in Rp.items()}                                  # edges 12 px wider on each side, whole frame +5 / -3
    tc = tie_labels(Rp, Tp, date(2026, 9, 4), date(2026, 9, 4))
    te = tie_labels(Rp, Tp, date(2026, 9, 4), date(2026, 9, 4), centre_poles=False)
    cerr = float(np.abs(apply_A(tc["A"], inside) - (inside + (5.0, -3.0))).max()) if tc["A"] is not None else np.inf
    okc = cerr < 0.3 and any(u.endswith("_C") for u in tc["units"])
    print(f"[{'PASS' if okc else 'FAIL'}] pole centre lines: widened edges (night bloom) leave the tie exact ({cerr:.2f} px; "
          f"with edges: held-out p90 {te.get('held_p90', np.nan):.1f} px)")
    okt = okt and okc
    house = samples("HOUSE_1_ROOF_X", "edge", pieces_of([[[0, 0], [10, 0]]]))
    ok2 = (not usable("HOUSE_1_ROOF_X", date(2026, 9, 4)) and usable("HOUSE_1_ROOF_X", date(2026, 9, 18))
           and usable("HOUSE_2_BASE_Z", date(2026, 9, 4)) and len(house) == 1
           and usable("HOUSE_1_ROOF_X", date(2026, 9, 4), ref_day=date(2026, 9, 4))
           and not usable("HOUSE_1_ROOF_X", date(2026, 9, 18), ref_day=date(2026, 9, 4)))
    print(f"[{'PASS' if ok2 else 'FAIL'}] house_1 only on the reference's side of the 09-18 move, house_2 always usable")
    set_camera("CH06")
    okc = in_fit("HOUSE_2_ROOF_X") and in_fit("HOUSE_2_LABEL") and in_fit("BLUETOOTH_ANTENNA") and not in_fit("POLE_B3_L") \
        and not in_fit("POLE_B3_C") and not in_fit("BOX_B3") and in_fit("NAILS")
    set_camera(None)
    okc = okc and not in_fit("HOUSE_2_ROOF_X") and in_fit("POLE_B3_L")
    print(f"[{'PASS' if okc else 'FAIL'}] per-camera rules: CH06 fits its house + antenna, its crossbeam pole B3 is validation only; "
          "other cameras unchanged")
    ok2 = ok2 and okc
    allok = ok and ok2 and okn and oko and okt
    print(("PASS" if allok else "FAIL") + " — landmark_track self-test")
    return 0 if allok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--cohort", default=None)
    ap.add_argument("--cameras", nargs="+", default=["CH01", "CH02", "CH03", "CH04"])
    ap.add_argument("--start", type=date.fromisoformat, default=date(2026, 8, 30))
    ap.add_argument("--end", type=date.fromisoformat, default=date(2026, 9, 17))
    ap.add_argument("--times", nargs="+", type=lambda s: datetime.strptime(s, "%H:%M").time(), default=[time(3, 1), time(12, 0), time(21, 30)])
    ap.add_argument("--labels-dir", default=str(REPO / "cv" / "configs" / "landmarks" / "2026c"))
    ap.add_argument("--cohort-root", default=r"F:\3rd_rat")
    ap.add_argument("--ref-session", default=r"F:\calibration\session_2026-09-18_13-54-34")
    ap.add_argument("--session", default=None)
    ap.add_argument("--fps", type=float, default=2.0)
    ap.add_argument("--ref-labels", nargs="+", default=[],
                    help="user-labelled reference(s) other than 09-18 (landmarks_CHxx_<date>_<time>.json; camera from the file)")
    ap.add_argument("--tie", action="store_true", help="tie each --ref-labels reference to the camera's 09-18 labels")
    ap.add_argument("--tag", default=None, help="name suffix of the run folder and report (keeps the canonical report)")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    import output_paths as op
    import camera_review as cr
    args.cohort = op.resolve_cohort(args.cohort)
    run = op.run_dir("cv_field_landmark_track" + (f"_{args.tag}" if args.tag else ""), args.cohort, make_figures=False)
    ref_files = {}
    for f in args.ref_labels:
        ref_files[json.loads(Path(f).read_text(encoding="utf-8"))["camera"]] = Path(f)
    ties = {}
    frames_dir = run / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    targets = run / "targets.csv"
    with open(targets, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["camera", "time", "tag"])
        d = args.start
        while d <= args.end:
            for cam in args.cameras:
                for t0 in args.times:
                    wr.writerow([cam, f"{datetime.combine(d, t0):%Y-%m-%d %H:%M:%S}", "track"])
            d += timedelta(days=1)
    subprocess.run([sys.executable, str(HERE / "grab_frames.py"), "--targets", str(targets), "--out", str(frames_dir),
                    "--root", args.cohort_root, "--workers", "3"], check=True)
    manifest = [r for r in csv.DictReader(open(frames_dir / "manifest.csv", encoding="utf-8")) if not r["error"]]
    rows_f, rows_l, report = [], [], {}
    ffmpeg = cr.find_ffmpeg()
    for cam in args.cameras:
        set_camera(cam)
        lab_files = sorted(Path(args.labels_dir).glob(f"landmarks_{cam}_20260918_*.json"))
        if not lab_files:
            print(f"{cam}: no 09-18 labels")
            continue
        lab18 = json.loads(lab_files[0].read_text(encoding="utf-8"))
        lab = json.loads(ref_files[cam].read_text(encoding="utf-8")) if cam in ref_files else lab18
        landmarks, kinds = lab["landmarks"], {**lab18.get("kind", {}), **lab.get("kind", {})}
        size = tuple(int(v) for v in lab["frame_size_upright"])
        ref_t = datetime.strptime(lab["time"], "%Y-%m-%d %H:%M:%S")
        ref_day = ref_t.date()
        got = cr.grab_at(ref_t, cam, args, ffmpeg, size)
        if got is None:
            print(f"{cam}: reference frame not found")
            continue
        ref = got[0]
        ref_g = prep(ref)
        A_tie = None
        if cam in ref_files and args.tie:                       # 09-18 px -> reference px, from the two label sets
            tie = tie_labels(lab18["landmarks"], landmarks, HOUSE1_MOVED, ref_day)
            A_tie = tie["A"]
            ties[cam] = tie
            if A_tie is None:
                print(f"{cam}: tie to 09-18 failed ({tie['status']})")
                continue
            (run / "overlays").mkdir(exist_ok=True)
            cap = (f"{cam} TIE 09-18 labels -> {ref_t:%m-%d %H:%M} labels: {tie['status']} held {tie['held_med']:.2f}/"
                   f"{tie['held_p90']:.2f}px, {len(tie['units'])} units, rejected {len(tie['rejected'])}")
            ov = draw_overlay(ref, lab18["landmarks"], A_tie, ref_day, cap)
            sc = 2400 / ov.shape[1]
            cv2.imwrite(str(run / "overlays" / f"{cam}_TIE_0918_to_{ref_t:%Y%m%d_%H%M%S}.jpg"),
                        cv2.resize(ov, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 88])
            print(f"  {cap}")
        cv2.imwrite(str(frames_dir / f"{cam}_REF_{lab['time'].replace(':', '').replace(' ', '_')}.jpg"), ref, [cv2.IMWRITE_JPEG_QUALITY, 95])
        items = []
        (run / "overlays").mkdir(exist_ok=True)
        todo = [("REF", ref_t, ref)] + [
            (r["out"], datetime.strptime(r["frame_time"][:19], "%Y-%m-%d %H:%M:%S"), None)
            for r in sorted((m for m in manifest if m["camera"] == cam), key=lambda m: m["frame_time"])]
        for tag, ft, img in todo:
            if img is None:
                img = cv2.imread(str(frames_dir / tag))
            res = track_frame(ref_g, prep(img), landmarks, kinds, ft.date(), ref_day=ref_day)
            A = res["A"]
            A_tot = A if A_tie is None or A is None else compose(A, A_tie)          # shift vs 09-18 when tied
            pr = params(A_tot, size) if A_tot is not None else {k: np.nan for k in ("tx", "ty", "rot_deg", "sx", "sy")}
            row = {"camera": cam, "frame_time": f"{ft:%Y-%m-%d %H:%M:%S}", "frame": tag, "n_fit_landmarks": len(res["fit_names"]),
                   "held_med_px": res.get("held_med", np.nan), "held_p90_px": res.get("held_p90", np.nan),
                   "status": res.get("status", "no fit"), **pr,
                   "house_valid_med_px": float(np.median(list(res["valid"].values()))) if res.get("valid") else np.nan,
                   "basis": res.get("basis", ""), "n_dropped": len(res.get("dropped", {})),
                   **affine_cols(A_tot), "map": "09-18 px -> frame px" + (" (A_track o A_tie)" if A_tie is not None else ""),
                   "dropped": "; ".join(f"{u}: {why}" for u, why in sorted(res.get("dropped", {}).items()))}
            rows_f.append(row)
            for n, obs in res["per"].items():
                role = ("dropped" if n in res.get("dropped", {}) else "fit" if n in res["fit_names"]
                        else "validation" if not in_fit(n) else "unused")
                rows_l.append({"camera": cam, "frame_time": row["frame_time"], "landmark": n, "role": role,
                               "tier": "occludable" if occludable(n) else "stable" if in_fit(n) else "validation",
                               "n_samples": len(obs), "mean_ncc": float(np.mean([o[2] for o in obs])),
                               "median_shift_px": float(np.median([np.hypot(*o[1]) for o in obs])),
                               "fit_residual_px": res.get("fit_res", {}).get(n, res.get("valid", {}).get(n, res.get("dropped_res", {}).get(n, np.nan))),
                               "held_out_px": res.get("held", {}).get(n, np.nan)})
            cap = (f"{cam} {ft:%m-%d %H:%M} {f'REF {ref_t:%m-%d %H:%M}' if tag == 'REF' else ''} {row['status']} held "
                   f"{row['held_med_px']:.1f}/{row['held_p90_px']:.1f}px  {'vs 09-18 ' if A_tie is not None else ''}"
                   f"t=({pr['tx']:+.1f},{pr['ty']:+.1f}) rot {pr['rot_deg']:+.2f}"
                   + (f"  dropped {row['n_dropped']}" if row["n_dropped"] else ""))
            ov = draw_overlay(img, landmarks, A, ft.date(), cap, res.get("dropped", {}), ref_day=ref_day)
            s = 2400 / ov.shape[1]
            op_path = run / "overlays" / f"{cam}_{ft:%Y%m%d_%H%M%S}.jpg"
            cv2.imwrite(str(op_path), cv2.resize(ov, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 88])
            items.append((op_path, ""))
            print(f"  {cap}")
        cr.render_video(items + items[:1], run / f"{cam}_track.mp4", args.fps)
        report[cam] = [r for r in rows_f if r["camera"] == cam]
    for name, rows in (("track_frames.csv", rows_f), ("track_landmarks.csv", rows_l)):
        if rows:
            with open(run / name, "w", newline="", encoding="utf-8") as f:
                wr = csv.DictWriter(f, fieldnames=list(rows[0]))
                wr.writeheader()
                wr.writerows(rows)
    rep = op.report_dir(args.cohort, "cv_field")
    refs_txt = "; ".join(f"{c}: `{f.name}`" + (f" tied to 09-18 by the label sets — {ties[c]['status']}, held-out "
                                                 f"{ties[c]['held_med']:.2f} / {ties[c]['held_p90']:.2f} px over "
                                                 f"{len(ties[c]['units'])} units, rejected {ties[c]['rejected'] or 'none'}"
                                                 if c in ties and ties[c]['A'] is not None else "")
                         for c, f in ref_files.items())
    L = [f"# Landmark tracking: cohort frames vs the 09-18 calibration reference (cohort `{args.cohort}`"
         f"{f', run `{args.tag}`' if args.tag else ''})\n",
         *([f"Reference other than 09-18 — {refs_txt}. Shifts below are vs 09-18 (A_track o A_tie) where tied; held-out "
            "errors are those of the tracking from that reference.\n"] if ref_files else []),
         f"Generated {datetime.now():%Y-%m-%d %H:%M} by `cv/cv_field/landmark_track.py` (method, definitions and status rule in its "
         f"docstring). Bulk: `{run}` (frames, overlays, `<CH>_track.mp4`, `track_frames.csv`, `track_landmarks.csv`). "
         "Overlays: red = the 09-18 labels as drawn, green = fit-set labels moved by the fitted affine, cyan = houses "
         "(validation), orange = occludable pieces (patches, building) dropped in that frame; nails are circles. "
         "**The user reviews the overlays; this report makes no visual claim.**\n",
         "| camera | frames | ok | unreliable | held-out median px (median over frames) | tx px (min..max) | ty px (min..max) | rot deg (min..max) | scale (min..max) | houses (validation) median px | occludable pieces dropped (frames with any) |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for cam, rows in report.items():
        rs = [r for r in rows if r["frame"] != "REF"]
        if not rs:
            continue
        def rng(k):
            v = np.array([r[k] for r in rs], float)
            v = v[np.isfinite(v)]
            return f"{v.min():+.1f}..{v.max():+.1f}" if len(v) else "-"
        sc = np.array([(r["sx"] + r["sy"]) / 2 for r in rs], float)
        sc = sc[np.isfinite(sc)]
        hv = np.array([r["house_valid_med_px"] for r in rs], float)
        hv = hv[np.isfinite(hv)]
        L.append(f"| {cam} | {len(rs)} | {sum(r['status'] == 'ok' for r in rs)} | {sum(r['status'] != 'ok' for r in rs)} | "
                 f"{np.nanmedian([r['held_med_px'] for r in rs]):.2f} | {rng('tx')} | {rng('ty')} | {rng('rot_deg')} | "
                 f"{(f'{sc.min():.4f}..{sc.max():.4f}' if len(sc) else '-')} | {(f'{np.median(hv):.2f}' if len(hv) else '-')} | "
                 f"{sum(r['n_dropped'] for r in rs)} ({sum(r['n_dropped'] > 0 for r in rs)}) |")
    L.append("\nReference self-check rows (frame = REF) should give ~0 shift. Per-frame values: `track_frames.csv`.")
    name = f"cv_field_landmark_track_{args.cohort}" + (f"_{args.tag}" if args.tag else "") + ".md"
    (rep / name).write_text("\n".join(L) + "\n", encoding="utf-8")
    meta = dict(cohort=args.cohort, direction="cv_field", analysis="landmark_track", cameras=args.cameras,
                labels_dir=args.labels_dir, start=str(args.start), end=str(args.end), times=[str(t) for t in args.times],
                ref_labels=[str(f) for f in ref_files.values()], tie=args.tie, report=name)
    if args.tag:                                   # own pointer: the canonical run_manifest.json stays the daytime run's
        (rep / f"run_manifest_landmark_track_{args.tag}_{args.cohort}.json").write_text(
            json.dumps({"run_dir": str(run.resolve()), **meta}, indent=2) + "\n", encoding="utf-8")
    else:
        op.write_run_manifest(rep, run, **meta)
    if ties:
        with open(run / "tie.json", "w", encoding="utf-8") as f:
            json.dump({c: {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in t.items()} for c, t in ties.items()},
                      f, indent=2, default=str)
    print(f"report -> {rep / name}\nbulk -> {run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
