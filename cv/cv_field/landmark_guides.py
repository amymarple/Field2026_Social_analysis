"""landmark_guides.py — where each rigid landmark name is, on the paddock and in each camera's image.

The landmark labels (cv/cv_field/landmark_gui.py) use paddock names — POLE_<row><col>, WALLTOP_<side>, HOUSE_1/2 —
so a structure keeps its name in every frame and camera. This module makes those names concrete:
  * a top-view schematic of the paddock (pole grid, wall sides, houses, and where each camera is and looks, from the
    2026-09-24 calibration's RESULT 1),
  * per-camera guides: the calibration's prediction of each pole's centre line (z = 0 … 2.4 m), each wall's top edge
    (z = 97.79 cm) and each house footprint (z = 0), projected into the camera's UPRIGHT pixels with the recording repo's
    calibration_qc/paddock_map.py. landmark_gui.py draws them as named dashed lines; annotated 09-18 IR frames are
    written for a quick look.
The guides only identify WHICH structure is which. They come from the calibration epoch (09-18/19), so on cohort frames
they are expected to be off (that offset is what the labels will measure) — always click the real structure.

Paddock frame (cv/configs/field_layout.json, calibration): origin = corner pole A0, x along the 40 ft length
(0–480 in, column 0–4 every 120 in), y across the 20 ft width (row A y = 0, B y = 120, C y = 240 in), z up.
Houses (user, 2026-09-30: keep the lab names): HOUSE_1 = house_1, next to pole B1, under CH05 (centre ≈ (134.9, 120.0)
in; WISER ROI house_1); HOUSE_2 = house_2, next to pole B3, under CH06 (≈ (347.0, 119.1) in; WISER ROI house_2).
(Which in-box camera, CH07/CH08, sits in which house is disputed between field_layout.json and the recording repo's
COLOUR_SAMPLING_LOG_cohort3.md — that does not affect the house names.)

Usage: python cv/cv_field/landmark_guides.py --cohort 2026c   # schematic + per-camera annotated 09-18 IR frames
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _p in (str(HERE), str(HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

CM_PER_IN = 2.54
POLE_TOP_MM = 2400.0
WALL_TOP_MM = 977.9
POLE_SKIP_IN = 20.0                     # the pole a camera is mounted on is too close to draw
HOUSE_OF_POLE = {"B1": "1", "B3": "2"}  # house_1 by pole B1 (CH05), house_2 by pole B3 (CH06)
IR_REF = {"CH01": "2026-09-18 13:57:30", "CH02": "2026-09-18 15:22:30",
          "CH03": "2026-09-18 15:45:00", "CH04": "2026-09-18 14:32:30"}


def calib_dir() -> Path:
    import camera_review as cr  # noqa: F401  (sibling-repo layout, same as the other tools)
    for root in (REPO.parent / "Field_2026_Social_Recording", Path("C:/Users/Cornell/Documents/GitHub/Field_2026_Social_Recording")):
        if (root / "calibration_qc" / "paddock_map.py").exists():
            return root / "calibration_qc"
    raise SystemExit("recording repo calibration_qc/ not found next to this repo")


def layout() -> dict:
    return json.loads((REPO / "cv" / "configs" / "field_layout.json").read_text(encoding="utf-8"))


def physical_landmarks() -> dict[str, tuple[str, list]]:
    """name -> (kind, points) for every structure a guide can be computed for; points = [(x_in, y_in, z_mm), ...] or,
    for a landmark made of several edges (a house's parallel bottom edges), a list of such pieces."""
    lay, out = layout(), {}
    for name, (x_cm, y_cm) in lay["poles"].items():
        x, y = x_cm / CM_PER_IN, y_cm / CM_PER_IN
        out[f"POLE_{name}"] = ("axis", [(x, y, z) for z in np.arange(0.0, POLE_TOP_MM + 1, 50.0)])
    s = np.arange(0.0, 1.0001, 0.01)
    L, Wd = lay["field_cm"]["x_len_40ft"] / CM_PER_IN, lay["field_cm"]["y_width_20ft"] / CM_PER_IN
    walls = {"WALLTOP_X0": [(0.0, t * Wd) for t in s], "WALLTOP_X480": [(L, t * Wd) for t in s],
             "WALLTOP_Y0": [(t * L, 0.0) for t in s], "WALLTOP_Y240": [(t * L, Wd) for t in s]}
    for k, pts in walls.items():
        out[k] = ("polyline", [(x, y, WALL_TOP_MM) for x, y in pts])
    for side, sh in lay["shelters"].items():
        if side.startswith("_"):
            continue
        cx, cy = (v / CM_PER_IN for v in sh["center_cm"])
        a, b = (v / CM_PER_IN / 2 for v in sh["size_cm"])
        th = np.radians(sh.get("orientation_deg", 0.0))
        corners = [(-a, -b), (a, -b), (a, b), (-a, b), (-a, -b)]
        pts = [(cx + u * np.cos(th) - v * np.sin(th), cy + u * np.sin(th) + v * np.cos(th)) for u, v in corners]
        pole = min(lay["poles"], key=lambda n: np.hypot(lay["poles"][n][0] / CM_PER_IN - cx, lay["poles"][n][1] / CM_PER_IN - cy))
        n = HOUSE_OF_POLE.get(pole, pole)
        # the footprint's four bottom edges, sorted by 3-D direction (one piece per edge, like the labels);
        # roof and vertical edges have no guide (heights unknown)
        for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
            axis = "X" if abs(x1 - x0) >= abs(y1 - y0) else "Y"
            out.setdefault(f"HOUSE_{n}_BASE_{axis}", ("edge", []))[1].append(
                [(x0 + t * (x1 - x0), y0 + t * (y1 - y0), 0.0) for t in np.linspace(0, 1, 11)])
    return out


def calib_guides(cam: str) -> dict[str, list[list[list[float]]]]:
    """Calibration-predicted UPRIGHT pixel PIECES of every landmark this camera sees: a piece ends where the structure
    leaves the frame / goes behind the camera or where the projection jumps (pano wrap), so nothing is joined across a
    gap (same convention as the labels: landmarks[name] = list of pieces)."""
    sys.path.insert(0, str(calib_dir()))
    import paddock_map as pm
    c = pm.load()[cam]
    jump = c.upright_size[0] / 4
    guides = {}
    for name, (kind, pts) in physical_landmarks().items():
        pieces3d = pts if isinstance(pts[0], list) else [pts]          # a landmark may already be several 3-D pieces
        if kind == "axis" and np.hypot(pieces3d[0][0][0] - c.centre[0] / 25.4, pieces3d[0][0][1] - c.centre[1] / 25.4) < POLE_SKIP_IN:
            continue
        pieces = []
        for p3 in pieces3d:
            run = []
            for x, y, z in p3:
                uv = None
                if bool(c.sees((x, y), z_mm=z, units="in")):
                    u, v = c.to_paddock_inv((x, y), z_mm=z, units="in")
                    if np.isfinite(u) and np.isfinite(v):
                        uv = [round(float(u), 1), round(float(v), 1)]
                if uv is None or (run and np.hypot(uv[0] - run[-1][0], uv[1] - run[-1][1]) > jump):
                    if len(run) >= 2:
                        pieces.append(run)
                    run = [uv] if uv is not None else []
                else:
                    run.append(uv)
            if len(run) >= 2:
                pieces.append(run)
        if pieces:
            guides[name] = pieces
    return guides


def cameras_from_fit() -> dict[str, tuple[float, float, float | None]]:
    """cam -> (x_in, y_in, bearing_deg or None) from CALIBRATION_FIT.txt RESULT 1."""
    txt = (calib_dir() / "CALIBRATION_FIT.txt").read_text(encoding="utf-8", errors="replace")
    out = {}
    for m in re.finditer(r"^\s+(CH0\d)\s+([\d.]+)\s+([\d.]+)\s+[\d.]+ m\s+(-?[\d.]+ deg|near-nadir)", txt, re.M):
        out[m[1]] = (float(m[2]), float(m[3]), None if m[4] == "near-nadir" else float(m[4].split()[0]))
    return out


def schematic(path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    lay = layout()
    L, Wd = lay["field_cm"]["x_len_40ft"] / CM_PER_IN, lay["field_cm"]["y_width_20ft"] / CM_PER_IN
    fig, ax = plt.subplots(figsize=(15, 8.6))
    ax.add_patch(plt.Rectangle((0, 0), L, Wd, fill=False, lw=3, color="#444"))
    for name, (x_cm, y_cm) in lay["poles"].items():
        x, y = x_cm / CM_PER_IN, y_cm / CM_PER_IN
        ax.plot(x, y, "o", ms=11, color="#1f77b4", zorder=5)
        ax.annotate(f"POLE_{name}", (x, y), xytext=(7, 7 if y < Wd / 2 else -16), textcoords="offset points",
                    fontsize=11, weight="bold", color="#1f77b4")
    ax.plot(0, 0, "*", ms=26, color="#d62728", zorder=6)
    ax.annotate("A0 = origin (0, 0)", (0, 0), xytext=(10, -34), textcoords="offset points", fontsize=12, weight="bold", color="#d62728")
    walls = {"WALLTOP_X0\n(x = 0 end)": (-16, Wd / 2, 90), "WALLTOP_X480\n(x = 480 end)": (L + 16, Wd / 2, 270),
             "WALLTOP_Y0  (row-A side, y = 0)": (L / 2, -14, 0), "WALLTOP_Y240  (row-C side, y = 240)": (L / 2, Wd + 12, 0)}
    for text, (x, y, rot) in walls.items():
        ax.text(x, y, text, rotation=rot, ha="center", va="center", fontsize=11, color="#8c2d04", weight="bold")
    for side, sh in lay["shelters"].items():
        if side.startswith("_"):
            continue
        cx, cy = (v / CM_PER_IN for v in sh["center_cm"])
        a, b = (v / CM_PER_IN for v in sh["size_cm"])
        w, h = (b, a) if abs(sh.get("orientation_deg", 0) - 90) < 1 else (a, b)
        pole = min(lay["poles"], key=lambda n: np.hypot(lay["poles"][n][0] / CM_PER_IN - cx, lay["poles"][n][1] / CM_PER_IN - cy))
        ax.add_patch(plt.Rectangle((cx - w / 2, cy - h / 2), w, h, color="#7f7f7f", alpha=0.6))
        n = HOUSE_OF_POLE.get(pole, pole)
        ax.text(cx, cy - h / 2 - 9, f"HOUSE_{n} (house_{n}, by pole {pole})", ha="center", fontsize=11, color="#333", weight="bold")
    for cam, (x, y, brg) in cameras_from_fit().items():
        col = "#2ca02c" if cam in ("CH01", "CH02") else "#9467bd" if cam in ("CH03", "CH04") else "#bcbd22"
        ax.plot(x, y, "s", ms=13, color=col, zorder=7)
        if brg is not None:
            ax.annotate("", xy=(x + 55 * np.cos(np.radians(brg)), y + 55 * np.sin(np.radians(brg))), xytext=(x, y),
                        arrowprops=dict(arrowstyle="-|>", lw=3, color=col), zorder=7)
        look = "" if brg is None else f" looks {brg:+.0f}°"
        ax.annotate(f"{cam}{look}", (x, y), xytext=(-40, 14 if cam != "CH01" else -24), textcoords="offset points",
                    fontsize=11, color=col, weight="bold")
    for name, y, va, where in (("TOWER_1", Wd + 26, "bottom", "beyond the row-C wall (y = 240)"),
                               ("TOWER_2", -30, "top", "beyond the row-A wall (y = 0)")):
        ax.annotate(f"{name}: water tower {where} — outside the paddock, x position not surveyed", (L * 0.82, y),
                    ha="center", va=va, fontsize=11, weight="bold", color="#006d77")
        ax.annotate("", xy=(L * 0.82, y + (14 if va == "bottom" else -12)), xytext=(L * 0.82, y + (2 if va == "bottom" else 2)),
                    arrowprops=dict(arrowstyle="-|>", lw=2.5, color="#006d77"))
    ax.text(L / 2, -44, "Not placed: PCBOX = the PC box that CH02 faces (location only you know). "
            "BOX_<pole> = the box on each pole = a WISER UWB anchor.", ha="center", fontsize=10.5, color="#555")
    ax.text(L / 2, -58, "POLE_* = the pole's vertical CENTRE LINE (ends usually not visible) · WALLTOP_* = TOP edge of the wall sheet "
            "(the foot is hidden by grass) · HOUSE_* = validation only.", ha="center", fontsize=10.5, color="#555")
    ax.set_xlim(-45, L + 45)
    ax.set_ylim(-70, Wd + 55)
    ax.set_aspect("equal")
    ax.set_xlabel("x (in) — along the 40 ft length")
    ax.set_ylabel("y (in) — across the 20 ft width")
    ax.set_title("Paddock landmark names (top view; camera positions/bearings from the 2026-09-24 calibration, 0° = +x, 90° = +y)")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def annotate_frame(cam: str, args, out: Path) -> None:
    """The camera's 09-18 IR reference with the named calibration guides (dashed) — to see which pole is which."""
    import camera_review as cr
    size = (7680, 2160) if cam in cr.PANO else (4512, 2512)
    got = cr.grab_at(datetime.strptime(IR_REF[cam], "%Y-%m-%d %H:%M:%S"), cam, args, cr.find_ffmpeg(), size)
    if got is None:
        print(f"{cam}: no 09-18 IR frame")
        return
    img = got[0].copy()
    th = max(3, img.shape[1] // 1200)
    for name, pieces in calib_guides(cam).items():
        colr = (255, 200, 0) if name.startswith("POLE") else (0, 140, 255) if name.startswith("WALL") else (200, 200, 200)
        for piece in pieces:
            p = np.asarray(piece, float)
            for a, b in zip(p[:-1], p[1:]):
                cv2.line(img, tuple(np.round(a).astype(int)), tuple(np.round(b).astype(int)), colr, th, cv2.LINE_AA)
        p = np.asarray(max(pieces, key=len), float)
        m = p[len(p) // 2]
        cv2.putText(img, name, (int(m[0]) + 8, int(m[1])), cv2.FONT_HERSHEY_SIMPLEX, th * 0.9, (0, 0, 0), th * 4, cv2.LINE_AA)
        cv2.putText(img, name, (int(m[0]) + 8, int(m[1])), cv2.FONT_HERSHEY_SIMPLEX, th * 0.9, colr, th, cv2.LINE_AA)
    s = 2400 / img.shape[1]
    cv2.imwrite(str(out), cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(f"{cam}: guides -> {out}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Landmark name schematic + calibration guides per camera.")
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--cameras", nargs="+", default=["CH01", "CH02", "CH03", "CH04"])
    ap.add_argument("--cohort-root", default=r"F:\3rd_rat")
    ap.add_argument("--ref-session", default=r"F:\calibration\session_2026-09-18_13-54-34")
    args = ap.parse_args(argv)
    import output_paths as op
    rep = REPO / "cv" / "configs" / "landmarks" / args.cohort
    rep.mkdir(parents=True, exist_ok=True)
    schematic(rep / "paddock_schematic.png")
    print(f"schematic -> {rep / 'paddock_schematic.png'}")
    out_dir = op.out_root() / args.cohort / "cv_field_landmarks"
    out_dir.mkdir(parents=True, exist_ok=True)
    for cam in args.cameras:
        annotate_frame(cam, args, out_dir / f"guides_{cam}_0918IR.jpg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
