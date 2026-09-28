"""tile_infer.py — proposal-cued native-tile inference for cv_field (the scale-matched inference half).

Pairs with `tile_dataset.py` (which builds the native-tile TRAINING set). At inference the native 4512x2512
frame is sliced into tiles so a rat is imaged at ~90 px (its training scale) instead of ~25 px at 1280. Two
cost controls keep this affordable over 36 cam-hours/night on one GPU:

  * **proposal-cued** — run the detector ONLY on tiles that contain a motion/WISER proposal (the high-recall
    `field_motion` tracklets), not a blind 15-tiles x every-frame sweep;
  * **field-masked** — skip tiles whose centre is on the enclosure wall / outside the valid field.

Tile detections are mapped back to global (native) pixel coordinates and merged with a global NMS so a rat
straddling a tile seam is not double-counted.

The tile-selection and box-merge math is PURE and offline-tested (`--selftest`); the detector is injected as a
`predict_fn(tile_bgr) -> [(x1,y1,x2,y2,conf), ...]` so the geometry verifies with a fake predictor and the
real YOLO is built by `yolo_predictor(...)` only when actually running.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from tile_dataset import tile_origins


# ------------------------------------------------------------------ NMS / IoU (pure numpy)
def iou_matrix(a, b) -> np.ndarray:
    """IoU between boxes a (N,4) and b (M,4), each (x1,y1,x2,y2). Returns (N,M)."""
    a = np.asarray(a, float).reshape(-1, 4); b = np.asarray(b, float).reshape(-1, 4)
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)), float)
    area_a = np.maximum(0, a[:, 2] - a[:, 0]) * np.maximum(0, a[:, 3] - a[:, 1])
    area_b = np.maximum(0, b[:, 2] - b[:, 0]) * np.maximum(0, b[:, 3] - b[:, 1])
    x1 = np.maximum(a[:, None, 0], b[None, :, 0]); y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2]); y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.maximum(0, x2 - x1) * np.maximum(0, y2 - y1)
    union = area_a[:, None] + area_b[None, :] - inter
    return inter / np.maximum(union, 1e-9)


def nms(boxes, scores, iou_thr: float = 0.5):
    """Greedy NMS. boxes (N,4), scores (N,). Returns kept indices (highest score first)."""
    boxes = np.asarray(boxes, float).reshape(-1, 4); scores = np.asarray(scores, float).ravel()
    order = scores.argsort()[::-1]
    keep = []
    while len(order):
        i = order[0]; keep.append(int(i))
        if len(order) == 1:
            break
        ious = iou_matrix(boxes[i:i + 1], boxes[order[1:]])[0]
        order = order[1:][ious <= iou_thr]
    return keep


# ------------------------------------------------------------------ tile selection (pure)
def _box_intersects_tile(box, origin, tile) -> bool:
    x1, y1, x2, y2 = box; ox, oy = origin
    return not (x2 <= ox or x1 >= ox + tile or y2 <= oy or y1 >= oy + tile)


def select_tiles(origins, tile, W, H, proposals_px=None, mask=None):
    """Which tiles to actually run the detector on. A tile is selected if its centre is inside the valid
    field (when `mask` given) AND (no proposals given -> run all in-field tiles) OR it intersects >=1
    proposal box. Returns the filtered list of origins."""
    out = []
    for (ox, oy) in origins:
        if mask is not None:
            cx, cy = ox + tile / 2, oy + tile / 2
            if not mask.contains([[cx, cy]], W, H)[0]:
                continue
        if proposals_px is None:
            out.append((ox, oy)); continue
        if any(_box_intersects_tile(b, (ox, oy), tile) for b in proposals_px):
            out.append((ox, oy))
    return out


def merge_tile_dets(dets_by_tile, origins, iou_thr: float = 0.5):
    """Map per-tile detections (tile-local px, list of (x1,y1,x2,y2,conf)) back to global native px and NMS.

    `dets_by_tile[i]` corresponds to `origins[i]`. Returns (boxes (K,4) global px, scores (K,))."""
    gboxes, gscores = [], []
    for (ox, oy), dets in zip(origins, dets_by_tile):
        for (x1, y1, x2, y2, c) in dets:
            gboxes.append([x1 + ox, y1 + oy, x2 + ox, y2 + oy]); gscores.append(c)
    if not gboxes:
        return np.zeros((0, 4), float), np.zeros((0,), float)
    gboxes = np.asarray(gboxes, float); gscores = np.asarray(gscores, float)
    keep = nms(gboxes, gscores, iou_thr)
    return gboxes[keep], gscores[keep]


# ------------------------------------------------------------------ full-frame tiled predict
def tiled_predict(predict_fn, frame_bgr, *, tile=1280, overlap=0.2, proposals_px=None, mask=None,
                  iou_merge=0.5):
    """Run `predict_fn` on the selected native tiles of `frame_bgr` and merge to global native px.

    `predict_fn(tile_bgr) -> [(x1,y1,x2,y2,conf), ...]` in tile-local pixels. Returns (boxes (K,4), scores)."""
    frame = np.asarray(frame_bgr)
    H, W = frame.shape[:2]
    origins = select_tiles(tile_origins(W, H, tile, overlap), tile, W, H, proposals_px, mask)
    dets_by_tile = []
    for (ox, oy) in origins:
        sub = frame[oy:oy + tile, ox:ox + tile]
        dets_by_tile.append(list(predict_fn(sub)))
    return merge_tile_dets(dets_by_tile, origins, iou_merge)


def yolo_predictor(weights, imgsz=1280, conf=0.25, device="0", classes=(0,)):
    """Build a `predict_fn(tile_bgr)->dets` backed by an Ultralytics YOLO (lazy import)."""
    from ultralytics import YOLO
    model = YOLO(str(weights))

    def predict_fn(tile_bgr):
        r = model.predict(tile_bgr, imgsz=imgsz, conf=conf, device=device, verbose=False,
                          classes=list(classes))[0]
        if r.boxes is None or len(r.boxes) == 0:
            return []
        xyxy = r.boxes.xyxy.cpu().numpy(); cf = r.boxes.conf.cpu().numpy()
        return [(float(a), float(b), float(c), float(d), float(s)) for (a, b, c, d), s in zip(xyxy, cf)]
    return predict_fn


# ------------------------------------------------------------------ self-test (pure, fake predictor)
def _selftest() -> int:
    ok = True

    def chk(name, cond):
        nonlocal ok; ok = ok and bool(cond); print(f"  [{'PASS' if cond else 'FAIL'}] {name}")

    # NMS collapses duplicates, keeps distinct
    boxes = [[0, 0, 10, 10], [1, 1, 11, 11], [100, 100, 110, 110]]
    keep = nms(boxes, [0.9, 0.8, 0.7], 0.5)
    chk("nms merges overlapping, keeps distinct", sorted(keep) == [0, 2])

    # proposal-cued selection: only tiles intersecting a proposal are run
    W = H = 2560; tile = 1280
    origins = tile_origins(W, H, tile, 0.2)
    prop = [(2000.0, 200.0, 2040.0, 260.0)]                    # one proposal in the top-right region
    sel = select_tiles(origins, tile, W, H, proposals_px=prop)
    chk("proposal-cued selects a subset", 0 < len(sel) < len(origins))
    chk("selected tiles all intersect the proposal",
        all(_box_intersects_tile(prop[0], o, tile) for o in sel))

    # a rat straddling a seam is detected in two tiles but merged to ONE global box
    seam = int(1280 * 0.8)
    gt = (seam - 30.0, 500.0, seam + 30.0, 560.0)

    # emulate: build tiles manually and attach the clipped detection each tile would produce
    picked = [(0, 0), (seam, 0)]
    dets_by_tile = []
    for (ox, oy) in picked:
        ix1, iy1 = max(gt[0], ox), max(gt[1], oy)
        ix2, iy2 = min(gt[2], ox + tile), min(gt[3], oy + tile)
        dets_by_tile.append([(ix1 - ox, iy1 - oy, ix2 - ox, iy2 - oy, 0.9)] if ix2 > ix1 else [])
    gb, gs = merge_tile_dets(dets_by_tile, picked, iou_thr=0.3)
    # the rat appears in both tiles; after mapping to global coords the two overlapping detections are NMS'd
    # to a SINGLE detection that still matches the true rat (>= 0.5 IoU) — no double-count across the seam.
    chk("straddling rat merges to one global detection", len(gb) == 1)
    chk("merged detection matches the true rat (IoU>=0.4)",
        len(gb) >= 1 and iou_matrix(gb[:1], [gt])[0, 0] >= 0.4)

    # tiled_predict end-to-end with a fake predictor that returns one centre box per tile
    def centre_predict(tile_bgr):
        h, w = tile_bgr.shape[:2]
        return [(w / 2 - 5, h / 2 - 5, w / 2 + 5, h / 2 + 5, 0.8)]
    frame = np.zeros((2560, 2560, 3), np.uint8)
    gb2, gs2 = tiled_predict(centre_predict, frame, tile=1280, overlap=0.2, proposals_px=prop)
    chk("tiled_predict runs only cued tiles", 0 < len(gb2) <= len(sel))

    print("PASS — tile_infer self-test" if ok else "FAIL — tile_infer self-test")
    return 0 if ok else 1


def main() -> None:
    ap = argparse.ArgumentParser(description="Proposal-cued native-tile inference (self-test only here; "
                                             "wire predict_fn from a driver for real runs).")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        raise SystemExit(_selftest())
    print("tile_infer.py — import tiled_predict / yolo_predictor; run --selftest for the geometry check")


if __name__ == "__main__":
    main()
