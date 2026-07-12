r"""
place_camera_landmarks.py — calibrate a camera channel by marking landmarks in its
OWN image (the intuitive direction), then map back to a WISER visibility polygon.

Workflow:
  1. --extract   grab a still frame from CHxx's recorded video (cv2; no ffmpeg).
  2. --gui       show that frame; click a landmark you recognise (house, water,
                 refuge, corner) then press its number to tag it with that WISER
                 landmark's known (x, y); optionally draw the visible GROUND region;
                 press `s` to fit a pixel->WISER homography and write this channel's
                 polygon into configs/camera_visibility_map.yaml.
  3. --build     (no display) build the polygon from a saved landmarks file
                 (configs/camera_landmarks/CHxx.json) or a CSV of px,py,wiser_x,wiser_y.

The homography is fit directly from your pixel<->WISER landmark pairs, so no
georeference is needed. Needs >= 4 landmarks.

    conda activate cv
    cd wiser
    python scripts/place_camera_landmarks.py --extract --channel CH01 --date 2026-06-29 --hour 12
    python scripts/place_camera_landmarks.py --gui     --channel CH01
    python scripts/place_camera_landmarks.py --build   --channel CH01   # from the saved json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import glob
import json
import sys
from pathlib import Path

import numpy as np

import matplotlib
if "--gui" not in sys.argv:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import wiser_analysis_utils as w              # noqa: E402
import camera_calibration as cc               # noqa: E402
import camera_router as cr                    # noqa: E402
import calibrate_camera_visibility as cal     # noqa: E402

DEFAULT_MAP = PROJECT_ROOT / "configs" / "camera_visibility_map.yaml"
DEFAULT_ROIS = PROJECT_ROOT / "configs" / "wiser_rois.json"
DEFAULT_LANDMARK_DIR = PROJECT_ROOT / "configs" / "camera_landmarks"
DEFAULT_OUT = PROJECT_ROOT / "outputs" / "camera_calibration"
# transferred footage on the analysis PC
DEFAULT_VIDEO_ROOT = Path(r"D:\Reolink_record\audio_in\Reolink_record")
KEYS = "1234567890abcdefghij"     # key -> landmark index in the menu


# CH01/CH02 (Duo 3 16MP) daytime keyframes are HARD-CAPPED at 2 MB by the camera encoder, so
# bright-hour frames drop their bottom band (it is never recorded — no decoder recovers it; see
# docs/methods/duo3_keyframe_2mb_cap.md). NIGHT IR keyframes (~1.1 MB) never hit the cap and are
# always full, so default --extract for these two channels to a night/IR hour for a clean
# calibration frame. Pass --hour explicitly to override.
_CAPPED_PANO = {"CH01", "CH02"}
_NIGHT_HOURS = (2, 3, 1, 4, 0, 23)             # preference order, all IR / uncapped


def _find_video(channel: str, date: str, hour: int | None) -> Path | None:
    d = DEFAULT_VIDEO_ROOT / channel
    pats = sorted(glob.glob(str(d / f"{channel}_{date}_*_to_*.mp4")))
    if not pats:
        return None
    hours_to_try = [hour] if hour is not None else (
        list(_NIGHT_HOURS) if channel in _CAPPED_PANO else [])
    for hh_i in hours_to_try:
        hh = f"{hh_i:02d}-"
        for p in pats:
            if f"_{hh}" in Path(p).name.split("_to_")[0]:
                return Path(p)
    return Path(pats[len(pats) // 2])          # midday-ish default (normal-res channels)


def _frame_path(channel, out):
    return out / f"{channel}_frame.png"


def _landmark_json(channel):
    return DEFAULT_LANDMARK_DIR / f"{channel}.json"


# ---------------------------------------------------------------------------
# build polygon from saved landmarks -> write yaml
# ---------------------------------------------------------------------------

def _write_channel_polygon(channel, poly, map_path, rms, source):
    """Update one channel's polygon in camera_visibility_map.yaml (keep others)."""
    import yaml
    try:
        base = cr.load_visibility_map(map_path)
    except Exception:
        base = {"meta": {}, "channels": []}
    chans = {c["name"]: c for c in base.get("channels", [])}
    ch = chans.get(channel, {"name": channel, "priority": 1.0, "notes": ""})
    ch["polygon"] = poly
    ch.pop("bbox", None)
    ch["source"] = source
    ch["rms_in"] = rms
    chans[channel] = ch
    out_chans = []
    for c in chans.values():
        e = {"name": c["name"], "priority": float(c.get("priority", 1.0)),
             "notes": c.get("notes", "")}
        if c.get("polygon"):
            e["polygon"] = [[round(float(a), 1), round(float(b), 1)] for a, b in c["polygon"]]
        if "source" in c:
            e["source"] = c["source"]
        if "rms_in" in c:
            e["rms_in"] = c["rms_in"]
        out_chans.append(e)
    meta = dict(base.get("meta", {}))
    meta["confirmed"] = all("polygon" in e and "hull" not in e.get("source", "")
                            and "placeholder" not in e.get("source", "") for e in out_chans) \
        and len(out_chans) > 0
    meta["calibrated_utc"] = _dt.datetime.utcnow().isoformat()
    header = ("# camera_visibility_map.yaml — WISER-inch -> camera channel map (Phase B2 router).\n"
              "# Channels calibrated by scripts/place_camera_landmarks.py: a pixel->WISER homography\n"
              "# fit from landmarks marked in each channel's own frame, mapped to a WISER polygon.\n\n")
    Path(map_path).write_text(header + yaml.safe_dump({"meta": meta, "channels": out_chans},
                                                      sort_keys=False), encoding="utf-8")


