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
     FIT SET (POLE_*, BOX_*, WALLTOP_*, TOWER_*, PCBOX). Houses are VALIDATION only (HOUSE_1 = roof 4 was moved on 09-18 ->
     used only on frames dated >= 09-18; HOUSE_2 = roof 7 never moved -> all frames).
  5. Held-out error: leave-one-landmark-out over the fit set — refit without landmark L, residuals of L's samples; per
     frame the median and p90 over landmarks of their median |residual|.
Definitions: residual r = n.(A p - (p + d)) for line samples, |A p - (p + d)| for corners [px, full-res upright];
held_med / held_p90 = median / 90th percentile over fit-set landmarks of median|r| under leave-one-out [px];
status = ok if >= 4 fit landmarks matched, both near-vertical and near-horizontal constraints present, held_med <= 3 px
and held_p90 <= 6 px; else unreliable. tx, ty = A applied to the frame centre minus the centre [px]; rot = mean rotation
of A's columns [deg]; sx, sy = column norms of A's linear part.

Usage: python cv/cv_field/landmark_track.py --cohort 2026c [--cameras CH01 CH02 CH03 CH04] [--start 2026-08-30 --end 2026-09-17]
       python cv/cv_field/landmark_track.py --selftest
Output: $FIELD2026_ANALYSIS_OUT_ROOT/<cohort>/cv_field_landmark_track_<ts>/ (frames, overlays, <CH>_track.mp4, CSVs) and
results/<cohort>/cv_field/reports/cv_field_landmark_track_<cohort>.md (+ run_manifest.json).
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
CORNER_PREFIXES = ("BOX_", "PCBOX")
FIT_PREFIXES = ("POLE_", "BOX_", "WALLTOP_", "TOWER_", "PCBOX")
HELD_MED_MAX, HELD_P90_MAX = 3.0, 6.0
HOUSE1_MOVED = date(2026, 9, 18)
IR_REF = {"CH01": "2026-09-18 13:57:30", "CH02": "2026-09-18 15:22:30", "CH03": "2026-09-18 15:45:00", "CH04": "2026-09-18 14:32:30"}


def is_corner_lm(name: str) -> bool:
    return name.startswith(CORNER_PREFIXES) or name.endswith("_LABEL")


def in_fit(name: str) -> bool:
    return name.startswith(FIT_PREFIXES)


def usable(name: str, frame_day: date) -> bool:
    return not (name.startswith("HOUSE_1_") and frame_day < HOUSE1_MOVED)


def prep(img: np.ndarray) -> np.ndarray:
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    g = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(g)
    g = cv2.GaussianBlur(g, (0, 0), 1.5).astype(np.float32)
    mag = cv2.magnitude(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))
    return (mag / (np.percentile(mag, 99) + 1e-6)).astype(np.float32)


def pieces_of(v) -> list[np.ndarray]:
    ps = v if (v and isinstance(v[0][0], (list, tuple))) else [v]
    return [np.asarray(p, float) for p in ps if len(p) >= 1]


def samples(name: str, kind: str, pieces: list[np.ndarray]) -> list[tuple[float, float, float, float, bool]]:
    """(x, y, nx, ny, is_corner) along a landmark. Corners: the labelled vertices of BOX_/PCBOX/_LABEL outlines."""
    out = []
    corner_lm = is_corner_lm(name)
    closed = kind == "outline" and len(pieces) == 1
    for p in pieces:
        if len(p) < 2:
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
    if len(out) > MAX_PER_LM:
        keep = np.linspace(0, len(out) - 1, MAX_PER_LM).round().astype(int)
        corners = [s for s in out if s[4]]
        out = [out[i] for i in keep if not out[i][4]] + corners
    return out


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

    def sub(c, l, rr):
        den = l - 2 * c + rr
        return 0.0 if abs(den) < 1e-9 else 0.5 * (l - rr) / den
    ox = px + (sub(res[py, px], res[py, px - 1], res[py, px + 1]) if 0 < px < res.shape[1] - 1 else 0.0) - r
    oy = py + (sub(res[py, px], res[py - 1, px], res[py + 1, px]) if 0 < py < res.shape[0] - 1 else 0.0) - r
    return float(ci + ox - x), float(cj + oy - y), float(score)


