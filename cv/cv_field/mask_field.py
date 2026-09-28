"""mask_field.py — interactive GUI to draw the static valid-field mask for CH03 / CH04.

Part of the CH03/CH04 frame is enclosure wall / out-of-field margin where a rat can never be. Click the
valid-field boundary once; every downstream stage (`field_motion` proposals, tiled inference, the density
probe) then drops anything outside it. Static geometry, drawn once per camera.

Usage (run locally — interactive, needs a display; from inside cv/):
    python cv_field/mask_field.py --channel CH03 --image dataset/rat_field/images/CH03_...png
    python cv_field/mask_field.py --channel CH04 --video E:/2026-06-28/CH04/CH04_...mp4 --offset 900

Workflow in the window:
    * The dashed cyan outline is the calibration-projected field rectangle — a TRACING GUIDE only (the far
      end is extrapolated and not trustworthy; trust your eye on where the wall actually is).
    * Left-click to place valid-field polygon vertices; close it near the first point (PolygonSelector).
    * Press 'e' to bank the current polygon as an EXCLUSION (wall/blind-band hole) and start a new one.
    * Press 'v' to (re)designate the current polygon as the VALID field boundary.
    * Press 's' to save -> cv/configs/<CH>_field_mask.json (normalized polygon + crop) and a PNG preview.
    * Press 'q' to quit without saving. 'r' resets the current polygon.

The geometry/serialization lives in `field_mask.FieldMask` (unit-tested); this file is only the thin GUI
shell + frame IO, so `--selftest` exercises the non-interactive save/load round-trip.
"""
from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from field_mask import CONFIG_DIR, FieldMask, projected_field_polygon_norm


# ------------------------------------------------------------------ frame IO
def load_frame_image(path) -> np.ndarray:
    import cv2
    img = cv2.imread(str(path))
    if img is None:
        raise FileNotFoundError(f"could not read image {path}")
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def extract_frame_from_video(src, offset_s: float, ffmpeg: str = "ffmpeg", scale: int = 0) -> np.ndarray:
    """Pull ONE frame at `offset_s` from a source video (seek before -i, so it is cheap). Optional downscale."""
    import cv2
    vf = f"scale={scale}:-2" if scale else "scale=iw:ih"
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "f.png"
        subprocess.run([ffmpeg, "-y", "-ss", str(offset_s), "-i", str(src), "-frames:v", "1",
                        "-vf", vf, str(out)], capture_output=True, text=True)
        if not out.exists():
            raise RuntimeError(f"ffmpeg could not extract a frame from {src} at {offset_s}s")
        return cv2.cvtColor(cv2.imread(str(out)), cv2.COLOR_BGR2RGB)


# ------------------------------------------------------------------ interactive editor
def run_gui(channel: str, frame: np.ndarray, config_dir=CONFIG_DIR):
    """Open the polygon editor on `frame`. Blocks until the user saves or quits."""
    import matplotlib.pyplot as plt
    from matplotlib.widgets import PolygonSelector

    H, W = frame.shape[:2]
    state = {"valid": None, "exclusions": []}          # normalized polygons

    fig, ax = plt.subplots(figsize=(13, 7))
    ax.imshow(frame)
    ax.set_title(f"{channel}: click valid-field polygon · 'e'=bank exclusion · 'v'=set valid · 's'=save · 'q'=quit")

    guide = projected_field_polygon_norm(channel, config_dir)
    if guide is not None:
        # The calib far-field is a wild extrapolation (survey landmarks cluster near x=0), so the projected
        # rectangle can land thousands of px OFF the frame. Only draw it if a meaningful part is on-image, and
        # NEVER let it drive the view (that shrinks the real frame to a thumbnail).
        on = ((guide[:, 0] > -0.3) & (guide[:, 0] < 1.3) & (guide[:, 1] > -0.3) & (guide[:, 1] < 1.3))
        if int(on.sum()) >= 4:
            g = guide * np.array([W, H], float)
            gx = np.append(g[:, 0], g[0, 0]); gy = np.append(g[:, 1], g[0, 1])
            ax.plot(gx, gy, "--", color="cyan", lw=1.2, alpha=0.7, label="calib field (guide, extrapolated)")
            ax.legend(loc="upper right")
        else:
            print("[guide] calibration projects mostly off-frame (far-field extrapolation) — hiding it; trust the image")
    ax.set_xlim(0, W); ax.set_ylim(H, 0)          # pin the view to the ACTUAL frame; a runaway guide is clipped, not the boss

    def _norm(verts):
        return (np.asarray(verts, float) / np.array([W, H], float)).tolist()

    def on_select(verts):
        state["current"] = list(verts)

    selector = PolygonSelector(ax, on_select)
    state["current"] = []

    def redraw_banked():
        # redraw banked polygons as static overlays
        for art in list(ax.lines):
            if art.get_label() in ("valid", "excl"):
                art.remove()
        if state["valid"] is not None:
            p = np.asarray(state["valid"], float) * np.array([W, H], float)
            ax.plot(np.append(p[:, 0], p[0, 0]), np.append(p[:, 1], p[0, 1]), "-", color="lime", lw=2, label="valid")
        for e in state["exclusions"]:
            p = np.asarray(e, float) * np.array([W, H], float)
            ax.plot(np.append(p[:, 0], p[0, 0]), np.append(p[:, 1], p[0, 1]), "-", color="red", lw=1.6, label="excl")
        fig.canvas.draw_idle()

    def on_key(event):
        if event.key == "v":
            if len(state["current"]) >= 3:
                state["valid"] = _norm(state["current"]); print(f"[valid] {len(state['current'])} pts set")
                redraw_banked()
        elif event.key == "e":
            if len(state["current"]) >= 3:
                state["exclusions"].append(_norm(state["current"]))
                print(f"[exclusion] banked ({len(state['exclusions'])} total)")
                redraw_banked()
        elif event.key == "r":
            selector.clear(); state["current"] = []; print("[reset] current polygon cleared")
        elif event.key == "s":
            if state["valid"] is None and len(state["current"]) >= 3:
                state["valid"] = _norm(state["current"])           # default: current polygon is the valid one
            if state["valid"] is None:
                print("[save] no valid polygon yet — draw one and press 'v' (or 's')"); return
            m = FieldMask(channel=channel, polygon=state["valid"], exclusions=state["exclusions"],
                          ref_image_size=(W, H), note="hand-drawn via mask_field.py")
            p = m.save(config_dir)
            _save_preview(channel, frame, m, config_dir)
            print(f"[save] wrote {p}")
            plt.close(fig)
        elif event.key == "q":
            print("[quit] no save"); plt.close(fig)

    fig.canvas.mpl_connect("key_press_event", on_key)
    plt.show()
    return state