def build_from_landmarks(channel, *, map_path, out, roi_cfg, margin_in=18.0,
                         csv=None, landmark_json=None):
    """Fit homography from a saved landmarks json (or a CSV of px,py,wiser_x,wiser_y)
    and write the channel's polygon + a verification figure."""
    region_px = None
    if csv:
        arr = np.genfromtxt(csv, delimiter=",", names=True)
        px = np.column_stack([arr["px"], arr["py"]])
        wz = np.column_stack([arr["wiser_x"], arr["wiser_y"]])
    else:
        lj = landmark_json or _landmark_json(channel)
        d = json.loads(Path(lj).read_text())
        corr = d["correspondences"]
        px = np.array([[c["px"], c["py"]] for c in corr], float)
        wz = np.array([[c["wiser_x"], c["wiser_y"]] for c in corr], float)
        region_px = d.get("region_px") or None
    res = cc.build_visibility_polygon(px, wz, region_px=region_px, margin_in=margin_in)
    _write_channel_polygon(channel, res["polygon"], map_path, res["rms_in"], res["source"])
    print(f"    {channel}: {res['n_landmarks']} landmarks, homography RMS "
          f"{res['rms_in']} in ({res['source']}) -> wrote {map_path}")
    # verification: the polygon over the WISER reference frame
    fig, ax = plt.subplots(figsize=(9, 7))
    cal._draw_landmarks(ax, roi_cfg, (200, 820, 520, 910))
    poly = np.asarray(res["polygon"], float)
    ax.add_patch(plt.Polygon(poly, closed=True, fill=True, alpha=0.15, color="#d62728"))
    ax.plot(*np.vstack([poly, poly[:1]]).T, "-", color="#d62728", lw=1.6, label=f"{channel} visibility")
    ax.plot(wz[:, 0], wz[:, 1], "k^", ms=7, label="mapped landmarks")
    ax.legend(fontsize=8)
    ax.set_title(f"{channel} visibility polygon from image landmarks (RMS {res['rms_in']} in)")
    p = out / f"{channel}_visibility_check.png"
    fig.tight_layout(); fig.savefig(p, dpi=140); plt.close(fig)
    print(f"    verification -> {p}")
    return res


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

