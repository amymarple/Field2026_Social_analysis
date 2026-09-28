"""tile_dataset.py — re-slice the labeled cv_field frames into NATIVE-resolution tiles for a scale-matched retrain.

WHY (the whole point): the stored `dataset/rat_field` PNGs are already downscaled to 1280x712, where a rat is
~25 px — the small-object regime the detector collapses in. The native source is 4512x2512 (rat ~90 px). A
zero-label inference ablation proved that slice-inferring a 1280-TRAINED model at native res is *worse*
(frozen-test AP 0.205 -> 0.007): the detector is scale-locked to 1280, so more pixels HURT. The fix is not to
tile at inference only — it is to **retrain on native tiles** so train and inference see a rat at the same
~90 px. This module builds that tiled training set.

For each labeled frame it: (1) parses the source video + offset from the filename, (2) ffmpeg-extracts the
NATIVE frame (no downscale) from the recording root, (3) slices it into overlapping tiles, (4) reprojects the
normalized YOLO boxes into each tile (keeping a box where enough of it is visible), and (5) writes
`dataset/rat_field_tiles/{images,labels}` with tile names that PRESERVE the source session key
(`CH0X_CH0X_<date>_<hh>-...__tIX_IY.png`) so `train_detector.build_split` still holds out whole videos.

    python cv_field/tile_dataset.py --data-root dataset/rat_field --out dataset/rat_field_tiles \
        --rec-root Q:/hc997/SocialFieldRat2026 --tile 1280 --overlap 0.2 --use-mask --neg-per-frame 1
    # then retrain scale-matched:
    python train_detector.py --data-root dataset/rat_field_tiles --name rat_field_tiles \
        --imgsz 1280 --augment --freeze 10 --lr0 0.002 --batch 8

HARD GUARD: refuses a --data-root that looks like the frozen test (`*_test`) — the 07-06 ruler must NEVER be
tiled into training. Tiling the test happens only at INFERENCE time (tile_infer / stratify_test).

The tiling + box-reprojection math is pure and offline-tested (`--selftest`); ffmpeg/cv2 are lazy so the
math verifies without any video or GPU.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CV_ROOT = HERE.parent
DEFAULT_REC_ROOT = "Q:/hc997/SocialFieldRat2026"

# dataset frame name: <sessionCH>_<sourceStem>_<offset>s.png ;
#   sourceStem = CH0X_<date>_<start>_to_<end> ; offset = seconds into that hour file
_NAME_RE = re.compile(
    r"^(?P<sess>CH0\d)_(?P<stem>(?P<ch>CH0\d)_(?P<date>\d{4}-\d{2}-\d{2})_"
    r"\d{2}-\d{2}-\d{2}_to_\d{2}-\d{2}-\d{2})_(?P<off>\d+)s$")


# ------------------------------------------------------------------ source resolution
def parse_source(image_name: str, rec_root: str = DEFAULT_REC_ROOT):
    """(source_mp4_path, offset_seconds, channel, source_stem) from a dataset frame name, or None."""
    m = _NAME_RE.match(Path(image_name).stem)
    if not m:
        return None
    ch, date, stem, off = m["ch"], m["date"], m["stem"], int(m["off"])
    src = Path(rec_root) / date / ch / f"{stem}.mp4"
    return src, off, ch, stem


def extract_native(src, offset_s: float, ffmpeg: str = "ffmpeg"):
    """ffmpeg-extract ONE native-resolution frame at `offset_s` (seek before -i, no scale). BGR ndarray or None."""
    import cv2
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "f.png"
        subprocess.run([ffmpeg, "-y", "-ss", str(offset_s), "-i", str(src), "-frames:v", "1", str(out)],
                       capture_output=True, text=True)
        return cv2.imread(str(out)) if out.exists() else None


# ------------------------------------------------------------------ tiling math (pure)
def tile_origins(W: int, H: int, tile: int, overlap: float):
    """Top-left (x0, y0) of each tile covering (W,H) with the given fractional overlap. Last tile is clamped
    to the edge so the whole frame is covered (no gap). Deterministic row-major order."""
    stride = max(1, int(round(tile * (1.0 - overlap))))

    def starts(extent):
        if extent <= tile:
            return [0]
        s = list(range(0, extent - tile + 1, stride))
        if s[-1] != extent - tile:
            s.append(extent - tile)
        return s
    return [(x, y) for y in starts(H) for x in starts(W)]


def reproject_box(box_px, origin, tile: int):
    """Clip a native-pixel box (x1,y1,x2,y2) to a tile at `origin`=(x0,y0), size `tile`.

    Returns (tile_norm_box or None, visible_fraction) where tile_norm_box = (cx,cy,w,h) normalized to the
    tile, and visible_fraction = (area inside tile) / (original box area). None if no overlap."""
    x1, y1, x2, y2 = box_px
    ox, oy = origin
    ix1, iy1 = max(x1, ox), max(y1, oy)
    ix2, iy2 = min(x2, ox + tile), min(y2, oy + tile)
    if ix2 <= ix1 or iy2 <= iy1:
        return None, 0.0
    orig_area = max((x2 - x1) * (y2 - y1), 1e-9)
    vis = (ix2 - ix1) * (iy2 - iy1) / orig_area
    # local coords within the tile, normalized by tile size
    cx = ((ix1 + ix2) / 2.0 - ox) / tile
    cy = ((iy1 + iy2) / 2.0 - oy) / tile
    w = (ix2 - ix1) / tile
    h = (iy2 - iy1) / tile
    return (cx, cy, w, h), float(vis)


def read_yolo_labels(path: Path):
    """List of (cls, cx, cy, w, h) from a YOLO label file (normalized). Missing/empty -> []."""
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        p = line.split()
        if len(p) >= 5:
            rows.append((int(float(p[0])), *(float(v) for v in p[1:5])))
    return rows


def norm_to_px(box_norm, W: int, H: int):
    """(cls,cx,cy,w,h) normalized -> (x1,y1,x2,y2) pixels at (W,H)."""
    _c, cx, cy, w, h = box_norm
    return (cx - w / 2) * W, (cy - h / 2) * H, (cx + w / 2) * W, (cy + h / 2) * H


# ------------------------------------------------------------------ driver
def build_tiles(data_root: Path, out_root: Path, rec_root: str, tile: int, overlap: float,
                min_visible: float, neg_per_frame: int, use_mask: bool, ffmpeg: str, limit: int = 0,
                skip_existing: bool = False):
    import cv2
    if "test" in data_root.name.lower():
        raise SystemExit(f"refusing to tile '{data_root.name}' — the frozen test must never enter training")
    img_dir, lbl_dir = data_root / "images", data_root / "labels"
    imgs = [p for p in sorted(img_dir.glob("*.png")) if (lbl_dir / f"{p.stem}.txt").exists()]
    if limit:
        imgs = imgs[:limit]
    out_img, out_lbl = out_root / "images", out_root / "labels"
    out_img.mkdir(parents=True, exist_ok=True); out_lbl.mkdir(parents=True, exist_ok=True)

    masks = {}
    if use_mask:
        from field_mask import FieldMask
        for ch in ("CH03", "CH04"):
            fm = FieldMask.load_or_none(ch)
            if fm is not None:
                masks[ch] = fm

    rng = np.random.default_rng(0)
    n_frames = n_pos_tiles = n_neg_tiles = n_boxes = n_missing = n_skipped = 0
    for p in imgs:
        if skip_existing and list(out_img.glob(f"{p.stem}__t*.png")):
            n_skipped += 1; continue                           # resume: this frame's tiles already exist
        parsed = parse_source(p.name, rec_root)
        if parsed is None:
            print(f"  [skip] cannot parse source from {p.name}"); continue
        src, off, ch, _stem = parsed
        if not Path(src).exists():
            print(f"  [miss] source not found: {src}"); n_missing += 1; continue
        frame = extract_native(src, off, ffmpeg)
        if frame is None:
            print(f"  [miss] ffmpeg failed: {src} @ {off}s"); n_missing += 1; continue
        H, W = frame.shape[:2]
        labels_px = [norm_to_px(b, W, H) for b in read_yolo_labels(lbl_dir / f"{p.stem}.txt")]
        fm = masks.get(ch)
        origins = tile_origins(W, H, tile, overlap)
        empty_tiles = []
        n_frames += 1
        for (ox, oy) in origins:
            cx_t, cy_t = ox + tile / 2, oy + tile / 2
            if fm is not None and not fm.contains([[cx_t, cy_t]], W, H)[0]:
                continue                                       # tile centre is on the wall / outside field
            rows = []
            for b in labels_px:
                nb, vis = reproject_box(b, (ox, oy), tile)
                if nb is not None and vis >= min_visible:
                    rows.append(nb)
            name = f"{p.stem}__t{ox}_{oy}"
            if rows:
                sub = frame[oy:oy + tile, ox:ox + tile]
                cv2.imwrite(str(out_img / f"{name}.png"), sub)
                (out_lbl / f"{name}.txt").write_text(
                    "\n".join(f"0 {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}" for (cx, cy, w, h) in rows) + "\n")
                n_pos_tiles += 1; n_boxes += len(rows)
            else:
                empty_tiles.append((ox, oy))
        # a few background (rat-free) tiles per frame to teach grass/negatives (empty label file)
        for (ox, oy) in [empty_tiles[i] for i in rng.permutation(len(empty_tiles))[:neg_per_frame]] if empty_tiles else []:
            name = f"{p.stem}__t{ox}_{oy}"
            cv2.imwrite(str(out_img / f"{name}.png"), frame[oy:oy + tile, ox:ox + tile])
            (out_lbl / f"{name}.txt").write_text("")           # empty = negative
            n_neg_tiles += 1
    print(f"\ntiled {n_frames} frames -> {n_pos_tiles} positive + {n_neg_tiles} background tiles "
          f"({n_boxes} boxes); {n_missing} sources missing; {n_skipped} skipped (already existed)")
    print(f"out: {out_root}  (retrain: train_detector.py --data-root {out_root} --name rat_field_tiles "
          f"--imgsz {tile} --augment --freeze 10 --lr0 0.002 --batch 8)")
    return n_pos_tiles


# ------------------------------------------------------------------ self-test (pure math)
def _selftest() -> int:
    ok = True

    def chk(name, cond):
        nonlocal ok; ok = ok and bool(cond); print(f"  [{'PASS' if cond else 'FAIL'}] {name}")

    # name parsing
    parsed = parse_source("CH03_CH03_2026-06-28_21-00-01_to_22-00-00_780s.png", "R:/rec")
    chk("parse_source src", parsed and str(parsed[0]).replace("\\", "/") ==
        "R:/rec/2026-06-28/CH03/CH03_2026-06-28_21-00-01_to_22-00-00.mp4")
    chk("parse_source offset", parsed and parsed[1] == 780 and parsed[2] == "CH03")
    chk("parse_source rejects junk", parse_source("random.png") is None)

    # tiling coverage: native 4512x2512, tile 1280, 20% overlap -> covers every pixel, clamped last tile
    origins = tile_origins(4512, 2512, 1280, 0.2)
    chk("tile origins cover right edge", any(x + 1280 == 4512 for (x, y) in origins))
    chk("tile origins cover bottom edge", any(y + 1280 == 2512 for (x, y) in origins))
    chk("tile count reasonable (12-25)", 12 <= len(origins) <= 25)

    # a box wholly inside one tile round-trips to the right tile-local normalized coords
    W, H, tile = 4512, 2512, 1280
    box = (2100.0, 1300.0, 2180.0, 1400.0)                     # ~80x100 px "rat" (native scale)
    hits = []
    for (ox, oy) in tile_origins(W, H, tile, 0.2):
        nb, vis = reproject_box(box, (ox, oy), tile)
        if nb is not None and vis >= 0.35:
            hits.append((ox, oy, nb, vis))
    chk("box lands in >=1 tile", len(hits) >= 1)
    ox, oy, nb, vis = hits[0]
    cx, cy, w, h = nb
    exp_cx = ((2100 + 2180) / 2 - ox) / tile
    exp_w = 80 / tile
    chk("reproject cx correct", abs(cx - exp_cx) < 1e-6)
    chk("reproject w correct", abs(w - exp_w) < 1e-6)
    chk("full box visible fraction ~1", abs(vis - 1.0) < 1e-6)
    chk("normalized coords in [0,1]", all(0 <= v <= 1 for v in nb))

    # tiles OVERLAP (stride 1024 < tile 1280), so a box in the overlap band appears in two tiles: fully in
    # the earlier tile (which still covers it) and clipped in the later one.
    stride = int(1280 * 0.8)                                   # 1024
    ov_box = (stride - 40.0, 500.0, stride + 40.0, 560.0)      # x in [984,1064], inside the 1024-1280 overlap
    nb0, vis0 = reproject_box(ov_box, (0, 0), 1280)            # tile 0 covers x[0,1280] -> whole box
    nb1, vis1 = reproject_box(ov_box, (stride, 0), 1280)       # tile 1 starts at 1024 -> left-clipped
    chk("box in overlap band appears in both tiles", nb0 is not None and nb1 is not None)
    chk("covering tile sees the whole box", abs(vis0 - 1.0) < 1e-6)
    chk("later tile sees a partial box", 0.0 < vis1 < 1.0)
    # direct edge clip: a box half beyond a tile's right edge -> ~0.5 visible
    _nb, v_half = reproject_box((80.0, 10.0, 120.0, 30.0), (0, 0), 100)
    chk("edge-clipped box vis ~0.5", abs(v_half - 0.5) < 1e-6)

    print("PASS — tile_dataset self-test" if ok else "FAIL — tile_dataset self-test")
    return 0 if ok else 1


def main() -> None:
    ap = argparse.ArgumentParser(description="Re-slice labeled cv_field frames into native-resolution tiles.")
    ap.add_argument("--data-root", default=str(CV_ROOT / "dataset" / "rat_field"))
    ap.add_argument("--out", default=str(CV_ROOT / "dataset" / "rat_field_tiles"))
    ap.add_argument("--rec-root", default=DEFAULT_REC_ROOT, help="recording root holding <date>/<CH>/*.mp4")
    ap.add_argument("--tile", type=int, default=1280)
    ap.add_argument("--overlap", type=float, default=0.2)
    ap.add_argument("--min-visible", type=float, default=0.35, help="keep a clipped box if >= this fraction visible")
    ap.add_argument("--neg-per-frame", type=int, default=1, help="background (rat-free) tiles per frame")
    ap.add_argument("--use-mask", action="store_true", help="skip tiles whose centre is outside the valid field")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--limit", type=int, default=0, help="process only the first N frames (smoke test)")
    ap.add_argument("--skip-existing", action="store_true", help="resume: skip frames whose tiles already exist")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        raise SystemExit(_selftest())
    build_tiles(Path(args.data_root), Path(args.out), args.rec_root, args.tile, args.overlap,
                args.min_visible, args.neg_per_frame, args.use_mask, args.ffmpeg, args.limit,
                skip_existing=args.skip_existing)


if __name__ == "__main__":
    main()