def _save_preview(channel, frame, mask: FieldMask, config_dir):
    """Write a PNG showing the frame dimmed outside the valid field, for a quick eyeball check."""
    import cv2
    H, W = frame.shape[:2]
    m = mask.render_mask(W, H)
    vis = frame.copy()
    vis[~m] = (vis[~m] * 0.25).astype(vis.dtype)
    out = Path(config_dir) / f"{channel}_field_mask_preview.png"
    cv2.imwrite(str(out), cv2.cvtColor(vis, cv2.COLOR_RGB2BGR))
    return out


# ------------------------------------------------------------------ self-test (non-interactive)
def _selftest() -> int:
    import tempfile as _tf
    ok = True

    def chk(name, cond):
        nonlocal ok; ok = ok and bool(cond); print(f"  [{'PASS' if cond else 'FAIL'}] {name}")

    with _tf.TemporaryDirectory() as d:
        poly = [[0.1, 0.2], [0.9, 0.2], [0.9, 0.8], [0.1, 0.8]]
        excl = [[[0.1, 0.2], [0.3, 0.2], [0.3, 0.4], [0.1, 0.4]]]     # a corner cut out (the "wall")
        m = FieldMask("CH03", polygon=poly, exclusions=excl, ref_image_size=(2560, 1426))
        p = m.save(d, created="2026-07-13T00:00:00")
        chk("mask file written", Path(p).exists())
        m2 = FieldMask.load("CH03", d)
        chk("round-trip polygon", np.allclose(m2.polygon, np.asarray(poly)))
        chk("round-trip exclusion count", len(m2.exclusions) == 1)
        # centre of frame is inside; the excluded corner is outside
        chk("centre inside", m2.contains([[640, 360]], 1280, 720)[0])
        chk("excluded corner outside", not m2.contains([[0.2 * 1280, 0.3 * 720]], 1280, 720)[0])
        chk("far corner (outside polygon) outside", not m2.contains([[5, 5]], 1280, 720)[0])
    print("PASS — mask_field self-test" if ok else "FAIL — mask_field self-test")
    return 0 if ok else 1


def main() -> None:
    ap = argparse.ArgumentParser(description="Draw the static valid-field mask for a whole-field cam.")
    ap.add_argument("--channel", help="e.g. CH03 or CH04")
    ap.add_argument("--image", help="a representative night-IR frame (PNG)")
    ap.add_argument("--video", help="source video to pull a frame from (alternative to --image)")
    ap.add_argument("--offset", type=float, default=900.0, help="seconds into --video to grab")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--config-dir", default=str(CONFIG_DIR))
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        raise SystemExit(_selftest())
    if not args.channel or not (args.image or args.video):
        raise SystemExit("provide --channel and one of --image / --video (or --selftest)")
    frame = (load_frame_image(args.image) if args.image
             else extract_frame_from_video(args.video, args.offset, args.ffmpeg))
    run_gui(args.channel, frame, Path(args.config_dir))


if __name__ == "__main__":
    main()