def run_gui(channel, frame_png, roi_cfg, map_path, out):
    for bk in ("TkAgg", "QtAgg", "Qt5Agg"):
        try:
            plt.switch_backend(bk); break
        except Exception:
            continue
    if plt.get_backend().lower() == "agg":
        print("    [gui] no interactive backend; use --build with a CSV/json instead.")
        return
    img = plt.imread(str(frame_png))
    lm = cc.roi_landmarks(roi_cfg)                       # ordered [(name, x, y), ...]
    # GUIDED flow: walk landmarks one at a time. i = current landmark index;
    # placed{name: corr}; skipped = names passed over. click = place current + advance.
    state = {"i": 0, "placed": {}, "skipped": set(), "region": [], "region_mode": False}

    fig, ax = plt.subplots(figsize=(13, 8))
    fig.subplots_adjust(bottom=0.12)
    fig.text(0.01, 0.02,
             "GUIDED: click the prompted landmark in the image (or 'k' to SKIP if you can't see it).\n"
             "k=skip   b=back   x=clear this one   r=region mode   f=finish region   s=save   q=save+quit",
             fontsize=8, family="monospace")

    def current():
        return lm[state["i"]] if state["i"] < len(lm) else None

    def redraw():
        ax.clear(); ax.imshow(img)
        for c in state["placed"].values():
            ax.plot(c["px"], c["py"], "g+", ms=13, mew=2)
            ax.annotate(c["name"], (c["px"], c["py"]), color="lime", fontsize=8)
        if state["region"]:
            r = np.array(state["region"] + state["region"][:1])
            ax.plot(r[:, 0], r[:, 1], "r.-", lw=1)
        cur = current()
        n_lm = len(lm); n_pl = len(state["placed"])
        if state["region_mode"]:
            ax.set_title(f"{channel} — REGION MODE: click the visible-ground outline ('f' when done). "
                         f"{n_pl} landmarks placed")
        elif cur is not None:
            name, wx, wy = cur
            status = ("✓ placed" if name in state["placed"]
                      else "skipped" if name in state["skipped"] else "")
            ax.set_title(f"{channel}  [{state['i']+1}/{n_lm}]  PLACE: {name}  (WISER {wx:.0f},{wy:.0f})"
                         f"  {status}   — click it, or 'k' to skip. {n_pl} placed")
        else:
            ax.set_title(f"{channel} — all {n_lm} reviewed, {n_pl} placed. "
                         f"{'Draw region (r) then ' if not state['region'] else ''}save (s)."
                         + ("" if n_pl >= 4 else "  NEED >= 4!"))
        fig.canvas.draw_idle()

    def advance():
        state["i"] = min(state["i"] + 1, len(lm))

    def on_click(ev):
        if ev.inaxes != ax or ev.button != 1:
            return
        if state["region_mode"]:
            state["region"].append([ev.xdata, ev.ydata])
        else:
            cur = current()
            if cur is not None:
                name, wx, wy = cur
                state["placed"][name] = {"px": float(ev.xdata), "py": float(ev.ydata),
                                         "wiser_x": wx, "wiser_y": wy, "name": name}
                state["skipped"].discard(name)
                advance()
        redraw()

    def on_key(ev):
        cur = current()
        if ev.key == "k" and not state["region_mode"] and cur is not None:      # SKIP
            state["skipped"].add(cur[0]); state["placed"].pop(cur[0], None); advance()
        elif ev.key == "b" and state["i"] > 0:                                    # back
            state["i"] -= 1
        elif ev.key == "x" and cur is not None:                                   # clear current
            state["placed"].pop(cur[0], None); state["skipped"].discard(cur[0])
        elif ev.key == "r":
            state["region_mode"] = not state["region_mode"]
        elif ev.key == "f":
            state["region_mode"] = False
        elif ev.key == "u" and state["region_mode"] and state["region"]:
            state["region"].pop()
        elif ev.key in ("s", "q"):
            corr = list(state["placed"].values())
            if len(corr) >= 4:
                DEFAULT_LANDMARK_DIR.mkdir(parents=True, exist_ok=True)
                lj = _landmark_json(channel)
                lj.write_text(json.dumps({"channel": channel, "image": str(frame_png),
                                          "correspondences": corr,
                                          "region_px": state["region"] or None}, indent=2))
                print(f"saved {len(corr)} landmarks -> {lj}")
                build_from_landmarks(channel, map_path=map_path, out=out, roi_cfg=roi_cfg)
            else:
                print(f"need >= 4 placed landmarks (have {len(corr)}); not saved")
            if ev.key == "q":
                plt.close(fig); return
        redraw()

    redraw()
    fig.canvas.mpl_connect("button_press_event", on_click)
    fig.canvas.mpl_connect("key_press_event", on_key)
    plt.show()


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--channel", default="CH01")
    ap.add_argument("--extract", action="store_true", help="grab a frame from the channel video")
    ap.add_argument("--gui", action="store_true", help="mark landmarks in the frame (needs display)")
    ap.add_argument("--build", action="store_true", help="build polygon from saved landmarks/CSV")
    ap.add_argument("--date", default="2026-06-29")
    ap.add_argument("--hour", type=int, default=None,
                    help="hour (0-23) to pull the frame from; default midday for normal "
                         "channels, a night/IR hour for CH01/CH02 so the tall panorama decodes full")
    ap.add_argument("--at-frac", type=float, default=0.5)
    ap.add_argument("--crop-blank", action="store_true",
                    help="trim the decoder's blown-white bottom margin (default: keep full frame)")
    ap.add_argument("--video", type=Path, default=None, help="explicit MP4 (else auto-find)")
    ap.add_argument("--image", type=Path, default=None, help="explicit frame PNG (else CHxx_frame.png)")
    ap.add_argument("--csv", type=Path, default=None, help="landmarks CSV (px,py,wiser_x,wiser_y)")
    ap.add_argument("--map", type=Path, default=DEFAULT_MAP)
    ap.add_argument("--rois", type=Path, default=DEFAULT_ROIS)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--margin-in", type=float, default=18.0)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    roi_cfg = w.load_rois(args.rois)

    if args.extract:
        vid = args.video or _find_video(args.channel, args.date, args.hour)
        if not vid or not Path(vid).exists():
            print(f"    no video for {args.channel} {args.date}; pass --video PATH"); return
        fp = _frame_path(args.channel, args.out)
        ok = cc.grab_frame(vid, fp, at_frac=args.at_frac, crop_blank=args.crop_blank)
        print(f"    {'saved' if ok else 'FAILED'} frame from {Path(vid).name} -> {fp}")
        return

    if args.build:
        build_from_landmarks(args.channel, map_path=args.map, out=args.out, roi_cfg=roi_cfg,
                             margin_in=args.margin_in, csv=args.csv)
        return

    if args.gui:
        frame = args.image or _frame_path(args.channel, args.out)
        if not Path(frame).exists():
            print(f"    no frame at {frame}; run --extract --channel {args.channel} first."); return
        run_gui(args.channel, frame, roi_cfg, args.map, args.out)
        return

    ap.print_help()


if __name__ == "__main__":
    main()
