r"""
calibrate_camera_visibility.py — build/refresh configs/camera_visibility_map.yaml
(the WISER-inch -> camera-channel map used by the Phase B2 router).

Three modes (all read-only on WISER data):

  --reference       render a WISER REFERENCE FRAME (occupancy backdrop + paddock
                    boundary + labeled ROIs) so you can relate WISER (x,y) to the
                    landmarks you see on video. Start here.  [default]
  --from-examples   read configs/camera_visibility_examples.csv (channel, wiser_x,
                    wiser_y) and build each channel's visibility polygon as the
                    convex hull of its points (+ margin) -> writes the yaml + a
                    verification figure. This is the easy path: log points, not draw.
  --gui             draw one polygon per channel by clicking over the WISER cloud
                    (needs a display; mirrors place_exclude_region.py).

Outputs to outputs/camera_calibration/. Numpy + matplotlib + PyYAML only.

    conda activate cv
    cd wiser
    python scripts/calibrate_camera_visibility.py --reference --date 2026-06-29
    # (log points into configs/camera_visibility_examples.csv, then)
    python scripts/calibrate_camera_visibility.py --from-examples
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys
from pathlib import Path

import numpy as np

import matplotlib
# Use a non-interactive backend for the batch modes (--reference / --from-examples);
# only --gui needs a real window, so keep the default interactive backend then.
if "--gui" not in sys.argv:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import wiser_analysis_utils as w              # noqa: E402
import time_utils                             # noqa: E402
import trajectory_stereotypy as ts            # noqa: E402
import camera_router as cr                    # noqa: E402
import analyze_trajectory_stereotypy as pa    # noqa: E402

DEFAULT_MAP = PROJECT_ROOT / "configs" / "camera_visibility_map.yaml"
DEFAULT_EXAMPLES = PROJECT_ROOT / "configs" / "camera_visibility_examples.csv"
DEFAULT_ROIS = PROJECT_ROOT / "configs" / "wiser_rois.json"
DEFAULT_OUT = PROJECT_ROOT / "outputs" / "camera_calibration"
DEFAULT_LAYOUT_IMG = (PROJECT_ROOT.parent / "preprocessing" / "computer_vision" /
                      "configs" / "field_layout_map.png")


# ---------------------------------------------------------------------------
# geometry helpers (numpy only)
# ---------------------------------------------------------------------------

def convex_hull(points: np.ndarray) -> np.ndarray:
    """Convex hull (Andrew's monotone chain), CCW, no repeated endpoint."""
    pts = sorted(set(map(tuple, np.asarray(points, float).tolist())))
    if len(pts) <= 2:
        return np.asarray(pts, float)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.asarray(lower[:-1] + upper[:-1], float)


def buffer_polygon(poly: np.ndarray, margin_in: float) -> np.ndarray:
    """Grow a polygon outward from its centroid by ``margin_in`` (a simple radial
    buffer — a visibility polygon just needs a slight outward margin, not exact
    offsetting)."""
    if len(poly) < 3 or margin_in <= 0:
        return poly
    c = poly.mean(0)
    d = poly - c
    n = np.linalg.norm(d, axis=1, keepdims=True)
    return poly + margin_in * d / np.clip(n, 1e-9, None)


def polygons_from_examples(examples: dict, *, margin_in: float, min_points: int = 3) -> dict:
    """{channel: [[x,y],...]} hull polygons from {channel: (M,2) points}."""
    out = {}
    for ch, pts in examples.items():
        pts = np.asarray(pts, float)
        if len(pts) >= min_points:
            out[ch] = buffer_polygon(convex_hull(pts), margin_in).round(1).tolist()
    return out


# ---------------------------------------------------------------------------
# io
# ---------------------------------------------------------------------------

def read_examples_csv(path: Path) -> dict:
    """Read the examples CSV (channel, wiser_x, wiser_y[, notes]); '#'/blank lines
    skipped. Returns {channel: [[x,y], ...]}."""
    import csv
    ex: dict = {}
    if not Path(path).exists():
        return ex
    with open(path, newline="") as f:
        for row in csv.DictReader((ln for ln in f if not ln.lstrip().startswith("#"))):
            try:
                ch = str(row["channel"]).strip()
                x = float(row["wiser_x"]); y = float(row["wiser_y"])
            except (KeyError, ValueError, TypeError):
                continue
            if ch:
                ex.setdefault(ch, []).append([x, y])
    return ex


def write_visibility_map(path: Path, base_map: dict, hull_polys: dict, examples: dict,
                         *, all_calibrated: bool):
    """Regenerate camera_visibility_map.yaml: channels get their hull polygon where
    examples exist, else keep the existing polygon/bbox. Priorities/notes preserved.
    A concise header + provenance is written; comment-rich template lives in git."""
    import yaml
    chans = []
    for ch in base_map.get("channels", []):
        name = ch["name"]
        entry = {"name": name, "priority": float(ch.get("priority", 1.0)),
                 "notes": ch.get("notes", "")}
        if name in hull_polys:
            entry["polygon"] = hull_polys[name]
            entry["source"] = f"convex hull of {len(examples.get(name, []))} example points + margin"
        elif ch.get("polygon"):
            entry["polygon"] = [[round(float(a), 1), round(float(b), 1)] for a, b in ch["polygon"]]
            entry["source"] = "placeholder (uncalibrated) — add examples to configs/camera_visibility_examples.csv"
        elif ch.get("bbox"):
            entry["bbox"] = ch["bbox"]
            entry["source"] = "placeholder bbox (uncalibrated)"
        entry["n_examples"] = len(examples.get(name, []))
        chans.append(entry)
    meta = dict(base_map.get("meta", {}))
    meta["confirmed"] = bool(all_calibrated)
    meta["calibrated_utc"] = _dt.datetime.utcnow().isoformat()
    meta["frame"] = "WISER native inches (offset origin, UNVERIFIED vs physical field)"
    doc = {"meta": meta, "channels": chans}
    header = ("# camera_visibility_map.yaml — WISER-inch -> camera channel map (Phase B2 router).\n"
              "# Regenerated by scripts/calibrate_camera_visibility.py from\n"
              "# configs/camera_visibility_examples.csv. Polygons are convex hulls of your logged\n"
              "# example points (+ margin), in the WISER inch frame (no georeference needed).\n"
              "# meta.confirmed becomes true only when every channel has >= 3 example points.\n"
              "# Edit points in the examples CSV and re-run; hand-edit polygons here if you prefer.\n\n")
    path.write_text(header + yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# occupancy backdrop + ROI overlay
# ---------------------------------------------------------------------------

def _load_backdrop(args):
    """Load one date's WISER fixes for the occupancy backdrop (read-only). Returns
    (x, y, extent) or (None, None, extent) if unavailable."""
    roi_cfg = w.load_rois(args.rois)
    boundary = (roi_cfg or {}).get("boundary")
    if boundary and "rect" in boundary:
        xmin, xmax, ymin, ymax = boundary["rect"]
        extent = (xmin - 24, xmax + 24, ymin - 24, ymax + 24)
    else:
        extent = (200, 820, 520, 910)
    try:
        df, _ = ts.load_incremental_days(args.incremental_dir, dates=[args.date])
        df = time_utils.convert_timestamps(df)
        df = df.dropna(subset=["x", "y"])
        return df["x"].to_numpy(), df["y"].to_numpy(), extent, roi_cfg
    except Exception as exc:
        print(f"    [backdrop] no WISER data ({exc}); drawing landmarks only")
        return None, None, extent, roi_cfg


def _draw_landmarks(ax, roi_cfg, extent):
    b = (roi_cfg or {}).get("boundary", {})
    if b.get("rect"):
        xmin, xmax, ymin, ymax = b["rect"]
        ax.plot([xmin, xmax, xmax, xmin, xmin], [ymin, ymin, ymax, ymax, ymin],
                "-", color="k", lw=1.2, label="boundary")
    for roi in (roi_cfg or {}).get("rois", []):
        x, y = roi["x"], roi["y"]
        col = {"refuge": "#1f77b4", "water": "#2ca02c", "food": "#ff7f0e",
               "tunnel": "#9467bd"}.get(roi.get("type"), "#7f7f7f")
        if roi.get("shape") == "rect":
            hw = roi.get("width_in", 20) / 2; hh = roi.get("height_in", 20) / 2
            ax.add_patch(plt.Rectangle((x - hw, y - hh), 2 * hw, 2 * hh, fill=False,
                                       edgecolor=col, lw=1.4))
        else:
            ax.add_patch(plt.Circle((x, y), roi.get("radius_in", 10), fill=False,
                                    edgecolor=col, lw=1.4))
        ax.annotate(roi["name"], (x, y), fontsize=7, color=col, ha="center", va="center")
    ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal"); ax.set_xlabel("WISER x (in)"); ax.set_ylabel("WISER y (in)")


def render_reference(args, out):
    x, y, extent, roi_cfg = _load_backdrop(args)
    fig, ax = plt.subplots(figsize=(9, 7))
    overlaid = False
    if getattr(args, "overlay_layout", False) and Path(args.layout_image).exists():
        try:
            img = plt.imread(str(args.layout_image))
            ax.imshow(img, extent=(extent[0], extent[1], extent[2], extent[3]),
                      alpha=0.30, zorder=0, aspect="auto")
            overlaid = True
        except Exception as exc:
            print(f"    [overlay] could not read {args.layout_image}: {exc}")
    if x is not None:
        ax.hexbin(x, y, gridsize=60, cmap="Greys", bins="log", mincnt=1, zorder=1)
    _draw_landmarks(ax, roi_cfg, extent)
    ttl = (f"WISER reference frame ({args.date}) — occupancy + boundary + ROIs.\n"
           "Relate WISER (x,y) to landmarks you recognize on video, then log points in "
           "configs/camera_visibility_examples.csv.")
    if overlaid:
        ttl += "\n(field_layout_map.png overlaid — APPROXIMATE/stretched, NOT georeferenced.)"
    ax.set_title(ttl)
    fig.tight_layout(); p = out / "wiser_reference_frame.png"
    fig.savefig(p, dpi=140); plt.close(fig)
    print(f"    reference frame -> {p}")
    return roi_cfg, extent


def render_verification(out, base_map, hull_polys, examples, roi_cfg, extent):
    fig, ax = plt.subplots(figsize=(9, 7))
    _draw_landmarks(ax, roi_cfg, extent)
    cmap = plt.get_cmap("tab10")
    for i, ch in enumerate(base_map.get("channels", [])):
        name = ch["name"]; col = cmap(i % 10)
        poly = hull_polys.get(name) or ch.get("polygon")
        if poly:
            poly = np.asarray(poly, float)
            ax.add_patch(plt.Polygon(poly, closed=True, fill=True, alpha=0.12, color=col))
            ax.plot(*np.vstack([poly, poly[:1]]).T, "-", color=col, lw=1.5,
                    label=f"{name}{' (hull)' if name in hull_polys else ' (placeholder)'}")
        pts = np.asarray(examples.get(name, []), float)
        if len(pts):
            ax.plot(pts[:, 0], pts[:, 1], "o", color=col, ms=5, mec="k", mew=0.5)
    ax.legend(fontsize=7, loc="upper right")
    ax.set_title("Camera visibility polygons (hull of example points) — verify before trusting routing")
    fig.tight_layout(); p = out / "camera_visibility_verification.png"
    fig.savefig(p, dpi=140); plt.close(fig)
    print(f"    verification figure -> {p}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reference", action="store_true", help="render the WISER reference frame (default)")
    ap.add_argument("--from-examples", action="store_true", help="build polygons from the examples CSV")
    ap.add_argument("--gui", action="store_true", help="draw polygons interactively (needs a display)")
    ap.add_argument("--incremental-dir", type=Path, default=pa.DEFAULT_INCR)
    ap.add_argument("--date", default="2026-06-29", help="date for the occupancy backdrop")
    ap.add_argument("--map", type=Path, default=DEFAULT_MAP)
    ap.add_argument("--examples", type=Path, default=DEFAULT_EXAMPLES)
    ap.add_argument("--rois", type=Path, default=DEFAULT_ROIS)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--margin-in", type=float, default=18.0, help="outward buffer on hull polygons")
    ap.add_argument("--overlay-layout", action="store_true",
                    help="draw field_layout_map.png as a faint backdrop (APPROXIMATE — not "
                         "georeferenced; trust the labeled ROIs, not the image alignment)")
    ap.add_argument("--layout-image", type=Path, default=DEFAULT_LAYOUT_IMG)
    args = ap.parse_args()
    out = args.out; out.mkdir(parents=True, exist_ok=True)

    try:
        base_map = cr.load_visibility_map(args.map)
    except Exception:
        base_map = {"meta": {}, "channels": []}

    if args.from_examples:
        print("== calibrate camera visibility: from examples ==")
        examples = read_examples_csv(args.examples)
        if not examples:
            print(f"    no usable rows in {args.examples}; add channel,wiser_x,wiser_y points."); return
        hull_polys = polygons_from_examples(examples, margin_in=args.margin_in)
        n_ch = len(base_map.get("channels", []))
        all_cal = n_ch > 0 and all(ch["name"] in hull_polys for ch in base_map["channels"])
        write_visibility_map(args.map, base_map, hull_polys, examples, all_calibrated=all_cal)
        print(f"    calibrated {len(hull_polys)} channel(s) from examples: "
              f"{ {k: len(v) for k, v in examples.items()} }")
        print(f"    meta.confirmed = {all_cal}; wrote {args.map}")
        roi_cfg, extent = (w.load_rois(args.rois), None)
        _, _, extent, roi_cfg = _load_backdrop(args)
        render_verification(out, base_map, hull_polys, examples, roi_cfg, extent)
        return

    if args.gui:
        _run_gui(args, base_map, out)
        return

    # default: reference frame
    print("== calibrate camera visibility: reference frame ==")
    render_reference(args, out)
    print("    next: log points per channel in configs/camera_visibility_examples.csv, then "
          "re-run with --from-examples")


def _run_gui(args, base_map, out):
    """Interactive polygon drawing per channel over the WISER cloud (needs a display).
    Mirrors place_exclude_region.py; left-click add vertex, `n` next channel, `s`
    save, `q` quit. Explicitly switches to a working interactive backend (TkAgg first,
    then QtAgg) — the env's default may silently fall back to Agg."""
    picked = None
    for bk in ("TkAgg", "QtAgg", "Qt5Agg"):
        try:
            plt.switch_backend(bk)
            picked = bk
            break
        except Exception:
            continue
    if picked is None or plt.get_backend().lower() == "agg":
        print("    [gui] no interactive backend could load (tried TkAgg/QtAgg). Use "
              "--from-examples, or `pip install pyqt5` into the cv env, then retry.")
        return
    print(f"    [gui] backend: {picked}")
    x, y, extent, roi_cfg = _load_backdrop(args)
    names = [c["name"] for c in base_map.get("channels", [])] or ["CH01", "CH02", "CH03", "CH04", "CH05"]
    state = {"i": 0, "polys": {n: [] for n in names}, "cur": []}
    fig, ax = plt.subplots(figsize=(10, 8))
    if x is not None:
        ax.hexbin(x, y, gridsize=60, cmap="Greys", bins="log", mincnt=1)
    _draw_landmarks(ax, roi_cfg, extent)

    def title():
        ax.set_title(f"Draw polygon for {names[state['i']]}  "
                     f"[{state['i']+1}/{len(names)}]  left-click=vertex  n=next  u=undo  s=save  q=quit")
        fig.canvas.draw_idle()

    def on_click(ev):
        if ev.inaxes == ax and ev.button == 1:
            state["cur"].append([ev.xdata, ev.ydata])
            ax.plot(ev.xdata, ev.ydata, "r.")
            fig.canvas.draw_idle()

    def on_key(ev):
        if ev.key == "n":
            if len(state["cur"]) >= 3:
                state["polys"][names[state["i"]]] = list(state["cur"])
            state["cur"] = []; state["i"] = (state["i"] + 1) % len(names); title()
        elif ev.key == "u" and state["cur"]:
            state["cur"].pop()
        elif ev.key in ("s", "q"):
            if len(state["cur"]) >= 3:
                state["polys"][names[state["i"]]] = list(state["cur"])
            hp = {n: np.asarray(p, float).round(1).tolist() for n, p in state["polys"].items() if len(p) >= 3}
            write_visibility_map(args.map, base_map, hp, {n: [] for n in hp},
                                 all_calibrated=len(hp) == len(names))
            print(f"saved {len(hp)} polygon(s) to {args.map}")
            if ev.key == "q":
                plt.close(fig)
    fig.canvas.mpl_connect("button_press_event", on_click)
    fig.canvas.mpl_connect("key_press_event", on_key)
    title(); plt.show()


if __name__ == "__main__":
    main()