def coarse_affine(ref_g, tgt_g, landmarks: dict, frame_day: date) -> np.ndarray:
    """Stage 1: a few large patches per fit-set landmark (they include ends/corners/context, so parallel edges cannot be
    confused) matched at half resolution over +/-R1/scale px, treated as 2-D matches -> Huber affine. Identity if too few."""
    s = COARSE_SCALE
    rs = cv2.resize(ref_g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    ts = cv2.resize(tgt_g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    obs = []
    for name, v in landmarks.items():
        if not (in_fit(name) and usable(name, frame_day)):
            continue
        pts = np.vstack([p for p in pieces_of(v) if len(p)])
        for q in pts[np.linspace(0, len(pts) - 1, min(COARSE_PER_LM, len(pts))).round().astype(int)]:
            m = match(rs, ts, q[0] * s, q[1] * s, h=H1, r=R1)
            if m and m[2] >= S_MIN:
                obs.append(((float(q[0]), float(q[1]), 0.0, 0.0, True), (m[0] / s, m[1] / s), m[2]))
    A = fit_affine(obs) if len({o[0][:2] for o in obs}) >= 3 else None
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
    """obs = [(sample, (dx, dy), weight)] -> 2x3 affine by Huber IRLS (k = 2 px)."""
    rows = [(r, b, w) for s, d, w in obs for r, b in rows_for(s, d)]
    if len(rows) < 6:
        return None
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


def track_frame(ref_g, tgt_g, landmarks: dict, kinds: dict, frame_day: date) -> dict:
    A0 = coarse_affine(ref_g, tgt_g, landmarks, frame_day)                       # stage 1
    per = {}
    for name, v in landmarks.items():                                             # stage 2: fine, around A0's prediction
        if not usable(name, frame_day):
            continue
        obs = []
        for s in samples(name, kinds.get(name, "polyline"), pieces_of(v)):
            pc = A0[:, :2] @ np.array(s[:2]) + A0[:, 2]
            m = match(ref_g, tgt_g, s[0], s[1], pc[0], pc[1])
            if m and m[2] >= S_MIN:
                obs.append((s, (m[0], m[1]), m[2]))
        if obs:
            per[name] = obs
    fit_names = [n for n in per if in_fit(n)]
    fit_obs = [o for n in fit_names for o in per[n]]
    A = fit_affine(fit_obs) if constrained(fit_obs) else None
    out = {"A": A, "A0": A0, "per": per, "fit_names": fit_names}
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
    out["fit_res"] = {n: float(np.median([residual(A, s, d) for s, d, _ in per[n]])) for n in fit_names}
    hv = np.array(list(held.values())) if held else np.array([np.inf])
    out["held_med"], out["held_p90"] = float(np.median(hv)), float(np.percentile(hv, 90))
    out["n_held"] = len(held)
    out["status"] = ("ok" if len(fit_names) >= 4 and len(held) >= 2
                     and out["held_med"] <= HELD_MED_MAX and out["held_p90"] <= HELD_P90_MAX else "unreliable")
    return out


def params(A: np.ndarray, size) -> dict:
    W, Hh = size
    c = np.array([W / 2, Hh / 2])
    t = A[:, :2] @ c + A[:, 2] - c
    sx, sy = float(np.hypot(*A[:, 0])), float(np.hypot(*A[:, 1]))
    rot = float(np.degrees((np.arctan2(A[1, 0], A[0, 0]) + np.arctan2(-A[0, 1], A[1, 1])) / 2))
    return {"tx": float(t[0]), "ty": float(t[1]), "rot_deg": rot, "sx": sx, "sy": sy}


def draw_overlay(img: np.ndarray, landmarks: dict, A: np.ndarray | None, frame_day: date, caption: str) -> np.ndarray:
    out = img.copy()
    th = max(2, img.shape[1] // 1600)
    for name, v in landmarks.items():
        if not usable(name, frame_day):
            continue
        for p in pieces_of(v):
            if len(p) < 2:
                continue
            q = p.reshape(-1, 1, 2)
            cv2.polylines(out, [np.round(q).astype(np.int32)], False, (0, 0, 255), max(1, th // 2), cv2.LINE_AA)
            if A is not None:
                pa = (p @ A[:, :2].T + A[:, 2]).reshape(-1, 1, 2)
                col = (0, 255, 0) if in_fit(name) else (255, 255, 0)
                cv2.polylines(out, [np.round(pa).astype(np.int32)], False, col, th, cv2.LINE_AA)
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
    house = samples("HOUSE_1_ROOF_X", "edge", pieces_of([[[0, 0], [10, 0]]]))
    ok2 = not usable("HOUSE_1_ROOF_X", date(2026, 9, 4)) and usable("HOUSE_1_ROOF_X", date(2026, 9, 18)) and usable("HOUSE_2_BASE_Z", date(2026, 9, 4)) and len(house) == 1
    print(f"[{'PASS' if ok2 else 'FAIL'}] house_1 excluded before 09-18, house_2 always usable")
    print(("PASS" if ok and ok2 else "FAIL") + " — landmark_track self-test")
    return 0 if ok and ok2 else 1


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
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    import output_paths as op
    import camera_review as cr
    args.cohort = op.resolve_cohort(args.cohort)
    run = op.run_dir("cv_field_landmark_track", args.cohort, make_figures=False)
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
        lab_files = sorted(Path(args.labels_dir).glob(f"landmarks_{cam}_20260918_*.json"))
        if not lab_files:
            print(f"{cam}: no 09-18 labels")
            continue
        lab = json.loads(lab_files[0].read_text(encoding="utf-8"))
        landmarks, kinds = lab["landmarks"], lab.get("kind", {})
        size = tuple(int(v) for v in lab["frame_size_upright"])
        got = cr.grab_at(datetime.strptime(lab["time"], "%Y-%m-%d %H:%M:%S"), cam, args, ffmpeg, size)
        if got is None:
            print(f"{cam}: reference frame not found")
            continue
        ref = got[0]
        ref_g = prep(ref)
        cv2.imwrite(str(frames_dir / f"{cam}_REF_{lab['time'].replace(':', '').replace(' ', '_')}.jpg"), ref, [cv2.IMWRITE_JPEG_QUALITY, 95])
        items = []
        (run / "overlays").mkdir(exist_ok=True)
        todo = [("REF", datetime.strptime(lab["time"], "%Y-%m-%d %H:%M:%S"), ref)] + [
            (r["out"], datetime.strptime(r["frame_time"][:19], "%Y-%m-%d %H:%M:%S"), None)
            for r in sorted((m for m in manifest if m["camera"] == cam), key=lambda m: m["frame_time"])]
        for tag, ft, img in todo:
            if img is None:
                img = cv2.imread(str(frames_dir / tag))
            res = track_frame(ref_g, prep(img), landmarks, kinds, ft.date())
            A = res["A"]
            pr = params(A, size) if A is not None else {k: np.nan for k in ("tx", "ty", "rot_deg", "sx", "sy")}
            row = {"camera": cam, "frame_time": f"{ft:%Y-%m-%d %H:%M:%S}", "frame": tag, "n_fit_landmarks": len(res["fit_names"]),
                   "held_med_px": res.get("held_med", np.nan), "held_p90_px": res.get("held_p90", np.nan),
                   "status": res.get("status", "no fit"), **pr,
                   "house_valid_med_px": float(np.median(list(res["valid"].values()))) if res.get("valid") else np.nan}
            rows_f.append(row)
            for n, obs in res["per"].items():
                rows_l.append({"camera": cam, "frame_time": row["frame_time"], "landmark": n, "role": "fit" if in_fit(n) else "validation",
                               "n_samples": len(obs), "mean_ncc": float(np.mean([o[2] for o in obs])),
                               "median_shift_px": float(np.median([np.hypot(*o[1]) for o in obs])),
                               "fit_residual_px": res.get("fit_res", {}).get(n, res.get("valid", {}).get(n, np.nan)),
                               "held_out_px": res.get("held", {}).get(n, np.nan)})
            cap = (f"{cam} {ft:%m-%d %H:%M} {'REF 09-18' if tag == 'REF' else ''} {row['status']} held {row['held_med_px']:.1f}/"
                   f"{row['held_p90_px']:.1f}px  t=({pr['tx']:+.1f},{pr['ty']:+.1f}) rot {pr['rot_deg']:+.2f}")
            ov = draw_overlay(img, landmarks, A, ft.date(), cap)
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
    L = [f"# Landmark tracking: cohort frames vs the 09-18 calibration reference (cohort `{args.cohort}`)\n",
         f"Generated {datetime.now():%Y-%m-%d %H:%M} by `cv/cv_field/landmark_track.py` (method, definitions and status rule in its "
         f"docstring). Bulk: `{run}` (frames, overlays, `<CH>_track.mp4`, `track_frames.csv`, `track_landmarks.csv`). "
         "Overlays: red = the 09-18 labels as drawn, green = fit-set labels moved by the fitted affine, cyan = houses "
         "(validation). **The user reviews the overlays; this report makes no visual claim.**\n",
         "| camera | frames | ok | unreliable | held-out median px (median over frames) | tx px (min..max) | ty px (min..max) | rot deg (min..max) | scale (min..max) | houses (validation) median px |",
         "|---|---|---|---|---|---|---|---|---|---|"]
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
                 f"{(f'{sc.min():.4f}..{sc.max():.4f}' if len(sc) else '-')} | {(f'{np.median(hv):.2f}' if len(hv) else '-')} |")
    L.append("\nReference self-check rows (frame = REF) should give ~0 shift. Per-frame values: `track_frames.csv`.")
    (rep / f"cv_field_landmark_track_{args.cohort}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    op.write_run_manifest(rep, run, cohort=args.cohort, direction="cv_field", analysis="landmark_track",
                          cameras=args.cameras, labels_dir=args.labels_dir, start=str(args.start), end=str(args.end))
    print(f"report -> {rep / f'cv_field_landmark_track_{args.cohort}.md'}\nbulk -> {run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
